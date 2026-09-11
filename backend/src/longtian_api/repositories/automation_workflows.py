"""SQLite persistence for the fixed collection -> analysis -> report workflow.

The repository deliberately contains no browser, network or model calls.  A run
is an immutable intent plus append-only stage attempts; services are responsible
for deciding when a child executor may be admitted.
"""

# SQL projections are intentionally aligned with their table contracts.
# ruff: noqa: E501

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, cast
from zoneinfo import ZoneInfo

from longtian_api.database import Database
from longtian_api.repositories.analysis_settings import (
    prompt_snapshot,
    resolve_prompt_choice,
)
from longtian_api.repositories.monitoring_rules import _read_record
from longtian_api.schemas.analysis_settings import (
    REPORT_SCHEMA_VERSION,
    PromptSnapshot,
)
from longtian_api.schemas.automation_workflows import (
    AUTOMATION_STAGES,
    AutomationFailure,
    AutomationScheduleKind,
    AutomationSnapshot,
    AutomationStageName,
    AutomationStageStatus,
    AutomationTaskCreate,
    AutomationTaskReplace,
)
from longtian_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform

MAX_SAFE_INTEGER = 9_007_199_254_740_991
ACTIVE_RUN_STATUSES = {"queued", "collecting", "analysing", "reporting"}
TERMINAL_RUN_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "configuration_blocked",
}


class AutomationRepositoryError(Exception):
    """Base class for detail-free repository failures."""


class AutomationTaskNotFoundError(AutomationRepositoryError):
    pass


class AutomationRunNotFoundError(AutomationRepositoryError):
    pass


class AutomationTaskNameConflictError(AutomationRepositoryError):
    pass


class AutomationTaskChangedError(AutomationRepositoryError):
    pass


class AutomationRunActiveError(AutomationRepositoryError):
    pass


class AutomationRunChangedError(AutomationRepositoryError):
    pass


class AutomationRunNotRetryableError(AutomationRepositoryError):
    pass


class AutomationRunNotActiveError(AutomationRepositoryError):
    pass


class AutomationOccurrenceChangedError(AutomationRepositoryError):
    pass


class AutomationRequestConflictError(AutomationRepositoryError):
    pass


class AutomationRepositoryUnavailableError(AutomationRepositoryError):
    pass


@dataclass(frozen=True, slots=True)
class AutomationTaskRecord:
    id: int
    name: str
    monitoring_rule_id: int | None
    rule_name: str
    rule_state: Literal["enabled", "disabled", "deleted", "invalid"]
    platforms: tuple[SearchPlatform, ...]
    max_results_per_term: int
    analysis_goal: str
    schedule_kind: AutomationScheduleKind
    interval_minutes: int | None
    daily_time: str | None
    timezone: str | None
    enabled: bool
    revision: int
    anchor_at: str | None
    next_due_at: str | None
    created_at: str
    updated_at: str
    latest_run: AutomationRunRecord | None
    initial_prompt: PromptSnapshot | None = None
    report_prompt: PromptSnapshot | None = None
    max_total_results: int | None = None


@dataclass(frozen=True, slots=True)
class AutomationOccurrenceRecord:
    id: int
    task_id: int
    task_revision: int
    due_at: str
    status: Literal["claimed", "admitted", "skipped", "missed", "interrupted"]
    reason: str | None
    run_id: int | None
    missed_count: int
    missed_until: str | None
    created_at: str
    admitted_at: str | None
    run_status: str | None


@dataclass(frozen=True, slots=True)
class AutomationOccurrenceClaim:
    id: int
    task_id: int
    task_revision: int
    due_at: str
    admission_key: str


@dataclass(frozen=True, slots=True)
class AutomationStageAttemptRecord:
    id: int
    run_id: int
    stage: AutomationStageName
    attempt_number: int
    operation_key: str
    status: AutomationStageStatus
    child_kind: str | None
    child_id: int | None
    input_hash: str | None
    output_hash: str | None
    input_count: int
    success_count: int
    failure_count: int
    usage_attempted: int
    usage_tokens: int | None
    error: AutomationFailure | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class AutomationRunRecord:
    id: int
    admission_key: str
    request_id: str | None
    task_id: int
    trigger: Literal["scheduled", "manual"]
    task_revision: int
    snapshot: AutomationSnapshot
    status: str
    active_stage: AutomationStageName | None
    stages: tuple[AutomationStageAttemptRecord, ...]
    cancel_requested: bool
    outcome: str | None
    topic_report_id: int | None
    error: AutomationFailure | None
    revision: int
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class TaskContentRecord:
    task_id: int
    content_id: int
    first_run_id: int
    first_collection_run_id: int | None
    first_seen_at: str


@dataclass(frozen=True, slots=True)
class BatchContentRecord:
    content_id: int
    collection_run_id: int | None
    first_seen_at: str


