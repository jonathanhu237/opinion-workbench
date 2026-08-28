"""Additive v11 history, immutable scope, coherent reads and cache invariants."""

import asyncio
import threading
from uuid import uuid4

import pytest
from pydantic import SecretStr
from schema_fixtures import create_legacy_schema
from summary_fixtures import BASE, KEY, MODEL, environment, finished, seed_run

from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.repositories.ai_summaries import SummaryVersions
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
)
from longtian_api.schemas.ai_summaries import SummaryCreate
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIConfiguration, AIUsage
from longtian_api.services.ai_summaries import SummaryService
from longtian_api.services.summary_errors import SummaryError


def request():
    return SummaryCreate(
        request_id=str(uuid4()), force_refresh=False, configuration_revision=1
    )


def test_v11_appends_only_summary_tables_preserving_actual_v10_rows(tmp_path):
    database = Database(tmp_path / "old.sqlite3")
    create_legacy_schema(database, 10)
    source = seed_run(database, 2)
    with database.connect() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        before = {
            table: [
                tuple(r)
                for r in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ]
            for table in tables
        }
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
            == 11
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in before.items():
            assert [
                tuple(r)
                for r in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ] == rows
        assert connection.execute("SELECT * FROM ai_summary_runs").fetchall() == []
        assert connection.execute("SELECT * FROM ai_summary_items").fetchall() == []
    assert SearchRunRepository(database).get(source).total_count == 2


def test_admission_rollback_never_keeps_partial_snapshot(tmp_path):
    database, source, service, _, _, _, _ = environment(tmp_path, count=2)
    # Fail the second actual INSERT, after the parent and first child have been
    # written. Pydantic's compiled post-init hook is not a runtime patch seam.
    with database.connect() as connection:
        connection.execute("""
            CREATE TRIGGER fail_second_summary_item BEFORE INSERT ON ai_summary_items
            WHEN NEW.position = 1 BEGIN
              SELECT RAISE(ABORT, 'private-path-and-source-sentinel');
            END
        """)

    async def scenario():
        with pytest.raises(SummaryError, match="ai_summary_storage_unavailable"):
            await service.create(source, request())

    asyncio.run(scenario())
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM ai_summary_runs").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM ai_summary_items").fetchone()[0]
            == 0
        )


def test_paused_parent_rejects_terminal_child_without_work(tmp_path):
    database, _, service, _, client, worker, _ = environment(tmp_path)
    batches = SearchBatchRepository(database)
    batch = batches.create_batch(
        monitoring_rule_id=1,
        rule_name="历史规则",
        terms=("对象",),
        platforms=("wb",),
        max_results_per_term=10,
    )
    batches.mark_running(batch.id)
    child = batches.create_attempt(batch.id, 0)
    searches = SearchRunRepository(database)
    searches.mark_running(child.id)
    searches.set_progress(child.id, 0)
    searches.observe_item(
        run_id=child.id,
        term_position=0,
        item=SearchContentInput(
            "1000",
            "post",
            "标题",
            "摘要",
            "",
            "",
            "刚刚",
            "https://m.weibo.cn/detail/1000",
            "2026-08-28T00:00:00+00:00",
        ),
    )
    searches.finish(child.id, "structure_changed")
    batches.finish_item(batch.id, 0, "structure_changed")

    async def scenario():
        with pytest.raises(SummaryError, match="ai_summary_source_active"):
            await service.create(child.id, request())
        assert worker.calls == client.calls == []

    asyncio.run(scenario())


def test_source_snapshot_mismatch_before_acquisition_makes_no_worker_calls(
    tmp_path, monkeypatch
):
    database, source, service, _, client, worker, _ = environment(tmp_path)
    original = service.repository.records

    def mutate_after_freeze(summary_id):
        records = original(summary_id)
        with database.connect() as connection:
            connection.execute("UPDATE search_contents SET snippet='更新后的内容'")
        return records

    monkeypatch.setattr(service.repository, "records", mutate_after_freeze)

    async def scenario():
        await service.create(source, request())
        result = await finished(service)
        item = service.repository.items(result.id).items[0]
        assert item.error.code == "source_changed" and item.status == "input_incomplete"
        assert item.source.snippet == "不是完整正文"
        assert worker.calls == client.calls == []
        assert not (tmp_path / "media").exists()

    asyncio.run(scenario())


