"""Explicit, serial stored-content acquisition without persistence or AI calls."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID, uuid4

from longtian_api.repositories.search_runs import (
    SearchResultNotFoundError,
    SearchResultSourceRecord,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
)
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.collector_contracts import (
    AuthWorkerError,
    EnrichmentWorkerResult,
    EnrichmentWorkerUnsettledError,
)
from longtian_api.services.enrichment_models import (
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
from longtian_api.services.enrichment_staging import (
    MediaOperation,
    MediaSpool,
    MediaStagingError,
    ValidatedMedia,
)
from longtian_api.services.settled_tasks import settle

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
    def configure_media_spool(self, root: Path) -> None: ...

    async def enrich(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        content_id: str,
        content_url: str,
        term: str,
        budget: EnrichmentBudget,
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

        return self.content is not None and bool(
            self.content.text.title.strip()
            or self.content.text.body.strip()
            or any(asset.status == "ready" for asset in self.content.assets)
        )

    @property
    def preview_analysis_eligible(self) -> bool:
        """Whether the frozen search result has usable preview text."""

        return bool(self.source.title.strip() or self.source.snippet.strip())

    @property
    def analysis_eligible(self) -> bool:
        """At least one trustworthy text or validated media item is present.

        This is intentionally broader than :attr:`ready`: a partial detail
        response can still contain useful text or media, and the frozen search
        title/snippet is a safe final fallback when detail acquisition fails.
        """

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
        spool: MediaSpool,
        timeout_seconds: float = 150.0,
    ) -> None:
        self._repository = repository
        self._worker = worker
        self._browser_operations = browser_operations
        self._spool = spool
        self._timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()
        self._active: EnrichmentSession | None = None
        self._closed = False
        # Configuration only; startup/GET must not create directories or processes.
        worker.configure_media_spool(spool.root)

    @property
    def native_acquisition(self):
        return bool(getattr(self._worker, "supports_manual_acquisition", False))

    def supports_platform(self, platform):
        from longtian_api.services.collector_contracts import supports_platform

        return supports_platform(self._worker, platform)

    @asynccontextmanager
    async def operation(self) -> AsyncIterator["EnrichmentSession"]:
        """Reserve Chrome across serial items; exit before text-only composition."""
        session = EnrichmentSession(
            self, BrowserOperationOwner("content_enrichment", uuid4())
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


class EnrichmentSession:
    """One browser lease, at most one item/file scope, no automatic retry."""

    def __init__(self, service: ContentEnrichmentService, owner: BrowserOperationOwner):
        self.owner = owner
        self._service = service
        self._closed = False
        self._item_open = False
        self._cancel_requested = False
        self._acquire_task: asyncio.Task[EnrichmentItem] | None = None
        self._worker_task: asyncio.Task[EnrichmentWorkerResult] | None = None
        self._operation: MediaOperation | None = None
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
        await self._service._browser_operations.release(self.owner)
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
            source = await asyncio.to_thread(
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
            self._operation = await asyncio.to_thread(
                self._service._spool.create_operation, request_id
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
                    # Only validated, owned files may accompany a text checkpoint.
                    media = await asyncio.to_thread(
                        self._operation.read_assets, checked, budget.max_total_bytes
                    )
                    await on_content(checked, media)

            native_options = (
                {"media_sink": self._operation, "on_content": observe_content}
                if self._service.native_acquisition
                else {}
            )
            self._worker_task = asyncio.create_task(
                self._service._worker.enrich(
                    request_id=request_id,
                    platform=source.platform,
                    content_id=source.platform_content_id,
                    content_url=source.content_url,
                    term=source.matched_terms[0],
                    budget=budget,
                    **native_options,
                )
            )
            try:
                async with asyncio.timeout(self._service._timeout_seconds):
                    result = await self._worker_task
            except TimeoutError:
                return EnrichmentItem(source, "timed_out")
            except asyncio.CancelledError:
                return EnrichmentItem(source, "cancelled")
            except EnrichmentWorkerUnsettledError as error:
                self._unsettled = error
                self._closed = True
                raise ContentEnrichmentError("worker_unsettled") from None
            except AuthWorkerError:
                return EnrichmentItem(source, "internal_error")
            if self._cancel_requested or self._closed:
                return EnrichmentItem(source, "cancelled")
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
            if (result.content is None) == (result.manifest is None):
                raise EnrichmentValidationError
            if result.manifest is not None:
                raw = await asyncio.to_thread(
                    self._operation.read_manifest, result.manifest
                )
            else:
                if result.content is None:
                    raise EnrichmentValidationError
                raw = result.content.model_dump()
            content = validate_content(
                raw,
                platform=source.platform,
                content_id=source.platform_content_id,
                content_url=source.content_url,
                budget=budget,
            )
            media = await asyncio.to_thread(
                self._operation.read_assets, content, budget.max_total_bytes
            )
            if self._cancel_requested or self._closed:
                return EnrichmentItem(source, "cancelled")
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
                    await asyncio.to_thread(operation.cleanup)
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
