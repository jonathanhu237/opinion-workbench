"""Focused fake-only coverage for the fixed automatic workflow backend."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from longtian_api import database as database_migrations
from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.main import create_app
from longtian_api.repositories.automation_workflows import (
    AutomationWorkflowRepository,
    BatchContentRecord,
)
from longtian_api.schemas.analysis_settings import PromptVersion
from longtian_api.schemas.automation_workflows import (
    AutomationDailySchedule,
    AutomationIntervalSchedule,
    AutomationRunCancel,
    AutomationRunNow,
    AutomationRunRetry,
    AutomationTaskCreate,
    AutomationTaskReplace,
)
from longtian_api.schemas.content_analyses import (
    AnalysisAdmission,
    AnalysisCounts,
    AnalysisJob,
    AnalysisUsage,
)
from longtian_api.services.automation_workflow_errors import AutomationWorkflowError
from longtian_api.services.automation_workflows import (
    AutomationWorkflowService,
    schedule_next_due,
)
from longtian_api.services.monitoring_rules import MonitoringRuleService

REQUEST = "123e4567-e89b-42d3-a456-426614174000"


def _task_payload(**changes):
    value = {
        "name": "重点舆情",
        "monitoring_rule_id": 1,
        "platforms": ["toutiao"],
        "max_results_per_term": 10,
        "analysis_goal": "识别与龙田街道相关的舆情内容",
        "schedule": {"kind": "interval", "interval_minutes": 30},
    }
    value.update(changes)
    return AutomationTaskCreate.model_validate(value)


def _repository(tmp_path: Path):
    database = Database(tmp_path / "automation.sqlite3")
    rules = MonitoringRuleService(database_path=database.path)
    rules.initialize()
    return database, rules, AutomationWorkflowRepository(database)


def _snapshot(task, now):
    from longtian_api.schemas.automation_workflows import AutomationSnapshot

    return AutomationSnapshot(
        task_id=task.id,
        task_revision=task.revision,
        task_name=task.name,
        monitoring_rule_id=1,
        rule_name=task.rule_name,
        terms=["龙田街道"],
        platforms=["toutiao"],
        max_results_per_term=10,
        analysis_goal=task.analysis_goal,
        analysis_goal_hash="0" * 64,
        initial_template_version="initial-understanding-v1",
        report_template_version="topic-report-v1",
        admitted_at=now.isoformat(),
    )


def _v14_database(tmp_path: Path) -> Database:
    from test_topic_report_migrations import populated_v13

    database = populated_v13(tmp_path)
    with database.connect() as connection:
        database_migrations._migrate_to_version_14(connection)
    return database


def test_v15_is_additive_and_does_not_convert_old_schedules(tmp_path: Path):
    database = _v14_database(tmp_path)
    with database.connect() as connection:
        old_schedule_count = connection.execute(
            "SELECT COUNT(*) FROM collection_schedules"
        ).fetchone()[0]
        assert old_schedule_count == 1

    database.initialize()
    Database(database.path).initialize()

    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
            == 15
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT COUNT(*) FROM collection_schedules").fetchone()[
                0
            ]
            == old_schedule_count
        )
        assert connection.execute("SELECT * FROM automation_tasks").fetchall() == []
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(search_batches)")
        }
        assert "workflow_operation_key" in columns


def test_v15_failure_rolls_back_real_schema_changes(tmp_path: Path, monkeypatch):
    import longtian_api.migrations.automation_workflows as migration

    database = _v14_database(tmp_path)
    original = migration.migrate

    def fail(connection):
        original(connection)
        connection.execute(
            """INSERT INTO automation_requests(request_id,action,intent_hash,
              result_json,created_at) VALUES (?,'run_now','hash','{}',?)""",
            (str(uuid4()), datetime.now(UTC).isoformat()),
        )
        raise RuntimeError("synthetic v15 failure")

    monkeypatch.setattr(migration, "migrate", fail)
    with pytest.raises(RuntimeError, match="v15 failure"):
        database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='automation_tasks'"
            ).fetchone()
            is None
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(search_batches)")
        }
        assert "workflow_operation_key" not in columns


def test_schedule_validation_and_dst_gap(tmp_path: Path):
    database, _, repository = _repository(tmp_path)
    assert database.path.exists()
    now = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
    assert schedule_next_due(
        AutomationIntervalSchedule(kind="interval", interval_minutes=5), now
    ) == now + timedelta(minutes=5)

    # America/New_York jumps from 01:59 to 03:00 on this date. The requested
    # 02:30 is materialized at the first valid instant after the gap.
    due = schedule_next_due(
        AutomationDailySchedule(
            kind="daily", daily_time="02:30", timezone="America/New_York"
        ),
        datetime(2024, 3, 9, 12, 0, tzinfo=UTC),
    )
    assert due == datetime(2024, 3, 10, 7, 0, tzinfo=UTC)

    task = repository.create_task(_task_payload(), now=now)
    assert task.enabled is False and task.next_due_at is None
    with pytest.raises(ValueError):
        AutomationTaskCreate.model_validate(
            {**_task_payload().model_dump(mode="json"), "platforms": ["wb", "toutiao"]}
        )


def test_occurrence_claim_and_run_snapshot_are_idempotent(tmp_path: Path):
    _, _, repository = _repository(tmp_path)
    now = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
    task = repository.create_task(_task_payload(), now=now)
    enabled = AutomationTaskReplace(
        **_task_payload().model_dump(),
        expected_revision=1,
        enabled=True,
    )
    task = repository.replace_task(
        task.id,
        enabled,
        now=now,
        anchor_at=now.isoformat(),
        next_due_at=(now + timedelta(minutes=30)).isoformat(),
    )
    claims = repository.advance_due(now + timedelta(minutes=30))
    assert len(claims) == 1
    assert repository.advance_due(now + timedelta(minutes=30)) == ()

    snapshot = _snapshot(task, now + timedelta(minutes=30))
    first, created = repository.create_run(
        task_id=task.id,
        trigger="scheduled",
        admission_key=claims[0].admission_key,
        request_id=None,
        snapshot=snapshot,
        now=now + timedelta(minutes=30),
        occurrence_id=claims[0].id,
    )
    replay, replayed = repository.create_run(
        task_id=task.id,
        trigger="scheduled",
        admission_key=claims[0].admission_key,
        request_id=None,
        snapshot=snapshot,
        now=now + timedelta(minutes=30),
        occurrence_id=claims[0].id,
    )
    assert created is True and replayed is False and replay.id == first.id
    assert repository.occurrence(claims[0].id).run_id == first.id


class _FakeBatch:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.calls = []

    async def start_workflow_batch(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Batch", (), {"id": 100 + len(self.calls), "status": next(self.statuses)}
        )()

    async def get_batch(self, batch_id):
        return type("Batch", (), {"id": batch_id, "status": "completed"})()


class _NoModel:
    def __init__(self):
        self.calls = []

    async def workflow_admit(self, **kwargs):
        self.calls.append(kwargs)
        return type("Job", (), {"id": 200 + len(self.calls), "status": "completed"})()

    async def read(self, job_id):
        return type("Job", (), {"id": job_id, "status": "completed"})()


class _NoReport:
    def __init__(self):
        self.calls = []

    async def workflow_admit(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Report", (), {"id": 300 + len(self.calls), "status": "completed"}
        )()

    async def read(self, report_id):
        return type("Report", (), {"id": report_id, "status": "completed"})()


class _ContentRepository(AutomationWorkflowRepository):
    def batch_contents(self, batch_id):
        del batch_id
        with self.database.connect() as connection:
            return tuple(
                BatchContentRecord(
                    content_id=row["id"],
                    collection_run_id=row["source_run_id"],
                    first_seen_at=row["first_seen_at"],
                )
                for row in connection.execute(
                    """SELECT c.id,MIN(l.run_id) AS source_run_id,c.first_seen_at
                       FROM search_contents c JOIN search_run_contents l
                         ON l.search_content_id=c.id
                       GROUP BY c.id,c.first_seen_at ORDER BY c.id"""
                ).fetchall()
            )


class _PartialAnalysis:
    def __init__(self, *, total=10, completed=8, failed=2):
        self.calls = []
        self.total, self.completed, self.failed = total, completed, failed

    async def workflow_admit(self, **kwargs):
        self.calls.append(kwargs)
        counts = type(
            "Counts",
            (),
            {
                "total": self.total,
                "completed": self.completed,
                "input_incomplete": 0,
                "unsupported": 0,
                "failed": self.failed,
                "cancelled": 0,
                "interrupted": 0,
            },
        )()
        usage = type(
            "Usage", (), {"attempted_requests": self.total, "total_tokens": 1200}
        )()
        return type(
            "Job",
            (),
            {
                "id": 200 + len(self.calls),
                "status": "completed",
                "counts": counts,
                "usage": usage,
            },
        )()

    async def read(self, job_id):
        raise AssertionError(f"terminal fake job {job_id} must not be polled")


class _QueuedAnalysisAdmission:
    """Return an admission envelope whose nested job settles on the first read."""

    job_id = 201

    def __init__(self):
        self.calls = []
        self.read_calls = []

    @staticmethod
    def _job(*, status, queued, completed):
        now = datetime.now(UTC)
        counts = AnalysisCounts(
            total=1,
            queued=queued,
            acquiring=0,
            analysing=0,
            completed=completed,
            input_incomplete=0,
            unsupported=0,
            failed=0,
            cancelled=0,
            interrupted=0,
            reused=0,
        )
        usage = AnalysisUsage(
            attempted_requests=0,
            accounted_requests=0,
            complete=True,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
        return AnalysisJob(
            id=_QueuedAnalysisAdmission.job_id,
            request_id=None,
            trigger="automatic",
            status=status,
            configuration_revision=1,
            base_url="https://example.test",
            model="test-model",
            initial_prompt=PromptVersion(
                id=1,
                stage="initial",
                instructions="test initial prompt",
                content_hash="0" * 64,
                schema_version="initial-understanding-v1",
                created_at=now,
            ),
            report_prompt=PromptVersion(
                id=2,
                stage="report",
                instructions="test report prompt",
                content_hash="1" * 64,
                schema_version="topic-report-v1",
                created_at=now,
            ),
            force_refresh=False,
            counts=counts,
            usage=usage,
            queue_reason=None,
            completion_event_id=1 if status == "completed" else None,
            created_at=now,
            started_at=now if status == "completed" else None,
            finished_at=now if status == "completed" else None,
        )

    async def workflow_admit(self, **kwargs):
        self.calls.append(kwargs)
        return AnalysisAdmission(
            job=self._job(status="queued", queued=1, completed=0),
            admitted_count=1,
            already_active_count=0,
        )

    async def read(self, job_id):
        self.read_calls.append(job_id)
        return self._job(status="completed", queued=0, completed=1)


class _ReportSequence:
    def __init__(self, statuses, *, total=10, ready=8, unavailable=2):
        self.statuses = iter(statuses)
        self.calls = []
        self.total, self.ready, self.unavailable = total, ready, unavailable

    async def workflow_admit(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["analysis_job_id"] is None:
            coverage = type(
                "Coverage",
                (),
                {
                    "total": 0,
                    "unavailable": 0,
                    "relevant": 0,
                    "irrelevant": 0,
                    "uncertain": 0,
                    "failed": 0,
                    "cancelled": 0,
                    "interrupted": 0,
                },
            )()
            total_usage = type(
                "Usage", (), {"attempted_requests": 0, "total_tokens": 0}
            )()
            return type(
                "Report",
                (),
                {
                    "id": 300 + len(self.calls),
                    "status": "empty",
                    "coverage": coverage,
                    "usage": type("ReportUsage", (), {"total": total_usage})(),
                },
            )()
        status = next(self.statuses)
        coverage = type(
            "Coverage",
            (),
            {
                "total": self.total,
                "unavailable": self.unavailable,
                "relevant": self.ready,
                "irrelevant": 0,
                "uncertain": 0,
                "failed": 0,
                "cancelled": 0,
                "interrupted": 0,
            },
        )()
        total_usage = type(
            "Usage", (), {"attempted_requests": self.ready, "total_tokens": 2400}
        )()
        usage = type("ReportUsage", (), {"total": total_usage})()
        return type(
            "Report",
            (),
            {
                "id": 300 + len(self.calls),
                "status": status,
                "coverage": coverage,
                "usage": usage,
            },
        )()

    async def read(self, report_id):
        raise AssertionError(f"terminal fake report {report_id} must not be polled")


class _BlockingBatch:
    def __init__(self):
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()
        self.calls = []

    async def start_workflow_batch(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        await self.gate.wait()
        return type("Batch", (), {"id": 901, "status": "completed"})()


class _RecoveryBatch:
    def __init__(self, status):
        self.status = status
        self.calls = []

    async def start_workflow_batch(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("recovery must not admit a second collection child")

    async def get_batch(self, batch_id):
        return type("Batch", (), {"id": batch_id, "status": self.status})()


def test_no_new_workflow_runs_fixed_stages_without_model_calls(tmp_path: Path):
    asyncio.run(_test_no_new_workflow_runs_fixed_stages_without_model_calls(tmp_path))


async def _test_no_new_workflow_runs_fixed_stages_without_model_calls(tmp_path: Path):
    database, rules, repository = _repository(tmp_path)
    batches, analyses, reports = _FakeBatch(["completed"]), _NoModel(), _NoReport()
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    run = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    await asyncio.sleep(0.15)
    final = service.get_run(run.id)
    assert final.status == "completed"
    assert final.outcome == "no_new_sources"
    assert [stage.status for stage in final.stages] == ["completed"] * 3
    assert analyses.calls == []
    assert len(reports.calls) == 1
    assert reports.calls[0]["analysis_job_id"] is None
    await service.shutdown()


def test_run_admission_rolls_back_when_request_proof_cannot_persist(tmp_path: Path):
    asyncio.run(
        _test_run_admission_rolls_back_when_request_proof_cannot_persist(tmp_path)
    )


async def _test_run_admission_rolls_back_when_request_proof_cannot_persist(
    tmp_path: Path,
):
    database, rules, repository = _repository(tmp_path)
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=_FakeBatch(["completed"]),
        analyses=_NoModel(),
        reports=_NoReport(),
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    with database.connect() as connection:
        connection.execute(
            """CREATE TRIGGER fail_automation_request BEFORE INSERT
               ON automation_requests
               BEGIN SELECT RAISE(ABORT,'synthetic request failure'); END"""
        )
    with pytest.raises(AutomationWorkflowError) as raised:
        await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    assert raised.value.code == "automation_storage_unavailable"
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM automation_requests").fetchone()[0]
            == 0
        )
    await service.shutdown()


@pytest.mark.parametrize(
    ("child_status", "expected_status"),
    [("completed", "completed"), ("paused_for_manual_action", "interrupted")],
)
def test_startup_trusts_only_settled_linked_child(
    tmp_path: Path, child_status: str, expected_status: str
):
    asyncio.run(
        _test_startup_trusts_only_settled_linked_child(
            tmp_path, child_status, expected_status
        )
    )


async def _test_startup_trusts_only_settled_linked_child(
    tmp_path: Path, child_status: str, expected_status: str
):
    database, rules, repository = _repository(tmp_path)
    now = datetime(2026, 8, 30, 0, 0, tzinfo=UTC)
    task = repository.create_task(_task_payload(), now=now)
    run, _ = repository.create_run(
        task_id=task.id,
        trigger="scheduled",
        admission_key=f"scheduled:{child_status}",
        request_id=None,
        snapshot=_snapshot(task, now),
        now=now,
    )
    repository.start_stage(run.id, "collection")
    repository.set_stage_child(
        run.id, "collection", child_kind="search_batch", child_id=901
    )
    batches = _RecoveryBatch(child_status)
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=_NoModel(),
        reports=_NoReport(),
        repository=repository,
        clock=lambda: now,
    )
    service.initialize()
    await service.start()
    await asyncio.sleep(0.15)
    recovered = service.get_run(run.id)
    assert recovered.status == expected_status
    if expected_status == "completed":
        assert recovered.outcome == "no_new_sources"
        assert recovered.stages[0].child_id == 901
    else:
        assert recovered.error.code == "backend_restart"
    assert batches.calls == []
    await service.shutdown()


def test_collection_failure_retry_appends_downstream_attempts(tmp_path: Path):
    asyncio.run(_test_collection_failure_retry_appends_downstream_attempts(tmp_path))


async def _test_collection_failure_retry_appends_downstream_attempts(tmp_path: Path):
    database, rules, repository = _repository(tmp_path)
    batches, analyses, reports = (
        _FakeBatch(["internal_error", "completed"]),
        _NoModel(),
        _NoReport(),
    )
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    first = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    await asyncio.sleep(0.1)
    failed = service.get_run(first.id)
    assert failed.status == "failed"
    retry = await service.retry_run(
        first.id,
        AutomationRunRetry(
            request_id="123e4567-e89b-42d3-a456-426614174001",
            expected_revision=failed.revision,
        ),
    )
    await asyncio.sleep(0.15)
    final = service.get_run(retry.id)
    assert final.status == "completed"
    assert len(batches.calls) == 2
    assert [stage.status for stage in final.stages] == ["completed"] * 3
    await service.shutdown()


def test_partial_analysis_coverage_is_visible_and_report_still_completes(
    tmp_path: Path,
):
    asyncio.run(_test_partial_analysis_coverage(tmp_path))


async def _test_partial_analysis_coverage(tmp_path: Path):
    from summary_fixtures import seed_run

    database, rules, _ = _repository(tmp_path)
    seed_run(database, 10)
    repository = _ContentRepository(database)
    batches = _FakeBatch(["completed"])
    analyses = _PartialAnalysis()
    reports = _ReportSequence(["completed"])
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    run = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    await asyncio.sleep(0.2)
    final = service.get_run(run.id)
    analysis = final.stages[1]
    report = final.stages[2]
    assert final.status == "completed" and final.outcome == "completed"
    assert (analysis.input_count, analysis.success_count, analysis.failure_count) == (
        10,
        8,
        2,
    )
    assert (report.input_count, report.success_count, report.failure_count) == (
        10,
        8,
        2,
    )
    assert analysis.usage_attempted == 10 and analysis.usage_tokens == 1200
    await service.shutdown()


def test_analysis_admission_waits_for_nested_job_to_settle(tmp_path: Path):
    asyncio.run(_test_analysis_admission_waits_for_nested_job_to_settle(tmp_path))


async def _test_analysis_admission_waits_for_nested_job_to_settle(tmp_path: Path):
    from summary_fixtures import seed_run

    database, rules, _ = _repository(tmp_path)
    seed_run(database, 1)
    repository = _ContentRepository(database)
    batches = _FakeBatch(["completed"])
    analyses = _QueuedAnalysisAdmission()
    reports = _ReportSequence(["completed"], total=1, ready=1, unavailable=0)
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    run = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    workflow_task = service._run_tasks[run.id]
    await asyncio.wait_for(asyncio.shield(workflow_task), 1)

    final = service.get_run(run.id)
    analysis = final.stages[1]
    assert final.status == "completed"
    assert analysis.status == "completed"
    assert (analysis.child_id, analysis.input_count, analysis.success_count) == (
        analyses.job_id,
        1,
        1,
    )
    assert analyses.read_calls == [analyses.job_id]
    assert reports.calls[0]["analysis_job_id"] == analyses.job_id
    await service.shutdown()


def test_report_retry_reuses_collection_and_initial_analysis(tmp_path: Path):
    asyncio.run(_test_report_retry_reuses_collection_and_initial_analysis(tmp_path))


async def _test_report_retry_reuses_collection_and_initial_analysis(tmp_path: Path):
    from summary_fixtures import seed_run

    database, rules, _ = _repository(tmp_path)
    seed_run(database, 1)
    batches = _FakeBatch(["completed"])
    analyses = _PartialAnalysis(total=1, completed=1, failed=0)
    reports = _ReportSequence(["failed", "completed"], total=1, ready=1, unavailable=0)
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=_ContentRepository(database),
    )
    service.initialize()
    task = service.create_task(_task_payload())
    admitted = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    await asyncio.sleep(0.15)
    failed = service.get_run(admitted.id)
    assert failed.status == "failed" and failed.stages[2].status == "failed"
    with database.connect() as connection:
        connection.execute(
            """CREATE TRIGGER fail_retry_request BEFORE INSERT
               ON automation_requests WHEN NEW.action='retry'
               BEGIN SELECT RAISE(ABORT,'synthetic retry request failure'); END"""
        )
    with pytest.raises(AutomationWorkflowError) as raised:
        await service.retry_run(
            failed.id,
            AutomationRunRetry(
                request_id="123e4567-e89b-42d3-a456-426614174009",
                expected_revision=failed.revision,
            ),
        )
    assert raised.value.code == "automation_storage_unavailable"
    unchanged = service.get_run(failed.id)
    assert unchanged.revision == failed.revision
    assert unchanged.attempts == failed.attempts
    with database.connect() as connection:
        connection.execute("DROP TRIGGER fail_retry_request")
    await service.retry_run(
        failed.id,
        AutomationRunRetry(
            request_id="123e4567-e89b-42d3-a456-426614174002",
            expected_revision=failed.revision,
        ),
    )
    await asyncio.sleep(0.15)
    final = service.get_run(failed.id)
    assert final.status == "completed" and final.stages[2].attempt_number == 2
    assert len(batches.calls) == len(analyses.calls) == 1
    assert len(reports.calls) == 2
    await service.shutdown()


def test_new_content_membership_is_per_task_not_global(tmp_path: Path):
    asyncio.run(_test_new_content_membership_is_per_task_not_global(tmp_path))


async def _test_new_content_membership_is_per_task_not_global(tmp_path: Path):
    from summary_fixtures import seed_run

    database, rules, _ = _repository(tmp_path)
    seed_run(database, 1)
    repository = _ContentRepository(database)
    batches = _FakeBatch(["completed", "completed", "completed"])
    analyses = _PartialAnalysis(total=1, completed=1, failed=0)
    reports = _ReportSequence(
        ["completed", "completed"], total=1, ready=1, unavailable=0
    )
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    first_task = service.create_task(_task_payload(name="任务 A"))
    second_task = service.create_task(_task_payload(name="任务 B"))
    request_ids = (
        REQUEST,
        "123e4567-e89b-42d3-a456-426614174005",
        "123e4567-e89b-42d3-a456-426614174006",
    )
    first = await service.run_now(
        first_task.id, AutomationRunNow(request_id=request_ids[0])
    )
    await asyncio.sleep(0.15)
    second = await service.run_now(
        second_task.id, AutomationRunNow(request_id=request_ids[1])
    )
    await asyncio.sleep(0.15)
    repeated = await service.run_now(
        first_task.id, AutomationRunNow(request_id=request_ids[2])
    )
    await asyncio.sleep(0.15)

    assert service.get_run(first.id).outcome == "completed"
    assert service.get_run(second.id).outcome == "completed"
    assert service.get_run(repeated.id).outcome == "no_new_sources"
    assert len(repository.task_contents(first_task.id)) == 1
    assert len(repository.task_contents(second_task.id)) == 1
    assert len(analyses.calls) == 2
    assert [call["analysis_job_id"] is None for call in reports.calls] == [
        False,
        False,
        True,
    ]
    await service.shutdown()


def test_same_task_overlap_conflicts_and_cancel_fences_downstream(tmp_path: Path):
    asyncio.run(_test_same_task_overlap_and_cancel(tmp_path))


async def _test_same_task_overlap_and_cancel(tmp_path: Path):
    database, rules, repository = _repository(tmp_path)
    batches = _BlockingBatch()
    analyses, reports = _NoModel(), _NoReport()
    service = AutomationWorkflowService(
        database,
        monitoring_rules=rules,
        batches=batches,
        analyses=analyses,
        reports=reports,
        repository=repository,
    )
    service.initialize()
    task = service.create_task(_task_payload())
    run = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
    await asyncio.wait_for(batches.entered.wait(), 1)
    with pytest.raises(AutomationWorkflowError, match="automation_run_active"):
        await service.run_now(
            task.id,
            AutomationRunNow(request_id="123e4567-e89b-42d3-a456-426614174003"),
        )
    active = service.get_run(run.id)
    cancelled = await service.cancel_run(
        run.id,
        AutomationRunCancel(
            request_id="123e4567-e89b-42d3-a456-426614174004",
            expected_revision=active.revision,
        ),
    )
    assert cancelled.status == "cancelled" and cancelled.outcome == "cancelled"
    assert all(stage.status == "cancelled" for stage in cancelled.stages)
    assert analyses.calls == reports.calls == []
    await service.shutdown()


def test_http_contract_replaces_old_schedule_route_and_replays_run_now(tmp_path: Path):
    database = Database(tmp_path / "automation-api.sqlite3")

    def rules_factory():
        return MonitoringRuleService(database_path=database.path)

    def workflow_factory(owner: Database):
        rules = MonitoringRuleService(database_path=owner.path)
        rules.initialize()
        return AutomationWorkflowService(
            owner,
            monitoring_rules=rules,
            batches=_FakeBatch(["completed"]),
            analyses=_NoModel(),
            reports=_NoReport(),
        )

    app = create_app(
        monitoring_rule_service_factory=rules_factory,
        automation_workflow_service_factory=workflow_factory,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/collection-schedules").status_code == 404
        created = client.post(
            "/api/v1/automation-tasks",
            json=_task_payload().model_dump(mode="json"),
        )
        assert created.status_code == 201, created.text
        task = created.json()
        assert task["enabled"] is False and task["next_due_at"] is None
        assert client.get("/api/v1/automation-tasks").json()["tasks"] == [task]

        invalid = client.post(
            "/api/v1/automation-tasks",
            json={**_task_payload().model_dump(mode="json"), "unknown": True},
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"
        assert invalid.json()["detail"]["code"] == "invalid_request"

        response = client.post(
            f"/api/v1/automation-tasks/{task['id']}/run-now",
            json={"request_id": REQUEST},
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        client.portal.call(asyncio.sleep, 0.2)
        finished = client.get(f"/api/v1/automation-runs/{run_id}").json()
        assert finished["status"] == "completed"
        assert finished["outcome"] == "no_new_sources"
        replay = client.post(
            f"/api/v1/automation-tasks/{task['id']}/run-now",
            json={"request_id": REQUEST},
        )
        assert replay.status_code == 202 and replay.json() == finished
