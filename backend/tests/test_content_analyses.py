"""Independent saved evidence, actual-media boundaries and owned queue lifecycle."""

import asyncio
import threading
from uuid import uuid4

import pytest
from initial_analysis_fixtures import UNDERSTANDING, environment, finish, request
from summary_fixtures import seed_run

from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.results import ResultsRepository
from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.schemas.ai_summaries import SummaryCreate
from longtian_api.schemas.analysis_settings import PromptUpdate
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIUsage
from longtian_api.services.ai_errors import AIError
from longtian_api.services.ai_summaries import SummaryService
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.browser_operations import BrowserOperationOwner
from longtian_api.services.media_crawler_auth_worker import EnrichmentWorkerResult


def test_independent_neutral_media_understanding_and_unique_settlement(tmp_path):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(
            tmp_path, count=10
        )
        worker.partial.add("1008")
        model.item_answers = [UNDERSTANDING] * 8 + ["invalid model JSON"]
        admission = await service.create(request(database))
        await finish(service)
        job = service.repository.read(admission.job.id)
        assert job.status == "completed"
        assert (
            job.counts.completed == 9
            and job.counts.input_incomplete == 0
            and job.counts.failed == 1
        )
        assert job.usage.attempted_requests == job.usage.accounted_requests == 10
        assert len(worker.calls) == 10 and len(model.calls) == 10
        assert all(stage == "analysis" for stage, _ in model.calls)
        assert coordinator._owner is None
        items = service.repository.items(job.id).items
        assert items[0].output.summary == UNDERSTANDING["summary"]
        assert items[0].input.text.body == worker.body
        assert items[8].input.evidence_coverage.level == "detail_text"
        assert items[8].input.evidence_coverage.image.unknown == 1
        assert items[8].usage is not None and items[8].error.code == "invalid_json"
        assert items[-1].output is not None
        text = model.calls[0][1][0]["content"]
        assert job.initial_prompt.instructions in text
        assert "monitoring_scope" not in str(model.calls)
        assert "image_url" in str(model.calls)
        assert "blob_ref" not in items[0].model_dump_json()
        events = service.repository.completion_events()
        assert len(events) == 1 and len(events[0]["successful_attempt_ids"]) == 9
        assert events[0]["job"].report_prompt == job.report_prompt
        service.repository.finish(job.id, "completed")
        assert len(service.repository.completion_events()) == 1
        with database.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM ai_summary_runs").fetchone()[0]
                == 0
            )
        await service.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["input_incomplete", "failed"])
def test_zero_successes_still_publish_one_normally_settled_handoff(tmp_path, outcome):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(tmp_path)
        if outcome == "input_incomplete":
            worker.partial.update({"1000", "1001"})
        else:
            model.item_answers = ["invalid JSON", "invalid JSON"]
        admission = await service.create(request(database))
        await finish(service)
        job = service.repository.read(admission.job.id)
        expected_completed = 2 if outcome == "input_incomplete" else 0
        assert job.status == "completed" and job.counts.completed == expected_completed
        assert getattr(job.counts, outcome) == 2 - expected_completed
        assert all(
            attempt.status == ("completed" if expected_completed else outcome)
            and (attempt.output is not None) == bool(expected_completed)
            for attempt in service.repository.items(job.id).items
        )
        events = service.repository.completion_events()
        assert len(events) == 1
        assert len(events[0]["successful_attempt_ids"]) == expected_completed
        assert events[0]["job"] == job and events[0]["state"] == "pending"
        assert job.completion_event_id == events[0]["id"]
        assert service.repository.completion_events(after_id=events[0]["id"]) == []
        assert (await service.cancel(job.id)) == job
        service.repository.finish(job.id, "completed")
        assert service.repository.completion_events() == events
        assert ResultsRepository(database).list().active_count == 0
        assert ResultsRepository(database).list().eligible_count == 0
        assert len(worker.calls) == 2
        assert len(model.calls) == 2
        assert all(stage == "analysis" for stage, _ in model.calls)
        assert coordinator._owner is None
        await service.shutdown()

    asyncio.run(run())


