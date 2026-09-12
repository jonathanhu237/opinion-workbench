"""Coordinate native browser connections for the platform catalog."""

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from opinion_workbench_api.application_paths import application_paths
from opinion_workbench_api.schemas.platform_connections import (
    PlatformBrowserResponse,
    PlatformConnection,
    PlatformConnectionAttemptResponse,
    PlatformConnectionErrorCode,
    PlatformConnectionGuidance,
    PlatformConnectionListResponse,
    PlatformId,
)
from opinion_workbench_api.search_platforms import SEARCH_PLATFORMS
from opinion_workbench_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from opinion_workbench_api.services.collector_contracts import (
    AuthPlatformId,
    AuthProgressPhase,
    AuthWorkerError,
    AuthWorkerResult,
    CollectorFactory,
    CollectorRuntime,
    supports_platform,
)
from opinion_workbench_api.services.native_chrome import native_collector_factory

_AUTH_PLATFORM_BY_ID: dict[PlatformId, AuthPlatformId] = {
    "wb": "wb",
    "dy": "dy",
    "ks": "ks",
    "xhs": "xhs",
    "toutiao": "toutiao",
}

Clock = Callable[[], datetime]


class PlatformConnectionError(Exception):
    """Expected product error translated by the HTTP route."""

    def __init__(
        self, *, status_code: int, code: PlatformConnectionErrorCode, message: str
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


class PlatformConnectionService:
    """Own public connection state and one bounded attempt at a time."""

    def __init__(
        self,
        *,
        browser_profile_dir: Path | None = None,
        attempt_timeout_seconds: float = 20.0,
        clock: Clock | None = None,
        browser_operation_coordinator: BrowserOperationCoordinator | None = None,
        collector_factory: CollectorFactory | None = None,
    ) -> None:
        if collector_factory is None:
            backend = os.environ.get(
                "OPINION_WORKBENCH_COLLECTOR_BACKEND", "native-weibo"
            )
            if backend != "native-weibo":
                raise ValueError(
                    "Unsupported collector backend; no fallback was started."
                )
            collector_factory = native_collector_factory
        self._browser_profile_dir = (
            browser_profile_dir or _default_browser_profile_dir()
        )
        self._attempt_timeout_seconds = attempt_timeout_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._browser_operations = (
            browser_operation_coordinator or BrowserOperationCoordinator()
        )

        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._connections = _initial_catalog()
        self._shutdown_started = False
        self._browser_was_opened = False
        self._worker: CollectorRuntime = collector_factory(
            browser_profile_dir=self._browser_profile_dir,
            on_progress=self._set_progress,
            on_session_disconnected=self._invalidate_connected,
        )
        self._connections = {
            platform: connection
            if supports_platform(self._worker, platform)
            else connection.model_copy(
                update={"availability": "coming_soon", "status": "coming_soon"}
            )
            for platform, connection in self._connections.items()
        }

    @property
    def worker(self) -> CollectorRuntime:
        """Expose the one process boundary shared with product search."""

        return self._worker

    @property
    def browser_operations(self) -> BrowserOperationCoordinator:
        """Return the coordinator shared with search-run admission."""

        return self._browser_operations

    def configure_platform_access(self, coordinator) -> None:
        """Inject the shared pacing state after the database service is built."""
        configure = getattr(self._worker, "configure_platform_access", None)
        if callable(configure):
            configure(coordinator)

    async def list_connections(self) -> PlatformConnectionListResponse:
        """Return isolated snapshots in stable catalog order."""
        async with self._lock:
            return PlatformConnectionListResponse(
                platforms=[
                    connection.model_copy() for connection in self._connections.values()
                ]
            )

    async def start_attempt(self, platform: str) -> PlatformConnectionAttemptResponse:
        """Accept one non-blocking authentication attempt."""
        async with self._lock:
            connection = self._connections.get(cast(PlatformId, platform))
            if connection is None:
                raise PlatformConnectionError(
                    status_code=404,
                    code="platform_not_found",
                    message="未找到该平台。",
                )
            if self._shutdown_started or (
                self._current_task is not None and not self._current_task.done()
            ):
                raise PlatformConnectionError(
                    status_code=409,
                    code="connection_attempt_active",
                    message="专用浏览器正在执行任务，请稍后检查。",
                )
            auth_platform = _AUTH_PLATFORM_BY_ID.get(connection.platform)
            if connection.availability == "coming_soon" or auth_platform is None:
                raise PlatformConnectionError(
                    status_code=409,
                    code="platform_not_available",
                    message="该平台暂未接入。",
                )
            attempt_id = uuid4()
            owner = BrowserOperationOwner("platform_connection", attempt_id)
            if not await self._browser_operations.try_claim(owner):
                raise PlatformConnectionError(
                    status_code=409,
                    code="connection_attempt_active",
                    message="专用浏览器正在执行任务，请稍后检查。",
                )
            if not getattr(self._worker, "browser_session_available", False):
                await self._browser_operations.release(owner)
                message = (
                    "专用浏览器已关闭，请打开后重新检查。"
                    if self._browser_was_opened
                    else "请先打开专用浏览器，再检查登录状态。"
                )
                raise PlatformConnectionError(
                    status_code=409,
                    code="browser_not_open",
                    message=message,
                )
            accepted = connection.model_copy(
                update={
                    "status": "checking",
                    "guidance": "none",
                    "active_attempt_id": attempt_id,
                }
            )
            self._connections[connection.platform] = accepted
            self._current_task = asyncio.create_task(
                self._run_attempt(auth_platform, attempt_id, owner),
                name=f"platform-connection-{connection.platform}-{attempt_id}",
            )
            return PlatformConnectionAttemptResponse(
                attempt_id=attempt_id,
                platform=accepted.model_copy(),
            )

    async def open_browser(
        self, platform: str | None = None
    ) -> PlatformBrowserResponse:
        """Open or foreground the project-owned browser without checking login."""
        async with self._lock:
            selected_platform: AuthPlatformId | None = None
            if platform is not None:
                connection = self._connections.get(cast(PlatformId, platform))
                if connection is None:
                    raise PlatformConnectionError(
                        status_code=404,
                        code="platform_not_found",
                        message="未找到该平台。",
                    )
                if connection.availability != "enabled":
                    raise PlatformConnectionError(
                        status_code=409,
                        code="platform_not_available",
                        message="该平台暂未接入。",
                    )
                selected_platform = cast(AuthPlatformId, connection.platform)
            if self._shutdown_started:
                raise PlatformConnectionError(
                    status_code=503,
                    code="browser_open_failed",
                    message="专用浏览器打开失败，请重试。",
                )
        request_id = uuid4()
        owner = BrowserOperationOwner("platform_connection", request_id)
        if not await self._browser_operations.try_claim(owner):
            raise PlatformConnectionError(
                status_code=409,
                code="connection_attempt_active",
                message="专用浏览器正在执行任务，请稍后检查。",
            )
        try:
            try:
                async with asyncio.timeout(25.0):
                    opener = getattr(self._worker, "open_browser", None)
                    if opener is None:
                        result = await self._worker.manual_page(
                            request_id=request_id,
                            platform=selected_platform or "wb",
                            action="show",
                        )
                    elif selected_platform is None:
                        # Keep injected runtimes that implement the original
                        # browser-open contract source-compatible.
                        result = await opener(request_id=request_id)
                    else:
                        result = await opener(
                            request_id=request_id, platform=selected_platform
                        )
            except (AuthWorkerError, TimeoutError):
                raise PlatformConnectionError(
                    status_code=503,
                    code="browser_open_failed",
                    message="专用浏览器打开失败，请重试。",
                ) from None
            except Exception:
                raise PlatformConnectionError(
                    status_code=503,
                    code="browser_open_failed",
                    message="专用浏览器打开失败，请重试。",
                ) from None
            if getattr(result, "outcome", None) not in {
                "opened_existing",
                "opened_homepage",
            }:
                raise PlatformConnectionError(
                    status_code=503,
                    code="browser_open_failed",
                    message="专用浏览器打开失败，请重试。",
                )
            self._browser_was_opened = True
            return PlatformBrowserResponse(outcome=result.outcome)
        finally:
            await self._browser_operations.release(owner)

    async def shutdown(self) -> None:
        """Cancel the active request and stop the lifespan-owned worker."""
        async with self._lock:
            self._shutdown_started = True
            task = self._current_task

        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._worker.shutdown()
        async with self._lock:
            for platform, connection in self._connections.items():
                if connection.active_attempt_id is None:
                    continue
                self._connections[platform] = connection.model_copy(
                    update={
                        "status": "failed",
                        "guidance": "retry",
                        "last_checked_at": self._clock(),
                        "active_attempt_id": None,
                    }
                )
            self._current_task = None

    async def _run_attempt(
        self,
        platform: AuthPlatformId,
        attempt_id: UUID,
        owner: BrowserOperationOwner,
    ) -> None:
        terminal_status: Literal["connected", "disconnected", "failed"] = "failed"
        terminal_guidance: PlatformConnectionGuidance = "retry"
        was_cancelled = False
        try:
            async with asyncio.timeout(self._attempt_timeout_seconds):
                result = await self._worker.check(
                    request_id=attempt_id, platform=platform
                )
                terminal_status, terminal_guidance = await self._project_result(
                    platform, result
                )
        except TimeoutError:
            terminal_status = "failed"
            terminal_guidance = "retry"
        except asyncio.CancelledError:
            was_cancelled = True
        except AuthWorkerError:
            terminal_status = "failed"
            terminal_guidance = "retry"
        except Exception:
            # Worker output and exception details are never logged or exposed.
            terminal_status = "failed"
            terminal_guidance = "retry"

        try:
            await self._finish_attempt(
                platform, attempt_id, terminal_status, terminal_guidance
            )
        finally:
            await self._browser_operations.release(owner)
        if was_cancelled:
            raise asyncio.CancelledError

    async def _project_result(
        self, platform: PlatformId, result: AuthWorkerResult
    ) -> tuple[
        Literal["connected", "disconnected", "failed"],
        PlatformConnectionGuidance,
    ]:
        if result == AuthWorkerResult("connected", "none"):
            return "connected", "none"
        if result == AuthWorkerResult("disconnected", "login_required"):
            return "disconnected", "retry"
        if result == AuthWorkerResult("failed", "browser_unavailable"):
            return "failed", "retry_browser"
        if result == AuthWorkerResult("failed", "browser_disconnected"):
            return "failed", "retry_browser"
        if result == AuthWorkerResult("failed", "manual_challenge"):
            return "failed", "complete_verification"
        if result == AuthWorkerResult("failed", "check_failed"):
            return "failed", "retry"
        return "failed", "retry"

    async def _set_progress(
        self,
        attempt_id: UUID,
        platform: AuthPlatformId,
        phase: AuthProgressPhase,
    ) -> None:
        # Account checks are a short read of an already-open browser.  Keep
        # legacy progress callbacks from reintroducing a waiting/manual state.
        async with self._lock:
            connection = self._connections[platform]
            if connection.active_attempt_id != attempt_id:
                return
            self._connections[platform] = connection.model_copy(
                update={"status": "checking", "guidance": "none"}
            )

    async def _invalidate_connected(self, affected_request_id: UUID | None) -> None:
        async with self._lock:
            for platform, connection in self._connections.items():
                affected_active = connection.active_attempt_id == affected_request_id
                if affected_request_id is None:
                    affected_active = False
                if connection.status != "connected" and not affected_active:
                    continue
                self._connections[platform] = connection.model_copy(
                    update={
                        "status": "failed",
                        "guidance": (
                            "retry_browser" if affected_request_id is None else "retry"
                        ),
                        "last_checked_at": (
                            self._clock()
                            if affected_active
                            else connection.last_checked_at
                        ),
                        "active_attempt_id": (
                            None if affected_active else connection.active_attempt_id
                        ),
                    }
                )

    async def _finish_attempt(
        self,
        platform: PlatformId,
        attempt_id: UUID,
        status: Literal["connected", "disconnected", "failed"],
        guidance: PlatformConnectionGuidance,
    ) -> None:
        async with self._lock:
            connection = self._connections[platform]
            if connection.active_attempt_id == attempt_id:
                self._connections[platform] = connection.model_copy(
                    update={
                        "status": status,
                        "guidance": guidance,
                        "last_checked_at": self._clock(),
                        "active_attempt_id": None,
                    }
                )
            if self._current_task is asyncio.current_task():
                self._current_task = None


def _initial_catalog() -> dict[PlatformId, PlatformConnection]:
    labels = {
        "wb": "微博",
        "dy": "抖音",
        "ks": "快手",
        "xhs": "小红书",
        "toutiao": "今日头条",
    }
    return {
        platform: PlatformConnection(
            platform=platform,
            display_name=labels[platform],
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        )
        for platform in SEARCH_PLATFORMS
    }


def _default_browser_profile_dir() -> Path:
    """Return the application-owned profile, outside an install directory."""
    return application_paths().browser_profile_dir
