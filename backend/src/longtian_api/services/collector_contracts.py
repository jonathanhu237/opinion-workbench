"""Project-owned collection contracts; no browser, transport or legacy imports.

Application services depend on these small protocols and result values instead
of a platform-specific process. Runtime selection is explicit: an injected
collector never falls back to another implementation after a failure.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.enrichment_models import (
    AcquisitionDiagnostic,
    EnrichedContent,
    EnrichmentBudget,
    EnrichmentOutcome,
    ManifestDescriptor,
)
from longtian_api.services.native_browser_contracts import ExecutionLimit


class QuiescentProcess(Protocol):
    @property
    def returncode(self) -> int | None: ...


AuthPlatformId = Literal["wb"]
AuthProgressPhase = Literal[
    "waiting_for_browser",
    "waiting_for_approval",
    "checking",
    "waiting_for_login",
]
AuthOutcome = Literal["connected", "disconnected", "failed", "cancelled"]
AuthReason = Literal[
    "none",
    "login_required",
    "browser_unavailable",
    "browser_disconnected",
    "internal_error",
    "cancelled",
]
SearchOutcome = Literal[
    "timed_out",
    "completed_with_results",
    "completed_empty",
    "completed_with_incomplete",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "page_state_unrecognized",
    "search_context_unavailable",
    "search_response_incompatible",
    "search_results_incompatible",
    "search_pagination_incompatible",
    "browser_unavailable",
    "browser_disconnected",
    "cancelled",
    "internal_error",
]
OpenResultOutcome = Literal[
    "opened",
    "content_not_found",
    "content_unavailable",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "internal_error",
]
ManualPageAction = Literal["show", "close"]
ManualPageOutcome = Literal[
    "opened_existing",
    "opened_homepage",
    "browser_unavailable",
    "navigation_failed",
    "internal_error",
    "cancelled",
    "closed",
    "not_present",
]
ProgressCallback = Callable[[UUID, AuthPlatformId, AuthProgressPhase], Awaitable[None]]
SessionDisconnectedCallback = Callable[[UUID | None], Awaitable[None]]
SearchProgressCallback = Callable[[int, int], Awaitable[None]]
SearchItemCallback = Callable[[int, "SearchWorkerItem"], Awaitable[None]]
SearchTermIncompleteReason = Literal["view_all_unresolved"]
SearchTermCompletedCallback = Callable[
    [int, int, SearchTermIncompleteReason | None], Awaitable[None]
]


def supports_platform(collector, platform):
    """Return whether the native Weibo collector owns this platform."""
    supported = getattr(collector, "supported_platforms", None)
    return platform == "wb" and (supported is None or platform in supported)


class AuthWorkerError(Exception):
    """A deliberately detail-free persistent-worker failure."""


class AuthWorkerBusyError(AuthWorkerError):
    """The worker client already owns one in-flight request."""


class EnrichmentWorkerUnsettledError(AuthWorkerError):
    """No terminal/exit proof: keep the operation quarantined, not reusable."""

    def __init__(self, process: QuiescentProcess):
        super().__init__()
        self._process = process

    def quiescent(self) -> bool:
        return self._process.returncode is not None


@dataclass(frozen=True, slots=True)
class AuthWorkerResult:
    outcome: AuthOutcome
    reason: AuthReason


@dataclass(frozen=True, slots=True)
class SearchWorkerItem:
    content_id: str
    content_type: str
    title: str
    snippet: str
    creator_hash: str
    publisher_name: str
    published_at_text: str
    content_url: str
    discovered_at: int


@dataclass(frozen=True, slots=True)
class SearchTermDiagnostic:
    """A keyword that ended after bounded omission recovery without full coverage."""

    position: int
    reason: SearchTermIncompleteReason
    result_count: int


@dataclass(frozen=True, slots=True)
class SearchWorkerResult:
    outcome: SearchOutcome
    execution_limit: ExecutionLimit | None = None
    incomplete_terms: tuple[SearchTermDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenResultWorkerResult:
    outcome: OpenResultOutcome


@dataclass(frozen=True, slots=True)
class ManualPageWorkerResult:
    outcome: ManualPageOutcome


@dataclass(frozen=True, slots=True)
class EnrichmentWorkerResult:
    outcome: EnrichmentOutcome
    content: EnrichedContent | None = field(default=None, repr=False)
    manifest: ManifestDescriptor | None = None
    diagnostic: AcquisitionDiagnostic | None = field(default=None, repr=False)


class SearchCollector(Protocol):
    @property
    def browser_session_available(self) -> bool: ...

    async def search(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        terms: Sequence[str],
        max_results_per_term: int,
        on_progress: SearchProgressCallback,
        on_item: SearchItemCallback,
        on_term_completed: SearchTermCompletedCallback,
        max_total_results: int | None = None,
        previous_content_ids: Sequence[str] = (),
        previous_content_ids_by_term: Sequence[Sequence[str]] = (),
    ) -> SearchWorkerResult: ...

    async def open_result(
        self,
        *,
        request_id: UUID,
        term: str,
        content_id: str,
    ) -> OpenResultWorkerResult: ...

    async def manual_page(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        action: ManualPageAction,
    ) -> ManualPageWorkerResult: ...

    async def discard_session(self) -> None: ...


class ContentCollector(Protocol):
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


class CollectorRuntime(SearchCollector, ContentCollector, Protocol):
    async def check(
        self,
        *,
        request_id: UUID,
        platform: AuthPlatformId,
    ) -> AuthWorkerResult: ...

    async def shutdown(self) -> None: ...


class CollectorFactory(Protocol):
    def __call__(
        self,
        *,
        browser_profile_dir: Path,
        on_progress: ProgressCallback,
        on_session_disconnected: SessionDisconnectedCallback,
    ) -> CollectorRuntime: ...
