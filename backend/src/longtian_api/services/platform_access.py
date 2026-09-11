"""Shared, cancellable pacing for active platform requests."""

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from longtian_api.repositories.platform_access import (
    PlatformAccessConflict,
    PlatformAccessRepository,
    parse_timestamp,
)
from longtian_api.schemas.platform_access import (
    PlatformAccessDiagnostic,
    PlatformAccessSettings,
    PlatformAccessSnapshot,
    PlatformAccessUpdate,
    default_platform_access_snapshot,
)
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.settled_tasks import database_call


class PlatformAccessBlockedError(Exception):
    """An explicit platform block requires user acknowledgement/continue."""

    def __init__(self, diagnostic: PlatformAccessDiagnostic | None = None):
        super().__init__("platform_access_blocked")
        self.diagnostic = diagnostic


class PlatformCooldownActiveError(PlatformAccessBlockedError):
    """The platform supplied a cooldown which has not elapsed yet."""


class PlatformAccessCoordinator:
    """Serialize controlled starts independently for each platform.

    Only the small interval between deciding to access and recording its start is
    protected by the per-platform asyncio lock. SQLite transactions are opened
    by the repository for that short state update; network/browser work happens
    after ``wait_for_turn`` returns and never inside a transaction.
    """

    def __init__(
        self,
        repository: PlatformAccessRepository | None = None,
        *,
        database=None,
        clock: Callable[[], float] | None = None,
        wall_clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[Any]] | None = None,
    ) -> None:
        if repository is not None and database is not None:
            raise ValueError("provide repository or database, not both")
        self.repository = repository or PlatformAccessRepository(database)
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._wake_events: dict[str, asyncio.Event] = {}
        self._last_started_monotonic: dict[str, float] = {}
        self._closed = False
        self._blocked: dict[str, PlatformAccessDiagnostic] = {}

    def initialize(self) -> None:
        self.repository.initialize()

    def snapshot(self):
        return self.repository.snapshot()

    def _lock(self, platform: str) -> asyncio.Lock:
        return self._locks.setdefault(platform, asyncio.Lock())

    def _wake_event(self, platform: str) -> asyncio.Event:
        return self._wake_events.setdefault(platform, asyncio.Event())

    async def wait_for_turn(
        self,
        platform: SearchPlatform,
        snapshot: PlatformAccessSnapshot | None = None,
        *,
        stage: str = "search",
        on_waiting: Callable[..., Any] | None = None,
    ) -> float:
        """Wait for and reserve the next controlled access start.

        Return the elapsed coordinator-clock time so callers with an overall
        work budget can exclude lawful pacing waits from their navigation
        timeout.  Older injected coordinators may still return ``None``.

        The method is intentionally an acquire operation rather than a bare
        ``sleep``: concurrent tasks for one platform cannot wake together and
        both start at the same instant. A caller must invoke it immediately
        before the actual navigation/request it controls.
        """
        if self._closed:
            raise asyncio.CancelledError
        wait_started = self._clock()
        value = snapshot or default_platform_access_snapshot()
        interval = value.for_platform(platform)
        async with self._lock(platform):
            while True:
                if self._closed:
                    raise asyncio.CancelledError
                state = await database_call(self.repository.state, platform)
                blocked = self._decode_block(platform, state)
                if blocked is not None:
                    self._blocked[platform] = blocked
                    raise PlatformAccessBlockedError(blocked)
                now = self._wall_now()
                last = parse_timestamp(state.get("last_access_started_at"))
                earliest = parse_timestamp(state.get("earliest_next_allowed_at"))
                wait_for = 0.0
                for boundary in (
                    earliest,
                    None if last is None else last + timedelta(seconds=interval),
                ):
                    if boundary is not None:
                        wait_for = max(
                            wait_for,
                            (boundary - now).total_seconds(),
                        )
                previous_monotonic = self._last_started_monotonic.get(platform)
                if previous_monotonic is not None:
                    wait_for = max(
                        wait_for,
                        previous_monotonic + interval - self._clock(),
                    )
                if wait_for > 0:
                    await self._notify_waiting(on_waiting, platform, wait_for, stage)
                    await self._wait_or_shutdown(platform, wait_for)
                    # Re-evaluation makes a virtual clock deterministic and
                    # avoids reserving early if a test advances less than the
                    # requested interval.
                    continue
                started = self._wall_now()
                started = _as_utc(started)
                earliest_next_allowed = started + timedelta(seconds=interval)
                reserved = await database_call(
                    self.repository.reserve_access,
                    platform,
                    started.isoformat(),
                    earliest_next_allowed.isoformat(),
                    interval_seconds=interval,
                )
                if not reserved:
                    # Another application instance may have reserved this
                    # platform between the state read and the write. Re-read
                    # the durable boundary rather than starting early.
                    continue
                self._last_started_monotonic[platform] = self._clock()
                await self._notify_waiting(on_waiting, platform, 0.0, stage)
                return max(0.0, self._clock() - wait_started)

    # Names used by injected collectors in earlier local prototypes.
    before_access = wait_for_turn
    acquire = wait_for_turn

    async def _notify_waiting(self, callback, platform, seconds, stage) -> None:
        if callback is None:
            return
        value = callback(platform, seconds, stage)
        if inspect.isawaitable(value):
            await value

    async def _wait_or_shutdown(self, platform: str, seconds: float) -> None:
        wake = self._wake_event(platform)
        # ``block`` may have set the event between the state read and this
        # wait. Do not clear it here: the durable state is checked again after
        # the wake, and ``authorize_resume`` clears an acknowledged edge.
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        notifier = asyncio.create_task(wake.wait())
        try:
            _done, pending = await asyncio.wait(
                (sleeper, notifier), return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if notifier.done():
                wake.clear()
                if self._closed:
                    raise asyncio.CancelledError
        finally:
            for task in (sleeper, notifier):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleeper, notifier, return_exceptions=True)

    def block(
        self,
        platform: SearchPlatform,
        diagnostic: PlatformAccessDiagnostic | None = None,
        *,
        stage: str = "search",
        status_code: int | None = None,
        platform_code: str | None = None,
        retry_after_at: datetime | None = None,
        manual_challenge_required: bool = False,
        basis: str = "explicit_platform_evidence",
    ) -> PlatformAccessDiagnostic:
        """Persist evidence and stop all future controlled starts."""
        if diagnostic is None:
            diagnostic = PlatformAccessDiagnostic(
                platform=platform,
                stage=stage,  # type: ignore[arg-type]
                outcome="platform_blocked_or_rate_limited",
                basis=basis,  # type: ignore[arg-type]
                status_code=status_code,
                platform_code=platform_code,
                retry_after_at=retry_after_at,
                manual_challenge_required=manual_challenge_required,
                observed_at=_as_utc(self._wall_now()),
            )
        self.repository.record_block(platform, diagnostic)
        persisted = self._decode_block(platform, self.repository.block_record(platform))
        self._blocked[platform] = persisted or diagnostic
        # Wake an existing interval waiter so it observes the durable block
        # immediately instead of sleeping until the old pacing deadline.
        self._wake_event(platform).set()
        return self._blocked[platform]

    def active_block(self, platform: SearchPlatform) -> PlatformAccessDiagnostic | None:
        """Read a block synchronously for non-async/UI callers.

        Async orchestration should use :meth:`active_block_async` so SQLite is
        never opened on the event-loop thread.  This compatibility method is
        retained for callers that already run in a worker thread.
        """
        cached = self._blocked.get(platform)
        if cached is not None:
            return cached
        state = self.repository.block_record(platform)
        if not state:
            return None
        value = self._decode_block(platform, state)
        if value is not None:
            self._blocked[platform] = value
        return value

    async def active_block_async(
        self, platform: SearchPlatform
    ) -> PlatformAccessDiagnostic | None:
        """Read the durable block without running SQLite on the event loop."""
        cached = self._blocked.get(platform)
        if cached is not None:
            return cached
        state = await database_call(self.repository.block_record, platform)
        if not state:
            return None
        value = self._decode_block(platform, state)
        if value is not None:
            self._blocked[platform] = value
        return value

    async def block_async(
        self,
        platform: SearchPlatform,
        diagnostic: PlatformAccessDiagnostic | None = None,
        **kwargs,
    ) -> PlatformAccessDiagnostic:
        """Persist a block from async orchestration and wake local waiters.

        ``block`` remains a synchronous compatibility API for worker-thread
        callers.  Network/browser code must use this method so both database
        operations settle across cancellation and the asyncio event is only
        touched on its owning loop.
        """
        if diagnostic is None:
            diagnostic = PlatformAccessDiagnostic(
                platform=platform,
                stage=kwargs.pop("stage", "search"),
                outcome="platform_blocked_or_rate_limited",
                basis=kwargs.pop("basis", "explicit_platform_evidence"),
                status_code=kwargs.pop("status_code", None),
                platform_code=kwargs.pop("platform_code", None),
                retry_after_at=kwargs.pop("retry_after_at", None),
                manual_challenge_required=kwargs.pop(
                    "manual_challenge_required", False
                ),
                observed_at=_as_utc(self._wall_now()),
            )
            if kwargs:
                raise TypeError("unknown platform block fields")
        elif kwargs:
            raise TypeError("diagnostic and block fields are mutually exclusive")
        await database_call(self.repository.record_block, platform, diagnostic)
        state = await database_call(self.repository.block_record, platform)
        persisted = self._decode_block(platform, state)
        self._blocked[platform] = persisted or diagnostic
        self._wake_event(platform).set()
        return self._blocked[platform]

    async def authorize_resume(self, platform: SearchPlatform) -> None:
        """Acknowledge a block only after any provider deadline has elapsed."""
        async with self._lock(platform):
            state = await database_call(self.repository.block_record, platform)
            diagnostic = self._decode_block(platform, state or {})
            if diagnostic is None:
                self._blocked.pop(platform, None)
                return
            now = _as_utc(self._wall_now())
            if (
                diagnostic.retry_after_at is not None
                and diagnostic.retry_after_at > now
            ):
                raise PlatformCooldownActiveError(diagnostic)
            await database_call(self.repository.acknowledge_block, platform)
            self._blocked.pop(platform, None)
            self._wake_event(platform).clear()

    def permit_explicit_resume(self, platform: str) -> None:
        """Compatibility no-op; explicit resume must still honor pacing.

        Older orchestrators called this after clearing a manual pause. Keeping
        the method avoids a rolling-upgrade attribute error, but it deliberately
        cannot create an in-memory bypass around the durable access boundary.
        """
        return None

    # Explicit-control spelling used by batch/report orchestrators.
    resume = authorize_resume

    def shutdown(self) -> None:
        self._closed = True
        for event in self._wake_events.values():
            event.set()

    def _decode_block(self, platform: str, state: dict[str, object] | None):
        if not state:
            return None
        for key in (
            "last_access_started_at",
            "earliest_next_allowed_at",
            "blocked_until",
            "updated_at",
        ):
            raw_timestamp = _state_value(state, key)
            if raw_timestamp is not None and parse_timestamp(raw_timestamp) is None:
                raise AnalysisError("platform_access_settings_unavailable")
        raw = _state_value(state, "diagnostic_json")
        blocked_until = _state_value(state, "blocked_until")
        if blocked_until is not None and raw is None:
            raise AnalysisError("platform_access_settings_unavailable")
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise AnalysisError("platform_access_settings_unavailable")
        try:
            value = PlatformAccessDiagnostic.model_validate_json(raw)
        except (TypeError, ValueError):
            raise AnalysisError("platform_access_settings_unavailable") from None
        if value.platform != platform:
            raise AnalysisError("platform_access_settings_unavailable")
        return value

    def _wall_now(self) -> datetime:
        value = self._wall_clock()
        if not isinstance(value, datetime):
            raise TypeError("wall_clock must return datetime")
        return _as_utc(value)


class PlatformAccessService:
    """Application service exposed to the settings endpoint and composition."""

    def __init__(self, database, *, repository=None, coordinator=None):
        self.repository = repository or PlatformAccessRepository(database)
        self.coordinator = coordinator or PlatformAccessCoordinator(self.repository)
        self._closed = False

    def initialize(self) -> None:
        self.repository.initialize()

    def read(self) -> PlatformAccessSettings:
        try:
            return self.repository.read()
        except AnalysisError:
            raise

    def snapshot(self) -> PlatformAccessSnapshot:
        return self.repository.snapshot()

    def update(self, payload: PlatformAccessUpdate) -> PlatformAccessSettings:
        try:
            return self.repository.replace(payload)
        except PlatformAccessConflict:
            raise

    async def shutdown(self) -> None:
        self._closed = True
        self.coordinator.shutdown()


def _state_value(state, key: str):
    try:
        return state[key]
    except (IndexError, KeyError, TypeError):
        return None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
