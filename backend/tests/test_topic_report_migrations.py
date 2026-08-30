"""Real v13 preservation and all-or-nothing v14 DDL/DML, never down-labelling."""

import json
from uuid import uuid4

import pytest
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

REPORT_TABLES = {
    "topic_report_runs",
    "topic_report_sources",
    "topic_report_nodes",
    "topic_report_node_sources",
    "topic_report_node_children",
    "topic_report_requests",
}


def populated_v13(tmp_path):
    database = Database(tmp_path / "old-v13.sqlite3")
    create_legacy_schema(database, 11)
    run_id = seed_historical_content(database, 10)
    seed_v11_summaries(database, run_id)
    now = "2026-08-28T00:00:00+00:00"
    with database.connect() as connection:
        migrations._migrate_to_version_12(connection)
        migrations._migrate_to_version_13(connection)
        # Frozen v13 parent/attempt/claim SQL. No current initialize or v14 DDL.
        job_id = connection.execute(
            """INSERT INTO content_analysis_jobs(request_id,trigger,
              configuration_revision,base_url,model,initial_prompt_version_id,
              report_prompt_version_id,force_refresh,status,created_at)
              VALUES (?,'manual',1,'https://example.com/v1','saved-model',1,2,
                0,'queued',?)""",
            (str(uuid4()), now),
        ).lastrowid
        source = {
            "source_run_id": run_id,
            "result_id": 10,
            "platform": "wb",
            "platform_content_id": "1009",
            "content_type": "post",
            "title": "历史标题",
            "snippet": "历史摘要",
            "content_url": "https://m.weibo.cn/detail/1009",
            "published_at_text": "刚刚",
            "matched_terms": ["历史关键词"],
        }
        attempt_id = connection.execute(
            """INSERT INTO content_analysis_attempts(job_id,content_id,
              source_run_id,position,source_json,first_seen_at,observation_hash,
              cache_key,status,created_at) VALUES (?,10,?,0,?,?,?,?,'queued',?)""",
            (
                job_id,
                run_id,
                json.dumps(source, ensure_ascii=False),
                now,
                "a" * 64,
                "b" * 64,
                now,
            ),
        ).lastrowid
        connection.execute(
            """UPDATE content_analysis_claims SET first_attempt_id=?,
              latest_attempt_id=?,active_job_id=? WHERE content_id=10""",
            (attempt_id, attempt_id, job_id),
        )
        completed_job = connection.execute(
            """INSERT INTO content_analysis_jobs(request_id,trigger,
              configuration_revision,base_url,model,initial_prompt_version_id,
              report_prompt_version_id,force_refresh,status,created_at,
              started_at,finished_at) VALUES (?,'manual',1,
                'https://example.com/v1','saved-model',1,2,0,'completed',?,?,?)""",
            (str(uuid4()), now, now, now),
        ).lastrowid
        completed_source = {
            **source,
            "result_id": 9,
            "platform_content_id": "1008",
            "content_url": "https://m.weibo.cn/detail/1008",
        }
        saved_input = {
            "schema_version": 1,
            "extractor_version": "wb-enrichment-v1",
            "acquired_at": 1750000000000,
            "status": "ready",
            "text": {
                "title": "已保存完整标题",
                "body": "已保存完整正文",
                "coverage": "complete",
            },
            "detected_modalities": ["text"],
            "media_inventory_complete": True,
            "assets": [],
            "issues": [],
        }
        understanding = {
            "summary": "历史来源的中立摘要。",
            "location_clues": [],
            "time_context": "具体时间未知。",
            "media_observations": [],
            "uncertainties": "陈述尚未核实。",
        }
        completed_attempt = connection.execute(
            """INSERT INTO content_analysis_attempts(job_id,content_id,
              source_run_id,position,source_json,first_seen_at,observation_hash,
              cache_key,status,input_json,input_fingerprint,output_json,
              attempted,usage_json,created_at,started_at,finished_at)
              VALUES (?,9,?,0,?,?,?,?,'completed',?,?,?,1,?,?,?,?)""",
            (
                completed_job,
                run_id,
                json.dumps(completed_source),
                now,
                "c" * 64,
                "d" * 64,
                json.dumps(saved_input),
                "e" * 64,
                json.dumps(understanding),
                '{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}',
                now,
                now,
                now,
            ),
        ).lastrowid
        connection.execute(
            """UPDATE content_analysis_claims SET first_attempt_id=?,
              latest_attempt_id=?,known_input_fingerprint=? WHERE content_id=9""",
            (completed_attempt, completed_attempt, "e" * 64),
        )
        connection.execute(
            "INSERT INTO analysis_completion_events(job_id,settled_at) VALUES (?,?)",
            (completed_job, now),
        )
        schedule_id = connection.execute(
            """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
              max_results_per_term,interval_minutes,created_at,updated_at)
              VALUES (1,'已保存的计划',10,60,?,?)""",
            (now, now),
        ).lastrowid
        connection.execute(
            "INSERT INTO collection_schedule_platforms VALUES (?,0,'wb')",
            (schedule_id,),
        )
        connection.execute(
            """INSERT INTO collection_occurrences(schedule_id,schedule_revision,
              due_at,dispatch_token,status,reason,missed_count,missed_until,
              created_at) VALUES (?,1,?,?,'missed','offline',3,?,?)""",
            (schedule_id, now, str(uuid4()), now, now),
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
    return database


def test_genuine_populated_v13_adds_only_reports(tmp_path):
    database = populated_v13(tmp_path)
    before = old_projection(database)
    with database.connect() as connection:
        migrations._migrate_to_version_14(connection)
    after = old_projection(database)
    assert set(after) - set(before) == REPORT_TABLES
    assert all(after[table] == rows for table, rows in before.items())
    assert all(after[table] == [] for table in REPORT_TABLES)
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert (
            connection.execute("SELECT enabled FROM analysis_settings").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT enabled FROM collection_schedules").fetchone()[0]
            == 0
        )


def test_v14_failure_after_actual_child_insert_rolls_back(tmp_path, monkeypatch):
    import longtian_api.migrations.topic_reports as migration

    database = populated_v13(tmp_path)
    before = old_projection(database)
    original = migration.migrate

    def fail(connection):
        original(connection)
        report_id = connection.execute(
            """INSERT INTO topic_report_runs(request_id,trigger,selection_json,
              prompt_json,configuration_revision,base_url,model,status,created_at)
              VALUES (?,'interval','{}','{}',1,'https://example.com/v1','model',
                'queued','2026-08-28T00:00:00Z')""",
            (str(uuid4()),),
        ).lastrowid
        connection.execute(
            """INSERT INTO topic_report_sources(report_id,content_id,position,
              source_json,first_seen_at,unavailable_reason)
              VALUES (?,10,0,'{}','2026-08-28T00:00:00Z','not_analysed')""",
            (report_id,),
        )
        raise RuntimeError("synthetic failure after real child insert")

    monkeypatch.setattr(migration, "migrate", fail)
    with pytest.raises(RuntimeError, match="child insert"):
        database.initialize()
    assert old_projection(database) == before
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
    monkeypatch.setattr(migration, "migrate", original)
    with database.connect() as connection:
        migrations._migrate_to_version_14(connection)
    assert set(old_projection(database)) - set(before) == REPORT_TABLES


def test_forward_version_is_rejected_without_changing_any_rows(tmp_path):
    database = populated_v13(tmp_path)
    with database.connect() as connection:
        connection.execute(f"PRAGMA user_version={CURRENT_DATABASE_VERSION + 1}")
    before = old_projection(database)
    with pytest.raises(DatabaseVersionError):
        database.initialize()
    assert old_projection(database) == before
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION + 1
        )
