"""Final database migration preserves the supported five-platform catalog."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from longtian_api import database as migrations
from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.repositories.automation_workflows import AutomationWorkflowRepository


def _version_25_database(path: Path) -> Database:
    database = Database(path)
    with database.connect() as connection:
        for version in range(1, 26):
            getattr(migrations, f"_migrate_to_version_{version}")(connection)
    return database


def _seed_v25(
    database: Database,
    *,
    with_run_history: bool = False,
    with_same_name_enabled_task: bool = False,
) -> None:
    timestamp = "2026-09-05T00:00:00+00:00"
    with database.connect() as connection:
        report_prompt = connection.execute(
            "SELECT instructions FROM analysis_prompt_versions WHERE id=2"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO ai_settings VALUES (1, ?, ?, ?, ?, ?)",
            (
                "https://example.com/v1",
                "fixture-model",
                str(uuid4()),
                7,
                timestamp,
            ),
        )
        for run_id, platform in ((1, "wb"), (2, "xhs")):
            connection.execute(
                """INSERT INTO search_runs(
                  id, monitoring_rule_id, platform, rule_name,
                  max_results_per_term, status, current_term_position,
                  created_at, started_at, finished_at
                ) VALUES (?, 1, ?, '历史规则', 1, 'completed_empty', 0, ?, ?, ?)""",
                (run_id, platform, timestamp, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO search_run_terms VALUES (?, 0, ?)",
                (run_id, "龙田街道"),
            )
            connection.execute(
                """INSERT INTO search_contents(
                  id, platform, platform_content_id, content_type, title, snippet,
                  creator_hash, publisher_name, published_at_text, content_url,
                  first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, 'post', '历史标题', '历史摘要', '', '',
                          '刚刚', ?, ?, ?)""",
                (
                    run_id,
                    platform,
                    str(run_id),
                    f"https://m.weibo.cn/detail/{run_id}",
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO search_run_contents VALUES (?, ?, 'new', ?, ?)",
                (run_id, run_id, timestamp, timestamp),
            )

        connection.execute(
            """INSERT INTO ai_summary_runs(
              request_id, source_run_id, source_run_status, platform, rule_name,
              terms_json, configuration_revision, base_url, model, force_refresh,
              analysis_prompt_version, summary_prompt_version, model_input_version,
              status, phase, created_at, finished_at
            ) VALUES (?, 1, 'completed_empty', 'xhs', '旧平台总结', '[]', 1,
                      'https://example.com/v1', 'fixture-model', 0, 'old-analysis',
                      'old-report', 'old-input', 'failed', 'analysing', ?, ?)""",
            (str(uuid4()), timestamp, timestamp),
        )

        def insert_task(
            task_id: int, name: str, platform: str, *, enabled: int = 0
        ) -> None:
            connection.execute(
                """INSERT INTO automation_tasks(
                  id, name, normalized_name, monitoring_rule_id,
                  max_results_per_term, analysis_goal, schedule_kind,
                  interval_minutes, daily_time, timezone, enabled, revision,
                  next_due_at, anchor_at, created_at, updated_at, deleted_at,
                  initial_prompt_mode, initial_prompt_version_id,
                  report_prompt_mode, report_prompt_version_id
                ) VALUES (?, ?, ?, 1, 1, ?, 'interval', 10, NULL, NULL, ?, 1,
                          ?, ?, ?, ?, NULL, 'default', 1, 'default', 2)""",
                (
                    task_id,
                    name,
                    name,
                    report_prompt,
                    enabled,
                    timestamp if enabled else None,
                    timestamp if enabled else None,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO automation_task_platforms VALUES (?, 0, ?)",
                (task_id, platform),
            )

        insert_task(
            1,
            "龙田街道舆情值守",
            "wb" if with_same_name_enabled_task else "xhs",
            enabled=1 if with_same_name_enabled_task else 0,
        )
        insert_task(2, "保留微博任务", "wb")

        connection.execute(
            """INSERT INTO collection_schedules(
              id, monitoring_rule_id, rule_name, max_results_per_term,
              interval_minutes, enabled, revision, anchor_at, next_due_at,
              created_at, updated_at
            ) VALUES (1, 1, '旧平台定时任务', 1, 10, 0, 1, NULL, NULL, ?, ?)""",
            (timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO collection_schedule_platforms VALUES (1, 0, 'xhs')"
        )

        if with_run_history:
            connection.execute(
                """INSERT INTO automation_runs(
                  admission_key, request_id, task_id, trigger, task_revision,
                  snapshot_json, status, active_stage, cancel_requested, outcome,
                  topic_report_id, error_json, revision, created_at, started_at,
                  finished_at
                ) VALUES ('fixture-run', NULL, 1, 'scheduled', 1, '{}', 'failed',
                          NULL, 0, NULL, NULL, NULL, 1, ?, ?, ?)""",
                (timestamp, timestamp, timestamp),
            )


def _seed_mixed_batch(database: Database) -> None:
    """Add a legacy batch whose valid Weibo item follows an obsolete item."""
    timestamp = "2026-09-05T00:00:00+00:00"
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO search_batches(
              id, monitoring_rule_id, rule_name, max_results_per_term, status,
              current_item_position, created_at, started_at, finished_at,
              control_revision
            ) VALUES (1, 1, '混合历史批次', 1, 'completed_with_failures',
                      1, ?, ?, ?, 0)""",
            (timestamp, timestamp, timestamp),
        )
        connection.execute("INSERT INTO search_batch_terms VALUES (1, 0, '龙田街道')")
        connection.executemany(
            """INSERT INTO search_batch_items(
              batch_id, position, platform, status, created_at, started_at,
              finished_at, pause_reason, completion_basis
            ) VALUES (1, ?, ?, ?, ?, ?, ?, NULL, ?)""",
            (
                (0, "xhs", "failed", timestamp, timestamp, timestamp, None),
                (
                    1,
                    "wb",
                    "completed",
                    timestamp,
                    timestamp,
                    timestamp,
                    "attempt_success",
                ),
            ),
        )
        connection.executemany(
            """INSERT INTO search_batch_attempts(
              batch_id, item_position, attempt_number, search_run_id, created_at
            ) VALUES (1, ?, 1, ?, ?)""",
            ((0, 2, timestamp), (1, 1, timestamp)),
        )
        connection.execute(
            """INSERT INTO search_batch_recoveries(
              batch_id, item_position, previous_control_revision,
              previous_batch_status, previous_item_status,
              previous_batch_finished_at, previous_item_finished_at, recovered_at
            ) VALUES (1, 0, 0, 'completed_with_failures', 'failed', ?, ?, ?)""",
            (timestamp, timestamp, timestamp),
        )
        connection.execute(
            """INSERT INTO collection_schedules(
              id, monitoring_rule_id, rule_name, max_results_per_term,
              interval_minutes, enabled, revision, anchor_at, next_due_at,
              created_at, updated_at
            ) VALUES (2, 1, '混合历史定时任务', 1, 10, 0, 1, NULL, NULL, ?, ?)""",
            (timestamp, timestamp),
        )
        connection.executemany(
            "INSERT INTO collection_schedule_platforms VALUES (2, ?, ?)",
            ((0, "xhs"), (1, "wb")),
        )