def test_prompts_freeze_both_stages_without_requeue_and_cache_reuses_no_usage(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=1)
        model.gate = asyncio.Event()
        admission = await service.create(request(database))
        await model.entered.wait()
        settings = AnalysisSettingsRepository(database)
        old = settings.read()
        changed = settings.save_prompt(
            "report",
            PromptUpdate(
                expected_version_id=old.report_prompt.id,
                instructions="只讨论其他同名地点，保留未知。",
            ),
        )
        model.gate.set()
        await finish(service)
        assert (
            service.repository.read(admission.job.id).report_prompt == old.report_prompt
        )
        assert ResultsRepository(database).list().eligible_count == 0
        again = await service.create(
            request(database, kind="reanalysis", result_ids=[1])
        )
        await finish(service)
        reused = service.repository.read(again.job.id)
        assert reused.report_prompt == changed.report_prompt
        assert reused.counts.reused == 1 and reused.usage.attempted_requests == 0
        assert len(model.calls) == len(worker.calls) == 1
        settings.save_prompt(
            "initial",
            PromptUpdate(
                expected_version_id=old.initial_prompt.id,
                instructions="详细提取来源的地理与时间信息。",
            ),
        )
        assert ResultsRepository(database).list().eligible_count == 0
        reanalysis = await service.create(
            request(database, kind="reanalysis", result_ids=[1])
        )
        await finish(service)
        assert service.repository.read(reanalysis.job.id).counts.reused == 0
        assert len(model.calls) == len(worker.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_search_preview_reuse_is_invalidated_by_richer_detail_evidence(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=1)
        detail_enrich = worker.enrich

        async def preview_only(**kwargs):
            worker.calls.append((kwargs["content_id"], kwargs["term"]))
            return EnrichmentWorkerResult("lookup_miss")

        worker.enrich = preview_only
        first = await service.create(request(database))
        await finish(service)
        original = service.repository.items(first.job.id).items[0]
        assert (
            original.status == "completed"
            and original.input.extractor_version == "wb-search-preview-v1"
            and original.input.evidence_coverage.level == "search_preview"
        )
        assert len(worker.calls) == len(model.calls) == 1

        reused = await service.create(
            request(database, kind="reanalysis", result_ids=[1])
        )
        await finish(service)
        reused_item = service.repository.items(reused.job.id).items[0]
        assert reused_item.reused_from_attempt_id == original.id
        assert reused_item.input_fingerprint == original.input_fingerprint
        assert len(worker.calls) == len(model.calls) == 1

        worker.enrich = detail_enrich
        worker.body = "后来保存的详情正文，与搜索摘要不同。"
        richer = await service.create(
            request(
                database,
                kind="reanalysis",
                result_ids=[1],
                force_refresh=True,
            )
        )
        await finish(service)
        richer_item = service.repository.items(richer.job.id).items[0]
        assert richer_item.reused_from_attempt_id is None
        assert richer_item.input_fingerprint != original.input_fingerprint
        assert len(worker.calls) == len(model.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_failed_known_new_input_cannot_resurrect_old_compatible_text(tmp_path):
    async def run():
        database, _, service, _, model, worker, _ = environment(tmp_path, count=1)
        first = await service.create(request(database))
        await finish(service)
        old = service.repository.items(first.job.id).items[0]
        worker.body = "已知新正文：同名地点发生变化。"
        model.item_answers = ["invalid"]
        refresh = await service.create(
            request(database, kind="reanalysis", result_ids=[1], force_refresh=True)
        )
        await finish(service)
        failed = service.repository.items(refresh.job.id).items[0]
        assert (
            failed.status == "failed"
            and failed.input_fingerprint != old.input_fingerprint
        )
        retry = await service.create(request(database, kind="retry", result_ids=[1]))
        await finish(service)
        assert service.repository.read(retry.job.id).counts.reused == 0
        assert len(worker.calls) == len(model.calls) == 3
        assert service.repository.attempt(old.id) == old
        await service.shutdown()

    asyncio.run(run())


def test_cancel_preserves_success_suppresses_event_and_requires_explicit_retry(
    tmp_path,
):
    async def run():
        database, _, service, _, model, worker, _ = environment(tmp_path)
        original = model.complete
        gate, entered = asyncio.Event(), asyncio.Event()

        async def block_second(configuration, **kwargs):
            if len(model.calls) == 1:
                entered.set()
                await gate.wait()
            return await original(configuration, **kwargs)

        model.complete = block_second
        first = await service.create(request(database))
        await entered.wait()
        cancelled = await service.cancel(first.job.id)
        assert cancelled.status == "cancelled" and cancelled.counts.completed == 1
        assert cancelled.counts.cancelled == 1 and cancelled.completion_event_id is None
        assert service.repository.completion_events() == []
        assert ResultsRepository(database).list().eligible_count == 0
        assert (await service.create(request(database))).job is None
        assert len(worker.calls) == 2
        gate.set()
        retry = await service.create(request(database, kind="retry", result_ids=[2]))
        await finish(service)
        assert service.repository.read(retry.job.id).counts.completed == 1
        assert service.repository.read(first.job.id).counts.completed == 1
        await service.shutdown()

    asyncio.run(run())


def test_restart_reconciles_without_calls_and_late_callbacks_fail_closed(tmp_path):
    database, _, service, _, model, worker, _ = environment(tmp_path)
    job = service.repository.create(request(database)).job
    attempt = service.repository.items(job.id).items[0]
    service.repository.start(job.id)
    service.repository.begin(attempt.id)
    restarted = ContentAnalysisRepository(database)
    restarted.initialize()
    assert restarted.read(job.id).status == "interrupted"
    assert restarted.read(job.id).counts.interrupted == 2
    assert ResultsRepository(database).list().active_count == 0
    assert ResultsRepository(database).list().eligible_count == 0
    assert model.calls == worker.calls == []
    with pytest.raises(AnalysisError, match="content_analysis_selection_conflict"):
        service.repository.mark_attempt(attempt.id)
    assert restarted.completion_events() == []


def test_busy_browser_stays_queued_without_attempt_and_release_allows_progress(
    tmp_path,
):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(
            tmp_path, count=1
        )
        owner = BrowserOperationOwner("search_batch", uuid4())
        assert await coordinator.try_claim(owner)
        job = (await service.create(request(database))).job
        for _ in range(100):
            current = service.repository.read(job.id)
            if current.queue_reason:
                break
            await asyncio.sleep(0.01)
        assert current.queue_reason == "browser_operation_active"
        assert current.counts.queued == 1 and current.usage.attempted_requests == 0
        assert worker.calls == model.calls == []
        await coordinator.release(owner)
        await finish(service)
        assert service.repository.read(job.id).counts.completed == 1
        await service.shutdown()

    asyncio.run(run())


def test_provider_changed_while_queued_settles_claims_without_calls(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()
        original = ai.operation
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def delayed(revision):
            entered.set()
            await release.wait()
            async with original(revision) as configuration:
                yield configuration

        ai.operation = delayed
        job = (await service.create(request(database))).job
        await entered.wait()
        settings = ai.read()
        ai.save(AISettingsUpdate(base_url=settings.base_url, model="changed-model"))
        release.set()
        await finish(service)
        current = service.repository.read(job.id)
        assert current.status == "configuration_blocked"
        assert current.counts.interrupted == 2 and current.completion_event_id is None
        assert ResultsRepository(database).list().active_count == 0
        assert worker.calls == model.calls == []
        await service.shutdown()

    asyncio.run(run())


def test_admission_at_empty_queue_exit_cannot_strand_work(tmp_path):
    async def run():
        database, _, service, _, model, _, _ = environment(tmp_path, count=1)
        original = service.repository.next_job
        empty_seen, release = threading.Event(), threading.Event()
        blocked = False

        def pause_empty():
            nonlocal blocked
            job = original()
            if job is None and not blocked:
                blocked = True
                empty_seen.set()
                assert release.wait(5)
            return job

        service.repository.next_job = pause_empty
        await service.create(request(database))
        assert await asyncio.to_thread(empty_seen.wait, 5)
        seed_run(database, 1, start=9000)
        second = await service.create(request(database))
        assert second.admitted_count == 1
        release.set()
        await finish(service)
        assert service.repository.read(second.job.id).counts.completed == 1
        assert len(model.calls) == 2
        await service.shutdown()

    asyncio.run(run())


def test_legacy_active_claim_and_new_active_claim_exclude_both_paths(tmp_path):
    async def run():
        database, source, service, ai, model, worker, _ = environment(tmp_path, count=1)
        legacy = SummaryService(
            database=database, ai_settings=ai, enrichment=service._enrichment
        )
        legacy.initialize()
        model.gate = asyncio.Event()
        old = await legacy.create(
            source,
            SummaryCreate(
                request_id=str(uuid4()), force_refresh=False, configuration_revision=1
            ),
        )
        await model.entered.wait()
        excluded = service.repository.create(request(database))
        assert excluded.job is None and excluded.already_active_count == 1
        await legacy.cancel(old.id)
        assert ResultsRepository(database).read(1).analysis_state == "legacy_attempted"
        assert service.repository.create(request(database)).job is None
        new = service.repository.create(
            request(database, kind="retry", result_ids=[1])
        ).job
        with pytest.raises(AIError, match="ai_operation_active"):
            await legacy.create(
                source,
                SummaryCreate(
                    request_id=str(uuid4()),
                    force_refresh=False,
                    configuration_revision=1,
                ),
            )
        assert service.repository.read(new.id).counts.total == 1
        await service.shutdown()
        await legacy.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize(
    "usage,known",
    [
        (None, False),
        (
            AIUsage(
                prompt_tokens=MAX_USAGE_TOKENS,
                completion_tokens=0,
                total_tokens=MAX_USAGE_TOKENS,
            ),
            True,
        ),
    ],
)
def test_unknown_and_overflow_usage_are_not_zero(tmp_path, usage, known):
    async def run():
        database, _, service, _, model, _, _ = environment(tmp_path)
        model.usage = usage
        job = (await service.create(request(database))).job
        await finish(service)
        result = service.repository.read(job.id)
        assert result.counts.completed == 2
        assert result.usage.accounted_requests == (2 if known else 0)
        assert result.usage.total_tokens is None and result.usage.complete is False
        await service.shutdown()

    asyncio.run(run())


def test_cancel_drains_inflight_success_write_before_releasing_browser(tmp_path):
    database, _, service, _, model, _, coordinator = environment(tmp_path, count=2)
    entered, release = threading.Event(), threading.Event()
    original = service.repository.finish_attempt

    def delayed(*args, **kwargs):
        if args[1] == "completed":
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    service.repository.finish_attempt = delayed

    async def run():
        job = (await service.create(request(database))).job
        assert await asyncio.to_thread(entered.wait, 5)
        cancelling = asyncio.create_task(service.cancel(job.id))
        await asyncio.sleep(0)
        assert not cancelling.done() and coordinator._owner is not None
        release.set()
        result = await asyncio.wait_for(cancelling, 5)
        assert result.status == "cancelled" and result.counts.completed == 1
        assert result.counts.cancelled == 1 and result.completion_event_id is None
        assert result.usage.total_tokens == 15 and len(model.calls) == 1
        assert coordinator._owner is None
        await service.shutdown()

    asyncio.run(run())


def test_ambiguous_cancelled_post_still_admits_once_under_its_uuid(tmp_path):
    database, _, service, _, model, _, _ = environment(tmp_path, count=1)
    entered, release = threading.Event(), threading.Event()
    original = service.repository.create
    payload = request(database)

    def delayed(value):
        admitted = original(value)
        entered.set()
        assert release.wait(5)
        return admitted

    service.repository.create = delayed

    async def run():
        posting = asyncio.create_task(service.create(payload))
        assert await asyncio.to_thread(entered.wait, 5)
        posting.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await posting
        await finish(service)
        replay = await service.create(payload)
        assert replay.admitted_count == 1 and replay.job.counts.completed == 1
        assert len(model.calls) == 1
        assert len(service.repository.list().jobs) == 1
        await service.shutdown()

    asyncio.run(run())
