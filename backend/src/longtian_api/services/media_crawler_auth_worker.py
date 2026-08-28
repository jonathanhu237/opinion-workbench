"""Own the persistent MediaCrawler authentication worker and its v2 protocol."""

import asyncio
import json
import os
import re
import signal
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast, get_args
from uuid import UUID

from pydantic import ValidationError

from longtian_api.search_platforms import (
    SEARCH_PLATFORMS,
    SearchPlatform,
    is_valid_search_content_url,
)
from longtian_api.services.enrichment_models import (
    ENRICHMENT_COMMAND_PREFIX,
    ENRICHMENT_EVENT_PREFIX,
    MAX_ENRICHMENT_COMMAND_BYTES,
    MAX_ENRICHMENT_EVENT_BYTES,
    MEDIA_ROOT_ENV,
    EnrichedContent,
    EnrichmentBudget,
    EnrichmentOutcome,
    EnrichmentValidationError,
    ManifestDescriptor,
    decode_json_object,
    valid_source_url,
    validate_content,
)
from longtian_api.services.settled_tasks import settle

AUTH_COMMAND_PREFIX = b"__MEDIACRAWLER_AUTH_COMMAND__"
AUTH_EVENT_PREFIX = b"__MEDIACRAWLER_AUTH_EVENT__"
SEARCH_COMMAND_PREFIX = b"__MEDIACRAWLER_SEARCH_COMMAND__"
SEARCH_EVENT_PREFIX = b"__MEDIACRAWLER_SEARCH_EVENT__"
MAX_AUTH_FRAME_BYTES = 1024
MAX_SEARCH_COMMAND_BYTES = 32 * 1024
MAX_SEARCH_EVENT_BYTES = 64 * 1024
MAX_CHILD_OUTPUT_LINE_BYTES = 64 * 1024
_MASKED_CREATOR_HASH = re.compile(r"[0-9a-f]{16}")

AuthPlatformId = Literal["wb", "dy", "ks", "xhs", "toutiao"]
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
    "completed_with_results",
    "completed_empty",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
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
_MANUAL_OUTCOMES = {
    "show": {
        "opened_existing",
        "opened_homepage",
        "browser_unavailable",
        "navigation_failed",
        "internal_error",
        "cancelled",
    },
    "close": {
        "closed",
        "not_present",
        "browser_unavailable",
        "internal_error",
        "cancelled",
    },
}

_WORKER_COMMAND = (
    "uv",
    "run",
    "--frozen",
    "--project",
    "{media_crawler_dir}",
    "python",
    "-m",
    "tools.auth_worker",
)
_RESULT_PAIRS: set[tuple[str, str]] = {
    ("connected", "none"),
    ("disconnected", "login_required"),
    ("failed", "browser_unavailable"),
    ("failed", "browser_disconnected"),
    ("failed", "internal_error"),
    ("cancelled", "cancelled"),
}


class _AsyncLineReader(Protocol):
    async def readline(self) -> bytes: ...