def test_fresh_database_has_the_supported_platform_constraints(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.sqlite3")
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        for table in (
            "search_runs",
            "search_contents",
            "search_batch_items",
            "ai_summary_runs",
            "collection_schedule_platforms",
            "automation_task_platforms",
        ):
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            assert "CHECK (platform IN" in schema
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO search_contents(
                  platform, platform_content_id, content_type, title, snippet,
                  creator_hash, publisher_name, published_at_text, content_url,
                  first_seen_at, last_seen_at
                ) VALUES ('invalid', 'fresh-invalid', 'post', 'bad', '', '', '', '刚刚',
                          'https://m.weibo.cn/detail/fresh-invalid', ?, ?)""",
                ("2026-09-05T00:00:00+00:00", "2026-09-05T00:00:00+00:00"),
            )


def test_v26_removes_obsolete_graph_preserves_valid_data_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = _version_25_database(tmp_path / "v25.sqlite3")
    _seed_v25(database)

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, platform FROM search_contents ORDER BY id"
            )
        ] == [(1, "wb")]
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, platform FROM search_runs ORDER BY id"
            )
        ] == [(1, "wb")]
        assert (
            connection.execute("SELECT COUNT(*) FROM ai_summary_runs").fetchone()[0]
            == 0
        )
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, name FROM automation_tasks ORDER BY id"
            )
        ] == [(2, "保留微博任务")]
        assert (
            connection.execute("SELECT COUNT(*) FROM collection_schedules").fetchone()[
                0
            ]
            == 0
        )
        assert tuple(
            connection.execute("SELECT model, revision FROM ai_settings").fetchone()
        ) == ("fixture-model", 7)
        assert (
            connection.execute("SELECT COUNT(*) FROM monitoring_rules").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='trigger' AND name LIKE '%weibo_only%'"
            ).fetchone()[0]
            == 0
        )
        for table in (
            "search_runs",
            "search_contents",
            "search_batch_items",
            "ai_summary_runs",
            "collection_schedule_platforms",
            "automation_task_platforms",
        ):
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            assert "CHECK (platform IN" in schema

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO search_contents(
                  platform, platform_content_id, content_type, title, snippet,
                  creator_hash, publisher_name, published_at_text, content_url,
                  first_seen_at, last_seen_at
                ) VALUES ('invalid', 'new', 'post', 'bad', '', '', '', '刚刚',
                          'https://m.weibo.cn/detail/new', ?, ?)""",
                ("2026-09-05T00:00:00+00:00", "2026-09-05T00:00:00+00:00"),
            )


