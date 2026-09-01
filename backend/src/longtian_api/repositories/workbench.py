"""One-transaction persistent read model for the homepage workbench."""

import json
from datetime import datetime

from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.search_batches import ACTIVE, _read_batch
from longtian_api.repositories.topic_reports import TopicReportRepository
from longtian_api.schemas.workbench import (
    WorkbenchActivity,
    WorkbenchAnalysisActivity,
    WorkbenchAttention,
    WorkbenchAutomationActivity,
    WorkbenchCollectionActivity,
    WorkbenchLatestReport,
    WorkbenchNextAutomation,
    WorkbenchReportActivity,
    WorkbenchSnapshot,
)
from longtian_api.services.monitoring_rules import (
    MonitoringRuleError,
    compose_monitoring_terms,
)
from longtian_api.services.search_runs import MAX_SEARCH_TERMS
from longtian_api.services.workbench_errors import WorkbenchError

_ACTIVE_ANALYSES = ("queued", "running")
_ACTIVE_REPORTS = ("queued", "judging", "composing")
_UNSUCCESSFUL_ANALYSES = (
    "input_incomplete",
    "unsupported",
    "failed",
    "cancelled",
    "interrupted",
)


class WorkbenchRepository:
    """Read all persistent homepage state from one SQLite snapshot."""

    def __init__(self, database, *, automation_available=True):
        self._database = database
        self._automation_available = automation_available
        self._analyses = ContentAnalysisRepository(database)
        self._reports = TopicReportRepository(database)

    def read(self, observed_at: str) -> WorkbenchSnapshot:
        connection = None
        try:
            connection = self._database.connect()
            connection.execute("BEGIN")
            attention = [
                *self._automation_attention(connection),
                *self._collection_attention(connection),
                *self._analysis_attention(connection),
                *self._report_attention(connection),
            ]
            attention.sort(
                key=lambda item: (
                    {"action_required": 0, "error": 1, "warning": 2}[item.severity],
                    -datetime.fromisoformat(item.occurred_at).timestamp(),
                    item.kind,
                    item.resource_id,
                )
            )
            snapshot = WorkbenchSnapshot(
                observed_at=observed_at,
                attention=attention[:100],
                activity=WorkbenchActivity(
                    automation=self._automation_activity(connection),
                    collection=self._collection_activity(connection),
                    initial_analysis=self._analysis_activity(connection),
                    report=self._report_activity(connection),
                ),
                next_automation=self._next_automation(connection, observed_at),
                latest_report=self._latest_report(connection),
            )
            connection.execute("COMMIT")
            return snapshot
        except WorkbenchError:
            raise
        except Exception:
            raise WorkbenchError("workbench_storage_unavailable") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()

    @staticmethod
    def _automation_attention(connection) -> list[WorkbenchAttention]:
        rows = connection.execute(
            """SELECT t.*,r.name AS rule_name,r.enabled AS rule_enabled,
              o.status AS occurrence_status,
              o.reason AS occurrence_reason,o.created_at AS occurrence_created_at,
              o.missed_count AS occurrence_missed_count
              FROM automation_tasks t
              LEFT JOIN monitoring_rules r ON r.id=t.monitoring_rule_id
              LEFT JOIN automation_occurrences o ON o.id=(
                SELECT id FROM automation_occurrences
                WHERE task_id=t.id AND task_revision=t.revision
                ORDER BY id DESC LIMIT 1
              )
              WHERE t.deleted_at IS NULL AND t.enabled=1 ORDER BY t.id"""
        ).fetchall()
        items = []
        for row in rows:
            reason = status = occurred_at = None
            if row["monitoring_rule_id"] is None or row["rule_enabled"] is None:
                status, reason = "invalid", "monitoring_rule_not_found"
                occurred_at = row["updated_at"]
            elif not row["rule_enabled"]:
                status, reason = "invalid", "monitoring_rule_disabled"
                occurred_at = row["updated_at"]
            elif (
                rule_reason := WorkbenchRepository._schedule_rule_reason(
                    connection, row["monitoring_rule_id"]
                )
            ) is not None:
                status, reason = "invalid", rule_reason
                occurred_at = row["updated_at"]
            elif row["occurrence_status"] in ("skipped", "missed", "interrupted"):
                status = row["occurrence_status"]
                reason = row["occurrence_reason"]
                occurred_at = row["occurrence_created_at"]
            if status is None:
                continue
            severity = (
                "action_required"
                if status == "skipped"
                else "warning"
                if status == "missed"
                else "error"
            )
            items.append(
                WorkbenchAttention(
                    kind="automation_task",
                    severity=severity,
                    status=status,
                    reason=reason,
                    resource_id=row["id"],
                    owner=row["rule_name"],
                    occurred_at=occurred_at,
                    unsuccessful_count=row["occurrence_missed_count"]
                    if status == "missed"
                    else None,
                )
            )
        failed_runs = connection.execute(
            """WITH terminal AS (
              SELECT a.*,ROW_NUMBER() OVER (
                PARTITION BY a.task_id ORDER BY a.id DESC
              ) AS ordinal
              FROM automation_runs a
              WHERE a.status NOT IN ('queued','collecting','analysing','reporting')
            )
            SELECT a.*,t.name AS task_name FROM terminal a
            JOIN automation_tasks t ON t.id=a.task_id AND t.deleted_at IS NULL
            WHERE a.ordinal=1 AND a.status IN
              ('failed','interrupted','configuration_blocked')
            ORDER BY a.id"""
        ).fetchall()
        for row in failed_runs:
            items.append(
                WorkbenchAttention(
                    kind="automation_run",
                    severity="action_required"
                    if row["status"] == "configuration_blocked"
                    else "error",
                    status=row["status"],
                    reason={
                        "failed": "internal_error",
                        "interrupted": "interrupted",
                        "configuration_blocked": "configuration_blocked",
                    }[row["status"]],
                    resource_id=row["id"],
                    owner=row["task_name"],
                    occurred_at=row["finished_at"] or row["created_at"],
                    unsuccessful_count=None,
                )
            )
        return items

    @staticmethod
    def _schedule_rule_reason(connection, rule_id: int) -> str | None:
        objects = tuple(
            row[0]
            for row in connection.execute(
                """SELECT value FROM monitoring_rule_terms
                  WHERE rule_id=? ORDER BY position""",
                (rule_id,),
            ).fetchall()
        )
        issues = tuple(
            row[0]
            for row in connection.execute(
                """SELECT value FROM monitoring_rule_issue_terms
                  WHERE rule_id=? ORDER BY position""",
                (rule_id,),
            ).fetchall()
        )
        try:
            terms = compose_monitoring_terms(objects, issues)
        except MonitoringRuleError:
            return "invalid_monitoring_rule"
        return "too_many_search_terms" if len(terms) > MAX_SEARCH_TERMS else None

    @staticmethod
    def _collection_attention(connection) -> list[WorkbenchAttention]:
        # A currently running batch does not make the last failed terminal
        # batch healthy. Keep the latest terminal outcome visible until a
        # later successful terminal batch supersedes it, while exposing a
        # paused batch as its own current blocker.
        rows = connection.execute(
            """SELECT b.* FROM search_batches b
              JOIN monitoring_rules r ON r.id=b.monitoring_rule_id
              WHERE b.status='paused_for_manual_action'
              ORDER BY b.id"""
        ).fetchall()
        rows += connection.execute(
            """WITH terminal AS (
              SELECT b.*,ROW_NUMBER() OVER (
                PARTITION BY b.monitoring_rule_id ORDER BY b.id DESC
              ) AS ordinal
              FROM search_batches b
              JOIN monitoring_rules r ON r.id=b.monitoring_rule_id
              WHERE b.status NOT IN
                ('queued','running','paused_for_manual_action')
            )
            SELECT * FROM terminal WHERE ordinal=1 AND status IN
              ('completed_with_failures','internal_error')
            ORDER BY id"""
        ).fetchall()
        items = []
        for row in rows:
            status = row["status"]
            reason = (
                connection.execute(
                    """SELECT pause_reason FROM search_batch_items
                      WHERE batch_id=? AND position=?""",
                    (row["id"], row["current_item_position"]),
                ).fetchone()
                if status == "paused_for_manual_action"
                else None
            )
            failed_count = connection.execute(
                """SELECT COUNT(*) FROM search_batch_items
                  WHERE batch_id=? AND status='failed'""",
                (row["id"],),
            ).fetchone()[0]
            items.append(
                WorkbenchAttention(
                    kind="collection_batch",
                    severity={
                        "paused_for_manual_action": "action_required",
                        "completed_with_failures": "warning",
                        "internal_error": "error",
                    }[status],
                    status=status,
                    reason=(
                        reason[0]
                        if reason is not None and reason[0] is not None
                        else "unsuccessful_members"
                        if status == "completed_with_failures"
                        else "internal_error"
                    ),
                    resource_id=row["id"],
                    owner=row["rule_name"],
                    occurred_at=row["finished_at"] or row["created_at"],
                    unsuccessful_count=failed_count
                    if status == "completed_with_failures"
                    else None,
                )
            )
        return items

    def _analysis_attention(self, connection) -> list[WorkbenchAttention]:
        row = connection.execute(
            """SELECT id,status,created_at,finished_at FROM content_analysis_jobs
              WHERE status NOT IN ('queued','running') ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None or row["status"] == "cancelled":
            return []
        job = self._analyses._read(connection, row["id"])
        unsuccessful = sum(
            getattr(job.counts, status) for status in _UNSUCCESSFUL_ANALYSES
        )
        if job.status == "completed" and unsuccessful == 0:
            return []
        if job.status not in ("configuration_blocked", "interrupted", "completed"):
            return []
        status = "unsuccessful_members" if job.status == "completed" else job.status
        return [
            WorkbenchAttention(
                kind="initial_analysis",
                severity="warning"
                if status == "unsuccessful_members"
                else "action_required"
                if status == "configuration_blocked"
                else "error",
                status=status,
                reason=status,
                resource_id=job.id,
                owner="初步分析",
                occurred_at=job.finished_at.isoformat()
                if job.finished_at is not None
                else job.created_at.isoformat(),
                unsuccessful_count=unsuccessful
                if status == "unsuccessful_members"
                else None,
            )
        ]

    @staticmethod
    def _report_attention(connection) -> list[WorkbenchAttention]:
        row = connection.execute(
            """SELECT id,status,created_at,finished_at FROM topic_report_runs
              WHERE status NOT IN ('queued','judging','composing')
              ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None or row["status"] not in (
            "failed",
            "interrupted",
            "configuration_blocked",
        ):
            return []
        status = row["status"]
        return [
            WorkbenchAttention(
                kind="report",
                severity="action_required"
                if status == "configuration_blocked"
                else "error",
                status=status,
                reason={
                    "failed": "internal_error",
                    "interrupted": "interrupted",
                    "configuration_blocked": "configuration_blocked",
                }[status],
                resource_id=row["id"],
                owner="舆情报告",
                occurred_at=row["finished_at"] or row["created_at"],
                unsuccessful_count=None,
            )
        ]

    @staticmethod
    def _automation_activity(connection) -> WorkbenchAutomationActivity | None:
        row = connection.execute(
            """SELECT a.* FROM automation_runs a
              JOIN automation_tasks t ON t.id=a.task_id AND t.deleted_at IS NULL
              WHERE a.status IN
              ('queued','collecting','analysing','reporting')
              ORDER BY a.id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["snapshot_json"])
        return WorkbenchAutomationActivity(
            run_id=row["id"],
            task_id=row["task_id"],
            task_name=snapshot["task_name"],
            status=row["status"],
            active_stage=row["active_stage"],
            created_at=row["created_at"],
            started_at=row["started_at"],
        )

    @staticmethod
    def _collection_activity(connection) -> WorkbenchCollectionActivity | None:
        row = connection.execute(
            """SELECT id FROM search_batches WHERE status IN
              ('queued','running','paused_for_manual_action')
              ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        batch = _read_batch(connection, row["id"])
        current = (
            batch.items[batch.current_item_position]
            if batch.current_item_position is not None
            else None
        )
        completed = sum(item.status not in ACTIVE for item in batch.items)
        return WorkbenchCollectionActivity(
            id=batch.id,
            status=batch.status,
            rule_name=batch.rule_name,
            current_platform=current.platform if current is not None else None,
            current_item_position=batch.current_item_position,
            completed_item_count=completed,
            item_count=len(batch.items),
            created_at=batch.created_at,
            started_at=batch.started_at,
        )

    def _analysis_activity(self, connection) -> WorkbenchAnalysisActivity | None:
        row = connection.execute(
            """SELECT id FROM content_analysis_jobs
              WHERE status IN ('queued','running') ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        job = self._analyses._read(connection, row["id"])
        return WorkbenchAnalysisActivity(
            id=job.id,
            status=job.status,
            total_count=job.counts.total,
            completed_count=job.counts.completed,
            unsuccessful_count=sum(
                getattr(job.counts, status) for status in _UNSUCCESSFUL_ANALYSES
            ),
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat()
            if job.started_at is not None
            else None,
        )

    def _report_activity(self, connection) -> WorkbenchReportActivity | None:
        row = connection.execute(
            """SELECT id FROM topic_report_runs WHERE status IN
              ('queued','judging','composing') ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        report = self._reports._read(connection, row["id"])
        return WorkbenchReportActivity(
            id=report.id,
            status=report.status,
            total_count=report.coverage.ready,
            completed_count=(
                report.coverage.relevant
                + report.coverage.irrelevant
                + report.coverage.uncertain
            ),
            failed_count=(
                report.coverage.failed
                + report.coverage.cancelled
                + report.coverage.interrupted
            ),
            created_at=report.created_at,
            started_at=report.started_at,
        )

    def _next_automation(
        self, connection, observed_at
    ) -> WorkbenchNextAutomation | None:
        if not self._automation_available:
            return None
        rows = connection.execute(
            """SELECT t.id,t.name,t.monitoring_rule_id,r.name AS rule_name,
              t.next_due_at,t.schedule_kind,t.interval_minutes,
              t.daily_time,t.timezone
              FROM automation_tasks t JOIN monitoring_rules r
                ON r.id=t.monitoring_rule_id AND r.enabled=1
              WHERE t.deleted_at IS NULL AND t.enabled=1 AND t.next_due_at>=?
              ORDER BY t.next_due_at,t.id""",
            (observed_at,),
        ).fetchall()
        for row in rows:
            if (
                WorkbenchRepository._schedule_rule_reason(
                    connection, row["monitoring_rule_id"]
                )
                is not None
            ):
                continue
            schedule = (
                {
                    "kind": "interval",
                    "interval_minutes": row["interval_minutes"],
                }
                if row["schedule_kind"] == "interval"
                else {
                    "kind": "daily",
                    "daily_time": row["daily_time"],
                    "timezone": row["timezone"],
                }
            )
            return WorkbenchNextAutomation(
                id=row["id"],
                name=row["name"],
                rule_name=row["rule_name"],
                due_at=row["next_due_at"],
                schedule=schedule,
            )
        return None

    def _latest_report(self, connection) -> WorkbenchLatestReport | None:
        row = connection.execute(
            """SELECT id FROM topic_report_runs
              WHERE status IN ('completed','empty') ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        report = self._reports._read(connection, row["id"])
        overview = None
        if report.status == "completed":
            section = self._reports._section(
                connection,
                connection.execute(
                    "SELECT * FROM topic_report_nodes WHERE id=? AND report_id=?",
                    (report.root_section_id, report.id),
                ).fetchone(),
            )
            document = section.document or section.overview_document
            if document is None:
                raise ValueError("missing readable report document")
            overview = document.overview
        if report.finished_at is None:
            raise ValueError("missing terminal report timestamp")
        return WorkbenchLatestReport(
            id=report.id,
            status=report.status,
            created_at=report.created_at,
            finished_at=report.finished_at,
            overview=overview,
            empty_reason=report.empty_reason,
            coverage=report.coverage,
        )