class AutomationWorkflowRepository:
    """Own automation tables, transactions and deterministic projections."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()

    def create_task(
        self,
        payload: AutomationTaskCreate,
        *,
        now: datetime,
        normalized_name: str | None = None,
    ) -> AutomationTaskRecord:
        timestamp = _utc(now)
        schedule = payload.schedule
        interval_minutes = getattr(schedule, "interval_minutes", None)
        daily_time = getattr(schedule, "daily_time", None)
        timezone = getattr(schedule, "timezone", None)
        identity = normalized_name or _normalize(payload.name)
        with self._connection(write=True) as connection:
            initial_prompt = resolve_prompt_choice(
                connection, "initial", payload.initial_prompt
            )
            report_prompt = resolve_prompt_choice(
                connection, "report", payload.report_prompt
            )
            if connection.execute(
                "SELECT 1 FROM automation_tasks WHERE normalized_name=?", (identity,)
            ).fetchone():
                raise AutomationTaskNameConflictError
            cursor = connection.execute(
                """INSERT INTO automation_tasks(
                  name,normalized_name,monitoring_rule_id,max_results_per_term,max_total_results,analysis_goal,
                  initial_prompt_mode,initial_prompt_version_id,
                  report_prompt_mode,report_prompt_version_id,schedule_kind,
                  interval_minutes,daily_time,timezone,enabled,revision,next_due_at,
                  anchor_at,created_at,updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1,NULL,NULL,?,?)""",
                (
                    payload.name,
                    identity,
                    payload.monitoring_rule_id,
                    payload.max_results_per_term,
                    payload.max_total_results,
                    _prompt_mirror(report_prompt, payload.analysis_goal),
                    initial_prompt.mode,
                    initial_prompt.version_id,
                    report_prompt.mode,
                    report_prompt.version_id,
                    schedule.kind,
                    interval_minutes,
                    daily_time,
                    timezone,
                    timestamp,
                    timestamp,
                ),
            )
            task_id = int(cursor.lastrowid)
            self._insert_platforms(connection, task_id, payload.platforms)
            return _read_task(connection, task_id)

    def replace_task(
        self,
        task_id: int,
        payload: AutomationTaskReplace,
        *,
        now: datetime,
        next_due_at: str | None,
        anchor_at: str | None,
        normalized_name: str | None = None,
    ) -> AutomationTaskRecord:
        timestamp = _utc(now)
        schedule = payload.schedule
        interval_minutes = getattr(schedule, "interval_minutes", None)
        daily_time = getattr(schedule, "daily_time", None)
        timezone = getattr(schedule, "timezone", None)
        identity = normalized_name or _normalize(payload.name)
        with self._connection(write=True) as connection:
            initial_prompt = resolve_prompt_choice(
                connection, "initial", payload.initial_prompt
            )
            report_prompt = resolve_prompt_choice(
                connection, "report", payload.report_prompt
            )
            old = _task_row(connection, task_id)
            if old["revision"] != payload.expected_revision:
                raise AutomationTaskChangedError
            conflict = connection.execute(
                "SELECT 1 FROM automation_tasks WHERE normalized_name=? AND id!=?",
                (identity, task_id),
            ).fetchone()
            if conflict:
                raise AutomationTaskNameConflictError
            connection.execute(
                """UPDATE automation_tasks SET name=?,normalized_name=?,
                  monitoring_rule_id=?,max_results_per_term=?,max_total_results=?,analysis_goal=?,
                  initial_prompt_mode=?,initial_prompt_version_id=?,
                  report_prompt_mode=?,report_prompt_version_id=?,schedule_kind=?,
                  interval_minutes=?,daily_time=?,timezone=?,enabled=?,
                  revision=revision+1,next_due_at=?,anchor_at=?,updated_at=?
                  WHERE id=? AND revision=?""",
                (
                    payload.name,
                    identity,
                    payload.monitoring_rule_id,
                    payload.max_results_per_term,
                    payload.max_total_results,
                    _prompt_mirror(report_prompt, payload.analysis_goal),
                    initial_prompt.mode,
                    initial_prompt.version_id,
                    report_prompt.mode,
                    report_prompt.version_id,
                    schedule.kind,
                    interval_minutes,
                    daily_time,
                    timezone,
                    int(payload.enabled),
                    next_due_at if payload.enabled else None,
                    anchor_at if payload.enabled else None,
                    timestamp,
                    task_id,
                    payload.expected_revision,
                ),
            )
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise AutomationTaskChangedError
            connection.execute(
                "DELETE FROM automation_task_platforms WHERE task_id=?", (task_id,)
            )
            self._insert_platforms(connection, task_id, payload.platforms)
            return _read_task(connection, task_id)

    def delete_task(
        self,
        task_id: int,
        *,
        expected_revision: int,
        now: datetime,
    ) -> None:
        """Soft-delete one task while preserving every historical child row.

        The write lock serializes this fence with due-time claims and run
        admission.  A retry carrying the revision immediately before the
        deletion is treated as an idempotent success; other reads of the
        tombstone are intentionally indistinguishable from an unknown task.
        """
        timestamp = _utc(now)
        with self._connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM automation_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise AutomationTaskNotFoundError
            deleted_at = row["deleted_at"]
            current_revision = int(row["revision"])
            if deleted_at is not None:
                if current_revision == expected_revision + 1:
                    return
                raise AutomationTaskNotFoundError
            if current_revision != expected_revision:
                raise AutomationTaskChangedError
            active = connection.execute(
                """SELECT 1 FROM automation_runs WHERE task_id=? AND status IN
                   ('queued','collecting','analysing','reporting') LIMIT 1""",
                (task_id,),
            ).fetchone()
            if active is not None:
                raise AutomationRunActiveError
            tombstone = f"\x00automation-task:{task_id}:{expected_revision}"
            changed = connection.execute(
                """UPDATE automation_tasks SET normalized_name=?,enabled=0,
                   next_due_at=NULL,anchor_at=NULL,deleted_at=?,updated_at=?,
                   revision=revision+1 WHERE id=? AND revision=? AND deleted_at IS NULL""",
                (
                    tombstone,
                    timestamp,
                    timestamp,
                    task_id,
                    expected_revision,
                ),
            ).rowcount
            if changed != 1:
                raise AutomationTaskChangedError

    def get_task(self, task_id: int) -> AutomationTaskRecord:
        with self._connection() as connection:
            return _read_task(connection, task_id)

    def list_tasks(
        self, *, limit: int, before_id: int | None = None
    ) -> tuple[tuple[AutomationTaskRecord, ...], int | None]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id FROM automation_tasks
                   WHERE deleted_at IS NULL AND (? IS NULL OR id<?)
                   ORDER BY id DESC LIMIT ?""",
                (before_id, before_id, limit + 1),
            ).fetchall()
            records = tuple(_read_task(connection, int(row[0])) for row in rows[:limit])
            return records, records[-1].id if len(rows) > limit and records else None

    def occurrences(
        self, task_id: int, *, limit: int, before_id: int | None = None
    ) -> tuple[tuple[AutomationOccurrenceRecord, ...], int | None]:
        with self._connection() as connection:
            _task_row(connection, task_id)
            rows = connection.execute(
                """SELECT o.*,r.status AS run_status FROM automation_occurrences o
                   LEFT JOIN automation_runs r ON r.id=o.run_id
                   WHERE o.task_id=? AND (? IS NULL OR o.id<?)
                   ORDER BY o.id DESC LIMIT ?""",
                (task_id, before_id, before_id, limit + 1),
            ).fetchall()
            records = tuple(_occurrence(row) for row in rows[:limit])
            return records, records[-1].id if len(rows) > limit and records else None

    def reconcile_startup(self, now: datetime | None = None) -> int:
        """Reconcile timer claims without deciding child-work recoverability."""
        timestamp = _utc(now or datetime.now(UTC))
        with self._connection(write=True) as connection:
            cursor = connection.execute(
                """UPDATE automation_occurrences SET status='interrupted',
                  reason='dispatch_interrupted'
                  WHERE status='claimed' AND run_id IS NULL"""
            )
            interrupted = cursor.rowcount

        # Startup must never turn overdue wall-clock time into a collection.
        # Record one bounded offline range per task and advance to a future due
        # instant before the timer is allowed to tick.
        while self.has_due(_parse_utc(timestamp)):
            self.advance_due(_parse_utc(timestamp), missed_reason="offline")
        return interrupted

    def active_runs(self) -> tuple[AutomationRunRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id FROM automation_runs WHERE status IN
                   ('queued','collecting','analysing','reporting') ORDER BY id"""
            ).fetchall()
            return tuple(_read_run(connection, int(row[0])) for row in rows)

    def prepare_recovered_stage(
        self, run_id: int, stage: AutomationStageName
    ) -> AutomationRunRecord:
        """Make one proven reusable child projectable without a new admission."""
        with self._connection(write=True) as connection:
            run = _read_run(connection, run_id)
            if run.status not in ACTIVE_RUN_STATUSES:
                raise AutomationRunChangedError
            attempt = _latest_attempt(connection, run_id, stage)
            if attempt is None or attempt.status not in {"queued", "running"}:
                raise AutomationRunChangedError
            if attempt.status == "running":
                connection.execute(
                    """UPDATE automation_stage_attempts
                       SET status='queued',started_at=NULL
                       WHERE id=? AND status='running'""",
                    (attempt.id,),
                )
            return _read_run(connection, run_id)

    def has_due(self, now: datetime) -> bool:
        """Return whether another enabled task is overdue at ``now``."""
        timestamp = _utc(now)
        with self._connection() as connection:
            return (
                connection.execute(
                    """SELECT 1 FROM automation_tasks
                       WHERE deleted_at IS NULL AND enabled=1 AND next_due_at<=? LIMIT 1""",
                    (timestamp,),
                ).fetchone()
                is not None
            )

    def advance_due(
        self,
        now: datetime,
        *,
        missed_reason: Literal["offline", "clock_jump"] | None = None,
    ) -> tuple[AutomationOccurrenceClaim, ...]:
        """Claim each due occurrence exactly once and advance its task atomically."""
        current = _as_utc(now)
        timestamp = current.isoformat()
        claims: list[AutomationOccurrenceClaim] = []
        with self._connection(write=True) as connection:
            rows = connection.execute(
                """SELECT * FROM automation_tasks WHERE enabled=1 AND next_due_at<=?
                   AND deleted_at IS NULL ORDER BY next_due_at,id LIMIT 100""",
                (timestamp,),
            ).fetchall()
            for row in rows:
                task_id = int(row["id"])
                due = _parse_utc(row["next_due_at"])
                due_times = _due_times(row, due, current)
                next_due = _next_due(row, current)
                missed = missed_reason is not None or len(due_times) > 1
                if missed:
                    first, last = due_times[0], due_times[-1]
                    connection.execute(
                        """INSERT INTO automation_occurrences(
                          task_id,task_revision,due_at,status,reason,missed_count,
                          missed_until,created_at)
                          VALUES (?,?,?,'missed',?,?,?,?)""",
                        (
                            task_id,
                            row["revision"],
                            first.isoformat(),
                            missed_reason or "offline",
                            len(due_times),
                            last.isoformat(),
                            timestamp,
                        ),
                    )
                else:
                    active = connection.execute(
                        """SELECT 1 FROM automation_runs WHERE task_id=? AND
                          status IN ('queued','collecting','analysing','reporting') LIMIT 1""",
                        (task_id,),
                    ).fetchone()
                    if active is not None:
                        connection.execute(
                            """INSERT INTO automation_occurrences(
                              task_id,task_revision,due_at,status,reason,created_at)
                              VALUES (?,?,?,'skipped','previous_run_active',?)""",
                            (task_id, row["revision"], due.isoformat(), timestamp),
                        )
                    else:
                        token = (
                            f"scheduled:{task_id}:{row['revision']}:{due.isoformat()}"
                        )
                        cursor = connection.execute(
                            """INSERT INTO automation_occurrences(
                              task_id,task_revision,due_at,status,created_at)
                              VALUES (?,?,?,'claimed',?)""",
                            (task_id, row["revision"], due.isoformat(), timestamp),
                        )
                        claims.append(
                            AutomationOccurrenceClaim(
                                id=int(cursor.lastrowid),
                                task_id=task_id,
                                task_revision=int(row["revision"]),
                                due_at=due.isoformat(),
                                admission_key=token,
                            )
                        )
                connection.execute(
                    "UPDATE automation_tasks SET next_due_at=? WHERE id=?",
                    (next_due.isoformat(), task_id),
                )
        return tuple(claims)

    def skip_occurrence(self, occurrence_id: int, reason: str) -> None:
        with self._connection(write=True) as connection:
            row = connection.execute(
                "SELECT status FROM automation_occurrences WHERE id=?", (occurrence_id,)
            ).fetchone()
            if row is None:
                raise AutomationOccurrenceChangedError
            if row[0] != "claimed":
                raise AutomationOccurrenceChangedError
            status = "interrupted" if reason == "dispatch_interrupted" else "skipped"
            connection.execute(
                "UPDATE automation_occurrences SET status=?,reason=? WHERE id=? AND status='claimed'",
                (status, reason, occurrence_id),
            )

    def occurrence(self, occurrence_id: int) -> AutomationOccurrenceRecord:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT o.*,r.status AS run_status FROM automation_occurrences o
                   LEFT JOIN automation_runs r ON r.id=o.run_id WHERE o.id=?""",
                (occurrence_id,),
            ).fetchone()
            if row is None:
                raise AutomationOccurrenceChangedError
            return _occurrence(row)

    def request(self, request_id: str):
        with self._connection() as connection:
            return connection.execute(
                "SELECT * FROM automation_requests WHERE request_id=?", (request_id,)
            ).fetchone()

    def save_request(
        self,
        *,
        request_id: str,
        action: Literal["run_now", "cancel", "retry"],
        task_id: int | None,
        run_id: int | None,
        intent_hash: str,
        result_json: str,
        now: datetime,
    ) -> None:
        with self._connection(write=True) as connection:
            existing = connection.execute(
                "SELECT intent_hash FROM automation_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if existing["intent_hash"] != intent_hash:
                    raise AutomationRequestConflictError
                return
            connection.execute(
                """INSERT INTO automation_requests(
                  request_id,action,task_id,run_id,intent_hash,result_json,created_at)
                  VALUES (?,?,?,?,?,?,?)""",
                (
                    request_id,
                    action,
                    task_id,
                    run_id,
                    intent_hash,
                    result_json,
                    _utc(now),
                ),
            )

    def create_run(
        self,
        *,
        task_id: int,
        trigger: Literal["scheduled", "manual"],
        admission_key: str,
        request_id: str | None,
        snapshot: AutomationSnapshot,
        now: datetime,
        occurrence_id: int | None = None,
        request_intent_hash: str | None = None,
    ) -> tuple[AutomationRunRecord, bool]:
        timestamp = _utc(now)
        snapshot_json = _encode_snapshot(snapshot)
        with self._connection(write=True) as connection:
            existing = connection.execute(
                "SELECT id FROM automation_runs WHERE admission_key=?", (admission_key,)
            ).fetchone()
            if existing is not None:
                return _read_run(connection, int(existing[0])), False
            _task_row(connection, task_id)
            active = connection.execute(
                """SELECT id FROM automation_runs WHERE task_id=? AND
                  status IN ('queued','collecting','analysing','reporting') LIMIT 1""",
                (task_id,),
            ).fetchone()
            if active is not None:
                raise AutomationRunActiveError
            cursor = connection.execute(
                """INSERT INTO automation_runs(
                  admission_key,request_id,task_id,trigger,task_revision,snapshot_json,
                  status,active_stage,created_at,started_at,finished_at)
                  VALUES (?,?,?,?,?,?,'queued','collection',?,NULL,NULL)""",
                (
                    admission_key,
                    request_id,
                    task_id,
                    trigger,
                    snapshot.task_revision,
                    snapshot_json,
                    timestamp,
                ),
            )
            run_id = int(cursor.lastrowid)
            for stage in AUTOMATION_STAGES:
                connection.execute(
                    """INSERT INTO automation_stage_attempts(
                      run_id,stage,attempt_number,operation_key,status,created_at)
                      VALUES (?,?,1,?,'queued',?)""",
                    (run_id, stage, f"{admission_key}:{stage}:1", timestamp),
                )
            if occurrence_id is not None:
                changed = connection.execute(
                    """UPDATE automation_occurrences SET status='admitted',run_id=?,
                      admitted_at=? WHERE id=? AND status='claimed' AND run_id IS NULL""",
                    (run_id, timestamp, occurrence_id),
                ).rowcount
                if changed != 1:
                    raise AutomationOccurrenceChangedError
            if request_id is not None:
                if request_intent_hash is None:
                    raise ValueError("manual run requires request intent")
                _insert_request(
                    connection,
                    request_id=request_id,
                    action="run_now",
                    task_id=task_id,
                    run_id=run_id,
                    intent_hash=request_intent_hash,
                    created_at=timestamp,
                )
            return _read_run(connection, run_id), True

    def get_run(self, run_id: int) -> AutomationRunRecord:
        with self._connection() as connection:
            return _read_run(connection, run_id)

    def list_runs(
        self, task_id: int, *, limit: int, before_id: int | None = None
    ) -> tuple[tuple[AutomationRunRecord, ...], int | None]:
        with self._connection() as connection:
            _task_row(connection, task_id)
            rows = connection.execute(
                """SELECT id FROM automation_runs WHERE task_id=?
                   AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?""",
                (task_id, before_id, before_id, limit + 1),
            ).fetchall()
            records = tuple(_read_run(connection, int(row[0])) for row in rows[:limit])
            return records, records[-1].id if len(rows) > limit and records else None

    def next_run(self) -> AutomationRunRecord | None:
        """Return the oldest queued/active run for deterministic progression."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT id FROM automation_runs
                   WHERE status IN ('queued','collecting','analysing','reporting')
                   ORDER BY id LIMIT 1"""
            ).fetchone()
            return _read_run(connection, int(row[0])) if row is not None else None

    def start_stage(
        self, run_id: int, stage: AutomationStageName
    ) -> AutomationRunRecord:
        timestamp = _utc(datetime.now(UTC))
        with self._connection(write=True) as connection:
            run = _read_run(connection, run_id)
            if run.status not in ACTIVE_RUN_STATUSES:
                raise AutomationRunChangedError
            attempt = _latest_attempt(connection, run_id, stage)
            if attempt is None or attempt.status not in {"queued", "interrupted"}:
                raise AutomationRunChangedError
            connection.execute(
                """UPDATE automation_stage_attempts SET status='running',started_at=?
                   WHERE id=? AND status IN ('queued','interrupted')""",
                (timestamp, attempt.id),
            )
            status = {
                "collection": "collecting",
                "initial_analysis": "analysing",
                "topic_report": "reporting",
            }[stage]
            connection.execute(
                """UPDATE automation_runs SET status=?,active_stage=?,started_at=COALESCE(started_at,?),
                  revision=revision+1 WHERE id=? AND status IN ('queued','collecting','analysing','reporting')""",
                (status, stage, timestamp, run_id),
            )
            return _read_run(connection, run_id)

    def set_stage_child(
        self,
        run_id: int,
        stage: AutomationStageName,
        *,
        child_kind: str,
        child_id: int,
        input_hash: str | None = None,
    ) -> AutomationStageAttemptRecord:
        with self._connection(write=True) as connection:
            attempt = _latest_attempt(connection, run_id, stage)
            if attempt is None or attempt.status not in {"queued", "running"}:
                raise AutomationRunChangedError
            connection.execute(
                """UPDATE automation_stage_attempts SET child_kind=?,child_id=?,input_hash=?
                   WHERE id=? AND status IN ('queued','running')""",
                (child_kind, child_id, input_hash, attempt.id),
            )
            return _read_attempt(connection, attempt.id)

    def finish_stage(
        self,
        run_id: int,
        stage: AutomationStageName,
        status: AutomationStageStatus,
        *,
        output_hash: str | None = None,
        input_count: int = 0,
        success_count: int = 0,
        failure_count: int = 0,
        usage_attempted: int = 0,
        usage_tokens: int | None = None,
        error: AutomationFailure | None = None,
    ) -> AutomationRunRecord:
        if status in {"queued", "running"}:
            raise ValueError("stage must be terminal")
        if min(input_count, success_count, failure_count, usage_attempted) < 0:
            raise ValueError("stage metrics must be non-negative")
        if success_count + failure_count > input_count:
            raise ValueError("stage metrics exceed input count")
        timestamp = _utc(datetime.now(UTC))
        with self._connection(write=True) as connection:
            attempt = _latest_attempt(connection, run_id, stage)
            if attempt is None or attempt.status not in {"queued", "running"}:
                raise AutomationRunChangedError
            connection.execute(
                """UPDATE automation_stage_attempts SET status=?,output_hash=?,
                   input_count=?,success_count=?,failure_count=?,usage_attempted=?,
                   usage_tokens=?,error_json=?,finished_at=?
                   WHERE id=? AND status IN ('queued','running')""",
                (
                    status,
                    output_hash,
                    input_count,
                    success_count,
                    failure_count,
                    usage_attempted,
                    usage_tokens,
                    error.model_dump_json() if error else None,
                    timestamp,
                    attempt.id,
                ),
            )
            return _read_run(connection, run_id)

    def set_run_terminal(
        self,
        run_id: int,
        status: Literal[
            "completed", "failed", "cancelled", "interrupted", "configuration_blocked"
        ],
        *,
        outcome: str | None = None,
        topic_report_id: int | None = None,
        error: AutomationFailure | None = None,
    ) -> AutomationRunRecord:
        timestamp = _utc(datetime.now(UTC))
        with self._connection(write=True) as connection:
            run = _read_run(connection, run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            # A terminal workflow must never expose queued/running downstream
            # attempts.  They are intentionally settled as cancelled (or
            # interrupted during restart) so the fixed three-stage projection
            # remains truthful and retry can identify the first failed stage.
            settle_status = "interrupted" if status == "interrupted" else "cancelled"
            connection.execute(
                """UPDATE automation_stage_attempts
                   SET status=?, finished_at=?
                   WHERE run_id=? AND status IN ('queued','running')""",
                (settle_status, timestamp, run_id),
            )
            connection.execute(
                """UPDATE automation_runs SET status=?,active_stage=NULL,outcome=?,topic_report_id=?,
                  error_json=?,revision=revision+1,finished_at=? WHERE id=? AND status IN
                  ('queued','collecting','analysing','reporting')""",
                (
                    status,
                    outcome,
                    topic_report_id,
                    error.model_dump_json() if error else None,
                    timestamp,
                    run_id,
                ),
            )
            return _read_run(connection, run_id)

    def request_cancel(
        self,
        run_id: int,
        *,
        expected_revision: int,
        request_id: str,
        request_intent_hash: str,
    ) -> AutomationRunRecord:
        timestamp = _utc(datetime.now(UTC))
        with self._connection(write=True) as connection:
            run = _read_run(connection, run_id)
            if run.revision != expected_revision:
                raise AutomationRunChangedError
            if run.status not in ACTIVE_RUN_STATUSES:
                raise AutomationRunNotActiveError
            connection.execute(
                """UPDATE automation_runs SET cancel_requested=1,status='cancelled',active_stage=NULL,
                  outcome='cancelled',revision=revision+1,finished_at=?
                  WHERE id=? AND revision=? AND status IN ('queued','collecting','analysing','reporting')""",
                (timestamp, run_id, expected_revision),
            )
            connection.execute(
                """UPDATE automation_stage_attempts SET status='cancelled',finished_at=?
                   WHERE run_id=? AND status IN ('queued','running')""",
                (timestamp, run_id),
            )
            _insert_request(
                connection,
                request_id=request_id,
                action="cancel",
                task_id=run.task_id,
                run_id=run_id,
                intent_hash=request_intent_hash,
                created_at=timestamp,
            )
            return _read_run(connection, run_id)

    def retry_run(
        self,
        run_id: int,
        *,
        expected_revision: int,
        request_id: str,
        request_intent_hash: str,
        now: datetime,
        reuse_child_kind: str | None = None,
        reuse_child_id: int | None = None,
    ) -> AutomationRunRecord:
        if (reuse_child_kind is None) != (reuse_child_id is None):
            raise ValueError("retry child kind and id must be provided together")
        timestamp = _utc(now)
        with self._connection(write=True) as connection:
            run = _read_run(connection, run_id)
            if run.revision != expected_revision:
                raise AutomationRunChangedError
            if run.status not in {
                "failed",
                "interrupted",
                "configuration_blocked",
            }:
                raise AutomationRunNotRetryableError
            active = connection.execute(
                """SELECT 1 FROM automation_runs WHERE task_id=? AND status IN
                  ('queued','collecting','analysing','reporting')""",
                (run.task_id,),
            ).fetchone()
            if active is not None:
                raise AutomationRunActiveError
            stage = _first_failed_stage(connection, run_id)
            if stage is None:
                raise AutomationRunNotRetryableError
            first = AUTOMATION_STAGES.index(stage)
            for next_stage in AUTOMATION_STAGES[first:]:
                previous = _latest_attempt(connection, run_id, next_stage)
                number = previous.attempt_number + 1 if previous else 1
                key = f"{run.admission_key}:{next_stage}:{number}:{request_id}"
                child_kind = reuse_child_kind if next_stage == stage else None
                child_id = reuse_child_id if next_stage == stage else None
                connection.execute(
                    """INSERT INTO automation_stage_attempts(
                      run_id,stage,attempt_number,operation_key,status,child_kind,
                      child_id,created_at)
                      VALUES (?,?,?,?,'queued',?,?,?)""",
                    (
                        run_id,
                        next_stage,
                        number,
                        key,
                        child_kind,
                        child_id,
                        timestamp,
                    ),
                )
            status = {
                "collection": "collecting",
                "initial_analysis": "analysing",
                "topic_report": "reporting",
            }[stage]
            connection.execute(
                """UPDATE automation_runs SET status=?,active_stage=?,cancel_requested=0,
                  outcome=NULL,error_json=NULL,revision=revision+1,finished_at=NULL
                  WHERE id=? AND revision=?""",
                (status, stage, run_id, expected_revision),
            )
            _insert_request(
                connection,
                request_id=request_id,
                action="retry",
                task_id=run.task_id,
                run_id=run_id,
                intent_hash=request_intent_hash,
                created_at=timestamp,
            )
            return _read_run(connection, run_id)

    def task_contents(
        self, task_id: int, *, limit: int | None = None
    ) -> tuple[TaskContentRecord, ...]:
        with self._connection() as connection:
            _task_row(connection, task_id)
            clause = " LIMIT ?" if limit is not None else ""
            params: tuple[object, ...] = (
                (task_id, limit) if limit is not None else (task_id,)
            )
            rows = connection.execute(
                """SELECT task_id,content_id,first_run_id,first_collection_run_id,first_seen_at
                   FROM automation_task_contents WHERE task_id=? ORDER BY content_id"""
                + clause,
                params,
            ).fetchall()
            return tuple(
                TaskContentRecord(
                    task_id=int(row["task_id"]),
                    content_id=int(row["content_id"]),
                    first_run_id=int(row["first_run_id"]),
                    first_collection_run_id=row["first_collection_run_id"],
                    first_seen_at=str(row["first_seen_at"]),
                )
                for row in rows
            )

    def register_task_contents(
        self,
        task_id: int,
        run_id: int,
        entries: Sequence[BatchContentRecord],
    ) -> tuple[TaskContentRecord, ...]:
        timestamp = _utc(datetime.now(UTC))
        with self._connection(write=True) as connection:
            _task_row(connection, task_id)
            _run_row(connection, run_id)
            inserted: list[TaskContentRecord] = []
            for entry in entries:
                inserted_content = False
                connection.execute(
                    """INSERT INTO automation_task_contents(
                      task_id,content_id,first_run_id,first_collection_run_id,first_seen_at)
                      VALUES (?,?,?,?,?) ON CONFLICT(task_id,content_id) DO NOTHING""",
                    (
                        task_id,
                        entry.content_id,
                        run_id,
                        entry.collection_run_id,
                        entry.first_seen_at or timestamp,
                    ),
                )
                if connection.execute("SELECT changes()").fetchone()[0] == 1:
                    inserted_content = True
                    row = connection.execute(
                        "SELECT * FROM automation_task_contents WHERE task_id=? AND content_id=?",
                        (task_id, entry.content_id),
                    ).fetchone()
                    inserted.append(
                        TaskContentRecord(
                            task_id=int(row["task_id"]),
                            content_id=int(row["content_id"]),
                            first_run_id=int(row["first_run_id"]),
                            first_collection_run_id=row["first_collection_run_id"],
                            first_seen_at=row["first_seen_at"],
                        )
                    )
                # The run's analysis membership is the content first observed
                # by this task, not every globally repeated result from the
                # collection batch.  Keeping repeated observations out here is
                # what makes R10 true across successive scheduled runs.
                if inserted_content:
                    connection.execute(
                        """INSERT INTO automation_run_contents(run_id,task_id,content_id,position)
                           VALUES (?,?,?,(SELECT COALESCE(MAX(position),-1)+1
                           FROM automation_run_contents WHERE run_id=?))""",
                        (run_id, task_id, entry.content_id, run_id),
                    )
            return tuple(inserted)

    def run_contents(self, run_id: int) -> tuple[int, ...]:
        with self._connection() as connection:
            _run_row(connection, run_id)
            return tuple(
                int(row[0])
                for row in connection.execute(
                    "SELECT content_id FROM automation_run_contents WHERE run_id=? ORDER BY position",
                    (run_id,),
                ).fetchall()
            )

    def batch_contents(self, batch_id: int) -> tuple[BatchContentRecord, ...]:
        """Return deterministic global content membership for a completed batch."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT c.id,MIN(a.search_run_id) AS collection_run_id,c.first_seen_at
                   FROM search_batch_attempts a
                   JOIN search_run_contents l ON l.run_id=a.search_run_id
                   JOIN search_contents c ON c.id=l.search_content_id
                   WHERE a.batch_id=? GROUP BY c.id,c.first_seen_at ORDER BY c.id""",
                (batch_id,),
            ).fetchall()
            return tuple(
                BatchContentRecord(
                    content_id=int(row["id"]),
                    collection_run_id=row["collection_run_id"],
                    first_seen_at=str(row["first_seen_at"]),
                )
                for row in rows
            )

    def latest_stage(self, run_id: int, stage: AutomationStageName):
        with self._connection() as connection:
            _run_row(connection, run_id)
            attempt = _latest_attempt(connection, run_id, stage)
            if attempt is None:
                raise AutomationRunChangedError
            return attempt

    @staticmethod
    def _insert_platforms(
        connection, task_id: int, platforms: Sequence[SearchPlatform]
    ) -> None:
        ordered = tuple(
            platform for platform in SEARCH_PLATFORMS if platform in platforms
        )
        if ordered != tuple(platforms):
            raise sqlite3.IntegrityError("invalid automation platform order")
        connection.executemany(
            "INSERT INTO automation_task_platforms(task_id,position,platform) VALUES (?,?,?)",
            (
                (task_id, position, platform)
                for position, platform in enumerate(ordered)
            ),
        )

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = self.database.connect()
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except (
            AutomationRepositoryError,
            AutomationTaskNotFoundError,
            AutomationRunNotFoundError,
            AutomationTaskNameConflictError,
            AutomationTaskChangedError,
            AutomationRunActiveError,
            AutomationRunChangedError,
            AutomationRunNotRetryableError,
            AutomationRunNotActiveError,
            AutomationOccurrenceChangedError,
            AutomationRequestConflictError,
        ):
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, UnicodeError):
            raise AutomationRepositoryUnavailableError from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()


