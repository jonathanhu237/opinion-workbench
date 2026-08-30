"""Real additive migrations, atomic uncapped membership and immutable history."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from initial_analysis_fixtures import environment, request
from schema_fixtures import (
    create_legacy_schema,
    seed_historical_content,
    seed_v11_summaries,
)
from summary_fixtures import seed_run

from longtian_api import database as migrations
from longtian_api.database import Database
from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.results import ResultsRepository
from longtian_api.schemas.analysis_settings import AutomationUpdate, PromptUpdate
from longtian_api.services.analysis_errors import AnalysisError


def old_projection(database):
    with database.connect() as connection:
        tables = [
            r[0]
            for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: [
                tuple(row)
                for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ]
            for table in tables
        }


def test_genuine_v11_preserves_old_data_and_forward_only_history(tmp_path):
    database = Database(tmp_path / "legacy.sqlite3")
    create_legacy_schema(database, 11)
    seed_historical_content(database, 3)
    before = old_projection(database)
    database.initialize()
    settings = AnalysisSettingsRepository(database)
    original = settings.read()
    changed = settings.save_prompt(
        "initial",
        PromptUpdate(
            expected_version_id=original.initial_prompt.id,
            instructions="逐条保留来源与未知信息。",
        ),
    )
    database.initialize()
    after = old_projection(database)
    assert all(after[table] == rows for table, rows in before.items())
    assert settings.read() == changed
    assert changed.report_prompt == original.report_prompt
    assert original.initial_prompt.id != changed.initial_prompt.id
    results = ResultsRepository(database).list()
    assert results.eligible_count == 3
    assert {r.analysis_state for r in results.items} == {"never_started"}
    assert ContentAnalysisRepository(database).list().jobs == []
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == migrations.CURRENT_DATABASE_VERSION
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM analysis_completion_events"
            ).fetchone()[0]
            == 0
        )


def test_v12_migration_rolls_back_real_ddl_and_seed_failure(tmp_path, monkeypatch):
    database = Database(tmp_path / "rollback.sqlite3")
    create_legacy_schema(database, 11)
    seed_historical_content(database)
    before = old_projection(database)
    import longtian_api.migrations.initial_analysis as migration

    original = migration.migrate

    def fail_after_real_migration(connection):
        original(connection)
        raise RuntimeError("synthetic failure after actual DDL/DML")

    monkeypatch.setattr(migration, "migrate", fail_after_real_migration)
    with database.connect() as connection:
        with pytest.raises(RuntimeError):
            migrations._migrate_to_version_12(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert old_projection(database) == before


@pytest.mark.parametrize("count", [0, 1, 101, 1001])
def test_one_action_atomically_selects_all_across_runs_without_page_cap(
    tmp_path, count
):
    database, _, service, _, model, worker, _ = environment(tmp_path, count=0)
    for start in range(0, count, 100):
        seed_run(database, min(count - start, 100), start=1000 + start)
    result = service.repository.create(request(database))
    assert result.admitted_count == count
    assert result.already_active_count == 0
    assert (result.job is None) == (count == 0)
    if result.job:
        assert result.job.counts.total == count
        page = service.repository.items(
            result.job.id, limit=100, offset=max(0, count - 1)
        )
        assert len(page.items) == 1 and page.items[0].position == count - 1
        seed_run(database, 1, start=9000)
        assert service.repository.read(result.job.id).counts.total == count
        assert ResultsRepository(database).list(limit=1).eligible_count == 1
    assert model.calls == worker.calls == []


def test_concurrent_requests_claim_each_content_once_and_noop_replays(tmp_path):
    database, _, service, _, _, _, _ = environment(tmp_path, count=101)
    payloads = [request(database) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(service.repository.create, payloads))
    assert sorted(r.admitted_count for r in results) == [0, 0, 101]
    for payload, result in zip(payloads, results, strict=True):
        assert service.repository.create(payload) == result
    with pytest.raises(AnalysisError, match="content_analysis_request_conflict"):
        service.repository.create(
            payloads[0].model_copy(update={"force_refresh": True})
        )
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM content_analysis_attempts"
            ).fetchone()[0]
            == 101
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM content_analysis_requests"
            ).fetchone()[0]
            == 3
        )


def test_automatic_and_manual_admissions_share_one_atomic_content_claim(tmp_path):
    database, source, service, _, model, worker, _ = environment(tmp_path, count=101)
    AnalysisSettingsRepository(database).save_automation(
        AutomationUpdate(expected_revision=1, enabled=True, configuration_revision=1)
    )
    payload = request(database)
    ready = Barrier(2)

    def manual():
        ready.wait(timeout=5)
        return service.repository.create(payload)

    def automatic():
        ready.wait(timeout=5)
        return service.repository.collection_finished("run", source, available=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        manual_future = executor.submit(manual)
        automatic_future = executor.submit(automatic)
        manual_result = manual_future.result()
        automatic_result = automatic_future.result()

    assert sorted(
        result.admitted_count for result in (manual_result, automatic_result)
    ) == [0, 101]
    assert service.repository.create(payload) == manual_result
    assert service.repository.collection_finished("run", source, available=True) is None
    jobs = service.repository.list().jobs
    assert len(jobs) == 1 and jobs[0].counts.total == 101
    assert ResultsRepository(database).list().active_count == 101
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(DISTINCT content_id) FROM content_analysis_attempts"
            ).fetchone()[0]
            == 101
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM content_analysis_attempts"
            ).fetchone()[0]
            == 101
        )
    assert model.calls == worker.calls == []


def test_real_second_member_insert_failure_rolls_back_job_claims_and_uuid(tmp_path):
    database, _, service, _, _, _, _ = environment(tmp_path)
    with database.connect() as connection:
        connection.execute("""CREATE TRIGGER fail_member
          BEFORE INSERT ON content_analysis_attempts WHEN NEW.position=1
          BEGIN SELECT RAISE(ABORT,'private SQL path sentinel'); END""")
    with pytest.raises(AnalysisError, match="analysis_storage_unavailable") as error:
        service.repository.create(request(database))
    assert "sentinel" not in str(error.value)
    assert service.repository.list().jobs == []
    assert ResultsRepository(database).list().eligible_count == 2
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM content_analysis_requests"
            ).fetchone()[0]
            == 0
        )


def test_auto_backlog_never_sweeps_history_or_loses_repeat(tmp_path):
    database = Database(tmp_path / "backlog.sqlite3")
    create_legacy_schema(database, 11)
    seed_historical_content(database, 1)
    database.initialize()
    # A storage-only provider row; this test never reads credentials or networks.
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO ai_settings
          (id,base_url,model,secret_ref,revision,updated_at)
          VALUES (1,'https://example.com/v1','model',?,1,'2026-08-29T00:00:00+00:00')""",
            (str(uuid4()),),
        )
    settings = AnalysisSettingsRepository(database)
    settings.save_automation(
        AutomationUpdate(expected_revision=1, enabled=True, configuration_revision=1)
    )
    repository = ContentAnalysisRepository(database)
    repeated = seed_run(database, 1)
    assert repository.collection_finished("run", repeated, available=True).job is None
    first = seed_run(database, 1, start=2000)
    assert repository.collection_finished("run", first, available=False) is None
    repeated_new = seed_run(database, 1, start=2000)
    result = repository.collection_finished("run", repeated_new, available=True)
    assert result.admitted_count == 1
    assert repository.items(result.job.id).items[0].source.result_id == 2
    assert repository.collection_finished("run", repeated_new, available=True) is None
    assert ResultsRepository(database).list().eligible_count == 1


