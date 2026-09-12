"""Explicit, serial stored-content acquisition without persistence or AI calls."""

import asyncio
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID, uuid4

from opinion_workbench_api.repositories.search_runs import (
    SearchResultNotFoundError,
    SearchResultSourceRecord,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
)
from opinion_workbench_api.search_platforms import SearchPlatform
from opinion_workbench_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from opinion_workbench_api.services.collector_contracts import (
    AuthWorkerError,
    EnrichmentWorkerResult,
    EnrichmentWorkerUnsettledError,
)
from opinion_workbench_api.services.enrichment_models import (
    AcquisitionDiagnostic,
    EnrichedContent,
    EnrichmentBudget,
    EnrichmentOutcome,
    EnrichmentValidationError,
    evidence_fingerprint,
    preview_fingerprint,
    valid_source_url,
    validate_content,
)
from opinion_workbench_api.services.enrichment_staging import (
    MediaStagingError,
    ValidatedMedia,
)
from opinion_workbench_api.services.platform_access import (
    PlatformAccessBlockedError,
    PlatformAccessCoordinator,
)
from opinion_workbench_api.services.settled_tasks import database_call, settle

EnrichmentErrorCode = Literal[
    "stored_content_unavailable",
    "source_not_found",
    "source_active",
    "source_changed",
    "invalid_source",
    "browser_operation_active",
    "staging_unavailable",
    "invalid_enrichment",
    "service_unavailable",
    "worker_unsettled",
]


class ContentEnrichmentError(Exception):
    def __init__(self, code: EnrichmentErrorCode):
        super().__init__(code)
        self.code = code


