"""Orchestrate durable serial multi-platform search batches."""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from longtian_api.database import Database
from longtian_api.repositories.search_batches import (
    SearchBatchAttemptRecord,
    SearchBatchItemRecord,
    SearchBatchNotActiveError,
    SearchBatchNotFoundError,
    SearchBatchNotPausedError,
    SearchBatchRecord,
    SearchBatchRepository,
    SearchBatchRepositoryError,
    SearchBatchRepositoryUnavailableError,
)
from longtian_api.repositories.search_runs import SearchRunRecord, SearchRunStatus
from longtian_api.schemas.search_batches import (
    SearchBatchAttempt,
    SearchBatchAttemptListResponse,
    SearchBatchCreate,
    SearchBatchDetail,
    SearchBatchErrorCode,
    SearchBatchItem,
    SearchBatchListResponse,
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
)


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
        self, batch_id: int, position: int, run_status: SearchRunStatus
    ) -> SearchBatchRecord: ...

    def finalize(self, batch_id: int) -> SearchBatchRecord: ...

    def fail_batch(self, batch_id: int) -> SearchBatchRecord: ...

    def continue_batch(self, batch_id: int) -> SearchBatchRecord: ...

    def cancel_batch(self, batch_id: int) -> SearchBatchRecord: ...

    def get(self, batch_id: int) -> SearchBatchRecord: ...

    def list(
        self, *, limit: int, before_id: int | None
    ) -> tuple[tuple[SearchBatchRecord, ...], int | None]: ...

    def list_attempts(
        self, batch_id: int, position: int
    ) -> tuple[SearchBatchAttemptRecord, ...]: ...

    def active_or_paused(self) -> SearchBatchRecord | None: ...


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
            if record.status != "paused_for_manual_action":
                self._current_task = self._create_runner(record.id, owner)

    async def start_batch(self, payload: SearchBatchCreate) -> SearchBatchDetail:
        try:
            rule = await self._search_runs.load_rule(payload.monitoring_rule_id)
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
                record = await asyncio.to_thread(
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
            except Exception:
                await self._browser_operations.release(owner)
                raise
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

    async def continue_batch(self, batch_id: int) -> SearchBatchDetail:
        persisted = await self._get_record(batch_id)
        if persisted.status != "paused_for_manual_action":
            raise _not_paused()
        async with self._lock:
            settling_task = (
                self._current_task
                if self._active_batch_id == batch_id
                and self._current_task is not None
                and not self._current_task.done()
                else None
            )
        if settling_task is not None:
            await settling_task
        async with self._lock:
            if (
                self._active_batch_id != batch_id
                or self._active_owner is None
                or (self._current_task is not None and not self._current_task.done())
            ):
                raise _browser_operation_active()
            try:
                record = await asyncio.to_thread(
                    self._repository.continue_batch, batch_id
                )
            except SearchBatchNotFoundError:
                raise _not_found() from None
            except SearchBatchNotPausedError:
                raise _not_paused() from None
            except SearchBatchRepositoryUnavailableError:
                raise _storage_unavailable() from None
            self._current_task = self._create_runner(batch_id, self._active_owner)
        return _to_detail(record)

    async def cancel_batch(self, batch_id: int) -> SearchBatchDetail:
        async with self._lock:
            try:
                record = await asyncio.to_thread(
                    self._repository.cancel_batch, batch_id
                )
            except SearchBatchNotFoundError:
                raise _not_found() from None
            except SearchBatchNotActiveError:
                raise _not_active() from None
            except SearchBatchRepositoryUnavailableError:
                raise _storage_unavailable() from None
            task = self._current_task if self._active_batch_id == batch_id else None
            owner = self._active_owner if self._active_batch_id == batch_id else None
            if task is not None and not task.done():
                task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if owner is not None:
            await self._release_owner(owner)
        return _to_detail(await self._get_record(record.id))

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown_started = True
            task = self._current_task
            owner = self._active_owner
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if owner is not None:
            await self._release_owner(owner)

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
                record = await asyncio.to_thread(
                    self._repository.mark_running, batch_id
                )
            if record.status != "running":
                return
            while True:
                item = await asyncio.to_thread(
                    self._repository.next_queued_item, batch_id
                )
                if item is None:
                    await asyncio.to_thread(self._repository.finalize, batch_id)
                    return
                run = await asyncio.to_thread(
                    self._repository.create_attempt, batch_id, item.position
                )
                request_id = uuid4()
                cancelled = False
                try:
                    run = await self._search_runs.execute_attempt(run, request_id)
                except asyncio.CancelledError:
                    cancelled = True
                    run = await self._search_runs.get_run(run.id)
                await asyncio.shield(
                    asyncio.to_thread(
                        self._repository.finish_item,
                        batch_id,
                        item.position,
                        run.status,
                    )
                )
                batch = await self._get_record(batch_id)
                if batch.status == "paused_for_manual_action":
                    preserve_owner = True
                    return
                if batch.status == "cancelled":
                    return
                if cancelled:
                    raise asyncio.CancelledError
        except asyncio.CancelledError:
            raise
        except (SearchBatchRepositoryUnavailableError, SearchRunError):
            try:
                await asyncio.to_thread(self._repository.fail_batch, batch_id)
            except SearchBatchRepositoryError:
                pass
        except Exception:
            try:
                await asyncio.to_thread(self._repository.fail_batch, batch_id)
            except Exception:
                pass
        finally:
            async with self._lock:
                if self._active_batch_id == batch_id:
                    self._current_task = None
            if not preserve_owner:
                await self._release_owner(owner)

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
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _to_summary(record: SearchBatchRecord) -> SearchBatchSummary:
    terminal_count = sum(
        item.status in {"completed", "failed", "cancelled"} for item in record.items
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
