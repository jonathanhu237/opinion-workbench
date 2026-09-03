"""Regression coverage for explicit two-stage prompt choices and snapshots."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from longtian_api import database as database_migrations
from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.repositories.analysis_settings import (
    prompt_snapshot,
    resolve_prompt_choice,
)
from longtian_api.repositories.automation_workflows import (
    AutomationWorkflowRepository,
)
from longtian_api.repositories.topic_reports import TopicReportRepository
from longtian_api.schemas.analysis_settings import (
    DEFAULT_INITIAL_INSTRUCTIONS,
    DEFAULT_REPORT_INSTRUCTIONS,
    PromptChoiceCustom,
    PromptSnapshot,
)
from longtian_api.schemas.automation_workflows import (
    AutomationSnapshot,
    AutomationTaskCreate,
)
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.monitoring_rules import MonitoringRuleService


def test_prompt_choices_reject_blank_unsafe_or_oversized_custom_text():
    for instructions in ("", " \n\t", "\x00保留证据", "x" * 8001, "\ud800"):
        with pytest.raises(ValidationError):
            PromptChoiceCustom(mode="custom", instructions=instructions)


def test_prompt_snapshots_validate_their_own_content_hash():
    instructions = "保留每条来源的时间和地点线索。"
    digest = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
    snapshot = PromptSnapshot(
        mode="custom",
        version_id=1,
        instructions=instructions,
        content_hash=digest,
        schema_version="topic-report-v1",
    )
    assert snapshot.content_hash == digest
    with pytest.raises(ValidationError):
        PromptSnapshot(
            mode="custom",
            version_id=1,
            instructions=instructions,
            content_hash="0" * 64,
            schema_version="topic-report-v1",
        )


def test_prompt_choice_resolution_reuses_versions_but_preserves_custom_mode(
    tmp_path: Path,
):
    database = Database(tmp_path / "prompts.sqlite3")
    database.initialize()
    with database.connect() as connection:
        default = resolve_prompt_choice(connection, "report", {"mode": "default"})
        custom_equal_default = resolve_prompt_choice(
            connection,
            "report",
            {"mode": "custom", "instructions": DEFAULT_REPORT_INSTRUCTIONS},
        )
        custom_repeat = resolve_prompt_choice(
            connection,
            "report",
            {"mode": "custom", "instructions": DEFAULT_REPORT_INSTRUCTIONS},
        )

    assert default.mode == "default"
    assert custom_equal_default.mode == "custom"
    assert custom_equal_default.version_id == default.version_id
    assert custom_repeat.version_id == custom_equal_default.version_id


def test_prompt_choice_resolution_rejects_ambiguous_mapping(tmp_path: Path):
    database = Database(tmp_path / "strict-prompts.sqlite3")
    database.initialize()
    with database.connect() as connection:
        with pytest.raises(AnalysisError, match="invalid_analysis_prompt"):
            resolve_prompt_choice(
                connection,
                "initial",
                {"mode": "default", "instructions": "must be rejected"},
            )


def test_prompt_choice_resolution_fails_closed_on_default_hash_collision(
    tmp_path: Path,
):
    database = Database(tmp_path / "default-collision.sqlite3")
    database.initialize()
    with database.connect() as connection:
        default = connection.execute(
            "SELECT content_hash FROM analysis_prompt_versions "
            "WHERE stage='report' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO analysis_prompt_versions(
              stage,instructions,content_hash,schema_version,created_at)
              VALUES ('report',?,?,?,?)""",
            (
                "故意冲突的报告模板",
                default,
                "topic-report-v1",
                "2026-08-30T00:00:00+00:00",
            ),
        )
        with pytest.raises(AnalysisError, match="analysis_storage_unavailable"):
            resolve_prompt_choice(connection, "report", {"mode": "default"})
        canonical_id = connection.execute(
            "SELECT id FROM analysis_prompt_versions "
            "WHERE stage='report' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        with pytest.raises(AnalysisError, match="analysis_storage_unavailable"):
            prompt_snapshot(connection, "report", canonical_id, mode="default")


def test_automation_task_persists_both_prompt_choices(tmp_path: Path):
    database = Database(tmp_path / "automation-prompts.sqlite3")
    MonitoringRuleService(database_path=database.path).initialize()
    repository = AutomationWorkflowRepository(database)
    task = repository.create_task(
        AutomationTaskCreate.model_validate(
            {
                "name": "双阶段提示词任务",
                "monitoring_rule_id": 1,
                "platforms": ["toutiao"],
                "max_results_per_term": 10,
                "initial_prompt": {
                    "mode": "custom",
                    "instructions": "先完整理解来源，不要提前判断相关性。",
                },
                "report_prompt": {"mode": "default"},
                "schedule": {"kind": "interval", "interval_minutes": 30},
            }
        ),
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )

    assert task.initial_prompt is not None
    assert task.initial_prompt.mode == "custom"
    assert task.report_prompt is not None
    assert task.report_prompt.mode == "default"
    with database.connect() as connection:
        row = connection.execute(
            """SELECT initial_prompt_mode,initial_prompt_version_id,
                      report_prompt_mode,report_prompt_version_id
               FROM automation_tasks WHERE id=?""",
            (task.id,),
        ).fetchone()
    assert tuple(row) == (
        "custom",
        task.initial_prompt.version_id,
        "default",
        task.report_prompt.version_id,
    )


def test_pre_v18_run_snapshot_is_adapted_without_rewriting_history(tmp_path: Path):
    database = Database(tmp_path / "legacy-run.sqlite3")
    MonitoringRuleService(database_path=database.path).initialize()
    repository = AutomationWorkflowRepository(database)
    task = repository.create_task(
        AutomationTaskCreate.model_validate(
            {
                "name": "历史运行任务",
                "monitoring_rule_id": 1,
                "platforms": ["toutiao"],
                "analysis_goal": "历史任务报告目标",
                "initial_prompt": {"mode": "default"},
                "report_prompt": {
                    "mode": "custom",
                    "instructions": "历史任务报告目标",
                },
                "schedule": {"kind": "interval", "interval_minutes": 30},
            }
        ),
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert task.initial_prompt is not None and task.report_prompt is not None
    old_snapshot = AutomationSnapshot(
        task_id=task.id,
        task_revision=task.revision,
        task_name=task.name,
        monitoring_rule_id=task.monitoring_rule_id,
        rule_name=task.rule_name,
        terms=["历史"],
        platforms=list(task.platforms),
        max_results_per_term=task.max_results_per_term,
        analysis_goal="历史任务报告目标",
        analysis_goal_hash=hashlib.sha256("历史任务报告目标".encode()).hexdigest(),
        initial_prompt_version_id=task.initial_prompt.version_id,
        report_prompt_version_id=task.report_prompt.version_id,
        initial_template_version="initial-understanding-v1",
        report_template_version="topic-report-v1",
        admitted_at="2026-08-30T00:00:00+00:00",
    )
    invalid_snapshot = old_snapshot.model_dump(mode="json")
    invalid_snapshot["initial_prompt"] = {
        "mode": "default",
        "version_id": task.initial_prompt.version_id,
        "instructions": task.initial_prompt.instructions,
        "content_hash": task.initial_prompt.content_hash,
        "schema_version": "topic-report-v1",
    }
    with pytest.raises(ValidationError):
        AutomationSnapshot.model_validate(invalid_snapshot)
    run, _ = repository.create_run(
        task_id=task.id,
        trigger="manual",
        admission_key="manual:legacy-run",
        request_id=None,
        snapshot=old_snapshot,
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )

    # Simulate the pre-v18 JSON shape in a temporary database.  The immutable
    # trigger is intentionally removed only in this test so the historical
    # row can be represented without modifying production migration behavior.
    old_json = old_snapshot.model_dump(mode="json")
    old_json.pop("initial_prompt", None)
    old_json.pop("report_prompt", None)
    serialized = json.dumps(old_json, ensure_ascii=False, separators=(",", ":"))
    with database.connect() as connection:
        connection.execute("DROP TRIGGER automation_run_snapshot_immutable")
        connection.execute(
            "UPDATE automation_runs SET snapshot_json=? WHERE id=?",
            (serialized, run.id),
        )

    adapted = repository.get_run(run.id)
    assert adapted.snapshot.initial_prompt is not None
    assert adapted.snapshot.initial_prompt.mode == "legacy"
    assert (
        adapted.snapshot.initial_prompt.instructions
        == task.initial_prompt.instructions
    )
    assert adapted.snapshot.report_prompt is not None
    assert adapted.snapshot.report_prompt.mode == "legacy"
    assert adapted.snapshot.report_prompt.instructions == "历史任务报告目标"
    with database.connect() as connection:
        assert connection.execute(
            "SELECT snapshot_json FROM automation_runs WHERE id=?", (run.id,)
        ).fetchone()[0] == serialized


def test_pre_v18_report_prompt_is_adapted_without_rewriting_history(tmp_path: Path):
    database = Database(tmp_path / "legacy-report.sqlite3")
    database.initialize()
    request_id = "123e4567-e89b-42d3-a456-426614174000"
    with database.connect() as connection:
        report_id = connection.execute(
            """INSERT INTO topic_report_runs(
              request_id,trigger,selection_json,prompt_json,configuration_revision,
              base_url,model,status,created_at)
              VALUES (?,'interval',?,'{"instructions":"历史报告提示词"}',1,
                'https://example.com/v1','historical-model','queued',?)""",
            (
                request_id,
                json.dumps(
                    {
                        "kind": "first_seen_interval",
                        "first_seen_from": "2026-08-30T00:00:00+00:00",
                        "first_seen_to": "2026-08-31T00:00:00+00:00",
                    },
                    separators=(",", ":"),
                ),
                "2026-08-30T00:00:00+00:00",
            ),
        ).lastrowid

    report = TopicReportRepository(database).read(report_id)
    assert report.prompt.mode == "legacy"
    assert report.prompt.origin == "legacy"
    assert report.prompt.version_id is None
    assert report.prompt.instructions == "历史报告提示词"
    with database.connect() as connection:
        assert connection.execute(
            "SELECT prompt_json FROM topic_report_runs WHERE id=?", (report_id,)
        ).fetchone()[0] == '{"instructions":"历史报告提示词"}'


def test_legacy_workflow_goal_preserves_report_version_reference(tmp_path: Path):
    database = Database(tmp_path / "legacy-workflow.sqlite3")
    database.initialize()
    with database.connect() as connection:
        initial = connection.execute(
            "SELECT id FROM analysis_prompt_versions "
            "WHERE stage='initial' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        report = connection.execute(
            "SELECT id FROM analysis_prompt_versions "
            "WHERE stage='report' ORDER BY id LIMIT 1"
        ).fetchone()[0]

    workflow_report = TopicReportRepository(database).create_workflow(
        run_id=1,
        analysis_job_id=None,
        operation_key="automation:legacy-version-reference",
        analysis_goal="历史任务报告目标",
        configuration_revision=1,
        base_url="https://example.com/v1",
        model="historical-model",
        initial_prompt_version_id=initial,
        report_prompt_version_id=report,
    )

    assert workflow_report.prompt.mode == "legacy"
    assert workflow_report.prompt.version_id == report
    assert workflow_report.prompt.instructions == "历史任务报告目标"


def test_workflow_preserves_custom_source_when_text_matches_default(tmp_path: Path):
    from initial_analysis_fixtures import environment, finish

    from longtian_api.repositories.analysis_settings import (
        AnalysisSettingsRepository,
    )

    async def run():
        database, _, service, ai, _, _, _ = environment(tmp_path, count=1)
        settings = AnalysisSettingsRepository(database).read()
        initial = PromptSnapshot(
            mode="custom",
            version_id=settings.initial_prompt.id,
            instructions=settings.initial_prompt.instructions,
            content_hash=settings.initial_prompt.content_hash,
            schema_version=settings.initial_prompt.schema_version,
        )
        report = PromptSnapshot(
            mode="custom",
            version_id=settings.report_prompt.id,
            instructions=settings.report_prompt.instructions,
            content_hash=settings.report_prompt.content_hash,
            schema_version=settings.report_prompt.schema_version,
        )
        admission = await service.workflow_admit(
            result_ids=[1],
            operation_key="automation:equal-custom:initial:1",
            snapshot=SimpleNamespace(
                ai_configuration_revision=1,
                initial_prompt_version_id=initial.version_id,
                report_prompt_version_id=report.version_id,
                initial_prompt=initial,
                report_prompt=report,
            ),
        )
        await finish(service)
        frozen = service.repository.read(admission.job.id)
        assert frozen.initial_prompt.mode == "custom"
        assert frozen.report_prompt.mode == "custom"
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_v18_backfills_legacy_automation_prompt_choices(tmp_path: Path):
    from test_topic_report_migrations import populated_v13

    database = populated_v13(tmp_path)
    with database.connect() as connection:
        database_migrations._migrate_to_version_14(connection)
        database_migrations._migrate_to_version_15(connection)
        database_migrations._migrate_to_version_16(connection)
        database_migrations._migrate_to_version_17(connection)
        connection.execute(
            """INSERT INTO automation_tasks(
              name,normalized_name,monitoring_rule_id,max_results_per_term,
              analysis_goal,schedule_kind,interval_minutes,enabled,revision,
              next_due_at,anchor_at,created_at,updated_at)
              VALUES ('迁移任务','迁移任务',1,10,'历史报告提示词',
                'interval',30,0,1,NULL,NULL,?,?)""",
            ("2026-08-30T00:00:00+00:00", "2026-08-30T00:00:00+00:00"),
        )
        connection.execute(
            """INSERT INTO automation_tasks(
              name,normalized_name,monitoring_rule_id,max_results_per_term,
              analysis_goal,schedule_kind,interval_minutes,enabled,revision,
              next_due_at,anchor_at,deleted_at,created_at,updated_at)
              VALUES ('已删除迁移任务','已删除迁移任务',1,10,'已删除任务的报告提示词',
                'interval',30,0,2,NULL,NULL,?,?,?)""",
            (
                "2026-08-30T00:00:00+00:00",
                "2026-08-30T00:00:00+00:00",
                "2026-08-30T00:00:00+00:00",
            ),
        )

    database.initialize()
    with database.connect() as connection:
        row = connection.execute(
            """SELECT initial_prompt_mode,initial_prompt_version_id,
                      report_prompt_mode,report_prompt_version_id
               FROM automation_tasks WHERE name='迁移任务'"""
        ).fetchone()
        deleted = connection.execute(
            """SELECT initial_prompt_mode,initial_prompt_version_id,
                      report_prompt_mode,report_prompt_version_id,deleted_at
               FROM automation_tasks WHERE name='已删除迁移任务'"""
        ).fetchone()
        settings = connection.execute(
            """SELECT initial_prompt_version_id,report_prompt_version_id
               FROM analysis_settings WHERE id=1"""
        ).fetchone()
        defaults = connection.execute(
            """SELECT stage,instructions FROM analysis_prompt_versions
               WHERE id IN (?,?) ORDER BY stage""",
            tuple(settings),
        ).fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == CURRENT_DATABASE_VERSION
    assert row[0] == "default" and row[2] == "custom"
    assert row[1] is not None and row[3] is not None
    assert deleted[0] == "default" and deleted[2] == "custom"
    assert deleted[1] is not None and deleted[3] is not None
    assert deleted[4] == "2026-08-30T00:00:00+00:00"
    assert [(item[0], item[1]) for item in defaults] == [
        ("initial", DEFAULT_INITIAL_INSTRUCTIONS),
        ("report", DEFAULT_REPORT_INSTRUCTIONS),
    ]


def test_v18_failure_rolls_back_prompt_columns_and_backfill(
    tmp_path: Path, monkeypatch
):
    from test_topic_report_migrations import populated_v13

    import longtian_api.migrations.automation_workflows_v18 as migration

    database = populated_v13(tmp_path)
    with database.connect() as connection:
        database_migrations._migrate_to_version_14(connection)
        database_migrations._migrate_to_version_15(connection)
        database_migrations._migrate_to_version_16(connection)
        database_migrations._migrate_to_version_17(connection)
        connection.execute(
            """INSERT INTO automation_tasks(
              name,normalized_name,monitoring_rule_id,max_results_per_term,
              analysis_goal,schedule_kind,interval_minutes,enabled,revision,
              next_due_at,anchor_at,created_at,updated_at)
              VALUES ('回滚任务','回滚任务',1,10,'迁移前报告提示词',
                'interval',30,0,1,NULL,NULL,?,?)""",
            ("2026-08-30T00:00:00+00:00", "2026-08-30T00:00:00+00:00"),
        )
        before_task = tuple(
            connection.execute(
                "SELECT name,analysis_goal,schedule_kind,revision FROM automation_tasks"
            ).fetchone()
        )
        before_settings = tuple(
            connection.execute(
                "SELECT initial_prompt_version_id,report_prompt_version_id "
                "FROM analysis_settings WHERE id=1"
            ).fetchone()
        )

    original = migration.migrate

    def fail(connection):
        original(connection)
        raise RuntimeError("synthetic v18 failure after prompt backfill")

    monkeypatch.setattr(migration, "migrate", fail)
    with pytest.raises(RuntimeError, match="v18 failure"):
        database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 17
        assert tuple(
            connection.execute(
                "SELECT name,analysis_goal,schedule_kind,revision FROM automation_tasks"
            ).fetchone()
        ) == before_task
        assert tuple(
            connection.execute(
                "SELECT initial_prompt_version_id,report_prompt_version_id "
                "FROM analysis_settings WHERE id=1"
            ).fetchone()
        ) == before_settings
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(automation_tasks)")
        }
        assert "initial_prompt_mode" not in columns
        assert "report_prompt_version_id" not in columns