def _task_row(connection: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM automation_tasks WHERE id=? AND deleted_at IS NULL",
        (task_id,),
    ).fetchone()
    if row is None:
        raise AutomationTaskNotFoundError
    return row


def _run_row(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM automation_runs WHERE id=?", (run_id,)
    ).fetchone()
    if row is None:
        raise AutomationRunNotFoundError
    return row


def _read_task(connection: sqlite3.Connection, task_id: int) -> AutomationTaskRecord:
    row = _task_row(connection, task_id)
    platforms = tuple(
        cast(SearchPlatform, child[0])
        for child in connection.execute(
            "SELECT platform FROM automation_task_platforms WHERE task_id=? ORDER BY position",
            (task_id,),
        ).fetchall()
    )
    rule = None
    if row["monitoring_rule_id"] is not None:
        try:
            rule = _read_record(
                connection, int(row["monitoring_rule_id"]), require_objects=False
            )
        except Exception:
            rule = None
    rule_state = (
        "deleted" if rule is None else "enabled" if rule.enabled else "disabled"
    )
    latest = connection.execute(
        "SELECT id FROM automation_runs WHERE task_id=? ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return AutomationTaskRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        monitoring_rule_id=row["monitoring_rule_id"],
        rule_name=rule.name if rule is not None else str(row["name"]),
        rule_state=cast(
            Literal["enabled", "disabled", "deleted", "invalid"], rule_state
        ),
        platforms=platforms,
        max_results_per_term=int(row["max_results_per_term"]),
        max_total_results=row["max_total_results"],
        analysis_goal=str(row["analysis_goal"]),
        schedule_kind=cast(AutomationScheduleKind, row["schedule_kind"]),
        interval_minutes=row["interval_minutes"],
        daily_time=row["daily_time"],
        timezone=row["timezone"],
        enabled=bool(row["enabled"]),
        revision=int(row["revision"]),
        anchor_at=row["anchor_at"],
        next_due_at=row["next_due_at"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        latest_run=_read_run(connection, int(latest[0]))
        if latest is not None
        else None,
        initial_prompt=prompt_snapshot(
            connection,
            "initial",
            int(row["initial_prompt_version_id"]),
            mode=str(row["initial_prompt_mode"]),
        ),
        report_prompt=prompt_snapshot(
            connection,
            "report",
            int(row["report_prompt_version_id"]),
            mode=str(row["report_prompt_mode"]),
        ),
    )


def _occurrence(row: sqlite3.Row) -> AutomationOccurrenceRecord:
    return AutomationOccurrenceRecord(
        id=int(row["id"]),
        task_id=int(row["task_id"]),
        task_revision=int(row["task_revision"]),
        due_at=str(row["due_at"]),
        status=row["status"],
        reason=row["reason"],
        run_id=row["run_id"],
        missed_count=int(row["missed_count"]),
        missed_until=row["missed_until"],
        created_at=str(row["created_at"]),
        admitted_at=row["admitted_at"],
        run_status=row["run_status"],
    )


def _read_attempt(
    connection: sqlite3.Connection, attempt_id: int
) -> AutomationStageAttemptRecord:
    row = connection.execute(
        "SELECT * FROM automation_stage_attempts WHERE id=?", (attempt_id,)
    ).fetchone()
    if row is None:
        raise AutomationRunChangedError
    return AutomationStageAttemptRecord(
        id=int(row["id"]),
        run_id=int(row["run_id"]),
        stage=cast(AutomationStageName, row["stage"]),
        attempt_number=int(row["attempt_number"]),
        operation_key=str(row["operation_key"]),
        status=cast(AutomationStageStatus, row["status"]),
        child_kind=row["child_kind"],
        child_id=row["child_id"],
        input_hash=row["input_hash"],
        output_hash=row["output_hash"],
        input_count=int(row["input_count"]),
        success_count=int(row["success_count"]),
        failure_count=int(row["failure_count"]),
        usage_attempted=int(row["usage_attempted"]),
        usage_tokens=row["usage_tokens"],
        error=AutomationFailure.model_validate_json(row["error_json"])
        if row["error_json"]
        else None,
        created_at=str(row["created_at"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _latest_attempt(connection: sqlite3.Connection, run_id: int, stage: str):
    row = connection.execute(
        """SELECT id FROM automation_stage_attempts WHERE run_id=? AND stage=?
           ORDER BY attempt_number DESC LIMIT 1""",
        (run_id, stage),
    ).fetchone()
    return _read_attempt(connection, int(row[0])) if row is not None else None


def _insert_request(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    action: str,
    task_id: int | None,
    run_id: int,
    intent_hash: str,
    created_at: str,
) -> None:
    existing = connection.execute(
        "SELECT intent_hash FROM automation_requests WHERE request_id=?",
        (request_id,),
    ).fetchone()
    if existing is not None:
        if existing["intent_hash"] != intent_hash:
            raise AutomationRequestConflictError
        return
    connection.execute(
        """INSERT INTO automation_requests(
          request_id,action,task_id,run_id,intent_hash,result_json,created_at)
          VALUES (?,?,?,?,?,'{}',?)""",
        (request_id, action, task_id, run_id, intent_hash, created_at),
    )


def _first_failed_stage(
    connection: sqlite3.Connection, run_id: int
) -> AutomationStageName | None:
    for stage in AUTOMATION_STAGES:
        attempt = _latest_attempt(connection, run_id, stage)
        if attempt is None or attempt.status != "completed":
            return stage
    return None


def _read_run(connection: sqlite3.Connection, run_id: int) -> AutomationRunRecord:
    row = _run_row(connection, run_id)
    rows = connection.execute(
        """SELECT id FROM automation_stage_attempts WHERE run_id=?
           ORDER BY CASE stage WHEN 'collection' THEN 0 WHEN 'initial_analysis' THEN 1 ELSE 2 END,
                    attempt_number""",
        (run_id,),
    ).fetchall()
    attempts = tuple(_read_attempt(connection, int(item[0])) for item in rows)
    return AutomationRunRecord(
        id=int(row["id"]),
        admission_key=str(row["admission_key"]),
        request_id=row["request_id"],
        task_id=int(row["task_id"]),
        trigger=cast(Literal["scheduled", "manual"], row["trigger"]),
        task_revision=int(row["task_revision"]),
        snapshot=_read_snapshot(connection, row["snapshot_json"]),
        status=str(row["status"]),
        active_stage=cast(AutomationStageName | None, row["active_stage"]),
        stages=attempts,
        cancel_requested=bool(row["cancel_requested"]),
        outcome=row["outcome"],
        topic_report_id=row["topic_report_id"],
        error=AutomationFailure.model_validate_json(row["error_json"])
        if row["error_json"]
        else None,
        revision=int(row["revision"]),
        created_at=str(row["created_at"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _encode_snapshot(snapshot: AutomationSnapshot) -> str:
    """Encode the complete immutable run intent, including nested snapshots.

    Automation runs keep their intent in one JSON column.  Keep this boundary
    explicit rather than relying on callers to serialize nested Pydantic models
    themselves; in particular, ``platform_access_snapshot`` must survive a
    create/read round trip while a missing field remains a legacy ``None``.
    """
    return snapshot.model_dump_json()


def _decode_snapshot(snapshot_json: str) -> AutomationSnapshot:
    """Decode one stored run intent without applying mutable defaults."""
    return AutomationSnapshot.model_validate_json(snapshot_json)


def _read_snapshot(
    connection: sqlite3.Connection, snapshot_json: str
) -> AutomationSnapshot:
    """Project pre-v18 run snapshots without changing their stored JSON.

    v18 added the complete prompt projections to new snapshots, but existing
    runs only contain the two version IDs and the old ``analysis_goal`` field.
    The old report ID points at the shared report setting; the task-specific
    text in ``analysis_goal`` was the actual report instruction.  Keep that
    historical distinction visible as ``legacy`` while resolving the initial
    shared row from its immutable version ID.
    """

    snapshot = _decode_snapshot(snapshot_json)
    updates: dict[str, PromptSnapshot] = {}
    if (
        snapshot.initial_prompt is None
        and snapshot.initial_prompt_version_id is not None
    ):
        updates["initial_prompt"] = prompt_snapshot(
            connection,
            "initial",
            snapshot.initial_prompt_version_id,
            mode="legacy",
        )
    if snapshot.report_prompt is None and snapshot.report_prompt_version_id is not None:
        updates["report_prompt"] = PromptSnapshot(
            mode="legacy",
            version_id=snapshot.report_prompt_version_id,
            instructions=snapshot.analysis_goal,
            content_hash=snapshot.analysis_goal_hash,
            schema_version=REPORT_SCHEMA_VERSION,
        )
    return snapshot.model_copy(update=updates) if updates else snapshot


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def _prompt_mirror(prompt: PromptSnapshot, legacy: str | None) -> str:
    """Keep the old bounded column useful without making it authoritative."""
    del legacy  # The full prompt is the source of truth for the v18 mirror.
    if len(prompt.instructions) <= 4000:
        return prompt.instructions
    return f"使用已保存提示词版本 {prompt.version_id}"


def _utc(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _parse_local_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _local_candidates(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    candidates: list[datetime] = []
    for fold in (0, 1):
        aware = local.replace(tzinfo=zone, fold=fold)
        roundtrip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip == local:
            instant = aware.astimezone(UTC)
            if instant not in candidates:
                candidates.append(instant)
    return tuple(sorted(candidates))


def _daily_due_after(
    local_date: date, daily_time: str, timezone: str, after: datetime
) -> datetime:
    zone = ZoneInfo(timezone)
    requested = datetime.combine(local_date, _parse_local_time(daily_time))
    candidates = _local_candidates(requested, zone)
    if candidates:
        future = [candidate for candidate in candidates if candidate > after]
        if future:
            return future[0]
    # A requested local wall time in a DST gap does not round-trip.  Advance to
    # the first valid minute after the requested wall time.
    probe = requested + timedelta(minutes=1)
    for _ in range(180):
        candidates = _local_candidates(probe, zone)
        future = [candidate for candidate in candidates if candidate > after]
        if future:
            return future[0]
        probe += timedelta(minutes=1)
    raise ValueError("daily schedule has no valid instant")


def _next_due(row: sqlite3.Row, now: datetime) -> datetime:
    current = _as_utc(now)
    if row["schedule_kind"] == "interval":
        return current + timedelta(minutes=int(row["interval_minutes"]))
    local = current.astimezone(ZoneInfo(row["timezone"]))
    candidate = _daily_due_after(
        local.date(), row["daily_time"], row["timezone"], current
    )
    if candidate > current:
        return candidate
    return _daily_due_after(
        local.date() + timedelta(days=1), row["daily_time"], row["timezone"], current
    )


def _due_times(row: sqlite3.Row, due: datetime, now: datetime) -> tuple[datetime, ...]:
    current = _as_utc(now)
    values: list[datetime] = []
    if row["schedule_kind"] == "interval":
        step = timedelta(minutes=int(row["interval_minutes"]))
        value = due
        while value <= current:
            values.append(value)
            value += step
            if len(values) > 100_000:
                break
    else:
        zone = ZoneInfo(row["timezone"])
        local = due.astimezone(zone).date()
        value = due
        while value <= current:
            values.append(value)
            local += timedelta(days=1)
            value = _daily_due_after(
                local,
                row["daily_time"],
                row["timezone"],
                value - timedelta(microseconds=1),
            )
            if len(values) > 100_000:
                break
    return tuple(values or (due,))


def _failure_json(code: str, message: str) -> str:
    return json.dumps(
        {"code": code, "message": message}, ensure_ascii=False, separators=(",", ":")
    )