class EnrichmentWorker(Protocol):
    async def enrich(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        content_id: str,
        content_url: str,
        term: str,
        budget: EnrichmentBudget,
        text_only: bool = True,
    ) -> EnrichmentWorkerResult: ...

    async def discard_session(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EnrichmentItem:
    source: SearchResultSourceRecord = field(repr=False)
    outcome: EnrichmentOutcome
    content: EnrichedContent | None = field(default=None, repr=False)
    input_fingerprint: str | None = None
    media: tuple[ValidatedMedia, ...] = field(default=(), repr=False)
    preview: bool = False
    diagnostic: AcquisitionDiagnostic | None = field(default=None, repr=False)

    @property
    def ready(self) -> bool:
        return (
            self.outcome == "completed"
            and self.content is not None
            and self.content.status == "ready"
        )

    @property
    def detail_analysis_eligible(self) -> bool:
        """Whether the acquired detail document contains usable evidence."""

        return self.content is not None and (
            self.content.text.coverage != "unavailable"
            and bool(self.content.text.title.strip() or self.content.text.body.strip())
        )

    @property
    def preview_analysis_eligible(self) -> bool:
        """Whether the frozen search result has usable preview text."""

        return bool(self.source.title.strip() or self.source.snippet.strip())

    @property
    def analysis_eligible(self) -> bool:
        """Whether trustworthy source text is available for analysis."""

        return self.detail_analysis_eligible or self.preview_analysis_eligible

    def as_preview(self) -> "EnrichmentItem":
        """Return a text-only view over the immutable stored search preview."""

        if self.preview or not self.preview_analysis_eligible:
            return self
        return EnrichmentItem(
            source=self.source,
            outcome=self.outcome,
            content=None,
            input_fingerprint=preview_fingerprint(
                platform=self.source.platform,
                content_id=self.source.platform_content_id,
                content_url=self.source.content_url,
                title=self.source.title,
                snippet=self.source.snippet,
            ),
            media=(),
            preview=True,
            diagnostic=self.diagnostic,
        )


class ContentEnrichmentService:
    def __init__(
        self,
        *,
        repository: SearchRunRepository,
        worker: EnrichmentWorker,
        browser_operations: BrowserOperationCoordinator,
        spool=None,
        timeout_seconds: float = 150.0,
        platform_access: PlatformAccessCoordinator | None = None,
    ) -> None:
        self._repository = repository
        self._worker = worker
        self._browser_operations = browser_operations
        # ``spool`` remains an injection compatibility seam for older tests
        # and callers.  The production composition no longer supplies one,
        # so this does not re-enable media staging in the live path.
        self._spool = spool
        if spool is not None:
            configure = getattr(worker, "configure_media_spool", None)
            if configure is not None:
                configure(spool.root if hasattr(spool, "root") else spool)
        self._timeout_seconds = timeout_seconds
        self._platform_access = platform_access
        self._lock = asyncio.Lock()
        self._active: EnrichmentSession | None = None
        self._closed = False

    def configure_platform_access(self, coordinator) -> None:
        self._platform_access = coordinator

    @property
    def native_acquisition(self):
        return bool(getattr(self._worker, "supports_manual_acquisition", False))

    def supports_platform(self, platform):
        from opinion_workbench_api.services.collector_contracts import supports_platform

        return supports_platform(self._worker, platform)

    @asynccontextmanager
    async def operation(
        self,
        *,
        access_snapshot=None,
        on_access_waiting=None,
        on_access_notice=None,
    ) -> AsyncIterator["EnrichmentSession"]:
        """Reserve Chrome across serial items; exit before text-only composition."""
        session = EnrichmentSession(
            self,
            BrowserOperationOwner("content_enrichment", uuid4()),
            access_snapshot=access_snapshot,
            on_access_waiting=on_access_waiting,
            on_access_notice=on_access_notice,
        )
        try:
            async with self._lock:
                if self._closed:
                    raise ContentEnrichmentError("service_unavailable")
                if (
                    self._active is not None
                    or not await self._browser_operations.try_claim(session.owner)
                ):
                    raise ContentEnrichmentError("browser_operation_active")
                self._active = session
            yield session
        finally:
            await settle(session.close())

    async def shutdown(self) -> None:
        async with self._lock:
            self._closed = True
            active = self._active
        if active is not None:
            await settle(active.close())
            await settle(active.release_hold())


def _to_enrichment_diagnostic(error: PlatformAccessBlockedError):
    value = error.diagnostic
    if value is None:
        return None
    return AcquisitionDiagnostic(
        stage="detail",
        outcome="platform_blocked_or_rate_limited",
        status_code=value.status_code,
        basis=(
            value.basis
            if value.basis
            in {"http_status", "explicit_platform_evidence", "browser_dom_evidence"}
            else "explicit_platform_evidence"
        ),
        target="selected_post",
    )


async def _maybe_await(value):
    if inspect.isawaitable(value):
        await value


async def _record_platform_block(service, platform, diagnostic):
    coordinator = getattr(service, "_platform_access", None)
    if coordinator is None:
        return
    active_block = getattr(coordinator, "active_block_async", None)
    if active_block is None:
        active_block = getattr(coordinator, "active_block", None)
    if callable(active_block):
        value = active_block(platform)
        if inspect.isawaitable(value):
            value = await value
        if value is not None:
            # A native bridge may already have persisted a richer diagnostic
            # (for example Retry-After) before the worker returned this
            # simplified acquisition result. Do not replace that durable
            # cooldown with a less-informative projection.
            return
    status_code = getattr(diagnostic, "status_code", None)
    basis = getattr(diagnostic, "basis", "explicit_platform_evidence")
    stage = getattr(diagnostic, "stage", "detail")
    blocker = getattr(coordinator, "block_async", None)
    if blocker is None:
        blocker = coordinator.block
    value = blocker(
        platform,
        stage=stage if stage in {"search", "detail", "media"} else "detail",
        status_code=status_code,
        basis=(
            basis
            if basis
            in {"http_status", "explicit_platform_evidence", "browser_dom_evidence"}
            else "explicit_platform_evidence"
        ),
    )
    if inspect.isawaitable(value):
        await value


class EnrichmentSession:
    """One browser lease, at most one item/file scope, no automatic retry."""

    def __init__(
        self,
        service: ContentEnrichmentService,
        owner: BrowserOperationOwner,
        *,
        access_snapshot=None,
        on_access_waiting=None,
        on_access_notice=None,
    ):
        self.owner = owner
        self._access_snapshot = access_snapshot
        self._on_access_waiting = on_access_waiting
        self._on_access_notice = on_access_notice
        self._service = service
        self._closed = False
        self._item_open = False
        self._cancel_requested = False
        self._acquire_task: asyncio.Task[EnrichmentItem] | None = None
        self._worker_task: asyncio.Task[EnrichmentWorkerResult] | None = None
        self._operation = None
        self._cleanup_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._unsettled: EnrichmentWorkerUnsettledError | None = None
        self._manual_hold = False
        self._settled = asyncio.Event()

    def hold_for_manual(self):
        self._manual_hold = True

    def discard_manual_hold(self):
        self._manual_hold = False

    async def show_manual(self, platform):
        await self._settled.wait()
        if (
            not self._manual_hold
            or not await self._service._browser_operations.is_owned_by(self.owner)
        ):
            raise ContentEnrichmentError("service_unavailable")
        result = await self._service._worker.manual_page(
            request_id=uuid4(), platform=platform, action="show"
        )
        if result.outcome not in ("opened_homepage", "opened_existing"):
            raise ContentEnrichmentError("service_unavailable")

    async def prepare_resume(self):
        await self._settled.wait()
        if self._unsettled is not None and not self._unsettled.quiescent():
            raise ContentEnrichmentError("worker_unsettled")
        # Stop the user-opened dedicated page before automated work is admitted.
        # This closes only the project's tab, preserving the browser profile.
        if self._manual_hold:
            await self._service._worker.discard_session()

    async def release_hold(self, *, abandon=False):
        await self.prepare_resume()
        if abandon:
            discard = getattr(
                self._service._worker, "discard_enrichment_checkpoint", None
            )
            if discard is not None:
                discard()
        self._manual_hold = False
        await self._release()

    async def _release(self):
        await settle(self._service._browser_operations.release(self.owner))
        async with self._service._lock:
            if self._service._active is self:
                self._service._active = None

    @asynccontextmanager
    async def item(
        self,
        *,
        run_id: int,
        result_id: int,
        budget: EnrichmentBudget | None = None,
        expected_source: SearchResultSourceRecord | None = None,
        on_content=None,
    ) -> AsyncIterator[EnrichmentItem]:
        if self._closed or not await self._service._browser_operations.is_owned_by(
            self.owner
        ):
            raise ContentEnrichmentError("service_unavailable")
        if self._item_open:
            raise ContentEnrichmentError("browser_operation_active")
        if any(
            type(value) is not int or not 1 <= value <= 9_223_372_036_854_775_807
            for value in (run_id, result_id)
        ):
            raise ContentEnrichmentError("invalid_source")
        self._item_open = True
        self._cancel_requested = False
        self._acquire_task = asyncio.create_task(
            self._acquire(
                run_id,
                result_id,
                budget or EnrichmentBudget(),
                expected_source,
                on_content,
            )
        )
        try:
            result = await asyncio.shield(self._acquire_task)
            if self._closed:
                raise ContentEnrichmentError("service_unavailable")
            yield result
        finally:
            try:
                await settle(self._stop_current())
            finally:
                try:
                    await settle(self._cleanup())
                finally:
                    self._acquire_task = None
                    self._worker_task = None
                    self._item_open = False

    async def _acquire(
        self,
        run_id: int,
        result_id: int,
        budget: EnrichmentBudget,
        expected_source: SearchResultSourceRecord | None = None,
        on_content=None,
    ) -> EnrichmentItem:
        try:
            source = await database_call(
                self._service._repository.get_result_source,
                run_id=run_id,
                result_id=result_id,
            )
        except SearchResultNotFoundError:
            raise ContentEnrichmentError("source_not_found") from None
        except SearchRunRepositoryUnavailableError:
            raise ContentEnrichmentError("service_unavailable") from None
        if source.collection_active:
            raise ContentEnrichmentError("source_active")
        # A summary freezes the observation before acquiring Chrome. Re-prove the
        # stored identity and compare before any navigation or staged allocation.
        if expected_source is not None and source != expected_source:
            raise ContentEnrichmentError("source_changed")
        if not valid_source_url(
            source.platform, source.platform_content_id, source.content_url
        ):
            raise ContentEnrichmentError("invalid_source")
        if self._cancel_requested or self._closed:
            return EnrichmentItem(source, "cancelled")
        request_id = uuid4()
        try:
            # This acquisition task is never cancelled by its caller. It owns
            # allocation/validation to completion; only the worker task receives
            # cancellation, so a filesystem thread cannot publish an orphan later.
            # Native acquisition is explicitly text-only.  Legacy/injected
            # workers retain the old manifest-backed spool seam for tests and
            # compatibility; the production native path never allocates it.
            if not self._service.native_acquisition:
                if self._service._spool is None:
                    raise MediaStagingError
                self._operation = await settle(
                    asyncio.to_thread(self._service._spool.create_operation, request_id)
                )
            if self._cancel_requested or self._closed:
                return EnrichmentItem(source, "cancelled")

            async def observe_content(value, *, force=False):
                if on_content is not None and (force or not self._cancel_requested):
                    checked = validate_content(
                        value.model_dump(),
                        platform=source.platform,
                        content_id=source.platform_content_id,
                        content_url=source.content_url,
                        budget=budget,
                    )
                    # Text-only analysis deliberately does not stage or read
                    # media files.  The callback receives an empty tuple so
                    # existing checkpoint consumers retain their shape.
                    await on_content(checked, ())

            native_options = (
                {"on_content": observe_content, "text_only": True}
                if self._service.native_acquisition
                else {}
            )
            worker_kwargs = {
                "request_id": request_id,
                "platform": source.platform,
                "content_id": source.platform_content_id,
                "content_url": source.content_url,
                "term": source.matched_terms[0],
                "budget": budget,
                **native_options,
            }
            # Native adapters coordinate each controlled request internally;
            # compatibility workers without that hook are paced at this one
            # detail-navigation boundary.
            native_pacing = self._service.native_acquisition and (
                self._service._platform_access is not None
            )
            if self._service._platform_access is not None and not native_pacing:
                await self._service._platform_access.wait_for_turn(
                    source.platform,
                    self._access_snapshot,
                    stage="detail",
                    on_waiting=self._on_access_waiting,
                )
            if self._service._platform_access is not None:
                worker_kwargs["platform_access_snapshot"] = self._access_snapshot
                worker_kwargs["on_access_waiting"] = self._on_access_waiting
            # Keep small test/injected workers compatible while making the
            # production contract explicit about the text-only scope.
            try:
                parameters = inspect.signature(self._service._worker.enrich).parameters
            except (TypeError, ValueError):
                parameters = {}
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if not accepts_kwargs:
                worker_kwargs = {
                    key: value
                    for key, value in worker_kwargs.items()
                    if key not in {"on_content", "text_only"} or key in parameters
                }
            if "text_only" in parameters or accepts_kwargs:
                worker_kwargs["text_only"] = True
            if not accepts_kwargs:
                for optional in ("platform_access_snapshot", "on_access_waiting"):
                    if optional not in parameters:
                        worker_kwargs.pop(optional, None)
            self._worker_task = asyncio.create_task(
                self._service._worker.enrich(**worker_kwargs)
            )
            try:
                access_timeout = 0.0
                coordinator = self._service._platform_access
                if coordinator is not None:
                    snapshot = self._access_snapshot
                    if snapshot is None:
                        from opinion_workbench_api.schemas.platform_access import (
                            default_platform_access_snapshot,
                        )

                        snapshot = default_platform_access_snapshot()
                    access_timeout = snapshot.for_platform(source.platform) * 64
                async with asyncio.timeout(
                    self._service._timeout_seconds + access_timeout
                ):
                    result = await self._worker_task
            except TimeoutError:
                return EnrichmentItem(source, "timed_out")
            except asyncio.CancelledError:
                return EnrichmentItem(source, "cancelled")
            except EnrichmentWorkerUnsettledError as error:
                self._unsettled = error
                self._closed = True
                raise ContentEnrichmentError("worker_unsettled") from None
            except PlatformAccessBlockedError as error:
                diagnostic = _to_enrichment_diagnostic(error)
                if self._on_access_notice is not None:
                    reader = (
                        getattr(
                            self._service._platform_access,
                            "active_block_async",
                            None,
                        )
                        or self._service._platform_access.active_block
                    )
                    value = reader(source.platform)
                    if inspect.isawaitable(value):
                        value = await value
                    await _maybe_await(
                        self._on_access_notice(
                            source.platform, value or error.diagnostic
                        )
                    )
                return EnrichmentItem(
                    source,
                    "platform_blocked_or_rate_limited",
                    diagnostic=diagnostic,
                )
            except AuthWorkerError:
                return EnrichmentItem(source, "internal_error")
            if self._cancel_requested or self._closed:
                return EnrichmentItem(source, "cancelled")
            if result.outcome == "platform_blocked_or_rate_limited":
                await _record_platform_block(
                    self._service,
                    source.platform,
                    result.diagnostic,
                )
                if self._on_access_notice is not None:
                    reader = (
                        getattr(
                            self._service._platform_access,
                            "active_block_async",
                            None,
                        )
                        or self._service._platform_access.active_block
                    )
                    value = reader(source.platform)
                    if inspect.isawaitable(value):
                        value = await value
                    await _maybe_await(self._on_access_notice(source.platform, value))
            paused_with_material = (
                result.outcome
                in (
                    "login_required",
                    "manual_challenge_required",
                    "platform_blocked_or_rate_limited",
                )
                and result.content is not None
                and self._service.native_acquisition
            )
            if result.outcome != "completed" and not paused_with_material:
                if result.content is not None or result.manifest is not None:
                    raise EnrichmentValidationError
                return EnrichmentItem(
                    source, result.outcome, diagnostic=result.diagnostic
                )
            if self._service.native_acquisition:
                if result.manifest is not None or result.content is None:
                    raise EnrichmentValidationError
                raw = result.content.model_dump()
            else:
                if (result.content is None) == (result.manifest is None):
                    raise EnrichmentValidationError
                if result.manifest is not None:
                    raw = await settle(
                        asyncio.to_thread(
                            self._operation.read_manifest, result.manifest
                        )
                    )
                else:
                    raw = result.content.model_dump()
            content = validate_content(
                raw,
                platform=source.platform,
                content_id=source.platform_content_id,
                content_url=source.content_url,
                budget=budget,
            )
            if self._cancel_requested or self._closed:
                return EnrichmentItem(source, "cancelled")
            media = ()
            if self._operation is not None:
                media = await settle(
                    asyncio.to_thread(
                        self._operation.read_assets,
                        content,
                        budget.max_total_bytes,
                    )
                )
            return EnrichmentItem(
                source,
                result.outcome,
                content,
                evidence_fingerprint(content),
                media,
                diagnostic=result.diagnostic,
            )
        except MediaStagingError:
            await self._service._worker.discard_session()
            raise ContentEnrichmentError("staging_unavailable") from None
        except EnrichmentValidationError:
            await self._service._worker.discard_session()
            raise ContentEnrichmentError("invalid_enrichment") from None

    async def _stop_current(self) -> None:
        self._cancel_requested = True
        worker_task = self._worker_task
        if (
            worker_task is not None
            and not worker_task.done()
            and not worker_task.cancelling()
        ):
            worker_task.cancel()
        acquire_task = self._acquire_task
        if acquire_task is not None:
            await asyncio.gather(acquire_task, return_exceptions=True)

    async def _cleanup(self) -> None:
        async with self._cleanup_lock:
            if self._unsettled is not None:
                if not self._unsettled.quiescent():
                    raise ContentEnrichmentError("worker_unsettled")
                self._unsettled = None
            operation = self._operation
            if operation is not None:
                try:
                    await settle(asyncio.to_thread(operation.cleanup))
                except MediaStagingError:
                    raise ContentEnrichmentError("staging_unavailable") from None
                finally:
                    self._operation = None

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed and self._operation is None:
                return
            self._closed = True
            try:
                await self._stop_current()
                await self._cleanup()
            finally:
                if not self._manual_hold and (
                    self._unsettled is None or self._unsettled.quiescent()
                ):
                    await self._release()
                self._settled.set()
