"""Orchestrate durable serial multi-platform search batches."""

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import uuid4

from longtian_api.database import Database
from longtian_api.repositories.collection_schedules import OccurrenceClaim
from longtian_api.repositories.search_batches import (
    ScheduledDispatchChangedError,
    SearchBatchAttemptRecord,
    SearchBatchItemNotRecoverableError,
    SearchBatchItemRecord,
    SearchBatchNotActiveError,
    SearchBatchNotFoundError,
    SearchBatchNotPausedError,
    SearchBatchRecord,
    SearchBatchRecoveryUnavailableError,
    SearchBatchRepository,
    SearchBatchRepositoryError,
    SearchBatchRepositoryUnavailableError,
    SearchBatchStateChangedError,
)
from longtian_api.repositories.search_runs import SearchRunRecord, SearchRunStatus
from longtian_api.schemas.collection_schedules import OccurrenceReason
from longtian_api.schemas.monitoring_rules import MonitoringRule
from longtian_api.schemas.search_batches import (
    ManualPageOutcome,
    SearchBatchAttempt,
    SearchBatchAttemptListResponse,
    SearchBatchCancel,
    SearchBatchControl,
    SearchBatchCreate,
    SearchBatchDetail,
    SearchBatchErrorCode,
    SearchBatchItem,
    SearchBatchListResponse,
    SearchBatchManualPageResponse,
    SearchBatchRecover,
    SearchBatchResult,
    SearchBatchResultListResponse,
    SearchBatchSummary,
)
from longtian_api.schemas.search_runs import SearchRunSummary
from longtian_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.search_runs import (
    MAX_SEARCH_TERMS,
    SearchRunError,
    SearchRunService,
    _to_result,
)
from longtian_api.services.settled_tasks import database_call, settle


class SearchBatchRepositoryProtocol(Protocol):
    def initialize(self) -> None: ...

    def create_batch(
        self,
        *,
        monitoring_rule_id: int,
        rule_name: str,
        terms: Sequence[str],
        platforms: Sequence[SearchPlatform],
        max_results_per_term: int,
    ) -> SearchBatchRecord: ...

    def mark_running(self, batch_id: int) -> SearchBatchRecord: ...

    def next_queued_item(self, batch_id: int) -> SearchBatchItemRecord | None: ...

    def create_attempt(self, batch_id: int, position: int) -> SearchRunRecord: ...

    def finish_item(
        self,
        batch_id: int,
        position: int,
        run_status: SearchRunStatus,
        expected_run_id: int | None = None,
    ) -> SearchBatchRecord: ...

    def finalize(self, batch_id: int) -> SearchBatchRecord: ...

    def fail_batch(self, batch_id: int) -> SearchBatchRecord: ...

    def continue_batch(self, batch_id: int, **kwargs) -> SearchBatchRecord: ...

    def cancel_batch(
        self, batch_id: int, *, expected_revision: int
    ) -> SearchBatchRecord: ...

    def skip_item(self, batch_id: int, **kwargs) -> SearchBatchRecord: ...

    def recover_item(
        self, batch_id: int, position: int, **kwargs
    ) -> SearchBatchRecord: ...

    def validate_control(self, batch_id: int, **kwargs) -> SearchBatchRecord: ...

    def reconcile_interrupted_items(self, batch_id: int | None = None) -> int: ...

    def list_results(self, **kwargs): ...

    def get(self, batch_id: int) -> SearchBatchRecord: ...

    def list(
        self, *, limit: int, before_id: int | None
    ) -> tuple[tuple[SearchBatchRecord, ...], int | None]: ...

    def list_attempts(
        self, batch_id: int, position: int
    ) -> tuple[SearchBatchAttemptRecord, ...]: ...

    def active_or_paused(self) -> SearchBatchRecord | None: ...

    def scheduled_batch(self, dispatch_token: str) -> SearchBatchRecord | None: ...

    def create_scheduled_batch(
        self, dispatch_token: str, rule: MonitoringRule, *, timestamp: str
    ) -> tuple[SearchBatchRecord, bool]: ...


class ScheduledAdmissionError(Exception):
    def __init__(self, reason: OccurrenceReason):
        super().__init__(reason)
        self.reason = reason