def test_cancelled_collection_does_not_admit_new_candidates(tmp_path):
    database, _, service, _, _, _, _ = environment(tmp_path, count=0)
    settings = AnalysisSettingsRepository(database)
    settings.save_automation(
        AutomationUpdate(expected_revision=1, enabled=True, configuration_revision=1)
    )
    cancelled = seed_run(database, 1, terminal="cancelled")
    assert (
        service.repository.collection_finished("run", cancelled, available=True) is None
    )
    assert service.repository.list().jobs == []
    assert ResultsRepository(database).list().eligible_count == 1


def test_uuid_noop_is_not_reused_for_later_arrivals(tmp_path):
    database, _, service, _, _, _, _ = environment(tmp_path, count=0)
    payload = request(database)
    noop = service.repository.create(payload)
    seed_run(database, 1)
    assert service.repository.create(payload) == noop
    assert (
        service.repository.create(
            payload.model_copy(update={"request_id": str(uuid4())})
        ).admitted_count
        == 1
    )


def test_genuine_legacy_outcomes_are_markers_not_generic_success(tmp_path):
    database = Database(tmp_path / "legacy-evidence.sqlite3")
    create_legacy_schema(database, 11)
    source = seed_historical_content(database, 7)
    seed_v11_summaries(database, source)
    before = old_projection(database)
    database.initialize()
    after = old_projection(database)
    assert all(after[table] == rows for table, rows in before.items())
    results = ResultsRepository(database)
    assert results.read(1).analysis_state == "legacy_completed"
    assert results.read(1).latest_attempt_id is None
    assert results.read(6).analysis_state == "queued"
    assert results.list().active_count == 1
    assert results.list().eligible_count == 1
    for content_id in (2, 3, 4, 5):
        assert results.read(content_id).analysis_state == "legacy_attempted"
    old = results.legacy(1).items
    assert len(old) == 2 and old[0].reused_from_item_id == old[1].item_id
    assert all(item.source_run_id == source for item in old)
    assert ContentAnalysisRepository(database).list().jobs == []
    from longtian_api.repositories.ai_summaries import SummaryRepository

    SummaryRepository(database).initialize()
    assert results.read(6).analysis_state == "legacy_attempted"
    assert results.list().active_count == 0
    assert results.list().eligible_count == 1


def test_later_completion_recovers_pre_handoff_crash_not_cancelled_sources(tmp_path):
    database, _, service, _, _, _, _ = environment(tmp_path, count=0)
    first = seed_run(database, 1)
    seed_run(database, 1, start=2000, terminal="cancelled")
    # Crash after the terminal collection commit, before its callback.
    service.repository.initialize()
    assert service.repository.list().jobs == []
    AnalysisSettingsRepository(database).save_automation(
        AutomationUpdate(
            expected_revision=1,
            enabled=True,
            configuration_revision=1,
        )
    )
    later = seed_run(database, 0, start=3000, terminal="completed_empty")
    result = service.repository.collection_finished("run", later, available=True)
    assert result.admitted_count == 1
    assert (
        service.repository.items(result.job.id).items[0].source.source_run_id == first
    )
    assert ResultsRepository(database).list().eligible_count == 1


def test_first_entry_filter_preserves_repeat_origins(tmp_path):
    from datetime import UTC, datetime

    from longtian_api.services.results import ResultsService

    database, source, _, _, _, _, _ = environment(tmp_path, count=1)
    first = ResultsRepository(database).read(1)
    repeated = seed_run(database, 1)
    current = ResultsRepository(database).read(1)
    assert current.first_seen_at == first.first_seen_at and current.origin_count == 2
    assert current.source.source_run_id == source
    origins = ResultsRepository(database).origins(1)
    assert {origin.source_run_id for origin in origins.items} == {source, repeated}
    results = ResultsService(database).list(
        first_seen_from=datetime(2026, 8, 29, tzinfo=UTC)
    )
    assert results.total == 0