def test_v26_refuses_to_delete_obsolete_task_history(tmp_path: Path) -> None:
    database = _version_25_database(tmp_path / "history.sqlite3")
    _seed_v25(database, with_run_history=True)

    with pytest.raises(
        sqlite3.DatabaseError, match="Cannot remove obsolete automation tasks"
    ):
        database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 25
        assert (
            connection.execute("SELECT COUNT(*) FROM automation_tasks").fetchone()[0]
            == 2
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='trigger' AND name LIKE '%weibo_only%'"
            ).fetchone()[0]
            == 0
        )


def test_v26_does_not_delete_same_name_weibo_only_task(tmp_path: Path) -> None:
    database = _version_25_database(tmp_path / "same-name-task.sqlite3")
    _seed_v25(database, with_same_name_enabled_task=True)

    database.initialize()

    with database.connect() as connection:
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, name FROM automation_tasks ORDER BY id"
            )
        ] == [(1, "龙田街道舆情值守"), (2, "保留微博任务")]
        assert tuple(
            connection.execute(
                "SELECT task_id, platform FROM automation_task_platforms "
                "WHERE task_id=1"
            ).fetchone()
        ) == (1, "wb")


def test_v26_keeps_unknown_enabled_task_readable_but_disables_it(
    tmp_path: Path,
) -> None:
    database = _version_25_database(tmp_path / "unknown-enabled-task.sqlite3")
    _seed_v25(database)
    timestamp = "2026-09-05T00:00:00+00:00"

    with database.connect() as connection:
        report_prompt = connection.execute(
            "SELECT instructions FROM analysis_prompt_versions WHERE id=2"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO automation_tasks(
              id, name, normalized_name, monitoring_rule_id,
              max_results_per_term, analysis_goal, schedule_kind,
              interval_minutes, daily_time, timezone, enabled, revision,
              next_due_at, anchor_at, created_at, updated_at, deleted_at,
              initial_prompt_mode, initial_prompt_version_id,
              report_prompt_mode, report_prompt_version_id
            ) VALUES (3, '未知启用旧平台任务', '未知启用旧平台任务', 1, 1, ?,
                      'interval', 10, NULL, NULL, 1, 1, ?, ?, ?, ?, NULL,
                      'default', 1, 'default', 2)""",
            (report_prompt, timestamp, timestamp, timestamp, timestamp),
        )
        connection.execute("INSERT INTO automation_task_platforms VALUES (3, 0, 'xhs')")

    database.initialize()

    with database.connect() as connection:
        assert tuple(
            connection.execute(
                "SELECT id, enabled, next_due_at, anchor_at "
                "FROM automation_tasks WHERE id=3"
            ).fetchone()
        ) == (3, 0, None, None)
        assert tuple(
            connection.execute(
                "SELECT position, platform FROM automation_task_platforms "
                "WHERE task_id=3"
            ).fetchone()
        ) == (0, "wb")
    tasks, _ = AutomationWorkflowRepository(database).list_tasks(limit=20)
    assert next(task for task in tasks if task.id == 3).platforms == ("wb",)


def test_v26_preserves_weibo_attempts_in_a_mixed_analysis_job(
    tmp_path: Path,
) -> None:
    database = _version_25_database(tmp_path / "mixed-analysis.sqlite3")
    _seed_v25(database)
    timestamp = "2026-09-05T00:00:00+00:00"

    with database.connect() as connection:
        job_id = connection.execute(
            """INSERT INTO content_analysis_jobs(
              request_id, trigger, configuration_revision, base_url, model,
              initial_prompt_version_id, report_prompt_version_id, force_refresh,
              status, created_at, started_at, finished_at
            ) VALUES ('mixed-analysis', 'manual', 1, 'https://example.com/v1',
                      'fixture-model', 1, 2, 0, 'completed', ?, ?, ?)""",
            (timestamp, timestamp, timestamp),
        ).lastrowid
        connection.executemany(
            """INSERT INTO content_analysis_attempts(
              job_id, content_id, source_run_id, position, source_json,
              first_seen_at, observation_hash, cache_key, input_json,
              input_fingerprint, output_json, attempted, error_json, status,
              created_at, finished_at
            ) VALUES (?, ?, ?, ?, '{}', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                (
                    job_id,
                    2,
                    2,
                    0,
                    timestamp,
                    "x" * 64,
                    "xhs-cache",
                    None,
                    None,
                    None,
                    1,
                    "{}",
                    "failed",
                    timestamp,
                    timestamp,
                ),
                (
                    job_id,
                    1,
                    1,
                    1,
                    timestamp,
                    "w" * 64,
                    "wb-cache",
                    "{}",
                    "w" * 64,
                    "{}",
                    1,
                    None,
                    "completed",
                    timestamp,
                    timestamp,
                ),
            ),
        )
        connection.executemany(
            """INSERT INTO content_analysis_claims(
              content_id, eligibility_origin, discovery_run_id
            ) VALUES (?, 'historical', ?)""",
            ((1, 1), (2, 2)),
        )
        connection.execute(
            """UPDATE content_analysis_claims
            SET first_attempt_id=2, latest_attempt_id=2
            WHERE content_id=1"""
        )
        connection.execute(
            """UPDATE content_analysis_claims
            SET first_attempt_id=1, latest_attempt_id=1
            WHERE content_id=2"""
        )

    database.initialize()

    with database.connect() as connection:
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, content_id, source_run_id, position, status "
                "FROM content_analysis_attempts"
            )
        ] == [(2, 1, 1, 1, "completed")]
        assert tuple(
            connection.execute(
                "SELECT first_attempt_id, latest_attempt_id "
                "FROM content_analysis_claims WHERE content_id=1"
            ).fetchone()
        ) == (2, 2)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM content_analysis_jobs WHERE id=?", (job_id,)
            ).fetchone()[0]
            == 1
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_v26_preserves_weibo_side_of_mixed_batch(tmp_path: Path) -> None:
    database = _version_25_database(tmp_path / "mixed-batch.sqlite3")
    _seed_v25(database)
    _seed_mixed_batch(database)

    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, platform FROM search_contents ORDER BY id"
            )
        ] == [(1, "wb")]
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT id, platform FROM search_runs ORDER BY id"
            )
        ] == [(1, "wb")]
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT batch_id, position, platform, status FROM search_batch_items"
            )
        ] == [(1, 0, "wb", "completed")]
        assert tuple(
            connection.execute(
                "SELECT batch_id, item_position, search_run_id "
                "FROM search_batch_attempts"
            ).fetchone()
        ) == (1, 0, 1)
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM search_batch_recoveries"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT current_item_position FROM search_batches WHERE id=1"
            ).fetchone()[0]
            == 0
        )
        assert tuple(
            connection.execute(
                "SELECT schedule_id, position, platform "
                "FROM collection_schedule_platforms"
            ).fetchone()
        ) == (2, 0, "wb")
        assert [
            tuple(row)
            for row in connection.execute("SELECT id FROM collection_schedules")
        ] == [(2,)]