class SearchBatchError(Exception):
    """Expected batch product error translated by the HTTP route."""

    def __init__(
        self, *, status_code: int, code: SearchBatchErrorCode, message: str
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


class SearchBatchService:
    """Own durable batch admission, serial scheduling, and recovery."""

    def __init__(
        self,
        *,
        search_runs: SearchRunService,
        browser_operations: BrowserOperationCoordinator,
        repository: SearchBatchRepositoryProtocol | None = None,
        database: Database | None = None,
        database_path: Path | None = None,
    ) -> None:
        configured_sources = sum(
            source is not None for source in (repository, database, database_path)
        )
        if configured_sources > 1:
            raise ValueError(
                "Provide only one of repository, database, or database_path."
            )
        self._search_runs = search_runs
        self._browser_operations = browser_operations
        self._repository = repository or SearchBatchRepository(
            database or Database(database_path)
        )
        self._lock = asyncio.Lock()
        self._active_batch_id: int | None = None
        self._active_owner: BrowserOperationOwner | None = None
        self._current_task: asyncio.Task[None] | None = None
        self._shutdown_started = False
        self._manual_task: asyncio.Task | None = None
        self._control_task: asyncio.Task | None = None
        self._cancelling = False
        self.on_collection_finished = None

    def initialize(self) -> None:
        self._repository.initialize()

    async def resume_after_startup(self) -> None:
        """Restore the single durable active or manually paused batch."""
        try:
            record = await asyncio.to_thread(self._repository.active_or_paused)
        except SearchBatchRepositoryUnavailableError:
            return
        if record is None:
            return
        owner = BrowserOperationOwner("search_batch", uuid4())
        async with self._lock:
            if self._shutdown_started:
                return
            if not await self._browser_operations.try_claim(owner):
                return
            self._active_batch_id = record.id
            self._active_owner = owner
            # Initialization already reconciled unfinished work to a pause.
            # Startup/GET never schedule browser work.

    async def start_batch(self, payload: SearchBatchCreate) -> SearchBatchDetail:
        return await settle(self._start_batch(payload))

    async def _start_batch(self, payload: SearchBatchCreate) -> SearchBatchDetail:
        rule = await self._load_rule(payload.monitoring_rule_id)
        requested = set(payload.platforms)
        platforms = tuple(
            platform for platform in SEARCH_PLATFORMS if platform in requested
        )
        owner = BrowserOperationOwner("search_batch", uuid4())
        async with self._lock:
            if self._shutdown_started or self._active_batch_id is not None:
                raise _browser_operation_active()
            if not await self._browser_operations.try_claim(owner):
                raise _browser_operation_active()
            try:
                record = await database_call(
                    self._repository.create_batch,
                    monitoring_rule_id=rule.id,
                    rule_name=rule.name,
                    terms=tuple(rule.terms),
                    platforms=platforms,
                    max_results_per_term=payload.max_results_per_term,
                )
            except SearchBatchRepositoryUnavailableError:
                await self._browser_operations.release(owner)
                raise _storage_unavailable() from None
            except BaseException:
                await self._browser_operations.release(owner)
                raise
            self._active_batch_id = record.id
            self._active_owner = owner
            self._current_task = self._create_runner(record.id, owner)
        return _to_detail(record)

    async def _load_rule(self, rule_id: int) -> MonitoringRule:
        try:
            rule = await self._search_runs.load_rule(rule_id)
        except SearchRunError as error:
            if error.code == "monitoring_rule_not_found":
                raise SearchBatchError(
                    status_code=404,
                    code="monitoring_rule_not_found",
                    message="未找到该监控规则。",
                ) from None
            if error.code == "monitoring_rule_disabled":
                raise SearchBatchError(
                    status_code=409,
                    code="monitoring_rule_disabled",
                    message="该监控规则已停用，请先启用后再采集。",
                ) from None
            raise _storage_unavailable() from None
        if len(rule.terms) > MAX_SEARCH_TERMS:
            raise SearchBatchError(
                status_code=422,
                code="too_many_search_terms",
                message="一次最多采集 20 个搜索词，请拆分监控规则后重试。",
            )
        return rule

    async def start_scheduled_batch(
        self,
        claim: OccurrenceClaim,
        *,
        timestamp: str,
        admission_allowed: Callable[[], bool],
    ) -> SearchBatchDetail:
        return await settle(
            self._start_scheduled_batch(
                claim, timestamp=timestamp, admission_allowed=admission_allowed
            )
        )

    async def _start_scheduled_batch(
        self,
        claim: OccurrenceClaim,
        *,
        timestamp: str,
        admission_allowed: Callable[[], bool],
    ) -> SearchBatchDetail:
        existing = await database_call(
            self._repository.scheduled_batch, claim.dispatch_token
        )
        if existing is not None:
            # Replay never schedules a runner, including a paused/restarted link.
            return _to_detail(existing)
        if claim.monitoring_rule_id is None:
            raise ScheduledAdmissionError("monitoring_rule_not_found")
        rule = await self._load_rule(claim.monitoring_rule_id)
        owner = BrowserOperationOwner("search_batch", uuid4())
        async with self._lock:
            existing = await database_call(
                self._repository.scheduled_batch, claim.dispatch_token
            )
            if existing is not None:
                return _to_detail(existing)
            if self._shutdown_started or not admission_allowed():
                raise ScheduledAdmissionError("dispatch_interrupted")
            if self._active_batch_id is not None:
                raise _browser_operation_active()
            if not await self._browser_operations.try_claim(owner):
                raise _browser_operation_active()
            try:
                if not self._search_runs.browser_session_available:
                    raise ScheduledAdmissionError("browser_unavailable")
                record, created = await database_call(
                    self._repository.create_scheduled_batch,
                    claim.dispatch_token,
                    rule,
                    timestamp=timestamp,
                )
            except ScheduledDispatchChangedError:
                await self._browser_operations.release(owner)
                raise ScheduledAdmissionError("schedule_changed") from None
            except SearchBatchRepositoryUnavailableError:
                await self._browser_operations.release(owner)
                raise _storage_unavailable() from None
            except BaseException:
                await self._browser_operations.release(owner)
                raise
            if not created:
                await self._browser_operations.release(owner)
                return _to_detail(record)
            self._active_batch_id = record.id
            self._active_owner = owner
            self._current_task = self._create_runner(record.id, owner)
        return _to_detail(record)

    async def list_batches(
        self, *, limit: int, before_id: int | None
    ) -> SearchBatchListResponse:
        try:
            records, next_before_id = await asyncio.to_thread(
                self._repository.list, limit=limit, before_id=before_id
            )
        except SearchBatchRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return SearchBatchListResponse(
            batches=[_to_summary(record) for record in records],
            next_before_id=next_before_id,
        )

    async def get_batch(self, batch_id: int) -> SearchBatchDetail:
        return _to_detail(await self._get_record(batch_id))

    async def list_attempts(
        self, batch_id: int, position: int
    ) -> SearchBatchAttemptListResponse:
        try:
            records = await asyncio.to_thread(
                self._repository.list_attempts, batch_id, position
            )
        except SearchBatchNotFoundError:
            raise _not_found() from None
        except SearchBatchRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return SearchBatchAttemptListResponse(
            attempts=[_to_attempt(record) for record in records]
        )

    async def list_results(
        self,
        *,
        batch_id: int,
        position: int,
        kind: Literal["all", "new", "repeated"],
        limit: int,
        offset: int,
    ) -> SearchBatchResultListResponse:
        records, total = await self._call(
            self._repository.list_results,
            batch_id=batch_id,
            position=position,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        return SearchBatchResultListResponse(
            results=[
                SearchBatchResult(
                    **_to_result(record.result).model_dump(),
                    source_run_id=record.source_run_id,
                )
                for record in records
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def continue_batch(
        self, batch_id: int, payload: SearchBatchControl
    ) -> SearchBatchDetail:
        return await settle(self._resume_control(batch_id, payload, skip=False))

    async def skip_item(
        self, batch_id: int, payload: SearchBatchControl
    ) -> SearchBatchDetail:
        return await settle(self._resume_control(batch_id, payload, skip=True))

    async def _resume_control(
        self, batch_id: int, payload: SearchBatchControl, *, skip: bool
    ) -> SearchBatchDetail:
        await self._call(
            self._repository.validate_control, batch_id, **payload.model_dump()
        )
        # The old runner can be in its finalizer after the durable pause is visible.
        task = self._current_task
        if task is not None:
            await asyncio.shield(task)
        async with self._lock:
            record = await self._call(
                self._repository.validate_control, batch_id, **payload.model_dump()
            )
            self._require_owner(batch_id)
            if self._control_task is not None:
                raise _browser_operation_active()
            if (
                not skip
                and not record.items[payload.item_position].checkpoint.available
            ):
                raise _repository_error(SearchBatchRecoveryUnavailableError())
            self._control_task = asyncio.current_task()
            manual = self._manual_task
            platform = record.items[payload.item_position].platform
        try:
            await _cancel_and_drain(manual)
            await self._search_runs.manual_page(platform, "close")
            async with self._lock:
                self._require_owner(batch_id)
                method = (
                    self._repository.skip_item
                    if skip
                    else self._repository.continue_batch
                )
                record = await self._call(method, batch_id, **payload.model_dump())
                self._current_task = self._create_runner(batch_id, self._active_owner)
            return _to_detail(record)
        finally:
            async with self._lock:
                if self._control_task is asyncio.current_task():
                    self._control_task = None

    async def manual_page(
        self, batch_id: int, payload: SearchBatchControl
    ) -> SearchBatchManualPageResponse:
        await self._call(
            self._repository.validate_control, batch_id, **payload.model_dump()
        )
        task = self._current_task
        if task is not None:
            await asyncio.shield(task)
        async with self._lock:
            record = await self._call(
                self._repository.validate_control, batch_id, **payload.model_dump()
            )
            self._require_owner(batch_id)
            if self._control_task is not None or self._manual_task is not None:
                raise _browser_operation_active()
            task = asyncio.create_task(
                self._search_runs.manual_page(
                    record.items[payload.item_position].platform, "show"
                )
            )
            self._manual_task = task
        try:
            try:
                result = await task
            except asyncio.CancelledError:
                return SearchBatchManualPageResponse(outcome="cancelled")
            async with self._lock:
                await self._call(
                    self._repository.validate_control, batch_id, **payload.model_dump()
                )
            return SearchBatchManualPageResponse(
                outcome=cast(ManualPageOutcome, result.outcome)
            )
        finally:
            async with self._lock:
                if self._manual_task is task:
                    self._manual_task = None

    async def recover_item(
        self, batch_id: int, position: int, payload: SearchBatchRecover
    ) -> SearchBatchDetail:
        return await settle(self._recover_item(batch_id, position, payload))

    async def _recover_item(
        self, batch_id: int, position: int, payload: SearchBatchRecover
    ) -> SearchBatchDetail:
        owner = BrowserOperationOwner("search_batch", uuid4())
        async with self._lock:
            if self._shutdown_started or self._active_batch_id is not None:
                raise _browser_operation_active()
            if not await self._browser_operations.try_claim(owner):
                raise _browser_operation_active()
            try:
                record = await self._call(
                    self._repository.recover_item,
                    batch_id,
                    position,
                    **payload.model_dump(),
                )
            except BaseException:
                await self._browser_operations.release(owner)
                raise
            self._active_batch_id = batch_id
            self._active_owner = owner
        return _to_detail(record)

    async def cancel_batch(
        self, batch_id: int, payload: SearchBatchCancel
    ) -> SearchBatchDetail:
        return await settle(self._cancel_batch(batch_id, payload))

    async def _cancel_batch(
        self, batch_id: int, payload: SearchBatchCancel
    ) -> SearchBatchDetail:
        async with self._lock:
            # Atomic status + revision fences callbacks before draining them.
            record = await self._call(
                self._repository.cancel_batch, batch_id, **payload.model_dump()
            )
            self._cancelling = True
            owner = self._active_owner if self._active_batch_id == batch_id else None
            tasks = (
                (self._current_task, self._manual_task, self._control_task)
                if owner is not None
                else ()
            )
            for task in tasks:
                if task is not None and not task.done():
                    task.cancel()
        try:
            for task in tasks:
                await _cancel_and_drain(task)
            if owner is not None and record.current_item_position is not None:
                await self._search_runs.manual_page(
                    record.items[record.current_item_position].platform, "close"
                )
        finally:
            if owner is not None:
                await self._release_owner(owner)

            self._cancelling = False
        return _to_detail(await self._get_record(batch_id))

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown_started = True
            tasks = (self._current_task, self._manual_task, self._control_task)
            owner, batch_id = self._active_owner, self._active_batch_id
            for task in tasks:
                if task is not None and not task.done():
                    task.cancel()
        for task in tasks:
            await _cancel_and_drain(task)
        if batch_id is not None:
            await self._call(self._repository.reconcile_interrupted_items, batch_id)
        if owner is not None:
            await self._release_owner(owner)

    def _require_owner(self, batch_id: int) -> None:
        if (
            self._shutdown_started
            or self._cancelling
            or self._active_batch_id != batch_id
            or self._active_owner is None
        ):
            raise _browser_operation_active()

    async def _call(self, method, *args, **kwargs):
        try:
            return await database_call(method, *args, **kwargs)
        except SearchBatchRepositoryError as error:
            raise _repository_error(error) from None

    def _create_runner(
        self, batch_id: int, owner: BrowserOperationOwner
    ) -> asyncio.Task[None]:
        return asyncio.create_task(
            self._run_batch(batch_id, owner),
            name=f"search-batch-{batch_id}-{owner.request_id}",
        )

    async def _run_batch(self, batch_id: int, owner: BrowserOperationOwner) -> None:
        preserve_owner = False
        try:
            record = await self._get_record(batch_id)
            if record.status == "queued":
                record = await database_call(self._repository.mark_running, batch_id)
            if record.status != "running":
                return
            while True:
                if self._shutdown_started or self._cancelling:
                    return
                item = await asyncio.to_thread(
                    self._repository.next_queued_item, batch_id
                )
                if item is None:
                    await database_call(self._repository.finalize, batch_id)
                    return
                run = await database_call(
                    self._repository.create_attempt, batch_id, item.position
                )
                request_id = uuid4()
                run = await self._search_runs.execute_attempt(
                    run,
                    request_id,
                    cancellation_status=lambda: (
                        "internal_error" if self._shutdown_started else "cancelled"
                    ),
                )
                batch = await database_call(
                    self._repository.finish_item,
                    batch_id,
                    item.position,
                    run.status,
                    expected_run_id=run.id,
                )
                if batch.status == "paused_for_manual_action":
                    preserve_owner = True
                    return
                if batch.status == "cancelled":
                    return
        except asyncio.CancelledError:
            if not self._cancelling:
                await database_call(
                    self._repository.reconcile_interrupted_items, batch_id
                )
                preserve_owner = True
            raise
        except (SearchBatchRepositoryError, SearchRunError, SearchBatchError):
            try:
                await database_call(self._repository.fail_batch, batch_id)
            except SearchBatchRepositoryError:
                pass
        except Exception:
            try:
                await database_call(self._repository.fail_batch, batch_id)
            except Exception:
                pass
        finally:
            async with self._lock:
                if self._active_batch_id == batch_id:
                    self._current_task = None
            if (
                not preserve_owner
                and not self._cancelling
                and not self._shutdown_started
            ):
                await self._release_owner(owner)
                if self.on_collection_finished is not None:
                    try:
                        await self.on_collection_finished("batch", batch_id)
                    except Exception:
                        # Collection success is independent of downstream analysis.
                        pass

    async def _release_owner(self, owner: BrowserOperationOwner) -> None:
        await self._browser_operations.release(owner)
        async with self._lock:
            if self._active_owner == owner:
                self._active_owner = None
                self._active_batch_id = None
                self._current_task = None

    async def _get_record(self, batch_id: int) -> SearchBatchRecord:
        try:
            return await asyncio.to_thread(self._repository.get, batch_id)
        except SearchBatchNotFoundError:
            raise _not_found() from None
        except SearchBatchRepositoryUnavailableError:
            raise _storage_unavailable() from None


def _to_run_summary(record: SearchRunRecord) -> SearchRunSummary:
    return SearchRunSummary(
        id=record.id,
        monitoring_rule_id=record.monitoring_rule_id,
        platform=record.platform,
        rule_name=record.rule_name,
        term_count=len(record.terms),
        max_results_per_term=record.max_results_per_term,
        status=record.status,
        current_term_position=record.current_term_position,
        new_count=record.new_count,
        repeated_count=record.repeated_count,
        total_count=record.total_count,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _to_attempt(record: SearchBatchAttemptRecord) -> SearchBatchAttempt:
    return SearchBatchAttempt(
        attempt_number=record.attempt_number,
        run=_to_run_summary(record.run),
    )


def _to_item(record: SearchBatchItemRecord) -> SearchBatchItem:
    return SearchBatchItem(
        position=record.position,
        platform=record.platform,
        status=record.status,
        attempt_count=record.attempt_count,
        latest_attempt=(
            _to_attempt(record.latest_attempt) if record.latest_attempt else None
        ),
        completed_term_count=record.checkpoint.completed,
        remaining_term_count=record.checkpoint.remaining,
        next_term_position=record.checkpoint.next_position,
        checkpoint_basis=record.checkpoint.basis,
        recovery_available=record.checkpoint.available,
        pause_reason=record.pause_reason,
        completion_basis=record.completion_basis,
        new_count=record.new_count,
        repeated_count=record.repeated_count,
        total_count=record.total_count,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _to_summary(record: SearchBatchRecord) -> SearchBatchSummary:
    terminal_count = sum(
        item.status in {"completed", "failed", "cancelled", "skipped"}
        for item in record.items
    )
    return SearchBatchSummary(
        id=record.id,
        monitoring_rule_id=record.monitoring_rule_id,
        rule_name=record.rule_name,
        term_count=len(record.terms),
        platform_count=len(record.items),
        terminal_item_count=terminal_count,
        max_results_per_term=record.max_results_per_term,
        status=record.status,
        control_revision=record.control_revision,
        current_item_position=record.current_item_position,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _to_detail(record: SearchBatchRecord) -> SearchBatchDetail:
    return SearchBatchDetail(
        **_to_summary(record).model_dump(),
        terms=record.terms,
        items=tuple(_to_item(item) for item in record.items),
    )


def _browser_operation_active() -> SearchBatchError:
    return SearchBatchError(
        status_code=409,
        code="browser_operation_active",
        message="谷歌浏览器正在执行其他操作，请稍后重试。",
    )


def _not_found() -> SearchBatchError:
    return SearchBatchError(
        status_code=404,
        code="search_batch_not_found",
        message="未找到该批采集任务。",
    )


def _not_active() -> SearchBatchError:
    return SearchBatchError(
        status_code=409,
        code="search_batch_not_active",
        message="该批采集任务已经结束，无法取消。",
    )


def _not_paused() -> SearchBatchError:
    return SearchBatchError(
        status_code=409,
        code="search_batch_not_paused",
        message="该批采集任务当前不需要继续操作。",
    )


def _storage_unavailable() -> SearchBatchError:
    return SearchBatchError(
        status_code=503,
        code="search_storage_unavailable",
        message="采集任务暂时无法读取或保存，请稍后重试。",
    )


async def _cancel_and_drain(task: asyncio.Task | None) -> None:
    if task is None:
        return
    if not task.done() and not task.cancelling():
        task.cancel()
    try:
        await settle(task)
    except (asyncio.CancelledError, SearchBatchError):
        pass


def _repository_error(error: SearchBatchRepositoryError) -> SearchBatchError:
    if isinstance(error, SearchBatchNotFoundError):
        return _not_found()
    if isinstance(error, SearchBatchNotActiveError):
        return _not_active()
    if isinstance(error, SearchBatchNotPausedError):
        return _not_paused()
    if isinstance(error, SearchBatchStateChangedError):
        return SearchBatchError(
            status_code=409,
            code="search_batch_state_changed",
            message="采集任务状态已变化，请刷新后重试。",
        )
    if isinstance(error, SearchBatchRecoveryUnavailableError):
        return SearchBatchError(
            status_code=409,
            code="search_batch_recovery_unavailable",
            message="无法确认可靠的续采位置，请跳过此平台或取消批次。",
        )
    if isinstance(error, SearchBatchItemNotRecoverableError):
        return SearchBatchError(
            status_code=409,
            code="search_batch_item_not_recoverable",
            message="该平台当前不能重新处理。",
        )
    return _storage_unavailable()
