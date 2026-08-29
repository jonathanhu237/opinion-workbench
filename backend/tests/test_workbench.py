"""Persistent homepage state is current, global, strict, and read-only."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from summary_fixtures import seed_run
from test_content_analysis_api import api_fixture
from topic_report_fixtures import analyse_all, environment

from longtian_api.database import Database
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.services.workbench import WorkbenchService
from longtian_api.services.workbench_errors import ERRORS, WorkbenchError

NOW = datetime(2026, 8, 29, 8, tzinfo=UTC)


def service(database):
    return WorkbenchService(database, clock=lambda: NOW)


def database(tmp_path):
    owner = Database(tmp_path / "workbench.sqlite3")
    owner.initialize()
    return owner


def test_empty_snapshot_and_global_next_schedule(tmp_path):
    owner = database(tmp_path)
    assert service(owner).read().model_dump() == {
        "observed_at": NOW.isoformat(),
        "attention": [],
        "activity": {
            "collection": None,
            "initial_analysis": None,
            "report": None,
        },
        "next_collection": None,
        "latest_report": None,
    }
    with owner.connect() as connection:
        for name, minutes in (("较晚规则", 60), ("最近规则", 15)):
            due = (NOW + timedelta(minutes=minutes)).isoformat()
            connection.execute(
                """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
                  max_results_per_term,interval_minutes,enabled,anchor_at,next_due_at,
                  created_at,updated_at) VALUES (1,?,10,30,1,?,?,?,?)""",
                (name, NOW.isoformat(), due, NOW.isoformat(), NOW.isoformat()),
            )
    next_collection = service(owner).read().next_collection
    assert next_collection is not None
    assert next_collection.rule_name == "最近规则"
    assert next_collection.due_at == (NOW + timedelta(minutes=15)).isoformat()


def test_unavailable_schedule_automation_is_not_presented_as_next_collection(tmp_path):
    owner = database(tmp_path)
    with owner.connect() as connection:
        connection.execute(
            """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
              max_results_per_term,interval_minutes,enabled,anchor_at,next_due_at,
              created_at,updated_at) VALUES (1,'社区规则',10,30,1,?,?,?,?)""",
            (
                NOW.isoformat(),
                (NOW + timedelta(minutes=30)).isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    assert service(owner).read().next_collection is not None
    assert (
        WorkbenchService(
            owner,
            clock=lambda: NOW,
            schedules_available=False,
        )
        .read()
        .next_collection
        is None
    )


def test_invalid_enabled_schedule_is_attention_and_not_next_collection(tmp_path):
    owner = database(tmp_path)
    with owner.connect() as connection:
        connection.execute(
            """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
              max_results_per_term,interval_minutes,enabled,anchor_at,next_due_at,
              created_at,updated_at) VALUES (1,'社区规则',10,30,1,?,?,?,?)""",
            (
                NOW.isoformat(),
                (NOW + timedelta(minutes=30)).isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.execute("DELETE FROM monitoring_rule_terms WHERE rule_id=1")
        connection.executemany(
            """INSERT INTO monitoring_rule_terms
              (rule_id,value,normalized_value,position) VALUES (1,?,?,?)""",
            ((str(index), str(index), index) for index in range(21)),
        )

    snapshot = service(owner).read()
    assert snapshot.next_collection is None
    assert [(item.status, item.reason) for item in snapshot.attention] == [
        ("invalid", "too_many_search_terms")
    ]


def test_schedule_issue_clears_on_revision_and_disabled_schedule_is_ignored(tmp_path):
    owner = database(tmp_path)
    with owner.connect() as connection:
        schedule_id = connection.execute(
            """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
              max_results_per_term,interval_minutes,enabled,anchor_at,next_due_at,
              created_at,updated_at) VALUES (1,'社区规则',10,30,1,?,?,?,?)""",
            (
                NOW.isoformat(),
                (NOW + timedelta(minutes=30)).isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        ).lastrowid
        connection.execute(
            """INSERT INTO collection_occurrences(schedule_id,schedule_revision,
              due_at,dispatch_token,status,reason,missed_count,missed_until,created_at)
              VALUES (?,1,?,'missed-token','missed','offline',2,?,?)""",
            (
                schedule_id,
                (NOW - timedelta(hours=1)).isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    issue = service(owner).read().attention[0]
    assert (issue.kind, issue.status, issue.reason, issue.unsuccessful_count) == (
        "collection_schedule",
        "missed",
        "offline",
        2,
    )
    with owner.connect() as connection:
        connection.execute(
            """UPDATE collection_schedules SET revision=2,updated_at=? WHERE id=?""",
            (NOW.isoformat(), schedule_id),
        )
    assert service(owner).read().attention == []
    with owner.connect() as connection:
        connection.execute(
            """UPDATE monitoring_rules SET enabled=0,updated_at=? WHERE id=1""",
            (NOW.isoformat(),),
        )
    issue = service(owner).read().attention[0]
    assert (issue.status, issue.reason) == ("invalid", "monitoring_rule_disabled")
    with owner.connect() as connection:
        connection.execute(
            """UPDATE collection_schedules SET enabled=0,anchor_at=NULL,
              next_due_at=NULL,updated_at=? WHERE id=?""",
            (NOW.isoformat(), schedule_id),
        )
    assert service(owner).read().attention == []


def test_collection_activity_and_latest_owner_success_clears_failure(tmp_path):
    owner = database(tmp_path)
    repository = SearchBatchRepository(owner)
    first = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="社区规则",
        terms=("对象",),
        platforms=("wb",),
        max_results_per_term=10,
    )
    activity = service(owner).read().activity.collection
    assert activity is not None
    assert (activity.id, activity.item_count, activity.completed_item_count) == (
        first.id,
        1,
        0,
    )
    with owner.connect() as connection:
        connection.execute(
            """UPDATE search_batch_items SET status='failed',finished_at=?
              WHERE batch_id=?""",
            (NOW.isoformat(), first.id),
        )
        connection.execute(
            """UPDATE search_batches SET status='internal_error',finished_at=?
              WHERE id=?""",
            (NOW.isoformat(), first.id),
        )
    assert service(owner).read().attention[0].status == "internal_error"
    running = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="社区规则",
        terms=("对象",),
        platforms=("wb",),
        max_results_per_term=10,
    )
    assert service(owner).read().attention[0].resource_id == first.id
    with owner.connect() as connection:
        connection.execute(
            """UPDATE search_batch_items SET status='completed',
              completion_basis='attempt_success',finished_at=? WHERE batch_id=?""",
            (NOW.isoformat(), running.id),
        )
        connection.execute(
            """UPDATE search_batches SET status='completed',finished_at=? WHERE id=?""",
            (NOW.isoformat(), running.id),
        )
    assert service(owner).read().attention == []


def _analysis_job(connection, run_id, status, attempt_status):
    prompts = connection.execute(
        """SELECT initial_prompt_version_id,report_prompt_version_id
          FROM analysis_settings WHERE id=1"""
    ).fetchone()
    terminal = status not in ("queued", "running")
    job_id = connection.execute(
        """INSERT INTO content_analysis_jobs(trigger,configuration_revision,
          base_url,model,initial_prompt_version_id,report_prompt_version_id,
          force_refresh,status,created_at,started_at,finished_at)
          VALUES ('manual',1,'https://example.com/v1','saved-model',?,?,0,?,?,?,?)""",
        (
            prompts[0],
            prompts[1],
            status,
            NOW.isoformat(),
            NOW.isoformat(),
            NOW.isoformat() if terminal else None,
        ),
    ).lastrowid
    completed = attempt_status == "completed"
    connection.execute(
        """INSERT INTO content_analysis_attempts(job_id,content_id,source_run_id,
          position,source_json,first_seen_at,observation_hash,cache_key,input_json,
          input_fingerprint,output_json,attempted,status,created_at,started_at,finished_at)
          VALUES (?,1,?,0,'{}',?,'observation','cache',?,?,?,1,?,?,?,?)""",
        (
            job_id,
            run_id,
            NOW.isoformat(),
            "{}" if completed else None,
            "fingerprint" if completed else None,
            "{}" if completed else None,
            attempt_status,
            NOW.isoformat(),
            NOW.isoformat(),
            NOW.isoformat() if terminal else None,
        ),
    )
    if status == "completed":
        connection.execute(
            """INSERT INTO analysis_completion_events(job_id,settled_at,state)
              VALUES (?,?,'consumed')""",
            (job_id, NOW.isoformat()),
        )
    return job_id


def test_analysis_progress_failure_and_later_success(tmp_path):
    owner = database(tmp_path)
    run_id = seed_run(owner, 1)
    with owner.connect() as connection:
        active_id = _analysis_job(connection, run_id, "running", "analysing")
    activity = service(owner).read().activity.initial_analysis
    assert activity is not None
    assert (activity.id, activity.total_count, activity.completed_count) == (
        active_id,
        1,
        0,
    )
    with owner.connect() as connection:
        connection.execute(
            """UPDATE content_analysis_attempts SET status='interrupted',finished_at=?
              WHERE job_id=?""",
            (NOW.isoformat(), active_id),
        )
        connection.execute(
            """UPDATE content_analysis_jobs SET status='interrupted',finished_at=?
              WHERE id=?""",
            (NOW.isoformat(), active_id),
        )
    assert service(owner).read().attention[0].status == "interrupted"
    with owner.connect() as connection:
        _analysis_job(connection, run_id, "completed", "completed")
    assert service(owner).read().attention == []


def _report_row(connection, status, *, empty_reason=None):
    prompt = connection.execute(
        """SELECT p.id,p.instructions,p.content_hash,p.schema_version
          FROM analysis_settings s JOIN analysis_prompt_versions p
            ON p.id=s.report_prompt_version_id WHERE s.id=1"""
    ).fetchone()
    prompt_json = json.dumps(
        {
            "version_id": prompt["id"],
            "origin": "shared",
            "instructions": prompt["instructions"],
            "content_hash": prompt["content_hash"],
            "schema_version": prompt["schema_version"],
        },
        ensure_ascii=False,
    )
    selection_json = json.dumps(
        {
            "kind": "first_seen_interval",
            "first_seen_from": "2026-08-01T00:00:00+00:00",
            "first_seen_to": "2026-08-02T00:00:00+00:00",
        }
    )
    return connection.execute(
        """INSERT INTO topic_report_runs(request_id,trigger,selection_json,
          prompt_json,configuration_revision,base_url,model,status,empty_reason,
          created_at,started_at,finished_at) VALUES (?,'interval',?,?,1,
          'https://example.com/v1','saved-model',?,?,?,?,?)""",
        (
            str(uuid4()),
            selection_json,
            prompt_json,
            status,
            empty_reason,
            NOW.isoformat(),
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    ).lastrowid


def test_newer_report_failure_keeps_readable_empty_report(tmp_path):
    owner = database(tmp_path)
    with owner.connect() as connection:
        readable_id = _report_row(connection, "empty", empty_reason="no_ready_sources")
        failed_id = _report_row(connection, "failed")
    snapshot = service(owner).read()
    assert snapshot.latest_report is not None
    assert (snapshot.latest_report.id, snapshot.latest_report.empty_reason) == (
        readable_id,
        "no_ready_sources",
    )
    assert (
        snapshot.attention[0].resource_id,
        snapshot.attention[0].status,
        snapshot.attention[0].reason,
    ) == (failed_id, "failed", "internal_error")
    with owner.connect() as connection:
        newest_id = _report_row(connection, "empty", empty_reason="no_ready_sources")
    snapshot = service(owner).read()
    assert snapshot.attention == []
    assert snapshot.latest_report is not None
    assert snapshot.latest_report.id == newest_id


def test_completed_report_reuses_strict_readable_document(tmp_path):
    async def run():
        owner, initial, reports, ai, *_ = environment(tmp_path, count=1)
        _, report = await analyse_all(owner, initial, reports)
        snapshot = service(owner).read()
        assert snapshot.latest_report is not None
        assert snapshot.latest_report.id == report.id
        assert snapshot.latest_report.status == "completed"
        assert snapshot.latest_report.overview == "以下内容来自保存的相关材料。"
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_corrupt_latest_readable_report_fails_the_snapshot(tmp_path):
    async def run():
        owner, initial, reports, ai, *_ = environment(tmp_path, count=1)
        _, report = await analyse_all(owner, initial, reports)
        with owner.connect() as connection:
            connection.execute("DROP TRIGGER topic_report_node_terminal_immutable")
            connection.execute(
                "UPDATE topic_report_nodes SET output_json='{}' WHERE id=?",
                (report.root_section_id,),
            )
        with pytest.raises(WorkbenchError) as caught:
            service(owner).read()
        assert caught.value.code == "workbench_storage_unavailable"
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_api_is_no_store_sanitized_and_read_only(tmp_path, monkeypatch):
    app, owner, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        tables = (
            "search_batches",
            "content_analysis_jobs",
            "topic_report_runs",
            "collection_occurrences",
        )

        def counts():
            with owner.connect() as connection:
                return tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in tables
                )

        before = counts()
        for _ in range(3):
            response = client.get("/api/v1/workbench")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
        assert counts() == before
        assert model.calls == media.calls == []

        def fail(_observed_at):
            raise RuntimeError("private database credential sentinel")

        monkeypatch.setattr(app.state.workbench_service.repository, "read", fail)
        response = client.get("/api/v1/workbench")
        status, message = ERRORS["workbench_unavailable"]
        assert response.status_code == status
        assert response.json() == {
            "detail": {"code": "workbench_unavailable", "message": message}
        }
        assert "private" not in response.text and "sentinel" not in response.text
        assert response.headers["cache-control"] == "no-store"
