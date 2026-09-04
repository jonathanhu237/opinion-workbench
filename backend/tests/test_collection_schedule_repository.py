"""Genuine v12 upgrade and transactional scheduling/replay boundaries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from collection_schedule_fixtures import enabled, environment, payload
from schema_fixtures import (
    create_legacy_schema,
    seed_historical_content,
    seed_v11_summaries,
)
from test_content_analysis_repository import old_projection

from longtian_api import database as migrations
from longtian_api.database import (
    CURRENT_DATABASE_VERSION,
    Database,
    DatabaseVersionError,
)
from longtian_api.repositories.search_batches import (
    ScheduledDispatchChangedError,
    SearchBatchRepository,
    SearchBatchRepositoryUnavailableError,
)
from longtian_api.schemas.collection_schedules import (
    CollectionScheduleCreate,
    CollectionScheduleReplace,
)
from longtian_api.schemas.monitoring_rules import MonitoringRuleReplace
from longtian_api.services.collection_schedule_errors import CollectionScheduleError


def test_real_v12_to_v13_preserves_every_old_column_and_reopens(tmp_path):
    database = Database(tmp_path / "old.sqlite3")
    create_legacy_schema(database, 11)
    source = seed_historical_content(database, 10)
    seed_v11_summaries(database, source)
    with database.connect() as connection:
        migrations._migrate_to_version_12(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
    before = old_projection(database)
    database.initialize()
    Database(database.path).initialize()
    after = old_projection(database)
    assert all(after[table] == rows for table, rows in before.items())
    assert set(after) - set(before) == {
        "collection_schedules",
        "collection_schedule_platforms",
        "collection_occurrences",
        "topic_report_runs",
        "topic_report_sources",
        "topic_report_nodes",
        "topic_report_node_sources",
        "topic_report_node_children",
        "topic_report_requests",
        "automation_tasks",
        "automation_task_platforms",
        "automation_occurrences",
        "automation_runs",
        "automation_stage_attempts",
        "automation_task_contents",
        "automation_run_contents",
        "automation_requests",
        "report_generations",
        "content_materials",
        "media_cache_owner",
        "media_cache_policy",
        "media_cache_entries",
        "media_cache_bindings",
    }
    assert all(
        after[table] == []
        for table in set(after) - set(before) - {"media_cache_policy"}
    )
    assert after["media_cache_policy"] == [(1, 30, 1024, 0)]
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_v13_migration_failure_rolls_back_actual_ddl(tmp_path, monkeypatch):
    import longtian_api.migrations.collection_schedules as migration

    database = Database(tmp_path / "rollback.sqlite3")
    create_legacy_schema(database, 12)
    before = old_projection(database)
    original = migration.migrate

    def fail(connection):
        original(connection)
        raise RuntimeError("synthetic failure after real DDL")

    monkeypatch.setattr(migration, "migrate", fail)
    with pytest.raises(RuntimeError):
        database.initialize()
    assert old_projection(database) == before
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        connection.execute(f"PRAGMA user_version={CURRENT_DATABASE_VERSION + 1}")
    with pytest.raises(DatabaseVersionError):
        database.initialize()


@pytest.mark.parametrize(
    ("value", "unit", "minutes"),
    [
        (1, "minutes", 1),
        (43200, "minutes", 43200),
        (720, "hours", 43200),
        (1, "hours", 60),
    ],
)
def test_interval_roundtrip_defaults_and_catalog_order(tmp_path, value, unit, minutes):
    database, service, clock, *_ = environment(tmp_path)
    schedule = service.create(
        CollectionScheduleCreate(
            **payload(
                interval={"value": value, "unit": unit},
                platforms=["wb"],
            )
        )
    )
    assert schedule.interval_minutes == minutes
    assert schedule.platforms == ["wb"]
    assert not schedule.enabled and schedule.anchor_at is schedule.next_due_at is None
    database.initialize()
    assert service.get(schedule.id) == schedule
    changed = service.replace(
        schedule.id,
        CollectionScheduleReplace(
            **payload(interval={"value": value, "unit": unit}),
            expected_revision=1,
            enabled=True,
        ),
    )
    assert changed.revision == 2
    assert changed.next_due_at == (clock.now + timedelta(minutes=minutes)).isoformat()


def test_interval_overflow_and_stale_update_do_not_mutate(tmp_path):
    _, service, clock, *_ = environment(tmp_path)
    with pytest.raises(CollectionScheduleError, match="invalid_collection_interval"):
        service.create(
            CollectionScheduleCreate(
                **payload(interval={"value": 721, "unit": "hours"})
            )
        )
    schedule = enabled(service)
    clock.advance(30)
    with pytest.raises(CollectionScheduleError, match="collection_schedule_changed"):
        service.replace(
            schedule.id,
            CollectionScheduleReplace(**payload(), expected_revision=1, enabled=False),
        )
    assert service.get(schedule.id) == schedule
    changed = service.replace(
        schedule.id,
        CollectionScheduleReplace(**payload(), expected_revision=2, enabled=True),
    )
    assert changed.revision == 3 and changed.next_due_at != schedule.next_due_at


def test_replace_rolls_back_parent_and_first_platform(tmp_path):
    database, service, *_ = environment(tmp_path)
    schedule = enabled(service)
    with database.connect() as connection:
        connection.execute("""CREATE TRIGGER fail_schedule_platform
            BEFORE INSERT ON collection_schedule_platforms WHEN NEW.position=0
            BEGIN SELECT RAISE(ABORT,'private-sentinel'); END""")
    with pytest.raises(
        CollectionScheduleError, match="collection_schedule_storage_unavailable"
    ):
        service.replace(
            schedule.id,
            CollectionScheduleReplace(
                **payload(platforms=["wb"]), expected_revision=2, enabled=True
            ),
        )
    assert service.get(schedule.id) == schedule


def test_concurrent_due_claims_have_one_durable_key(tmp_path):
    database, service, clock, *_ = environment(tmp_path)
    schedule = enabled(service)
    clock.advance(60)
    barrier = Barrier(2)

    def claim():
        barrier.wait()
        return service.repository.advance_due(clock.now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: claim(), range(2)))
    assert len(first) + len(second) == 1
    assert service.repository.advance_due(clock.now) == []
    assert service.get(schedule.id).revision == schedule.revision
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM collection_occurrences").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO collection_occurrences(schedule_id,schedule_revision,
                  due_at,dispatch_token,status,created_at)
                  VALUES (?,?,?,'other','claimed',?)""",
                (
                    row["schedule_id"],
                    row["schedule_revision"],
                    row["due_at"],
                    row["created_at"],
                ),
            )


