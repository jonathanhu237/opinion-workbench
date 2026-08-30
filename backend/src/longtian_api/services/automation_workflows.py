"""Fixed-purpose automatic collection, understanding and report orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from uuid import uuid4
from zoneinfo import ZoneInfo

from longtian_api.repositories.automation_workflows import (
    ACTIVE_RUN_STATUSES,
    AutomationOccurrenceChangedError,
    AutomationOccurrenceClaim,
    AutomationRepositoryUnavailableError,
    AutomationRequestConflictError,
    AutomationRunActiveError,
    AutomationRunChangedError,
    AutomationRunNotActiveError,
    AutomationRunNotFoundError,
    AutomationRunNotRetryableError,
    AutomationStageAttemptRecord,
    AutomationTaskChangedError,
    AutomationTaskNameConflictError,
    AutomationTaskNotFoundError,
    AutomationTaskRecord,
    AutomationWorkflowRepository,
    BatchContentRecord,
)
from longtian_api.schemas.analysis_settings import (
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)
from longtian_api.schemas.automation_workflows import (
    AUTOMATION_STAGES,
    AutomationDailySchedule,
    AutomationFailure,
    AutomationIntervalSchedule,
    AutomationOccurrence,
    AutomationOccurrenceList,
    AutomationRun,
    AutomationRunCancel,
    AutomationRunList,
    AutomationRunNow,
    AutomationRunRetry,
    AutomationSchedule,
    AutomationSnapshot,
    AutomationStage,
    AutomationStageName,
    AutomationTask,
    AutomationTaskCreate,
    AutomationTaskList,
    AutomationTaskReplace,
)
from longtian_api.schemas.search_batches import SearchBatchCancel, SearchBatchCreate
from longtian_api.schemas.topic_reports import ReportCancel
from longtian_api.services.ai_errors import AIError
from longtian_api.services.automation_workflow_errors import (
    AutomationWorkflowError,
)
from longtian_api.services.monitoring_rules import (
    MonitoringRuleError,
    compose_monitoring_terms,
)
from longtian_api.services.settled_tasks import database_call, settle


def schedule_next_due(
    schedule: AutomationSchedule,
    now: datetime,
) -> datetime:
    """Compute the first due instant strictly after ``now``.

    Daily plans are evaluated with IANA rules.  Ambiguous wall times execute at
    their earlier UTC instant; nonexistent wall times advance to the first
    valid minute after the requested time.
    """
    current = _as_utc(now)
    if isinstance(schedule, AutomationIntervalSchedule):
        return current + timedelta(minutes=schedule.interval_minutes)
    zone = ZoneInfo(schedule.timezone)
    local = current.astimezone(zone)
    return _daily_after(local.date(), schedule.daily_time, schedule.timezone, current)


def _daily_after(
    local_date: date,
    requested_time: str,
    timezone: str,
    after: datetime,
) -> datetime:
    zone = ZoneInfo(timezone)
    requested = datetime.combine(local_date, _parse_wall_time(requested_time))
    candidates = _local_candidates(requested, zone)
    future = [candidate for candidate in candidates if candidate > after]
    if future:
        return min(future)
    # The requested local time may be in a DST gap.  Check each following
    # minute, bounded to the largest practical transition window.
    probe = requested + timedelta(minutes=1)
    for _ in range(240):
        candidates = _local_candidates(probe, zone)
        future = [candidate for candidate in candidates if candidate > after]
        if future:
            return min(future)
        probe += timedelta(minutes=1)
    return _daily_after(local_date + timedelta(days=1), requested_time, timezone, after)


def _parse_wall_time(value: str) -> wall_time:
    hour, minute = value.split(":")
    return wall_time(int(hour), int(minute))


def _local_candidates(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    values: list[datetime] = []
    for fold in (0, 1):
        aware = local.replace(tzinfo=zone, fold=fold)
        roundtrip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip == local:
            instant = aware.astimezone(UTC)
            if instant not in values:
                values.append(instant)
    return tuple(sorted(values))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class _StageMetrics:
    input_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    usage_attempted: int = 0
    usage_tokens: int | None = None


class AutomationWorkflowService:
    """Own the only automatic transition between the three fixed stages."""

    def __init__(
        self,
        database,
        *,
        monitoring_rules=None,
        batches=None,
        analyses=None,
        reports=None,
        ai_settings=None,
        repository=None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        available: bool = True,
    ) -> None:
        self.database = database
        self.repository = repository or AutomationWorkflowRepository(database)
        self._rules = monitoring_rules
        self._batches = batches
        self._analyses = analyses
        self._reports = reports
        self._ai = ai_settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic
        self.available = available
        self._closed = False
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._runner: asyncio.Task | None = None
        self._run_tasks: dict[int, asyncio.Task] = {}
        self._last_wall: datetime | None = None
        self._last_monotonic: float | None = None

    def initialize(self) -> None:
        self.repository.initialize()

    async def start(self) -> None:
        now = _as_utc(self._clock())
        await database_call(self.repository.reconcile_startup, now)
        resumable = await self._reconcile_active_runs()
        self._last_wall, self._last_monotonic = now, self._monotonic()
        if self.available and not self._closed and self._runner is None:
            self._runner = asyncio.create_task(self._timer(), name="automation-timer")
        for run_id in resumable:
            await self._launch_run(run_id)

    async def _reconcile_active_runs(self) -> tuple[int, ...]:
        """Resume only work whose linked child is durably settled."""
        resumable: list[int] = []
        runs = await database_call(self.repository.active_runs)
        for run in runs:
            stage = next(
                (
                    name
                    for name in AUTOMATION_STAGES
                    if (_latest_stage(run, name) is None)
                    or _latest_stage(run, name).status != "completed"
                ),
                None,
            )
            if stage is None:
                resumable.append(run.id)
                continue
            attempt = _latest_stage(run, stage)
            if attempt is None:
                await self._interrupt_recovered_run(run.id)
                continue
            if attempt.status == "queued":
                resumable.append(run.id)
                continue
            if attempt.status != "running" or attempt.child_id is None:
                await self._interrupt_recovered_run(run.id)
                continue
            try:
                child = await self._read_recovery_child(stage, attempt.child_id)
                status = _value(child, "status")
            except Exception:
                await self._interrupt_recovered_run(run.id)
                continue
            if status in {
                "queued",
                "running",
                "acquiring",
                "analysing",
                "judging",
                "composing",
                "interrupted",
                "paused_for_manual_action",
            }:
                await self._interrupt_recovered_run(run.id)
                continue
            await database_call(self.repository.prepare_recovered_stage, run.id, stage)
            resumable.append(run.id)
        return tuple(resumable)

    async def _interrupt_recovered_run(self, run_id: int) -> None:
        await database_call(
            self.repository.set_run_terminal,
            run_id,
            "interrupted",
            error=AutomationFailure(
                code="backend_restart", message="应用重启后需要从失败阶段重试。"
            ),
        )

    async def _read_recovery_child(self, stage: AutomationStageName, child_id: int):
        owner = {
            "collection": self._batches,
            "initial_analysis": self._analyses,
            "topic_report": self._reports,
        }[stage]
        if owner is None:
            raise AutomationWorkflowError("automation_unavailable")
        if stage == "collection" and hasattr(owner, "get_batch"):
            value = owner.get_batch(child_id)
        elif hasattr(owner, "read"):
            value = owner.read(child_id)
        elif getattr(owner, "repository", None) is not None:
            method = getattr(
                owner.repository, "get" if stage == "collection" else "read"
            )
            value = await database_call(method, child_id)
            return value
        else:
            raise AutomationWorkflowError("automation_unavailable")
        return await value if inspect.isawaitable(value) else value

    async def _timer(self) -> None:
        try:
            while not self._closed:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1.0)
                    return
                except TimeoutError:
                    pass
                try:
                    await self.tick()
                except Exception:
                    # Product errors are durably represented by occurrence/run
                    # state.  Never leak raw timer exceptions to the task loop.
                    continue
        finally:
            self._runner = None

    async def tick(self) -> None:
        async with self._lock:
            if self._closed or not self.available:
                return
            now = _as_utc(self._clock())
            monotonic = self._monotonic()
            jump = (
                self._last_wall is not None
                and self._last_monotonic is not None
                and (now - self._last_wall).total_seconds()
                - (monotonic - self._last_monotonic)
                > 5
            )
            self._last_wall, self._last_monotonic = now, monotonic
            claims = await database_call(
                self.repository.advance_due,
                now,
                missed_reason="clock_jump" if jump else None,
            )
            if jump:
                # ``advance_due`` deliberately processes bounded storage pages.
                # Drain every page for a forward jump so a large task set does
                # not leave an overdue task to be mistaken for a live trigger
                # on the next timer tick.
                has_due = getattr(self.repository, "has_due", None)
                while has_due is not None and await database_call(has_due, now):
                    await database_call(
                        self.repository.advance_due,
                        now,
                        missed_reason="clock_jump",
                    )
            for claim in claims:
                await self._admit_claim(claim, now)

    async def _admit_claim(
        self, claim: AutomationOccurrenceClaim, now: datetime
    ) -> None:
        try:
            task = await database_call(self.repository.get_task, claim.task_id)
            snapshot = await self._snapshot(task, now)
            run, _ = await database_call(
                self.repository.create_run,
                task_id=task.id,
                trigger="scheduled",
                admission_key=claim.admission_key,
                request_id=None,
                snapshot=snapshot,
                now=now,
                occurrence_id=claim.id,
            )
        except AutomationTaskNotFoundError:
            await self._safe_skip(claim.id, "monitoring_rule_not_found")
            return
        except AutomationWorkflowError as error:
            await self._safe_skip(claim.id, _reason_for_error(error.code))
            return
        except (AutomationRunActiveError, AutomationOccurrenceChangedError):
            await self._safe_skip(claim.id, "previous_run_active")
            return
        except (AutomationRepositoryUnavailableError, Exception):
            await self._safe_skip(claim.id, "dispatch_interrupted")
            return
        await self._launch_run(run.id)

    async def _safe_skip(self, occurrence_id: int, reason: str) -> None:
        try:
            await database_call(self.repository.skip_occurrence, occurrence_id, reason)
        except Exception:
            pass

    def create_task(self, payload: AutomationTaskCreate) -> AutomationTask:
        # A disabled task may retain a disabled rule for operator correction;
        # an enabled task always validates executable terms before persisting.
        rule = self._rule(payload.monitoring_rule_id)
        if rule is None:
            raise AutomationWorkflowError("automation_rule_not_found")
        if payload.name.strip() != payload.name:
            raise AutomationWorkflowError("automation_invalid_goal")
        try:
            compose_monitoring_terms(rule.monitoring_objects, rule.issue_keywords)
        except MonitoringRuleError:
            # Creation is harmless while disabled, but stores a visible blocked
            # task.  Enabling is rejected below.
            pass
        try:
            record = self.repository.create_task(payload, now=_as_utc(self._clock()))
        except AutomationTaskNameConflictError:
            raise AutomationWorkflowError("automation_task_name_conflict") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        return self._to_task(record)

    def replace_task(
        self,
        task_id: int,
        payload: AutomationTaskReplace,
    ) -> AutomationTask:
        self._get_task_record(task_id)
        rule = self._rule(payload.monitoring_rule_id)
        if payload.monitoring_rule_id is not None and rule is None:
            raise AutomationWorkflowError("automation_rule_not_found")
        if payload.name.strip() != payload.name:
            raise AutomationWorkflowError("automation_invalid_goal")
        if payload.enabled:
            self._validate_executable_rule(rule)
            self._validate_ai_configuration()
        now = _as_utc(self._clock())
        due = schedule_next_due(payload.schedule, now) if payload.enabled else None
        try:
            record = self.repository.replace_task(
                task_id,
                payload,
                now=now,
                next_due_at=due.isoformat() if due else None,
                anchor_at=now.isoformat() if due else None,
            )
        except AutomationTaskNotFoundError:
            raise AutomationWorkflowError("automation_task_not_found") from None
        except AutomationTaskChangedError:
            raise AutomationWorkflowError("automation_task_changed") from None
        except AutomationTaskNameConflictError:
            raise AutomationWorkflowError("automation_task_name_conflict") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        return self._to_task(record)

    def get_task(self, task_id: int) -> AutomationTask:
        return self._to_task(self._get_task_record(task_id))

    def list_tasks(
        self, *, limit: int = 50, before_id: int | None = None
    ) -> AutomationTaskList:
        try:
            records, cursor = self.repository.list_tasks(
                limit=limit, before_id=before_id
            )
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        return AutomationTaskList(
            tasks=[self._to_task(record) for record in records], next_before_id=cursor
        )

    def list_occurrences(
        self,
        task_id: int,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> AutomationOccurrenceList:
        try:
            rows, cursor = self.repository.occurrences(
                task_id, limit=limit, before_id=before_id
            )
        except AutomationTaskNotFoundError:
            raise AutomationWorkflowError("automation_task_not_found") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        return AutomationOccurrenceList(
            occurrences=[
                AutomationOccurrence(
                    id=row.id,
                    task_id=row.task_id,
                    task_revision=row.task_revision,
                    due_at=row.due_at,
                    status=row.status,
                    reason=row.reason,
                    run_id=row.run_id,
                    missed_count=row.missed_count,
                    missed_until=row.missed_until,
                    created_at=row.created_at,
                    admitted_at=row.admitted_at,
                    run_status=row.run_status,
                )
                for row in rows
            ],
            next_before_id=cursor,
        )

    def list_runs(
        self,
        task_id: int,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> AutomationRunList:
        try:
            rows, cursor = self.repository.list_runs(
                task_id, limit=limit, before_id=before_id
            )
        except AutomationTaskNotFoundError:
            raise AutomationWorkflowError("automation_task_not_found") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        return AutomationRunList(
            runs=[self._to_run(row) for row in rows], next_before_id=cursor
        )

    def get_run(self, run_id: int) -> AutomationRun:
        try:
            return self._to_run(self.repository.get_run(run_id))
        except AutomationRunNotFoundError:
            raise AutomationWorkflowError("automation_run_not_found") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None

    async def run_now(self, task_id: int, payload: AutomationRunNow) -> AutomationRun:
        async with self._request_lock:
            return await self._run_now(task_id, payload)

    async def _run_now(self, task_id: int, payload: AutomationRunNow) -> AutomationRun:
        intent_hash = _intent_hash("run_now", task_id, payload)
        replay = await self._replay_request(payload.request_id, intent_hash)
        if replay is not None:
            return replay
        if self._closed or not self.available:
            raise AutomationWorkflowError("automation_unavailable")
        task = self._get_task_record(task_id)
        self._validate_executable_rule(self._rule(task.monitoring_rule_id))
        now = _as_utc(self._clock())
        snapshot = await self._snapshot(task, now)
        try:
            run, _ = await database_call(
                self.repository.create_run,
                task_id=task_id,
                trigger="manual",
                admission_key=f"manual:{payload.request_id}",
                request_id=payload.request_id,
                snapshot=snapshot,
                now=now,
                request_intent_hash=intent_hash,
            )
        except AutomationRunActiveError:
            raise AutomationWorkflowError("automation_run_active") from None
        except AutomationRequestConflictError:
            raise AutomationWorkflowError("automation_request_conflict") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        await self._launch_run(run.id)
        return self._to_run(run)

    async def cancel_run(
        self,
        run_id: int,
        payload: AutomationRunCancel,
    ) -> AutomationRun:
        async with self._request_lock:
            return await self._cancel_run(run_id, payload)

    async def _cancel_run(
        self,
        run_id: int,
        payload: AutomationRunCancel,
    ) -> AutomationRun:
        intent_hash = _intent_hash("cancel", run_id, payload)
        replay = await self._replay_request(payload.request_id, intent_hash)
        if replay is not None:
            return replay
        try:
            before_cancel = await database_call(self.repository.get_run, run_id)
            run = await database_call(
                self.repository.request_cancel,
                run_id,
                expected_revision=payload.expected_revision,
                request_id=payload.request_id,
                request_intent_hash=intent_hash,
            )
        except AutomationRunNotFoundError:
            raise AutomationWorkflowError("automation_run_not_found") from None
        except AutomationRunChangedError:
            raise AutomationWorkflowError("automation_run_changed") from None
        except AutomationRunNotActiveError:
            raise AutomationWorkflowError("automation_run_not_active") from None
        except AutomationRequestConflictError:
            raise AutomationWorkflowError("automation_request_conflict") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        task = self._run_tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
            await _cancel_and_drain(task)
        await self._cancel_child(before_cancel)
        return self._to_run(run)

    async def retry_run(
        self,
        run_id: int,
        payload: AutomationRunRetry,
    ) -> AutomationRun:
        async with self._request_lock:
            return await self._retry_run(run_id, payload)

    async def _retry_run(
        self,
        run_id: int,
        payload: AutomationRunRetry,
    ) -> AutomationRun:
        intent_hash = _intent_hash("retry", run_id, payload)
        replay = await self._replay_request(payload.request_id, intent_hash)
        if replay is not None:
            return replay
        try:
            run = await database_call(
                self.repository.retry_run,
                run_id,
                expected_revision=payload.expected_revision,
                request_id=payload.request_id,
                request_intent_hash=intent_hash,
                now=_as_utc(self._clock()),
            )
        except AutomationRunNotFoundError:
            raise AutomationWorkflowError("automation_run_not_found") from None
        except AutomationRunChangedError:
            raise AutomationWorkflowError("automation_run_changed") from None
        except AutomationRunNotRetryableError:
            raise AutomationWorkflowError("automation_run_not_retryable") from None
        except AutomationRunActiveError:
            raise AutomationWorkflowError("automation_run_active") from None
        except AutomationRequestConflictError:
            raise AutomationWorkflowError("automation_request_conflict") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        await self._launch_run(run_id)
        return self._to_run(run)

    async def _replay_request(
        self, request_id: str, intent_hash: str
    ) -> AutomationRun | None:
        try:
            row = await database_call(self.repository.request, request_id)
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None
        if row is None:
            return None
        if row["intent_hash"] != intent_hash:
            raise AutomationWorkflowError("automation_request_conflict")
        try:
            # The request row proves which durable run was admitted.  Return
            # its current projection so a retry after an ambiguous response
            # never duplicates work or rewinds the client to the queued view
            # captured at admission time.
            if row["run_id"] is not None:
                return self._to_run(self.repository.get_run(row["run_id"]))
            return AutomationRun.model_validate_json(row["result_json"])
        except Exception:
            raise AutomationWorkflowError("automation_storage_unavailable") from None

    async def _launch_run(self, run_id: int) -> None:
        async with self._lock:
            task = self._run_tasks.get(run_id)
            if task is None or task.done():
                task = asyncio.create_task(
                    self._execute_run(run_id), name=f"automation-run-{run_id}"
                )
                self._run_tasks[run_id] = task

    async def _execute_run(self, run_id: int) -> None:
        try:
            run = await database_call(self.repository.get_run, run_id)
            for stage in AUTOMATION_STAGES:
                run = await database_call(self.repository.get_run, run_id)
                if run.cancel_requested or run.status == "cancelled":
                    return
                attempt = _latest_stage(run, stage)
                if attempt is None or attempt.status == "completed":
                    continue
                if attempt.status not in {"queued", "interrupted"}:
                    await database_call(
                        self.repository.set_run_terminal,
                        run_id,
                        "failed",
                        error=AutomationFailure(
                            code="stage_failed", message="自动任务阶段未完成。"
                        ),
                    )
                    return
                await database_call(self.repository.start_stage, run_id, stage)
                try:
                    if stage == "collection":
                        child_id, success, metrics = await self._execute_collection(
                            run_id, attempt
                        )
                    elif stage == "initial_analysis":
                        child_id, success, metrics = await self._execute_analysis(
                            run_id, attempt
                        )
                    else:
                        child_id, success, metrics = await self._execute_report(
                            run_id, attempt
                        )
                except asyncio.CancelledError:
                    return
                except AutomationWorkflowError as error:
                    await database_call(
                        self.repository.finish_stage,
                        run_id,
                        stage,
                        "configuration_blocked"
                        if error.code.startswith("ai_")
                        else "failed",
                        error=AutomationFailure(code=error.code, message=error.message),
                    )
                    await database_call(
                        self.repository.set_run_terminal,
                        run_id,
                        "configuration_blocked"
                        if error.code.startswith("ai_")
                        else "failed",
                        error=AutomationFailure(code=error.code, message=error.message),
                    )
                    return
                except Exception:
                    await database_call(
                        self.repository.finish_stage,
                        run_id,
                        stage,
                        "failed",
                        error=AutomationFailure(
                            code="stage_failed",
                            message="自动任务阶段执行失败，请重试。",
                        ),
                    )
                    await database_call(
                        self.repository.set_run_terminal,
                        run_id,
                        "failed",
                        error=AutomationFailure(
                            code="stage_failed",
                            message="自动任务阶段执行失败，请重试。",
                        ),
                    )
                    return
                await database_call(
                    self.repository.finish_stage,
                    run_id,
                    stage,
                    "completed" if success else "failed",
                    input_count=metrics.input_count,
                    success_count=metrics.success_count,
                    failure_count=metrics.failure_count,
                    usage_attempted=metrics.usage_attempted,
                    usage_tokens=metrics.usage_tokens,
                    error=(
                        None
                        if success
                        else AutomationFailure(
                            code="stage_failed",
                            message="自动任务阶段执行失败，请从失败阶段重试。",
                        )
                    ),
                )
                if not success:
                    await database_call(
                        self.repository.set_run_terminal,
                        run_id,
                        "failed",
                        error=AutomationFailure(
                            code="stage_failed",
                            message="自动任务阶段未完成，请从失败阶段重试。",
                        ),
                    )
                    return
            run = await database_call(self.repository.get_run, run_id)
            if run.status not in ACTIVE_RUN_STATUSES:
                return
            # An empty membership is a valid, zero-model successful run.
            members = await database_call(self.repository.run_contents, run_id)
            outcome = "no_new_sources" if not members else "completed"
            report_attempt = _latest_stage(run, "topic_report")
            await database_call(
                self.repository.set_run_terminal,
                run_id,
                "completed",
                outcome=outcome,
                topic_report_id=(
                    _value(report_attempt, "child_id") if report_attempt else None
                ),
            )
        finally:
            self._run_tasks.pop(run_id, None)

    async def _execute_collection(
        self, run_id: int, attempt: AutomationStageAttemptRecord
    ):
        run = await database_call(self.repository.get_run, run_id)
        snapshot = run.snapshot
        if self._batches is None:
            raise AutomationWorkflowError("automation_unavailable")
        child_id = attempt.child_id
        if child_id is not None:
            child = await self._read_recovery_child("collection", child_id)
        else:
            method = getattr(self._batches, "start_workflow_batch", None)
            if method is not None:
                child = await method(
                    monitoring_rule_id=snapshot.monitoring_rule_id,
                    rule_name=snapshot.rule_name,
                    terms=tuple(snapshot.terms),
                    platforms=tuple(snapshot.platforms),
                    max_results_per_term=snapshot.max_results_per_term,
                    operation_key=attempt.operation_key,
                )
            else:
                child = await self._batches.start_batch(
                    SearchBatchCreate(
                        monitoring_rule_id=snapshot.monitoring_rule_id,
                        platforms=list(snapshot.platforms),
                        max_results_per_term=snapshot.max_results_per_term,
                    )
                )
            child_id = _value(child, "id")
            await database_call(
                self.repository.set_stage_child,
                run_id,
                "collection",
                child_kind="search_batch",
                child_id=child_id,
            )
        child = await self._wait_child(self._batches, "get_batch", child_id, child)
        status = _value(child, "status")
        items = tuple(_value(child, "items", ()) or ())
        failed_items = sum(
            _value(item, "status") in {"failed", "skipped", "cancelled"}
            for item in items
        )
        if status not in {"completed", "completed_with_failures"}:
            return (
                child_id,
                False,
                _StageMetrics(
                    input_count=len(items),
                    success_count=max(0, len(items) - failed_items),
                    failure_count=failed_items,
                ),
            )
        entries = ()
        if hasattr(self.repository, "batch_contents"):
            raw_entries = await database_call(self.repository.batch_contents, child_id)
            entries = tuple(_batch_content_entry(entry) for entry in raw_entries)
        inserted = await database_call(
            self.repository.register_task_contents,
            snapshot.task_id,
            run_id,
            entries,
        )
        # The stage input is the current run's first-membership set.  Repeated
        # global observations deliberately do not enter this run.
        # An empty completed batch is a valid collection result. Insertion
        # count is observability, never stage success.
        return (
            child_id,
            True,
            _StageMetrics(input_count=len(entries), success_count=len(inserted)),
        )

    async def _execute_analysis(
        self, run_id: int, attempt: AutomationStageAttemptRecord
    ):
        if self._analyses is None:
            raise AutomationWorkflowError("automation_unavailable")
        run = await database_call(self.repository.get_run, run_id)
        ids = await database_call(self.repository.run_contents, run_id)
        if not ids:
            return None, True, _StageMetrics()
        child_id = attempt.child_id
        if child_id is not None:
            child = await self._read_recovery_child("initial_analysis", child_id)
        else:
            method = getattr(self._analyses, "workflow_admit", None)
            if method is not None:
                child = await method(
                    result_ids=ids,
                    operation_key=attempt.operation_key,
                    snapshot=run.snapshot,
                )
            else:
                # A normal ContentAnalysisService supports the same strict
                # explicit selection contract; prompt versions are read-only data.
                from longtian_api.repositories.analysis_settings import (
                    AnalysisSettingsRepository,
                )
                from longtian_api.schemas.content_analyses import AnalysisCreate

                settings = AnalysisSettingsRepository(self.database).read()
                if settings is None:
                    raise AutomationWorkflowError("ai_configuration_required")
                payload = AnalysisCreate(
                    request_id=str(uuid4()),
                    configuration_revision=run.snapshot.ai_configuration_revision or 1,
                    initial_prompt_version_id=settings.initial_prompt.id,
                    report_prompt_version_id=settings.report_prompt.id,
                    force_refresh=False,
                    selection={"kind": "explicit", "result_ids": list(ids)},
                )
                child = await self._analyses.create(payload)
            child_id = _value(_value(child, "job", child), "id")
            if child_id is None:
                return None, True, _StageMetrics()
            await database_call(
                self.repository.set_stage_child,
                run_id,
                "initial_analysis",
                child_kind="content_analysis_job",
                child_id=child_id,
            )
        child = await self._wait_child(self._analyses, "read", child_id, child)
        status = _value(child, "status")
        counts = _value(child, "counts", {})
        total = int(_value(counts, "total", len(ids)) or 0)
        completed = int(_value(counts, "completed", 0) or 0)
        unavailable = sum(
            int(_value(counts, name, 0) or 0)
            for name in (
                "input_incomplete",
                "unsupported",
                "failed",
                "cancelled",
                "interrupted",
            )
        )
        usage = _value(child, "usage", {})
        return (
            child_id,
            status == "completed",
            _StageMetrics(
                input_count=total,
                success_count=min(completed, total),
                failure_count=min(unavailable, max(0, total - completed)),
                usage_attempted=int(_value(usage, "attempted_requests", 0) or 0),
                usage_tokens=_value(usage, "total_tokens"),
            ),
        )

    async def _execute_report(self, run_id: int, attempt: AutomationStageAttemptRecord):
        if self._reports is None:
            raise AutomationWorkflowError("automation_unavailable")
        run = await database_call(self.repository.get_run, run_id)
        analysis_attempt = _latest_stage(run, "initial_analysis")
        child_id = _value(analysis_attempt, "child_id") if analysis_attempt else None
        report_id = attempt.child_id
        if report_id is not None:
            child = await self._read_recovery_child("topic_report", report_id)
        elif child_id is not None and hasattr(self._reports, "workflow_admit"):
            child = await self._reports.workflow_admit(
                run_id=run_id,
                analysis_job_id=child_id,
                operation_key=attempt.operation_key,
                snapshot=run.snapshot,
            )
        elif hasattr(self._reports, "workflow_admit"):
            child = await self._reports.workflow_admit(
                run_id=run_id,
                analysis_job_id=None,
                operation_key=attempt.operation_key,
                snapshot=run.snapshot,
            )
        else:
            raise AutomationWorkflowError("automation_unavailable")
        if report_id is None:
            report_id = _value(child, "id")
            if report_id is None:
                raise AutomationWorkflowError("automation_unavailable")
            await database_call(
                self.repository.set_stage_child,
                run_id,
                "topic_report",
                child_kind="topic_report",
                child_id=report_id,
            )
        child = await self._wait_report(self._reports, report_id, child)
        status = _value(child, "status")
        coverage = _value(child, "coverage", {})
        total = int(_value(coverage, "total", 0) or 0)
        successful = sum(
            int(_value(coverage, name, 0) or 0)
            for name in ("relevant", "irrelevant", "uncertain")
        )
        failed = sum(
            int(_value(coverage, name, 0) or 0)
            for name in ("unavailable", "failed", "cancelled", "interrupted")
        )
        usage = _value(_value(child, "usage", {}), "total", {})
        return (
            report_id,
            status in {"completed", "empty"},
            _StageMetrics(
                input_count=total,
                success_count=min(successful, total),
                failure_count=min(failed, max(0, total - successful)),
                usage_attempted=int(_value(usage, "attempted_requests", 0) or 0),
                usage_tokens=_value(usage, "total_tokens"),
            ),
        )

    async def _wait_report(self, owner, report_id: int, initial):
        child = initial
        while _value(child, "status") in {"queued", "judging", "composing"}:
            await asyncio.sleep(0.05)
            getter = getattr(owner, "read", None)
            if getter is None and getattr(owner, "repository", None) is not None:
                getter = getattr(owner.repository, "read", None)
            if getter is None:
                break
            value = getter(report_id)
            child = await value if inspect.isawaitable(value) else value
        return child

    async def _wait_child(self, owner, method_name: str, child_id: int, initial):
        child = initial
        getter = owner
        if "." in method_name:
            getter = getattr(owner, method_name.split(".", 1)[0], None)
            method_name = method_name.split(".", 1)[1]
        method = getattr(getter, method_name, None)
        if method is None and getattr(owner, "repository", None) is not None:
            method = getattr(owner.repository, method_name, None)
            getter = owner.repository
        while _value(child, "status") in {
            "queued",
            "running",
            "judging",
            "composing",
            "acquiring",
            "analysing",
        }:
            await asyncio.sleep(0.05)
            method = getattr(getter, method_name, None)
            if method is None:
                break
            value = method(child_id)
            child = await value if inspect.isawaitable(value) else value
        return child

    async def shutdown(self) -> None:
        self._closed = True
        self._stop.set()
        if self._runner is not None:
            await settle(self._runner)
        tasks = tuple(self._run_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            await _cancel_and_drain(task)
        self._run_tasks.clear()

    async def _cancel_child(self, run) -> None:
        """Best-effort cancellation of the currently owned domain child.

        The workflow row is fenced first, so late child callbacks cannot
        advance a cancelled run.  Child cancellation is then drained through
        its own service boundary to release browser/AI ownership as well.
        """
        stage = run.active_stage
        if stage is None:
            return
        attempt = _latest_stage(run, stage)
        child_id = _value(attempt, "child_id")
        if child_id is None:
            return
        try:
            if stage == "collection" and self._batches is not None:
                cancel = getattr(self._batches, "cancel_batch", None)
                get = getattr(self._batches, "get_batch", None)
                if cancel is not None and get is not None:
                    child = get(child_id)
                    child = await child if inspect.isawaitable(child) else child
                    revision = _value(child, "revision")
                    if revision is not None:
                        payload = SearchBatchCancel(expected_revision=revision)
                        value = cancel(child_id, payload)
                        if inspect.isawaitable(value):
                            await settle(value)
            elif stage == "initial_analysis" and self._analyses is not None:
                cancel = getattr(self._analyses, "cancel", None)
                if cancel is not None:
                    value = cancel(child_id)
                    if inspect.isawaitable(value):
                        await settle(value)
            elif stage == "topic_report" and self._reports is not None:
                cancel = getattr(self._reports, "cancel", None)
                get = getattr(self._reports, "read", None)
                if cancel is not None and get is not None:
                    child = get(child_id)
                    child = await child if inspect.isawaitable(child) else child
                    revision = _value(child, "revision")
                    if revision is not None:
                        payload = ReportCancel(
                            request_id=str(uuid4()), expected_revision=revision
                        )
                        value = cancel(child_id, payload)
                        if inspect.isawaitable(value):
                            await settle(value)
        except (asyncio.CancelledError, Exception):
            # Cancellation of the workflow is already durable.  A child that
            # disappeared or was concurrently settled must not turn a 202
            # cancellation into an unhandled transport error.
            return

    async def _snapshot(
        self, task: AutomationTaskRecord, now: datetime
    ) -> AutomationSnapshot:
        rule = self._rule(task.monitoring_rule_id)
        self._validate_executable_rule(rule)
        if rule is None:
            raise AutomationWorkflowError("automation_rule_not_found")
        try:
            terms = compose_monitoring_terms(
                rule.monitoring_objects, rule.issue_keywords
            )
        except MonitoringRuleError:
            raise AutomationWorkflowError("automation_rule_invalid") from None
        ai_revision = ai_base = ai_model = None
        initial_prompt_version_id = report_prompt_version_id = None
        if self._ai is not None:
            try:
                settings = self._validate_ai_configuration(self._ai.read())
                ai_revision = settings.revision or None
                ai_base, ai_model = settings.base_url, settings.model
                from longtian_api.repositories.analysis_settings import (
                    AnalysisSettingsRepository,
                )

                prompt_settings = AnalysisSettingsRepository(self.database).read()
                initial_prompt_version_id = prompt_settings.initial_prompt.id
                report_prompt_version_id = prompt_settings.report_prompt.id
            except AIError:
                raise AutomationWorkflowError("ai_configuration_required") from None
        return AutomationSnapshot(
            task_id=task.id,
            task_revision=task.revision,
            task_name=task.name,
            monitoring_rule_id=task.monitoring_rule_id,
            rule_name=rule.name,
            terms=list(terms),
            platforms=list(task.platforms),
            max_results_per_term=task.max_results_per_term,
            analysis_goal=task.analysis_goal,
            analysis_goal_hash=hashlib.sha256(task.analysis_goal.encode()).hexdigest(),
            ai_configuration_revision=ai_revision,
            ai_base_url=ai_base,
            ai_model=ai_model,
            initial_prompt_version_id=initial_prompt_version_id,
            report_prompt_version_id=report_prompt_version_id,
            initial_template_version=INITIAL_SCHEMA_VERSION,
            report_template_version=REPORT_SCHEMA_VERSION,
            admitted_at=now.isoformat(),
        )

    def _rule(self, rule_id: int | None):
        if rule_id is None or self._rules is None:
            return None
        try:
            if hasattr(self._rules, "list_rules"):
                return next(
                    (
                        rule
                        for rule in self._rules.list_rules().rules
                        if rule.id == rule_id
                    ),
                    None,
                )
            if hasattr(self._rules, "get_rule"):
                return self._rules.get_rule(rule_id)
        except Exception:
            return None
        return None

    @staticmethod
    def _validate_executable_rule(rule) -> None:
        if rule is None:
            raise AutomationWorkflowError("automation_rule_not_found")
        if not rule.enabled:
            raise AutomationWorkflowError("automation_rule_disabled")
        try:
            if len(rule.terms) > 20:
                raise AutomationWorkflowError("automation_rule_invalid")
            compose_monitoring_terms(rule.monitoring_objects, rule.issue_keywords)
        except MonitoringRuleError:
            raise AutomationWorkflowError("automation_rule_invalid") from None

    def _validate_ai_configuration(self, settings=None):
        """Reject activation without a complete, credential-backed provider."""
        if self._ai is None:
            return None
        if settings is None:
            try:
                settings = self._ai.read()
            except AIError:
                raise AutomationWorkflowError("ai_configuration_required") from None
        if not (
            getattr(settings, "revision", 0)
            and getattr(settings, "base_url", None)
            and getattr(settings, "model", None)
            and getattr(settings, "has_api_key", True)
        ):
            raise AutomationWorkflowError("ai_configuration_required")
        return settings

    def _get_task_record(self, task_id: int) -> AutomationTaskRecord:
        try:
            return self.repository.get_task(task_id)
        except AutomationTaskNotFoundError:
            raise AutomationWorkflowError("automation_task_not_found") from None
        except AutomationRepositoryUnavailableError:
            raise AutomationWorkflowError("automation_storage_unavailable") from None

    def _to_task(self, record: AutomationTaskRecord) -> AutomationTask:
        schedule: AutomationSchedule
        if record.schedule_kind == "interval":
            schedule = AutomationIntervalSchedule(
                kind="interval", interval_minutes=record.interval_minutes
            )
        else:
            schedule = AutomationDailySchedule(
                kind="daily", daily_time=record.daily_time, timezone=record.timezone
            )
        return AutomationTask(
            id=record.id,
            name=record.name,
            monitoring_rule_id=record.monitoring_rule_id,
            rule_name=record.rule_name,
            rule_state=record.rule_state,
            platforms=list(record.platforms),
            max_results_per_term=record.max_results_per_term,
            analysis_goal=record.analysis_goal,
            schedule=schedule,
            enabled=record.enabled,
            revision=record.revision,
            anchor_at=record.anchor_at,
            next_due_at=record.next_due_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            latest_run=AutomationWorkflowService._to_run(record.latest_run)
            if record.latest_run
            else None,
            available=self.available,
        )

    @staticmethod
    def _to_run(record) -> AutomationRun:
        attempts = {stage: _latest_stage(record, stage) for stage in AUTOMATION_STAGES}
        stages = []
        for stage in AUTOMATION_STAGES:
            attempt = attempts[stage]
            if attempt is None:
                raise AutomationWorkflowError("automation_storage_unavailable")
            stages.append(_to_stage(attempt))
        return AutomationRun(
            id=record.id,
            admission_key=record.admission_key,
            request_id=record.request_id,
            task_id=record.task_id,
            trigger=record.trigger,
            task_revision=record.task_revision,
            snapshot=record.snapshot,
            status=record.status,
            active_stage=record.active_stage,
            stages=stages,
            attempts=[_to_stage(attempt) for attempt in record.stages],
            cancel_requested=record.cancel_requested,
            outcome=record.outcome,
            topic_report_id=record.topic_report_id,
            error=record.error,
            revision=record.revision,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )


def _latest_stage(record, stage: AutomationStageName):
    candidates = [item for item in record.stages if item.stage == stage]
    return max(candidates, key=lambda item: item.attempt_number) if candidates else None


def _to_stage(attempt) -> AutomationStage:
    return AutomationStage(
        name=attempt.stage,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        child_kind=attempt.child_kind,
        child_id=attempt.child_id,
        input_count=attempt.input_count,
        success_count=attempt.success_count,
        failure_count=attempt.failure_count,
        usage_attempted=attempt.usage_attempted,
        usage_tokens=attempt.usage_tokens,
        error=attempt.error,
        created_at=attempt.created_at,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
    )


def _value(value, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _batch_content_entry(value) -> BatchContentRecord:
    """Normalize adapter/fake rows at the workflow boundary."""
    return BatchContentRecord(
        content_id=int(_value(value, "content_id", _value(value, "id"))),
        collection_run_id=_value(
            value, "collection_run_id", _value(value, "source_run_id")
        ),
        first_seen_at=str(
            _value(value, "first_seen_at", _value(value, "first_observed_at", ""))
        ),
    )


def _intent_hash(action: str, target: int, payload) -> str:
    body = (
        payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    )
    encoded = json.dumps(
        {"action": action, "target": target, "payload": body},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reason_for_error(code: str) -> str:
    return {
        "automation_rule_not_found": "monitoring_rule_not_found",
        "automation_rule_disabled": "monitoring_rule_disabled",
        "automation_rule_invalid": "invalid_monitoring_rule",
        "ai_configuration_required": "configuration_unavailable",
        "automation_storage_unavailable": "storage_unavailable",
    }.get(code, "dispatch_interrupted")


async def _cancel_and_drain(task: asyncio.Task | None) -> None:
    if task is None:
        return
    if not task.done() and not task.cancelling():
        task.cancel()
    try:
        await settle(task)
    except asyncio.CancelledError:
        pass