def test_v26_removes_completed_obsolete_report_graph(tmp_path: Path) -> None:
    database = _version_25_database(tmp_path / "report-graph.sqlite3")
    _seed_v25(database)
    timestamp = "2026-09-05T00:00:00+00:00"

    with database.connect() as connection:
        report_id = connection.execute(
            """INSERT INTO topic_report_runs(
              request_id, trigger, selection_json, prompt_json,
              configuration_revision, base_url, model, status, created_at
            ) VALUES (?, 'interval', '{}', '{}', 1, 'https://example.com/v1',
                      'fixture-model', 'queued', ?)""",
            (str(uuid4()), timestamp),
        ).lastrowid
        source_id = connection.execute(
            """INSERT INTO topic_report_sources(
              report_id, content_id, position, source_json, first_seen_at,
              unavailable_reason
            ) VALUES (?, 2, 0, '{}', ?, 'not_analysed')""",
            (report_id, timestamp),
        ).lastrowid
        node_id = connection.execute(
            """INSERT INTO topic_report_nodes(
              report_id, node_key, kind, position, level, status, created_at
            ) VALUES (?, 'judgment-0', 'judgment', 0, 0, 'queued', ?)""",
            (report_id, timestamp),
        ).lastrowid
        connection.execute(
            """INSERT INTO topic_report_node_sources(node_id, source_id, position)
              VALUES (?, ?, 0)""",
            (node_id, source_id),
        )
        connection.execute(
            """UPDATE topic_report_nodes SET status='completed', attempted=1,
              output_json='{}', output_hash=?, finished_at=? WHERE id=?""",
            ("f" * 64, timestamp, node_id),
        )
        connection.execute(
            """UPDATE topic_report_runs SET status='completed',
              root_section_id=?, finished_at=? WHERE id=?""",
            (node_id, timestamp, report_id),
        )

    database.initialize()

    with database.connect() as connection:
        assert [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "topic_report_runs",
                "topic_report_sources",
                "topic_report_nodes",
                "topic_report_node_sources",
            )
        ] == [0, 0, 0, 0]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