def test_batch_token_link_is_atomic_replay_and_rule_guarded(tmp_path):
    database, service, clock, _, _, _, rules, _ = environment(tmp_path)
    schedule = enabled(service)
    clock.advance(60)
    claim = service.repository.advance_due(clock.now)[0]
    rule = rules.list_enabled()[0]
    repository = SearchBatchRepository(database)
    with database.connect() as connection:
        connection.execute("""CREATE TRIGGER fail_link
            BEFORE UPDATE OF batch_id ON collection_occurrences
            BEGIN SELECT RAISE(ABORT,'private-link-sentinel'); END""")
    with pytest.raises(SearchBatchRepositoryUnavailableError):
        repository.create_scheduled_batch(
            claim.dispatch_token, rule, timestamp=clock.now.isoformat()
        )
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0] == 0
        )
        connection.execute("DROP TRIGGER fail_link")
    first, created = repository.create_scheduled_batch(
        claim.dispatch_token, rule, timestamp=clock.now.isoformat()
    )
    replay, created_again = repository.create_scheduled_batch(
        claim.dispatch_token, rule, timestamp=clock.now.isoformat()
    )
    assert created and not created_again and replay == first
    assert service.get(schedule.id).latest_occurrence.batch_id == first.id
    rules.replace_rule(
        rule.id,
        MonitoringRuleReplace(
            name="新规则",
            monitoring_objects=["新对象"],
            issue_keywords=[],
            enabled=True,
        ),
    )
    assert repository.get(first.id).terms == tuple(rule.terms)
    repository.fail_batch(first.id)
    clock.advance(60)
    second = service.repository.advance_due(clock.now)[0]
    with pytest.raises(ScheduledDispatchChangedError):
        repository.create_scheduled_batch(
            second.dispatch_token, rule, timestamp=clock.now.isoformat()
        )


def test_deleted_rule_reference_can_be_disabled_and_history_survives(tmp_path):
    _, service, _, _, _, _, rules, _ = environment(tmp_path)
    schedule = enabled(service)
    rules.delete_rule(1)
    current = service.get(schedule.id)
    assert current.monitoring_rule_id is None and current.rule_state == "deleted"
    disabled = service.replace(
        schedule.id,
        CollectionScheduleReplace(
            **payload(monitoring_rule_id=None),
            expected_revision=current.revision,
            enabled=False,
        ),
    )
    assert disabled.rule_name == schedule.rule_name and not disabled.enabled


@pytest.mark.parametrize("invalid_minutes", [0, 43201, 1.5])
def test_database_rejects_non_whole_or_out_of_range_interval(tmp_path, invalid_minutes):
    database, service, *_ = environment(tmp_path)
    schedule = enabled(service)
    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE collection_schedules SET interval_minutes=? WHERE id=?",
                (invalid_minutes, schedule.id),
            )


def test_occurrence_state_constraints_and_history_references(tmp_path):
    database, service, clock, *_ = environment(tmp_path)
    schedule = enabled(service)
    clock.advance(60)
    claim = service.repository.advance_due(clock.now)[0]
    with database.connect() as connection:
        for state in ["skipped", "missed", "interrupted", "dispatched"]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE collection_occurrences SET status=? WHERE id=?",
                    (state, claim.id),
                )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM collection_schedules WHERE id=?", (schedule.id,)
            )
    assert service.get(schedule.id).latest_occurrence.status == "claimed"