def test_startup_interrupts_unfinished_only_without_reanalysis(tmp_path):
    _, source, service, settings, client, worker, _ = environment(tmp_path, count=2)

    async def scenario():
        # Complete one prior version, then simulate the precise unfinished DB state
        # with one canonical reused row and one pending row; no live runner exists.
        await service.create(source, request())
        previous = await finished(service)
        config = AIConfiguration(BASE, MODEL, 1, SecretStr(KEY))
        queued = service.repository.create(
            source,
            request(),
            config,
            SummaryVersions(
                "opinion-analysis-v1",
                "opinion-summary-v1",
                "enrichment-v1-omni-inline-v1",
            ),
        )
        first = service.repository.records(queued.id)[0]
        cached = service.repository.find_cached(first)
        service.repository.reuse(queued.id, first.item.id, cached.item.id)
        calls = len(client.calls)
        restarted = SummaryService(
            database=service.repository.database,
            ai_settings=settings,
            enrichment=service._enrichment,
        )
        restarted.initialize()
        result = restarted.read(queued.id)
        assert result.status == "interrupted" and result.counts.interrupted == 1
        assert result.counts.reused == 1 and result.counts.relevant == 1
        assert restarted.read(previous.id) == previous
        assert len(client.calls) == calls and len(worker.calls) == 2
        restarted.read(queued.id)
        restarted.repository.items(queued.id)
        restarted.repository.list(source)
        assert len(client.calls) == calls
        await restarted.shutdown()

    asyncio.run(scenario())


def test_graceful_shutdown_interrupts_and_preserves_prior_completed_item(tmp_path):
    _, source, service, settings, client, worker, coordinator = environment(tmp_path)
    client.gate = asyncio.Event()
    client.block_stage = "composition"

    async def scenario():
        run = await service.create(source, request())
        await asyncio.wait_for(client.entered.wait(), 5)
        await service.shutdown()
        result = service.read(run.id)
        assert result.status == "interrupted" and result.counts.relevant == 1
        assert coordinator._owner is None
        assert service.repository.items(run.id).items[0].status == "completed"
        with pytest.raises(SummaryError, match="ai_summary_unavailable"):
            await service.create(source, request())

    asyncio.run(scenario())


def test_cancel_waits_for_inflight_sqlite_write_then_preserves_analysis(
    tmp_path, monkeypatch
):
    _, source, service, _, client, _, coordinator = environment(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    original = service.repository.finish_item

    def delayed(*args, **kwargs):
        if args[2] == "completed":
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(service.repository, "finish_item", delayed)

    async def scenario():
        run = await service.create(source, request())
        assert await asyncio.to_thread(entered.wait, 5)
        cancelling = asyncio.create_task(service.cancel(run.id))
        await asyncio.sleep(0)
        assert not cancelling.done() and coordinator._owner is not None
        release.set()
        result = await asyncio.wait_for(cancelling, 5)
        assert result.status == "cancelled" and result.counts.relevant == 1
        assert result.usage.total_tokens == 15 and len(client.calls) == 1
        assert coordinator._owner is None

    asyncio.run(scenario())


def test_usage_aggregate_overflow_is_unknown_without_erasing_single_attempts(tmp_path):
    _, source, service, _, client, _, _ = environment(tmp_path)
    client.usage = AIUsage(
        prompt_tokens=MAX_USAGE_TOKENS - 1,
        completion_tokens=1,
        total_tokens=MAX_USAGE_TOKENS,
    )

    async def scenario():
        await service.create(source, request())
        result = await finished(service)
        assert result.status == "completed"
        assert result.usage.accounted_requests == result.usage.attempted_requests == 2
        assert result.usage.complete is False and result.usage.total_tokens is None
        assert (
            service.repository.items(result.id).items[0].usage.total_tokens
            == MAX_USAGE_TOKENS
        )

    asyncio.run(scenario())
