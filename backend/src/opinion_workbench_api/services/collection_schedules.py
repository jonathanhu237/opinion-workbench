"""Lifespan interval admission; batch execution remains with its existing owner."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime

from opinion_workbench_api.collection_timing import utc, utc_now
from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.collection_schedules import (
    CollectionScheduleRepository,
    ScheduleRecord,
)
from opinion_workbench_api.schemas.collection_schedules import (
    MAX_INTERVAL_MINUTES,
    CollectionSchedule,
    CollectionScheduleCreate,
    CollectionScheduleList,
    CollectionScheduleReplace,
)
from opinion_workbench_api.search_platforms import SEARCH_PLATFORMS
from opinion_workbench_api.services.collection_schedule_errors import (
    CollectionScheduleError,
)
from opinion_workbench_api.services.monitoring_rules import (
    MonitoringRuleError,
    compose_monitoring_terms,
)
from opinion_workbench_api.services.search_batches import (
    ScheduledAdmissionError,
    SearchBatchError,
    SearchBatchService,
)
from opinion_workbench_api.services.search_runs import MAX_SEARCH_TERMS
from opinion_workbench_api.services.settled_tasks import database_call, settle


class CollectionScheduleService:
    def __init__(
        self,
        database: Database,
        batches: SearchBatchService,
        *,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        available: bool = False,
    ):
        self.repository = CollectionScheduleRepository(database)
        self._batches = batches
        self._clock = clock
        self._monotonic = monotonic
        self.available = available
        self._closed = False
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._last_wall: datetime | None = None
        self._last_monotonic: float | None = None

    def create(self, payload: CollectionScheduleCreate) -> CollectionSchedule:
        return self._save(payload, schedule_id=None)

    def replace(
        self, schedule_id: int, payload: CollectionScheduleReplace
    ) -> CollectionSchedule:
        return self._save(payload, schedule_id=schedule_id)

    def _save(
        self,
        payload: CollectionScheduleCreate | CollectionScheduleReplace,
        *,
        schedule_id: int | None,
    ) -> CollectionSchedule:
        if self._closed:
            raise CollectionScheduleError("collection_schedule_unavailable")
        minutes = payload.interval.value * (
            60 if payload.interval.unit == "hours" else 1
        )
        if minutes > MAX_INTERVAL_MINUTES:
            raise CollectionScheduleError("invalid_collection_interval")
        enabled = isinstance(payload, CollectionScheduleReplace) and payload.enabled
        rule = (
            self.repository.rule(payload.monitoring_rule_id)
            if payload.monitoring_rule_id is not None
            else None
        )
        if enabled:
            if rule is None:
                raise CollectionScheduleError("monitoring_rule_not_found")
            if not rule.enabled:
                raise CollectionScheduleError("monitoring_rule_disabled")
            try:
                terms = compose_monitoring_terms(
                    rule.monitoring_objects, rule.issue_keywords
                )
            except MonitoringRuleError:
                raise CollectionScheduleError("invalid_collection_schedule") from None
            if len(terms) > MAX_SEARCH_TERMS:
                raise CollectionScheduleError("too_many_search_terms")
        return self._project(
            self.repository.save(
                schedule_id=schedule_id,
                expected_revision=payload.expected_revision
                if isinstance(payload, CollectionScheduleReplace)
                else None,
                rule=rule,
                platforms=tuple(p for p in SEARCH_PLATFORMS if p in payload.platforms),
                max_results_per_term=payload.max_results_per_term,
                **(
                    {"max_total_results": payload.max_total_results}
                    if payload.max_total_results is not None
                    else {}
                ),
                interval_minutes=minutes,
                enabled=enabled,
                now=utc(self._clock()),
            )
        )

    def get(self, schedule_id: int) -> CollectionSchedule:
        return self._project(self.repository.get(schedule_id))

    def list(
        self, *, limit: int = 50, before_id: int | None = None
    ) -> CollectionScheduleList:
        records, cursor = self.repository.list(limit=limit, before_id=before_id)
        return CollectionScheduleList(
            schedules=[self._project(record) for record in records],
            next_before_id=cursor,
        )

    def _project(self, record: ScheduleRecord) -> CollectionSchedule:
        state = "deleted"
        if record.rule is not None:
            state = "enabled" if record.rule.enabled else "disabled"
            if record.rule.enabled:
                try:
                    if (
                        len(
                            compose_monitoring_terms(
                                record.rule.monitoring_objects,
                                record.rule.issue_keywords,
                            )
                        )
                        > MAX_SEARCH_TERMS
                    ):
                        state = "invalid"
                except MonitoringRuleError:
                    state = "invalid"
        values = {
            field.name: getattr(record, field.name)
            for field in fields(record)
            if field.name != "rule"
        }
        values["platforms"] = list(record.platforms)
        return CollectionSchedule(**values, rule_state=state, available=self.available)

    async def start(self) -> None:
        """Storage-only startup, before the first monotonic wait; never catch up."""
        now = utc(self._clock())
        await database_call(self.repository.reconcile_startup, now)
        self._last_wall, self._last_monotonic = now, self._monotonic()
        if self.available and not self._closed and self._task is None:
            self._task = asyncio.create_task(
                self._run(), name="collection-schedule-timer"
            )

    async def tick(self) -> None:
        """One deterministic clock-injected admission pass, also used by tests."""
        async with self._lock:
            if self._closed or not self.available:
                return
            now, monotonic = utc(self._clock()), self._monotonic()
            jump = (
                self._last_wall is not None
                and self._last_monotonic is not None
                and (
                    (now - self._last_wall).total_seconds()
                    - (monotonic - self._last_monotonic)
                    > 5
                )
            )
            self._last_wall, self._last_monotonic = now, monotonic
            if jump:
                # All schedules crossed this clock jump, not only the first page.
                while not self._closed and await database_call(
                    self.repository.advance_due, now, missed_reason="clock_jump"
                ):
                    pass
                return
            claims = await database_call(
                self.repository.advance_due,
                now,
            )
            if isinstance(claims, int):
                return
            for claim in claims:
                if self._closed:
                    await database_call(
                        self.repository.skip,
                        claim.dispatch_token,
                        "dispatch_interrupted",
                    )
                    continue
                try:
                    if claim.monitoring_rule_id is not None:
                        try:
                            rule = await database_call(
                                self.repository.rule, claim.monitoring_rule_id
                            )
                        except CollectionScheduleError as error:
                            if error.code == "monitoring_rule_not_found":
                                raise ScheduledAdmissionError(
                                    "monitoring_rule_not_found"
                                ) from None
                            raise
                        try:
                            compose_monitoring_terms(
                                rule.monitoring_objects, rule.issue_keywords
                            )
                        except MonitoringRuleError:
                            raise ScheduledAdmissionError(
                                "invalid_monitoring_rule"
                            ) from None
                    await self._batches.start_scheduled_batch(
                        claim,
                        timestamp=now.isoformat(),
                        admission_allowed=lambda: not self._closed,
                    )
                except ScheduledAdmissionError as error:
                    await database_call(
                        self.repository.skip, claim.dispatch_token, error.reason
                    )
                except SearchBatchError as error:
                    reason = {
                        "monitoring_rule_not_found": "monitoring_rule_not_found",
                        "monitoring_rule_disabled": "monitoring_rule_disabled",
                        "too_many_search_terms": "too_many_search_terms",
                        "browser_operation_active": "browser_operation_active",
                    }.get(error.code, "storage_unavailable")
                    await database_call(
                        self.repository.skip, claim.dispatch_token, reason
                    )
                except CollectionScheduleError:
                    await database_call(
                        self.repository.skip,
                        claim.dispatch_token,
                        "storage_unavailable",
                    )
                except Exception:
                    # A linked dispatch cannot be converted into an unlinked skip.
                    # An uncertain unlinked claim is interrupted, never retried.
                    await database_call(
                        self.repository.skip,
                        claim.dispatch_token,
                        "dispatch_interrupted",
                    )

    async def _run(self) -> None:
        while not self._closed:
            try:
                # asyncio timeout uses the loop's monotonic clock, not wall time.
                await asyncio.wait_for(self._stop.wait(), timeout=1.0)
                return
            except TimeoutError:
                pass
            try:
                await self.tick()
            except CollectionScheduleError:
                # Durable key/next-due fences survive storage recovery; no raw logs.
                pass

    async def shutdown(self) -> None:
        self._closed = True
        self._stop.set()
        if self._task is not None:
            await settle(self._task)
        # Also drain a direct/in-flight tick before other lifespan owners close.
        async with self._lock:
            pass
