"""Stored-source and enrichment ownership tests use only isolated fake inputs."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from enrichment_fixtures import PNG, content_payload, image_asset, write_file

from longtian_api.database import Database
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchResultNotFoundError,
    SearchRunRepository,
)
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.collector_contracts import (
    EnrichmentWorkerResult,
    EnrichmentWorkerUnsettledError,
)
from longtian_api.services.content_enrichment import (
    ContentEnrichmentError,
    ContentEnrichmentService,
)
from longtian_api.services.enrichment_models import EnrichedContent
from longtian_api.services.enrichment_staging import MediaSpool


def stored_source(tmp_path: Path, *, platform="wb", identity="12345"):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    repository = SearchRunRepository(database)
    run = repository.create_run(
        monitoring_rule_id=1,
        platform=platform,
        rule_name="测试规则",
        terms=("对象", "另一个对象"),
        max_results_per_term=10,
    )
    repository.mark_running(run.id)
    url = f"https://m.weibo.cn/detail/{identity}"
    item = SearchContentInput(
        platform_content_id=identity,
        content_type="post",
        title="已保存的标题",
        snippet="搜索摘要",
        creator_hash="",
        publisher_name="",
        published_at_text="",
        content_url=url,
        observed_at="2026-08-28T00:00:00+00:00",
    )
    for position in (0, 1):
        repository.set_progress(run.id, position)
        repository.observe_item(run_id=run.id, term_position=position, item=item)
        repository.complete_term(run.id, position, 1)
    repository.finish(run.id, "completed_with_results")
    results, _ = repository.list_results(run_id=run.id, kind="all", limit=10, offset=0)
    return database, repository, run.id, results[0].id


def test_stored_source_proves_relation_preserves_order_and_old_open_projection(
    tmp_path,
):
    _, repository, run_id, result_id = stored_source(tmp_path)
    source = repository.get_result_source(run_id=run_id, result_id=result_id)
    assert source.run_id == run_id
    assert source.result_id == result_id
    assert source.platform == "wb"
    assert source.platform_content_id == "12345"
    assert source.content_url == "https://m.weibo.cn/detail/12345"
    assert source.title == "已保存的标题"
    assert source.snippet == "搜索摘要"
    assert source.matched_terms == ("对象", "另一个对象")
    assert source.collection_active is False
    target = repository.get_result_open_target(run_id=run_id, result_id=result_id)
    assert (target.platform, target.platform_content_id, target.matched_terms) == (
        source.platform,
        source.platform_content_id,
        source.matched_terms,
    )
    for wrong_run, wrong_result in ((run_id + 1, result_id), (run_id, result_id + 1)):
        with pytest.raises(SearchResultNotFoundError):
            repository.get_result_source(run_id=wrong_run, result_id=wrong_result)


def test_stored_source_rejects_active_parent_even_if_child_is_terminal(tmp_path):
    database, repository, _, _ = stored_source(tmp_path)
    batches = SearchBatchRepository(database)
    batch = batches.create_batch(
        monitoring_rule_id=1,
        rule_name="测试规则",
        terms=("对象",),
        platforms=("wb",),
        max_results_per_term=10,
    )
    batches.mark_running(batch.id)
    run = batches.create_attempt(batch.id, 0)
    repository.mark_running(run.id)
    repository.set_progress(run.id, 0)
    repository.observe_item(
        run_id=run.id,
        term_position=0,
        item=SearchContentInput(
            "12345",
            "post",
            "已保存的标题",
            "",
            "",
            "",
            "",
            "https://m.weibo.cn/detail/12345",
            "2026-08-28T00:00:00+00:00",
        ),
    )
    repository.finish(run.id, "structure_changed")
    batches.finish_item(batch.id, 0, "structure_changed")
    results, _ = repository.list_results(run_id=run.id, kind="all", limit=10, offset=0)
    assert (
        repository.get_result_source(
            run_id=run.id, result_id=results[0].id
        ).collection_active
        is True
    )


class EnrichmentFake:
    def __init__(self, mode="ready"):
        self.root = None
        self.mode = mode
        self.calls = 0
        self.cancelled = 0
        self.entered = asyncio.Event()
        self.cancel_seen = asyncio.Event()
        self.release_cancel = asyncio.Event()
        self.process = SimpleNamespace(returncode=None)

    def configure_media_spool(self, root):
        self.root = root

    async def discard_session(self):
        pass

    async def enrich(
        self, *, request_id, platform, content_id, content_url, term, budget
    ):
        self.calls += 1
        assert term == "对象"
        payload = content_payload(platform, content_id, content_url)
        asset = image_asset()
        write_file(self.root / request_id.hex, asset["asset_id"], PNG)
        payload.update(assets=[asset], detected_modalities=["text", "image"])
        self.entered.set()
        if self.mode == "unsettled":
            raise EnrichmentWorkerUnsettledError(self.process)
        if self.mode in {"hanging", "timeout"}:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                self.cancel_seen.set()
                if self.mode == "hanging":
                    await self.release_cancel.wait()
                raise
        if self.mode == "partial":
            payload.update(
                status="partial",
                media_inventory_complete=False,
                detected_modalities=["text", "image", "unknown"],
                issues=[{"code": "inventory_unknown", "asset_position": None}],
            )
        return EnrichmentWorkerResult(
            "completed", EnrichedContent.model_validate(payload)
        )


def enrichment_service(
    tmp_path, repository, worker, *, spool=None, timeout_seconds=150
):
    coordinator = BrowserOperationCoordinator()
    service = ContentEnrichmentService(
        repository=repository,
        worker=worker,
        browser_operations=coordinator,
        spool=spool or MediaSpool(tmp_path / "media"),
        timeout_seconds=timeout_seconds,
    )
    return service, coordinator


def test_service_reserves_serial_lease_and_cleans_each_item_before_composition(
    tmp_path,
):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        worker = EnrichmentFake()
        service, coordinator = enrichment_service(tmp_path, repository, worker)
        assert not (tmp_path / "media").exists()
        other = BrowserOperationOwner("search_batch", uuid4())
        async with service.operation() as session:
            for _ in range(2):
                async with session.item(run_id=run_id, result_id=result_id) as result:
                    assert result.ready and result.media[0].data == PNG
                    assert result.source.result_id == result_id
                    assert len(result.input_fingerprint) == 64
                    assert len(list((tmp_path / "media").iterdir())) == 1
                    assert not await coordinator.try_claim(other)
                assert not list((tmp_path / "media").iterdir())
                assert not await coordinator.try_claim(other)
        assert await coordinator.try_claim(other)
        assert worker.calls == 2
        await coordinator.release(other)

    asyncio.run(scenario())


def test_partial_media_stays_structured_and_not_model_ready(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        service, _ = enrichment_service(tmp_path, repository, EnrichmentFake("partial"))
        async with service.operation() as session:
            async with session.item(run_id=run_id, result_id=result_id) as result:
                assert result.outcome == "completed"
                assert not result.ready
                assert result.content.issues[0].code == "inventory_unknown"
        assert not list((tmp_path / "media").iterdir())

    asyncio.run(scenario())


def test_missing_source_or_paused_owner_starts_no_worker_or_files(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        worker = EnrichmentFake()
        service, coordinator = enrichment_service(tmp_path, repository, worker)
        paused = BrowserOperationOwner("search_batch", uuid4())
        assert await coordinator.try_claim(paused)
        with pytest.raises(ContentEnrichmentError, match="browser_operation_active"):
            async with service.operation():
                pytest.fail("paused owner was bypassed")
        assert await coordinator.is_owned_by(paused)
        await coordinator.release(paused)
        with pytest.raises(ContentEnrichmentError, match="source_not_found"):
            async with service.operation() as session:
                async with session.item(run_id=run_id + 1, result_id=result_id):
                    pytest.fail("foreign source was accepted")
        assert worker.calls == 0
        assert not (tmp_path / "media").exists()

    asyncio.run(scenario())


def test_cancellation_waits_for_writer_ack_before_files_or_owner_release(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        worker = EnrichmentFake("hanging")
        service, coordinator = enrichment_service(tmp_path, repository, worker)

        async def consume():
            async with service.operation() as session:
                async with session.item(run_id=run_id, result_id=result_id):
                    pytest.fail("cancelled acquisition was delivered")

        task = asyncio.create_task(consume())
        await worker.entered.wait()
        task.cancel()
        await worker.cancel_seen.wait()
        other = BrowserOperationOwner("search_run", uuid4())
        assert not task.done()
        assert not await coordinator.try_claim(other)
        assert list((tmp_path / "media").iterdir())
        worker.release_cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not list((tmp_path / "media").iterdir())
        assert await coordinator.try_claim(other)
        assert worker.cancelled == 1

    asyncio.run(scenario())


def test_timeout_and_shutdown_cancel_without_retries(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        worker = EnrichmentFake("timeout")
        service, coordinator = enrichment_service(
            tmp_path, repository, worker, timeout_seconds=0.01
        )
        async with service.operation() as session:
            async with session.item(run_id=run_id, result_id=result_id) as result:
                assert result.outcome == "timed_out" and not result.ready
        assert worker.calls == worker.cancelled == 1
        assert not list((tmp_path / "media").iterdir())
        worker.mode = "hanging"
        worker.entered.clear()
        worker.cancel_seen.clear()

        async def consume():
            async with service.operation() as session:
                async with session.item(run_id=run_id, result_id=result_id):
                    pytest.fail("shutdown acquisition delivered")

        consumer = asyncio.create_task(consume())
        await worker.entered.wait()
        closing = asyncio.create_task(service.shutdown())
        await worker.cancel_seen.wait()
        other = BrowserOperationOwner("platform_connection", uuid4())
        assert not await coordinator.try_claim(other)
        worker.release_cancel.set()
        await closing
        with pytest.raises(ContentEnrichmentError, match="service_unavailable"):
            await consumer
        assert not list((tmp_path / "media").iterdir())
        assert await coordinator.try_claim(other)

    asyncio.run(scenario())


def test_unproven_process_exit_quarantines_files_and_browser_until_confirmed(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)

    async def scenario():
        worker = EnrichmentFake("unsettled")
        service, coordinator = enrichment_service(tmp_path, repository, worker)
        with pytest.raises(ContentEnrichmentError, match="worker_unsettled"):
            async with service.operation() as session:
                async with session.item(run_id=run_id, result_id=result_id):
                    pytest.fail("unsettled worker delivered")
        other = BrowserOperationOwner("search_run", uuid4())
        assert not await coordinator.try_claim(other)
        assert list((tmp_path / "media").iterdir())
        with pytest.raises(ContentEnrichmentError, match="worker_unsettled"):
            await service.shutdown()
        assert list((tmp_path / "media").iterdir())
        worker.process.returncode = -9
        await service.shutdown()
        assert not list((tmp_path / "media").iterdir())
        assert await coordinator.try_claim(other)

    asyncio.run(scenario())


def test_cancel_during_threaded_directory_creation_does_not_leave_an_orphan(tmp_path):
    _, repository, run_id, result_id = stored_source(tmp_path)
    started, release = threading.Event(), threading.Event()

    class SlowSpool(MediaSpool):
        def create_operation(self, request_id):
            started.set()
            assert release.wait(2)
            return super().create_operation(request_id)

    async def scenario():
        worker = EnrichmentFake()
        service, coordinator = enrichment_service(
            tmp_path, repository, worker, spool=SlowSpool(tmp_path / "media")
        )

        async def consume():
            async with service.operation() as session:
                async with session.item(run_id=run_id, result_id=result_id):
                    pytest.fail("cancelled allocation delivered")

        task = asyncio.create_task(consume())
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        other = BrowserOperationOwner("search_run", uuid4())
        assert not await coordinator.try_claim(other)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not list((tmp_path / "media").iterdir())
        assert worker.calls == 0
        assert await coordinator.try_claim(other)

    asyncio.run(scenario())
