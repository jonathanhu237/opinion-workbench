"""Orchestrate durable one-shot platform searches through the shared worker."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID, uuid4

from longtian_api.database import Database
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchResultNotFoundError,
    SearchResultOpenTargetRecord,
    SearchResultRecord,
    SearchRunNotActiveError,
    SearchRunNotFoundError,
    SearchRunRecord,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
    SearchRunStatus,
)
from longtian_api.schemas.monitoring_rules import MonitoringRule
from longtian_api.schemas.search_runs import (
    SearchResult,
    SearchResultListResponse,
    SearchResultOpenResponse,
    SearchRunCreate,
    SearchRunDetail,
    SearchRunErrorCode,
    SearchRunListResponse,
    SearchRunSummary,
)
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.media_crawler_auth_worker import (
    AuthWorkerError,
    ManualPageAction,
    ManualPageWorkerResult,
    PersistentAuthWorkerClient,
    SearchWorkerItem,
)
from longtian_api.services.monitoring_rules import (
    MonitoringRuleError,
    MonitoringRuleService,
)
from longtian_api.services.settled_tasks import database_call

MAX_SEARCH_TERMS = 20


class SearchRunRepositoryProtocol(Protocol):
    def initialize(self) -> None: ...

    def create_run(
        self,
        *,
        monitoring_rule_id: int,
        platform: SearchPlatform,
        rule_name: str,
        terms: tuple[str, ...],
        max_results_per_term: int,
    ) -> SearchRunRecord: ...

    def mark_running(self, run_id: int) -> SearchRunRecord: ...

    def set_progress(self, run_id: int, term_position: int) -> None: ...

    def complete_term(
        self, run_id: int, term_position: int, item_count: int
    ) -> None: ...

    def observe_item(
        self, *, run_id: int, term_position: int, item: SearchContentInput
    ) -> None: ...

    def finish(self, run_id: int, status: SearchRunStatus) -> SearchRunRecord: ...

    def get(self, run_id: int) -> SearchRunRecord: ...

    def list(
        self, *, limit: int, before_id: int | None, standalone_only: bool = False
    ) -> tuple[tuple[SearchRunRecord, ...], int | None]: ...

    def list_results(
        self,
        *,
        run_id: int,
        kind: Literal["all", "new", "repeated"],
        limit: int,
        offset: int,
    ) -> tuple[tuple[SearchResultRecord, ...], int]: ...

    def get_result_open_target(
        self, *, run_id: int, result_id: int
    ) -> SearchResultOpenTargetRecord: ...


class SearchRunError(Exception):
    """Expected product error translated by the HTTP route."""

    def __init__(
        self, *, status_code: int, code: SearchRunErrorCode, message: str
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


class SearchRunService:
    """Own search admission, background lifecycle, and public projections."""

    def __init__(
        self,
        *,
        monitoring_rules: MonitoringRuleService,
        worker: PersistentAuthWorkerClient,
        browser_operations: BrowserOperationCoordinator,
        repository: SearchRunRepositoryProtocol | None = None,
        database: Database | None = None,
        database_path: Path | None = None,
        search_timeout_seconds: float = 180.0,
        open_timeout_seconds: float = 45.0,
    ) -> None:
        configured_sources = sum(
            source is not None for source in (repository, database, database_path)
        )
        if configured_sources > 1:
            raise ValueError(
                "Provide only one of repository, database, or database_path."
            )
        self._monitoring_rules = monitoring_rules
        self._worker = worker
        self._browser_operations = browser_operations
        if repository is None:
            self._database: Database | None = database or Database(database_path)
            self._repository = SearchRunRepository(self._database)
        else:
            self._database = None
            self._repository = repository
        self._search_timeout_seconds = search_timeout_seconds
        self._open_timeout_seconds = open_timeout_seconds
        self._lock = asyncio.Lock()
        self._active_run_id: int | None = None
        self._active_request_id: UUID | None = None
        self._current_task: asyncio.Task[None] | None = None
        self._active_open_task: asyncio.Task[object] | None = None
        self._active_open_request_id: UUID | None = None
        self._shutdown_started = False
        self.on_collection_finished = None

    @property
    def database(self) -> Database | None:
        """Return the shared product database when this service owns one."""
        return self._database

    def initialize(self) -> None:
        self._repository.initialize()

    @property
    def browser_session_available(self) -> bool:
        """No-I/O conservative session evidence; never launch a worker to probe."""
        return getattr(self._worker, "browser_session_available", False) is True

    async def start_run(self, payload: SearchRunCreate) -> SearchRunDetail:
        rule = await self.load_rule(payload.monitoring_rule_id)
        if len(rule.terms) > MAX_SEARCH_TERMS:
            raise SearchRunError(
                status_code=422,
                code="too_many_search_terms",
                message="一次最多采集 20 个搜索词，请拆分监控规则后重试。",
            )

        request_id = uuid4()
        owner = BrowserOperationOwner("search_run", request_id)
        async with self._lock:
            if self._shutdown_started or (
                self._current_task is not None and not self._current_task.done()
            ):
                raise _browser_operation_active()
            if not await self._browser_operations.try_claim(owner):
                raise _browser_operation_active()
            try:
                record = await asyncio.to_thread(
                    self._repository.create_run,
                    monitoring_rule_id=rule.id,
                    platform=payload.platform,
                    rule_name=rule.name,
                    terms=tuple(rule.terms),
                    max_results_per_term=payload.max_results_per_term,
                )
            except SearchRunRepositoryUnavailableError:
                await self._browser_operations.release(owner)
                raise _storage_unavailable() from None
            except Exception:
                await self._browser_operations.release(owner)
                raise

            self._active_run_id = record.id
            self._active_request_id = request_id
            self._current_task = asyncio.create_task(
                self._run_search(record, request_id, owner),
                name=f"search-run-{record.id}-{request_id}",
            )
            return _to_detail(record)

    async def list_runs(
        self, *, limit: int, before_id: int | None, standalone_only: bool = False
    ) -> SearchRunListResponse:
        try:
            records, next_before_id = await asyncio.to_thread(
                self._repository.list,
                limit=limit,
                before_id=before_id,
                standalone_only=standalone_only,
            )
        except SearchRunRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return SearchRunListResponse(
            runs=[_to_summary(record) for record in records],
            next_before_id=next_before_id,
        )

    async def get_run(self, run_id: int) -> SearchRunDetail:
        return _to_detail(await self._get_record(run_id))

    async def list_results(
        self,
        *,
        run_id: int,
        kind: Literal["all", "new", "repeated"],
        limit: int,
        offset: int,
    ) -> SearchResultListResponse:
        try:
            records, total = await asyncio.to_thread(
                self._repository.list_results,
                run_id=run_id,
                kind=kind,
                limit=limit,
                offset=offset,
            )
        except SearchRunNotFoundError:
            raise _not_found() from None
        except SearchRunRepositoryUnavailableError:
            raise _storage_unavailable() from None
        return SearchResultListResponse(
            results=[_to_result(record) for record in records],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def open_result(
        self, *, run_id: int, result_id: int
    ) -> SearchResultOpenResponse:
        try:
            target = await asyncio.to_thread(
                self._repository.get_result_open_target,
                run_id=run_id,
                result_id=result_id,
            )
        except SearchResultNotFoundError:
            raise _result_not_found() from None
        except SearchRunRepositoryUnavailableError:
            raise _storage_unavailable() from None
        if target.platform != "xhs":
            raise _open_not_supported()

        request_id = uuid4()
        owner = BrowserOperationOwner("search_result_open", request_id)
        current_task = asyncio.current_task()
        if (
            current_task is None
        ):  # pragma: no cover - always called by an event loop task.
            raise RuntimeError("open result requires an asyncio task")
        async with self._lock:
            if self._shutdown_started or (
                self._active_open_task is not None and not self._active_open_task.done()
            ):
                raise _browser_operation_active()
            if not await self._browser_operations.try_claim(owner):
                raise _browser_operation_active()
            self._active_open_task = current_task
            self._active_open_request_id = request_id

        try:
            try:
                async with asyncio.timeout(self._open_timeout_seconds):
                    result = await self._worker.open_result(
                        request_id=request_id,
                        term=target.matched_terms[0],
                        content_id=target.platform_content_id,
                    )
            except (AuthWorkerError, TimeoutError):
                return SearchResultOpenResponse(outcome="internal_error")
            return SearchResultOpenResponse(outcome=result.outcome)
        finally:
            await self._browser_operations.release(owner)
            async with self._lock:
                if self._active_open_request_id == request_id:
                    self._active_open_task = None
                    self._active_open_request_id = None

    async def cancel_run(self, run_id: int) -> SearchRunDetail:
        async with self._lock:
            task = self._current_task
            if self._active_run_id != run_id or task is None or task.done():
                record = await self._get_record(run_id)
                if record.status not in {"queued", "running"}:
                    raise _not_active()
                raise _not_active()
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return _to_detail(await self._get_record(run_id))

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown_started = True
            task = self._current_task
            open_task = self._active_open_task
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if open_task is not None and not open_task.done():
            open_task.cancel()
        if open_task is not None:
            try:
                await open_task
            except asyncio.CancelledError:
                pass

    async def execute_attempt(
        self,
        record: SearchRunRecord,
        request_id: UUID,
        cancellation_status: Callable[[], SearchRunStatus] | None = None,
    ) -> SearchRunRecord:
        """Execute one already-persisted batch attempt under external ownership."""
        terminal, cancelled = await self._execute_record(
            record, request_id, cancellation_status
        )
        if cancelled:
            raise asyncio.CancelledError
        return await self._get_record(record.id)

    async def manual_page(
        self, platform: SearchPlatform, action: ManualPageAction
    ) -> ManualPageWorkerResult:
        """Caller already owns the batch browser operation."""
        try:
            async with asyncio.timeout(self._open_timeout_seconds):
                result = await self._worker.manual_page(
                    request_id=uuid4(), platform=platform, action=action
                )
        except (AuthWorkerError, TimeoutError):
            await self._worker.discard_session()
            return ManualPageWorkerResult("internal_error")
        if action == "close" and result.outcome not in {
            "closed",
            "not_present",
            "browser_unavailable",
        }:
            await self._worker.discard_session()
        return result

    async def load_rule(self, rule_id: int) -> MonitoringRule:
        """Load and validate the enabled rule shared by run orchestrators."""
        try:
            enabled_rules = await asyncio.to_thread(self._monitoring_rules.list_enabled)
        except MonitoringRuleError:
            raise _storage_unavailable() from None
        rule = next((item for item in enabled_rules if item.id == rule_id), None)
        if rule is not None:
            return rule

        try:
            disabled_rules = await asyncio.to_thread(
                self._monitoring_rules.list_rules, enabled=False
            )
        except MonitoringRuleError:
            raise _storage_unavailable() from None
        if any(item.id == rule_id for item in disabled_rules.rules):
            raise SearchRunError(
                status_code=409,
                code="monitoring_rule_disabled",
                message="该监控规则已停用，请先启用后再采集。",
            )
        raise SearchRunError(
            status_code=404,
            code="monitoring_rule_not_found",
            message="未找到该监控规则。",
        )

    async def _get_record(self, run_id: int) -> SearchRunRecord:
        try:
            return await asyncio.to_thread(self._repository.get, run_id)
        except SearchRunNotFoundError:
            raise _not_found() from None
        except SearchRunRepositoryUnavailableError:
            raise _storage_unavailable() from None

    async def _run_search(
        self,
        record: SearchRunRecord,
        request_id: UUID,
        owner: BrowserOperationOwner,
    ) -> None:
        cancelled = False
        try:
            _, cancelled = await self._execute_record(record, request_id)
        finally:
            await self._browser_operations.release(owner)
            async with self._lock:
                if self._active_request_id == request_id:
                    self._active_run_id = None
                    self._active_request_id = None
                    self._current_task = None
            if (
                not self._shutdown_started
                and not cancelled
                and self.on_collection_finished is not None
            ):
                try:
                    await self.on_collection_finished("run", record.id)
                except Exception:
                    # Committed discovery claims survive a downstream admission failure.
                    pass
        if cancelled:
            raise asyncio.CancelledError

    async def _execute_record(
        self,
        record: SearchRunRecord,
        request_id: UUID,
        cancellation_status: Callable[[], SearchRunStatus] | None = None,
    ) -> tuple[SearchRunStatus, bool]:
        terminal: SearchRunStatus = "internal_error"
        cancelled = False
        try:
            await database_call(self._repository.mark_running, record.id)
            start = record.execution_start_term_position

            async def on_progress(position: int, _count: int) -> None:
                await database_call(
                    self._repository.set_progress, record.id, start + position
                )

            async def on_term_completed(position: int, count: int) -> None:
                await database_call(
                    self._repository.complete_term, record.id, start + position, count
                )

            async def on_item(position: int, item: SearchWorkerItem) -> None:
                observed_at = _timestamp_from_epoch_milliseconds(item.discovered_at)
                await database_call(
                    self._repository.observe_item,
                    run_id=record.id,
                    term_position=start + position,
                    item=SearchContentInput(
                        platform_content_id=item.content_id,
                        content_type=item.content_type,
                        title=item.title,
                        snippet=item.snippet,
                        creator_hash=item.creator_hash,
                        publisher_name=item.publisher_name,
                        published_at_text=item.published_at_text,
                        content_url=item.content_url,
                        observed_at=observed_at,
                    ),
                )

            async with asyncio.timeout(self._search_timeout_seconds):
                result = await self._worker.search(
                    request_id=request_id,
                    platform=record.platform,
                    terms=record.terms[start:],
                    max_results_per_term=record.max_results_per_term,
                    on_progress=on_progress,
                    on_item=on_item,
                    on_term_completed=on_term_completed,
                )
            terminal = _project_worker_outcome(result.outcome)
        except TimeoutError:
            terminal = "timed_out"
        except asyncio.CancelledError:
            terminal = cancellation_status() if cancellation_status else "cancelled"
            cancelled = True
        except (AuthWorkerError, SearchRunRepositoryUnavailableError):
            terminal = "internal_error"
        except Exception:
            terminal = "internal_error"
        try:
            await database_call(self._repository.finish, record.id, terminal)
        except (SearchRunNotActiveError, SearchRunRepositoryUnavailableError):
            pass
        return terminal, cancelled


def _project_worker_outcome(outcome: str) -> SearchRunStatus:
    if outcome == "browser_disconnected":
        return "browser_unavailable"
    if outcome in {
        "completed_with_results",
        "completed_empty",
        "login_required",
        "manual_challenge_required",
        "platform_blocked_or_rate_limited",
        "structure_changed",
        "browser_unavailable",
        "cancelled",
        "internal_error",
    }:
        return outcome  # type: ignore[return-value]
    return "internal_error"


def _to_summary(record: SearchRunRecord) -> SearchRunSummary:
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


def _to_detail(record: SearchRunRecord) -> SearchRunDetail:
    return SearchRunDetail(**_to_summary(record).model_dump(), terms=record.terms)


def _to_result(record: SearchResultRecord) -> SearchResult:
    return SearchResult(
        id=record.id,
        platform=record.platform,
        platform_content_id=record.platform_content_id,
        content_type=record.content_type,
        title=record.title,
        snippet=record.snippet,
        creator_hash=record.creator_hash,
        publisher_name=record.publisher_name,
        published_at_text=record.published_at_text,
        content_url=record.content_url,
        kind=record.discovery_kind,
        matched_terms=record.matched_terms,
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
        first_observed_at=record.first_observed_at,
        last_observed_at=record.last_observed_at,
    )


def _timestamp_from_epoch_milliseconds(value: int) -> str:
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(value / 1000, UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        raise AuthWorkerError from None


def _browser_operation_active() -> SearchRunError:
    return SearchRunError(
        status_code=409,
        code="browser_operation_active",
        message="谷歌浏览器正在执行其他操作，请稍后重试。",
    )


def _not_found() -> SearchRunError:
    return SearchRunError(
        status_code=404,
        code="search_run_not_found",
        message="未找到该采集任务。",
    )


def _not_active() -> SearchRunError:
    return SearchRunError(
        status_code=409,
        code="search_run_not_active",
        message="该采集任务已经结束，无法取消。",
    )


def _result_not_found() -> SearchRunError:
    return SearchRunError(
        status_code=404,
        code="search_result_not_found",
        message="未在该采集任务中找到这条结果。",
    )


def _open_not_supported() -> SearchRunError:
    return SearchRunError(
        status_code=409,
        code="search_result_open_not_supported",
        message="该平台的结果不需要通过浏览器任务打开。",
    )


def _storage_unavailable() -> SearchRunError:
    return SearchRunError(
        status_code=503,
        code="search_storage_unavailable",
        message="采集任务暂时无法读取或保存，请稍后重试。",
    )