class _AsyncByteReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class _AsyncLineWriter(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


class ManagedProcess(Protocol):
    """The asyncio subprocess surface required by the worker client."""

    pid: int
    returncode: int | None
    stdin: _AsyncLineWriter | None
    stdout: _AsyncLineReader | None
    stderr: _AsyncByteReader | None

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessLauncher = Callable[[tuple[str, ...], Path], Awaitable[ManagedProcess]]
ProcessGroupTerminator = Callable[[ManagedProcess, float], Awaitable[None]]
ProgressCallback = Callable[[UUID, AuthPlatformId, AuthProgressPhase], Awaitable[None]]
SessionDisconnectedCallback = Callable[[UUID | None], Awaitable[None]]
SearchProgressCallback = Callable[[int, int], Awaitable[None]]
SearchItemCallback = Callable[[int, "SearchWorkerItem"], Awaitable[None]]
SearchTermCompletedCallback = Callable[[int, int], Awaitable[None]]


class AuthWorkerError(Exception):
    """A deliberately detail-free persistent-worker failure."""


class AuthWorkerBusyError(AuthWorkerError):
    """The worker client already owns one in-flight request."""


class EnrichmentWorkerUnsettledError(AuthWorkerError):
    """No terminal/exit proof: keep the operation quarantined, not reusable."""

    def __init__(self, process: ManagedProcess):
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
class SearchWorkerResult:
    outcome: SearchOutcome


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


@dataclass(slots=True)
class _ActiveRequest:
    request_id: UUID
    platform: AuthPlatformId
    kind: Literal["auth", "search", "open_result", "manual_page", "enrichment"]
    result: asyncio.Future[
        AuthWorkerResult
        | SearchWorkerResult
        | OpenResultWorkerResult
        | ManualPageWorkerResult
        | EnrichmentWorkerResult
    ]
    search_term_count: int = 0
    search_max_results_per_term: int = 0
    search_current_term_position: int = -1
    search_item_count: int = 0
    search_item_counts: list[int] = field(default_factory=list)
    on_search_progress: SearchProgressCallback | None = None
    on_search_item: SearchItemCallback | None = None
    on_term_completed: SearchTermCompletedCallback | None = None
    search_completed_count: int = 0
    manual_action: ManualPageAction | None = None
    cancel_requested: bool = False
    previous_phase: AuthProgressPhase | None = None
    seen_login: bool = False
    enrichment_content_id: str | None = None
    enrichment_content_url: str | None = None
    enrichment_budget: EnrichmentBudget | None = None
    enrichment_accepted: bool = False
    enrichment_terminal: bool = False


class PersistentAuthWorkerClient:
    """Lazily launch and serialize requests over one MediaCrawler worker."""

    def __init__(
        self,
        *,
        media_crawler_dir: Path,
        on_progress: ProgressCallback,
        on_session_disconnected: SessionDisconnectedCallback,
        process_launcher: ProcessLauncher | None = None,
        process_group_terminator: ProcessGroupTerminator | None = None,
        ready_timeout_seconds: float = 30.0,
        cancel_timeout_seconds: float = 3.0,
        shutdown_timeout_seconds: float = 5.0,
        termination_grace_seconds: float = 3.0,
        media_spool_root: Path | None = None,
    ) -> None:
        self._media_crawler_dir = media_crawler_dir
        self._on_progress = on_progress
        self._on_session_disconnected = on_session_disconnected
        self._process_launcher = process_launcher
        self._media_spool_root = media_spool_root
        self._process_group_terminator = (
            process_group_terminator or terminate_owned_process_group
        )
        self._ready_timeout_seconds = ready_timeout_seconds
        self._cancel_timeout_seconds = cancel_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._termination_grace_seconds = termination_grace_seconds

        self._request_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._generation = 0
        self._failed_generations: set[int] = set()
        self._process: ManagedProcess | None = None
        self._ready: asyncio.Future[None] | None = None
        self._stopped: asyncio.Future[None] | None = None
        self._exited: asyncio.Future[int] | None = None
        self._active: _ActiveRequest | None = None
        self._completed_request_id: UUID | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._shutdown_generation: int | None = None
        self._closed = False

    @property
    def command(self) -> tuple[str, ...]:
        """Return the fixed, credential-free worker command."""
        return tuple(
            str(self._media_crawler_dir) if part == "{media_crawler_dir}" else part
            for part in _WORKER_COMMAND
        )

    def configure_media_spool(self, root: Path) -> None:
        """Configure a trusted root before launch, without filesystem/browser I/O."""
        if not root.is_absolute() or ".." in root.parts:
            raise AuthWorkerError
        if root == self._media_spool_root:
            return
        if self._process is not None or self._generation or self._request_lock.locked():
            raise AuthWorkerError
        self._media_spool_root = root

    async def enrich(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        content_id: str,
        content_url: str,
        term: str,
        budget: EnrichmentBudget,
    ) -> EnrichmentWorkerResult:
        """One exact stored-source request, isolated from auth/search protocols."""
        if self._request_lock.locked():
            raise AuthWorkerBusyError
        if (
            self._media_spool_root is None
            or not isinstance(request_id, UUID)
            or request_id.version != 4
            or not valid_source_url(platform, content_id, content_url)
            or type(term) is not str
            or len(term) > 200
            or (platform == "xhs" and not term.strip())
            or not isinstance(budget, EnrichmentBudget)
        ):
            raise AuthWorkerError
        async with self._request_lock:
            if self._closed:
                raise AuthWorkerError
            self._completed_request_id = None
            try:
                generation = await self._ensure_worker()
            except asyncio.CancelledError:
                await asyncio.shield(
                    self._recycle_generation(self._generation, invalidate=True)
                )
                raise
            request = _ActiveRequest(
                request_id=request_id,
                platform=platform,
                kind="enrichment",
                result=asyncio.get_running_loop().create_future(),
                enrichment_content_id=content_id,
                enrichment_content_url=content_url,
                enrichment_budget=budget,
            )
            process = self._process
            if process is None:
                raise AuthWorkerError
            self._active = request
            try:
                await self._write_command(
                    generation,
                    {
                        "version": 1,
                        "type": "command",
                        "command": "enrich",
                        "request_id": str(request_id),
                        "platform": platform,
                        "content_id": content_id,
                        "content_url": content_url,
                        "term": term,
                        "budget": budget.model_dump(),
                    },
                    prefix=ENRICHMENT_COMMAND_PREFIX,
                    max_bytes=MAX_ENRICHMENT_COMMAND_BYTES,
                )
                result = await asyncio.shield(request.result)
                if not isinstance(result, EnrichmentWorkerResult):
                    raise AuthWorkerError
                return result
            except asyncio.CancelledError:
                await settle(self._cancel_request(generation, request))
                raise
            finally:
                if self._active is request:
                    self._active = None
                if not request.enrichment_terminal and process.returncode is None:
                    raise EnrichmentWorkerUnsettledError(process)

    async def check(
        self, *, request_id: UUID, platform: AuthPlatformId
    ) -> AuthWorkerResult:
        """Run one correlated platform check on the shared worker."""
        if self._request_lock.locked():
            raise AuthWorkerBusyError

        async with self._request_lock:
            if self._closed:
                raise AuthWorkerError
            # The service cannot accept another request until it has projected
            # the prior result, so a new check safely acknowledges that result.
            self._completed_request_id = None
            try:
                generation = await self._ensure_worker()
            except asyncio.CancelledError:
                generation = self._generation
                await asyncio.shield(
                    self._recycle_generation(generation, invalidate=True)
                )
                raise
            loop = asyncio.get_running_loop()
            request = _ActiveRequest(
                request_id=request_id,
                platform=platform,
                kind="auth",
                result=loop.create_future(),
            )
            if self._active is not None:
                raise AuthWorkerBusyError
            self._active = request
            try:
                await self._write_command(
                    generation,
                    {
                        "version": 2,
                        "type": "command",
                        "command": "check",
                        "request_id": str(request_id),
                        "platform": platform,
                    },
                )
                result = await asyncio.shield(request.result)
                if not isinstance(result, AuthWorkerResult):
                    raise AuthWorkerError
                return result
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel_request(generation, request))
                raise
            finally:
                if self._active is request:
                    self._active = None

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
    ) -> SearchWorkerResult:
        """Run one correlated product search on the shared worker."""

        if self._request_lock.locked():
            raise AuthWorkerBusyError
        if (
            platform not in SEARCH_PLATFORMS
            or not 1 <= len(terms) <= 20
            or not 1 <= max_results_per_term <= 50
        ):
            raise AuthWorkerError

        async with self._request_lock:
            if self._closed:
                raise AuthWorkerError
            self._completed_request_id = None
            try:
                generation = await self._ensure_worker()
            except asyncio.CancelledError:
                generation = self._generation
                await asyncio.shield(
                    self._recycle_generation(generation, invalidate=True)
                )
                raise
            loop = asyncio.get_running_loop()
            request = _ActiveRequest(
                request_id=request_id,
                platform=platform,
                kind="search",
                result=loop.create_future(),
                search_term_count=len(terms),
                search_max_results_per_term=max_results_per_term,
                search_item_counts=[0] * len(terms),
                on_search_progress=on_progress,
                on_search_item=on_item,
                on_term_completed=on_term_completed,
            )
            if self._active is not None:
                raise AuthWorkerBusyError
            self._active = request
            try:
                await self._write_command(
                    generation,
                    {
                        "version": 2,
                        "type": "command",
                        "command": "search",
                        "request_id": str(request_id),
                        "platform": platform,
                        "terms": list(terms),
                        "max_results_per_term": max_results_per_term,
                    },
                    prefix=SEARCH_COMMAND_PREFIX,
                    max_bytes=MAX_SEARCH_COMMAND_BYTES,
                )
                result = await asyncio.shield(request.result)
                if not isinstance(result, SearchWorkerResult):
                    raise AuthWorkerError
                return result
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel_request(generation, request))
                raise
            finally:
                if self._active is request:
                    self._active = None

    async def open_result(
        self,
        *,
        request_id: UUID,
        term: str,
        content_id: str,
    ) -> OpenResultWorkerResult:
        """Resolve and open one stored XHS result through the strict worker."""

        if self._request_lock.locked():
            raise AuthWorkerBusyError
        if (
            type(term) is not str
            or term != term.strip()
            or not term
            or len(term) > 200
            or re.fullmatch(r"[0-9a-f]{24}", content_id) is None
        ):
            raise AuthWorkerError

        async with self._request_lock:
            if self._closed:
                raise AuthWorkerError
            self._completed_request_id = None
            try:
                generation = await self._ensure_worker()
            except asyncio.CancelledError:
                generation = self._generation
                await asyncio.shield(
                    self._recycle_generation(generation, invalidate=True)
                )
                raise
            loop = asyncio.get_running_loop()
            request = _ActiveRequest(
                request_id=request_id,
                platform="xhs",
                kind="open_result",
                result=loop.create_future(),
            )
            if self._active is not None:
                raise AuthWorkerBusyError
            self._active = request
            try:
                await self._write_command(
                    generation,
                    {
                        "version": 2,
                        "type": "command",
                        "command": "open_result",
                        "request_id": str(request_id),
                        "platform": "xhs",
                        "term": term,
                        "content_id": content_id,
                    },
                    prefix=SEARCH_COMMAND_PREFIX,
                    max_bytes=MAX_SEARCH_COMMAND_BYTES,
                )
                result = await asyncio.shield(request.result)
                if not isinstance(result, OpenResultWorkerResult):
                    raise AuthWorkerError
                return result
            except asyncio.CancelledError:
                await asyncio.shield(
                    self._recycle_generation(generation, invalidate=True)
                )
                raise
            finally:
                if self._active is request:
                    self._active = None

    async def manual_page(
        self,
        *,
        request_id: UUID,
        platform: SearchPlatform,
        action: ManualPageAction,
    ) -> ManualPageWorkerResult:
        """Show/close owned pages; absent cleanup never launches a worker."""
        if self._request_lock.locked():
            raise AuthWorkerBusyError
        if platform not in SEARCH_PLATFORMS or action not in _MANUAL_OUTCOMES:
            raise AuthWorkerError
        async with self._request_lock:
            if action == "close" and (
                self._process is None
                or self._process.returncode is not None
                or self._generation in self._failed_generations
            ):
                return ManualPageWorkerResult("not_present")
            if self._closed:
                raise AuthWorkerError
            try:
                generation = (
                    self._generation
                    if action == "close"
                    else await self._ensure_worker()
                )
            except asyncio.CancelledError:
                await asyncio.shield(
                    self._recycle_generation(self._generation, invalidate=True)
                )
                raise
            request = _ActiveRequest(
                request_id=request_id,
                platform=platform,
                kind="manual_page",
                result=asyncio.get_running_loop().create_future(),
                manual_action=action,
            )
            self._active = request
            self._completed_request_id = None
            try:
                await self._write_command(
                    generation,
                    {
                        "version": 2,
                        "type": "command",
                        "command": "manual_page",
                        "request_id": str(request_id),
                        "platform": platform,
                        "action": action,
                    },
                    prefix=SEARCH_COMMAND_PREFIX,
                    max_bytes=MAX_SEARCH_COMMAND_BYTES,
                )
                result = await asyncio.shield(request.result)
                if not isinstance(result, ManualPageWorkerResult):
                    raise AuthWorkerError
                return result
            except asyncio.CancelledError:
                await asyncio.shield(self._cancel_request(generation, request))
                raise
            finally:
                if self._active is request:
                    self._active = None

    async def discard_session(self) -> None:
        """Recycle only the owned worker when its page cleanup cannot be proved."""
        await self._recycle_generation(self._generation, invalidate=True)

    async def shutdown(self) -> None:
        """Stop the owned worker, falling back to its process group only."""
        self._closed = True
        async with self._request_lock:
            process = self._process
            generation = self._generation
            stopped = self._stopped
            exited = self._exited
            if process is None:
                return

            self._shutdown_generation = generation
            try:
                await self._write_command(
                    generation,
                    {"version": 2, "type": "command", "command": "shutdown"},
                )
                if stopped is None or exited is None:
                    raise AuthWorkerError
                async with asyncio.timeout(self._shutdown_timeout_seconds):
                    await asyncio.shield(stopped)
                    return_code = await asyncio.shield(exited)
                if return_code != 0:
                    raise AuthWorkerError
                await self._detach_generation(generation)
            except (AuthWorkerError, TimeoutError):
                await self._recycle_generation(generation, invalidate=False)

    async def _ensure_worker(self) -> int:
        async with self._lifecycle_lock:
            if self._closed:
                raise AuthWorkerError
            existing_process = self._process
            if existing_process is not None:
                if (
                    existing_process.returncode is None
                    and self._generation not in self._failed_generations
                    and self._ready is not None
                    and self._ready.done()
                    and self._ready.exception() is None
                ):
                    return self._generation
                stale_generation = self._generation
            else:
                stale_generation = None

        if stale_generation is not None:
            await self._recycle_generation(stale_generation, invalidate=True)

        async with self._lifecycle_lock:
            if self._closed:
                raise AuthWorkerError
            try:
                if self._process_launcher is None:
                    process = await launch_process(
                        self.command,
                        self._media_crawler_dir,
                        media_spool_root=self._media_spool_root,
                    )
                else:
                    process = await self._process_launcher(
                        self.command, self._media_crawler_dir
                    )
            except Exception:
                raise AuthWorkerError from None
            if (
                process.stdin is None
                or process.stdout is None
                or process.stderr is None
            ):
                if process.returncode is None:
                    await self._process_group_terminator(
                        process, self._termination_grace_seconds
                    )
                raise AuthWorkerError

            self._generation += 1
            generation = self._generation
            loop = asyncio.get_running_loop()
            self._process = process
            self._ready = loop.create_future()
            self._stopped = loop.create_future()
            self._exited = loop.create_future()
            self._shutdown_generation = None
            self._reader_task = asyncio.create_task(
                self._read_stdout(generation, process.stdout),
                name=f"media-crawler-auth-reader-{generation}",
            )
            self._stderr_task = asyncio.create_task(
                _drain(process.stderr),
                name=f"media-crawler-auth-stderr-{generation}",
            )
            self._wait_task = asyncio.create_task(
                self._watch_process(generation, process),
                name=f"media-crawler-auth-wait-{generation}",
            )
            ready = self._ready

        try:
            async with asyncio.timeout(self._ready_timeout_seconds):
                await asyncio.shield(ready)
        except (AuthWorkerError, TimeoutError):
            await self._recycle_generation(generation, invalidate=True)
            raise AuthWorkerError from None
        return generation

    async def _cancel_request(self, generation: int, request: _ActiveRequest) -> None:
        if request.result.done():
            return
        try:
            is_search = request.kind in {"search", "manual_page"}
            is_enrichment = request.kind == "enrichment"
            request.cancel_requested = True
            await self._write_command(
                generation,
                {
                    "version": 1 if is_enrichment else 2,
                    "type": "command",
                    "command": "cancel",
                    "request_id": str(request.request_id),
                },
                prefix=(
                    ENRICHMENT_COMMAND_PREFIX
                    if is_enrichment
                    else SEARCH_COMMAND_PREFIX
                    if is_search
                    else AUTH_COMMAND_PREFIX
                ),
                max_bytes=(
                    MAX_ENRICHMENT_COMMAND_BYTES
                    if is_enrichment
                    else MAX_SEARCH_COMMAND_BYTES
                    if is_search
                    else MAX_AUTH_FRAME_BYTES
                ),
            )
            async with asyncio.timeout(self._cancel_timeout_seconds):
                result = await asyncio.shield(request.result)
            expected = (
                EnrichmentWorkerResult("cancelled")
                if is_enrichment
                else ManualPageWorkerResult("cancelled")
                if request.kind == "manual_page"
                else SearchWorkerResult("cancelled")
                if is_search
                else AuthWorkerResult("cancelled", "cancelled")
            )
            if result != expected:
                raise AuthWorkerError
        except (AuthWorkerError, TimeoutError):
            await self._recycle_generation(generation, invalidate=True)

    async def _write_command(
        self,
        generation: int,
        payload: dict[str, object],
        *,
        prefix: bytes = AUTH_COMMAND_PREFIX,
        max_bytes: int = MAX_AUTH_FRAME_BYTES,
    ) -> None:
        process = self._process
        if (
            generation != self._generation
            or process is None
            or process.returncode is not None
            or process.stdin is None
        ):
            raise AuthWorkerError
        frame = (
            prefix
            + json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
        if len(frame) > max_bytes:
            raise AuthWorkerError
        try:
            process.stdin.write(frame)
            await process.stdin.drain()
        except Exception:
            await self._fail_generation(generation)
            raise AuthWorkerError from None

    async def _read_stdout(self, generation: int, reader: _AsyncLineReader) -> None:
        try:
            while line := await reader.readline():
                event = _parse_worker_event(line)
                await self._handle_event(generation, event)
            if not self._is_valid_shutdown_eof(generation):
                raise AuthWorkerError
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._fail_generation(generation)

    async def _watch_process(self, generation: int, process: ManagedProcess) -> None:
        try:
            return_code = await process.wait()
            if generation != self._generation:
                return
            exited = self._exited
            if exited is not None and not exited.done():
                exited.set_result(return_code)
            if self._shutdown_generation != generation:
                await self._fail_generation(generation)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._fail_generation(generation)

    async def _handle_event(self, generation: int, event: dict[str, object]) -> None:
        if generation != self._generation:
            return
        event_name = event["event"]
        protocol = event["protocol"]
        if event_name == "ready":
            if protocol != "auth":
                raise AuthWorkerError
            ready = self._ready
            if ready is None or ready.done() or self._active is not None:
                raise AuthWorkerError
            ready.set_result(None)
            return
        if event_name == "stopped":
            if protocol != "auth":
                raise AuthWorkerError
            stopped = self._stopped
            if (
                self._shutdown_generation != generation
                or stopped is None
                or stopped.done()
                or self._active is not None
            ):
                raise AuthWorkerError
            stopped.set_result(None)
            return
        if event_name == "session":
            if protocol != "auth":
                raise AuthWorkerError
            active = self._active
            if active is not None and (
                active.previous_phase is not None
                or active.enrichment_accepted
                or (
                    active.kind == "search" and active.search_current_term_position >= 0
                )
            ):
                raise AuthWorkerError
            # The worker may emit an idle-session disconnect immediately before
            # it reads a newly queued check. Its stdout frame can reach this
            # reader after `check()` has installed the new active request. Such
            # a pre-progress event still belongs to the previous browser
            # session and must not recycle the healthy worker or cancel the new
            # request. Once request progress has started, the strict busy
            # contract remains result(failed/browser_disconnected) -> session.
            affected_request_id = self._completed_request_id if active is None else None
            await self._on_session_disconnected(affected_request_id)
            return

        active = self._active
        if active is None:
            raise AuthWorkerError
        request_id = cast(UUID, event["request_id"])
        platform = cast(AuthPlatformId, event["platform"])
        if request_id != active.request_id or platform != active.platform:
            raise AuthWorkerError

        if active.kind == "enrichment":
            if (
                protocol != "enrichment"
                or active.result.done()
                or event["content_id"] != active.enrichment_content_id
            ):
                raise AuthWorkerError
            if event_name == "accepted":
                if active.enrichment_accepted:
                    raise AuthWorkerError
                active.enrichment_accepted = True
                return
            if (
                event_name != "result"
                or not active.enrichment_accepted
                or (event["outcome"] == "cancelled" and not active.cancel_requested)
            ):
                raise AuthWorkerError
            content = None
            if event["content"] is not None:
                if (
                    active.enrichment_budget is None
                    or active.enrichment_content_url is None
                ):
                    raise AuthWorkerError
                try:
                    content = validate_content(
                        event["content"],
                        platform=platform,
                        content_id=active.enrichment_content_id or "",
                        content_url=active.enrichment_content_url,
                        budget=active.enrichment_budget,
                    )
                except EnrichmentValidationError:
                    raise AuthWorkerError from None
            active.enrichment_terminal = True
            self._active = None
            active.result.set_result(
                EnrichmentWorkerResult(
                    cast(EnrichmentOutcome, event["outcome"]),
                    content,
                    cast(ManifestDescriptor | None, event["manifest"]),
                )
            )
            return

        if active.kind == "search":
            if protocol != "search":
                raise AuthWorkerError
            if event_name == "progress":
                position = cast(int, event["term_position"])
                count = cast(int, event["term_count"])
                if (
                    count != active.search_term_count
                    or position != active.search_current_term_position + 1
                    or position != active.search_completed_count
                ):
                    raise AuthWorkerError
                active.search_current_term_position = position
                callback = active.on_search_progress
                if callback is None:
                    raise AuthWorkerError
                await callback(position, count)
                return
            if event_name == "item":
                position = cast(int, event["term_position"])
                callback = active.on_search_item
                if (
                    callback is None
                    or position != active.search_current_term_position
                    or position != active.search_completed_count
                    or not 0 <= position < active.search_term_count
                    or active.search_item_counts[position]
                    >= active.search_max_results_per_term
                ):
                    raise AuthWorkerError
                await callback(position, cast(SearchWorkerItem, event["item"]))
                active.search_item_counts[position] += 1
                active.search_item_count += 1
                return
            if event_name == "term_completed":
                position = cast(int, event["term_position"])
                count = cast(int, event["item_count"])
                callback = active.on_term_completed
                if (
                    callback is None
                    or position != active.search_current_term_position
                    or position != active.search_completed_count
                    or not 0 <= position < active.search_term_count
                    or count != active.search_item_counts[position]
                ):
                    raise AuthWorkerError
                await callback(position, count)
                active.search_completed_count += 1
                return
            if event_name != "result" or active.result.done():
                raise AuthWorkerError
            outcome = cast(SearchOutcome, event["outcome"])
            if outcome == "cancelled" and not active.cancel_requested:
                raise AuthWorkerError
            if outcome in {"completed_with_results", "completed_empty"}:
                if active.search_completed_count != active.search_term_count:
                    raise AuthWorkerError
                if (outcome == "completed_with_results") != (
                    active.search_item_count > 0
                ):
                    raise AuthWorkerError
            self._active = None
            active.result.set_result(SearchWorkerResult(outcome))
            return

        if active.kind == "manual_page":
            if (
                protocol != "search"
                or event_name != "manual_page"
                or active.result.done()
                or event["action"] != active.manual_action
                or (event["outcome"] == "cancelled" and not active.cancel_requested)
            ):
                raise AuthWorkerError
            self._active = None
            active.result.set_result(
                ManualPageWorkerResult(cast(ManualPageOutcome, event["outcome"]))
            )
            return

        if active.kind == "open_result":
            if protocol != "search" or event_name != "open_result":
                raise AuthWorkerError
            if active.result.done():
                raise AuthWorkerError
            self._active = None
            active.result.set_result(
                OpenResultWorkerResult(cast(OpenResultOutcome, event["outcome"]))
            )
            return

        if protocol != "auth":
            raise AuthWorkerError

        if event_name == "progress":
            phase = cast(AuthProgressPhase, event["phase"])
            if phase == "waiting_for_login":
                if active.seen_login:
                    raise AuthWorkerError
                active.seen_login = True
            _validate_progress_transition(active.previous_phase, phase)
            active.previous_phase = phase
            await self._on_progress(request_id, platform, phase)
            return

        outcome = cast(AuthOutcome, event["outcome"])
        reason = cast(AuthReason, event["reason"])
        if (
            outcome in {"connected", "disconnected"}
            and active.previous_phase != "checking"
        ):
            raise AuthWorkerError
        if active.result.done():
            raise AuthWorkerError
        self._active = None
        self._completed_request_id = active.request_id
        active.result.set_result(AuthWorkerResult(outcome, reason))

    async def _fail_generation(self, generation: int) -> None:
        if generation != self._generation or generation in self._failed_generations:
            return
        self._failed_generations.add(generation)
        error = AuthWorkerError()
        control_futures = (self._ready, self._stopped, self._exited)
        active = self._active
        affected_request_id = (
            active.request_id if active is not None else self._completed_request_id
        )
        # Clear and terminate this generation before waking a caller. That
        # prevents a fast follow-up POST from writing to a known-broken worker.
        await self._recycle_generation(generation, invalidate=False)
        await self._on_session_disconnected(affected_request_id)
        for future in control_futures:
            if future is not None and not future.done():
                future.set_exception(error)
                # Control futures are not always awaited (for example, an idle
                # crash has no shutdown waiter). Mark the exception observed
                # while preserving its behavior for any existing waiter.
                future.exception()
        if active is not None and not active.result.done():
            active.result.set_exception(error)
            active.result.exception()

    async def _recycle_generation(self, generation: int, *, invalidate: bool) -> None:
        should_invalidate = False
        if invalidate and generation not in self._failed_generations:
            self._failed_generations.add(generation)
            should_invalidate = True

        async with self._lifecycle_lock:
            if generation != self._generation or self._process is None:
                return
            process = self._process
            tasks = (self._reader_task, self._stderr_task, self._wait_task)
            self._clear_generation()

        current = asyncio.current_task()
        for task in tasks:
            if task is not None and task is not current and not task.done():
                task.cancel()
        if process.returncode is None:
            try:
                await self._process_group_terminator(
                    process, self._termination_grace_seconds
                )
            except Exception:
                pass
        await _settle_tasks(tasks, exclude=current)
        if should_invalidate:
            await self._on_session_disconnected(None)

    async def _detach_generation(self, generation: int) -> None:
        async with self._lifecycle_lock:
            if generation != self._generation:
                return
            tasks = (self._reader_task, self._stderr_task, self._wait_task)
            self._clear_generation()
        current = asyncio.current_task()
        for task in tasks:
            if task is not None and task is not current and not task.done():
                task.cancel()
        await _settle_tasks(tasks, exclude=current)

    def _clear_generation(self) -> None:
        self._process = None
        self._ready = None
        self._stopped = None
        self._exited = None
        self._active = None
        self._reader_task = None
        self._stderr_task = None
        self._wait_task = None
        self._shutdown_generation = None

    def _is_valid_shutdown_eof(self, generation: int) -> bool:
        return (
            self._shutdown_generation == generation
            and self._stopped is not None
            and self._stopped.done()
            and self._stopped.exception() is None
        )


def _parse_worker_event(line: bytes) -> dict[str, object]:
    if line.startswith(AUTH_EVENT_PREFIX):
        event = _parse_auth_event(line)
        event["protocol"] = "auth"
        return event
    if line.startswith(SEARCH_EVENT_PREFIX):
        event = _parse_search_event(line)
        event["protocol"] = "search"
        return event
    if line.startswith(ENRICHMENT_EVENT_PREFIX):
        event = _parse_enrichment_event(line)
        event["protocol"] = "enrichment"
        return event
    raise AuthWorkerError


def _parse_event(line: bytes) -> dict[str, object]:
    """Backward-compatible test seam for the strict worker event parser."""

    return _parse_worker_event(line)


def _parse_enrichment_event(line: bytes) -> dict[str, object]:
    if len(line) > MAX_ENRICHMENT_EVENT_BYTES or not line.endswith(b"\n"):
        raise AuthWorkerError
    try:
        raw = decode_json_object(line[len(ENRICHMENT_EVENT_PREFIX) :])
        base = {"version", "type", "event", "request_id", "platform", "content_id"}
        _require_exact_fields(
            raw,
            base
            if raw.get("event") == "accepted"
            else base | {"outcome", "content", "manifest"},
        )
        if (
            type(raw["version"]) is not int
            or raw["version"] != 1
            or raw["type"] != "event"
            or raw["event"] not in {"accepted", "result"}
            or type(raw["platform"]) is not str
            or raw["platform"] not in SEARCH_PLATFORMS
            or type(raw["content_id"]) is not str
            or not 1 <= len(raw["content_id"]) <= 128
        ):
            raise AuthWorkerError
        raw["request_id"] = _parse_canonical_uuid(raw["request_id"])
        if raw["event"] == "accepted":
            return raw
        if type(raw["outcome"]) is not str or raw["outcome"] not in get_args(
            EnrichmentOutcome
        ):
            raise AuthWorkerError
        if raw["outcome"] == "completed":
            if (raw["content"] is None) == (raw["manifest"] is None):
                raise AuthWorkerError
            if raw["content"] is not None and not isinstance(raw["content"], dict):
                raise AuthWorkerError
            if raw["manifest"] is not None:
                raw["manifest"] = ManifestDescriptor.model_validate(raw["manifest"])
        elif raw["content"] is not None or raw["manifest"] is not None:
            raise AuthWorkerError
        return raw
    except (EnrichmentValidationError, ValidationError, ValueError, TypeError):
        raise AuthWorkerError from None


def _parse_auth_event(line: bytes) -> dict[str, object]:
    if (
        len(line) > MAX_AUTH_FRAME_BYTES
        or not line.endswith(b"\n")
        or not line.startswith(AUTH_EVENT_PREFIX)
    ):
        raise AuthWorkerError
    payload = line[len(AUTH_EVENT_PREFIX) :]
    try:
        decoded = payload.decode("utf-8")
        raw = json.loads(
            decoded,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise AuthWorkerError from None
    if not isinstance(raw, dict):
        raise AuthWorkerError
    if type(raw.get("version")) is not int or raw.get("version") != 2:
        raise AuthWorkerError
    if type(raw.get("type")) is not str or raw.get("type") != "event":
        raise AuthWorkerError

    event = raw.get("event")
    if type(event) is not str:
        raise AuthWorkerError
    if event == "ready":
        _require_exact_fields(raw, {"version", "type", "event"})
    elif event == "progress":
        _require_exact_fields(
            raw,
            {"version", "type", "event", "request_id", "platform", "phase"},
        )
        raw["request_id"] = _parse_canonical_uuid(raw["request_id"])
        _require_platform(raw["platform"])
        if raw["phase"] not in {
            "waiting_for_browser",
            "waiting_for_approval",
            "checking",
            "waiting_for_login",
        }:
            raise AuthWorkerError
    elif event == "result":
        _require_exact_fields(
            raw,
            {
                "version",
                "type",
                "event",
                "request_id",
                "platform",
                "outcome",
                "reason",
            },
        )
        raw["request_id"] = _parse_canonical_uuid(raw["request_id"])
        _require_platform(raw["platform"])
        if (raw["outcome"], raw["reason"]) not in _RESULT_PAIRS:
            raise AuthWorkerError
    elif event == "session":
        _require_exact_fields(raw, {"version", "type", "event", "state", "reason"})
        if raw["state"] != "disconnected" or raw["reason"] != "browser_disconnected":
            raise AuthWorkerError
    elif event == "stopped":
        _require_exact_fields(raw, {"version", "type", "event"})
    else:
        raise AuthWorkerError
    return raw


def _parse_search_event(line: bytes) -> dict[str, object]:
    if (
        len(line) > MAX_SEARCH_EVENT_BYTES
        or not line.endswith(b"\n")
        or not line.startswith(SEARCH_EVENT_PREFIX)
    ):
        raise AuthWorkerError
    try:
        raw = json.loads(
            line[len(SEARCH_EVENT_PREFIX) :].decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise AuthWorkerError from None
    if not isinstance(raw, dict):
        raise AuthWorkerError
    if type(raw.get("version")) is not int or raw.get("version") != 2:
        raise AuthWorkerError
    if type(raw.get("type")) is not str or raw.get("type") != "event":
        raise AuthWorkerError
    if (
        type(raw.get("platform")) is not str
        or raw.get("platform") not in SEARCH_PLATFORMS
    ):
        raise AuthWorkerError
    platform = cast(SearchPlatform, raw["platform"])
    raw["request_id"] = _parse_canonical_uuid(raw.get("request_id"))

    event = raw.get("event")
    base = {"version", "type", "event", "request_id", "platform"}
    if event == "progress":
        _require_exact_fields(raw, base | {"phase", "term_position", "term_count"})
        if raw["phase"] != "term_started":
            raise AuthWorkerError
        position = raw["term_position"]
        count = raw["term_count"]
        if (
            type(position) is not int
            or type(count) is not int
            or not 0 <= position < count <= 20
        ):
            raise AuthWorkerError
    elif event == "item":
        _require_exact_fields(raw, base | {"term_position", "item"})
        position = raw["term_position"]
        if type(position) is not int or not 0 <= position < 20:
            raise AuthWorkerError
        raw["item"] = _parse_search_item(raw["item"], platform)
    elif event == "term_completed":
        _require_exact_fields(raw, base | {"term_position", "item_count"})
        if (
            type(raw["term_position"]) is not int
            or not 0 <= raw["term_position"] < 20
            or type(raw["item_count"]) is not int
            or not 0 <= raw["item_count"] <= 50
        ):
            raise AuthWorkerError
    elif event == "manual_page":
        _require_exact_fields(raw, base | {"action", "outcome"})
        if (
            type(raw["action"]) is not str
            or raw["action"] not in _MANUAL_OUTCOMES
            or type(raw["outcome"]) is not str
            or raw["outcome"] not in _MANUAL_OUTCOMES[raw["action"]]
        ):
            raise AuthWorkerError
    elif event == "result":
        _require_exact_fields(raw, base | {"outcome"})
        if raw["outcome"] not in {
            "completed_with_results",
            "completed_empty",
            "login_required",
            "manual_challenge_required",
            "platform_blocked_or_rate_limited",
            "structure_changed",
            "browser_unavailable",
            "browser_disconnected",
            "cancelled",
            "internal_error",
        }:
            raise AuthWorkerError
    elif event == "open_result":
        _require_exact_fields(raw, base | {"outcome"})
        if platform != "xhs" or raw["outcome"] not in {
            "opened",
            "content_not_found",
            "content_unavailable",
            "login_required",
            "manual_challenge_required",
            "platform_blocked_or_rate_limited",
            "structure_changed",
            "browser_unavailable",
            "internal_error",
        }:
            raise AuthWorkerError
    else:
        raise AuthWorkerError
    return raw


def _parse_search_item(value: object, platform: SearchPlatform) -> SearchWorkerItem:
    if not isinstance(value, dict):
        raise AuthWorkerError
    fields = {
        "content_id",
        "content_type",
        "title",
        "snippet",
        "creator_hash",
        "publisher_name",
        "published_at_text",
        "content_url",
        "discovered_at",
    }
    _require_exact_fields(value, fields)
    limits = {
        "content_id": 128,
        "content_type": 32,
        "title": 300,
        "snippet": 1000,
        "creator_hash": 64,
        "publisher_name": 100,
        "published_at_text": 100,
        "content_url": 2048,
    }
    for item_field, limit in limits.items():
        item_value = value[item_field]
        if type(item_value) is not str or len(item_value) > limit:
            raise AuthWorkerError
    if (
        not value["content_id"]
        or not value["content_type"]
        or not value["title"]
        or not value["content_url"]
    ):
        raise AuthWorkerError
    creator_hash = cast(str, value["creator_hash"])
    publisher_name = cast(str, value["publisher_name"])
    if (
        bool(creator_hash) != bool(publisher_name)
        or (creator_hash and _MASKED_CREATOR_HASH.fullmatch(creator_hash) is None)
        or not _is_masked_publisher_name(publisher_name)
    ):
        raise AuthWorkerError
    discovered_at = value["discovered_at"]
    if (
        type(discovered_at) is not int
        or not 1_000_000_000_000 <= discovered_at <= 9_999_999_999_999
    ):
        raise AuthWorkerError
    if not is_valid_search_content_url(
        platform,
        cast(str, value["content_id"]),
        cast(str, value["content_url"]),
    ):
        raise AuthWorkerError
    return SearchWorkerItem(**cast(dict[str, object], value))


def _is_masked_publisher_name(value: str) -> bool:
    return (
        not value
        or value == "*"
        or (len(value) == 2 and value.endswith("*"))
        or (len(value) == 5 and value[1:4] == "***")
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_nonstandard_constant(_value: str) -> None:
    raise ValueError


def _require_exact_fields(raw: dict[str, object], fields: set[str]) -> None:
    if set(raw) != fields:
        raise AuthWorkerError


def _parse_canonical_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise AuthWorkerError
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise AuthWorkerError from None
    if str(parsed) != value or parsed.version != 4:
        raise AuthWorkerError
    return parsed


def _require_platform(value: object) -> None:
    if value not in {"wb", "dy", "ks", "xhs", "toutiao"}:
        raise AuthWorkerError


def _validate_progress_transition(
    previous: AuthProgressPhase | None, current: AuthProgressPhase
) -> None:
    allowed: dict[AuthProgressPhase | None, set[AuthProgressPhase]] = {
        None: {"waiting_for_browser", "waiting_for_approval", "checking"},
        "waiting_for_browser": {"waiting_for_approval"},
        "waiting_for_approval": {"checking"},
        "checking": {"waiting_for_login"},
        "waiting_for_login": {"checking"},
    }
    if current not in allowed[previous]:
        raise AuthWorkerError


async def _drain(reader: _AsyncByteReader) -> None:
    while await reader.read(8192):
        pass


async def _settle_tasks(
    tasks: tuple[
        asyncio.Task[None] | None,
        asyncio.Task[None] | None,
        asyncio.Task[None] | None,
    ],
    *,
    exclude: asyncio.Task[object] | None,
) -> None:
    pending = [task for task in tasks if task is not None and task is not exclude]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def launch_process(
    command: tuple[str, ...], cwd: Path, *, media_spool_root: Path | None = None
) -> ManagedProcess:
    """Launch the fixed worker command without a shell."""
    options = {}
    if media_spool_root is not None:
        options["env"] = {**os.environ, MEDIA_ROOT_ENV: str(media_spool_root)}
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_CHILD_OUTPUT_LINE_BYTES,
        start_new_session=os.name == "posix",
        **options,
    )
    return cast(ManagedProcess, process)


async def terminate_owned_process_group(
    process: ManagedProcess, grace_seconds: float
) -> None:
    """Terminate only the worker process group, with a bounded kill fallback."""
    if process.returncode is not None:
        return

    _send_process_group_signal(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass

    _send_process_group_signal(process, signal.SIGKILL)
    try:
        await asyncio.wait_for(process.wait(), timeout=max(grace_seconds, 0.1))
    except (ProcessLookupError, TimeoutError):
        pass


def _send_process_group_signal(process: ManagedProcess, sig: signal.Signals) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        try:
            if sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            pass
