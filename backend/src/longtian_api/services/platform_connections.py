"""Coordinate platform authentication through one persistent MediaCrawler worker."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from longtian_api.schemas.platform_connections import (
    PlatformConnection,
    PlatformConnectionAttemptResponse,
    PlatformConnectionErrorCode,
    PlatformConnectionGuidance,
    PlatformConnectionListResponse,
    PlatformId,
)
from longtian_api.services.media_crawler_auth_worker import (
    AuthPlatformId,
    AuthProgressPhase,
    AuthWorkerError,
    AuthWorkerResult,
    PersistentAuthWorkerClient,
    ProcessGroupTerminator,
    ProcessLauncher,
)

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
        media_crawler_dir: Path | None = None,
        process_launcher: ProcessLauncher | None = None,
        process_group_terminator: ProcessGroupTerminator | None = None,
        attempt_timeout_seconds: float = 300.0,
        worker_ready_timeout_seconds: float = 30.0,
        cancel_timeout_seconds: float = 3.0,
        worker_shutdown_timeout_seconds: float = 5.0,
        termination_grace_seconds: float = 3.0,
        clock: Clock | None = None,
    ) -> None:
        self._media_crawler_dir = media_crawler_dir or _default_media_crawler_dir()
        self._attempt_timeout_seconds = attempt_timeout_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._connections = _initial_catalog()
        self._shutdown_started = False
        self._worker = PersistentAuthWorkerClient(
            media_crawler_dir=self._media_crawler_dir,
            on_progress=self._set_progress,
            on_session_disconnected=self._invalidate_connected,
            process_launcher=process_launcher,
            process_group_terminator=process_group_terminator,
            ready_timeout_seconds=worker_ready_timeout_seconds,
            cancel_timeout_seconds=cancel_timeout_seconds,
            shutdown_timeout_seconds=worker_shutdown_timeout_seconds,
            termination_grace_seconds=termination_grace_seconds,
        )

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
                    message="已有平台连接任务正在进行，请稍后重试。",
                )
            auth_platform = _AUTH_PLATFORM_BY_ID.get(connection.platform)
            if connection.availability == "coming_soon" or auth_platform is None:
                raise PlatformConnectionError(
                    status_code=409,
                    code="platform_not_available",
                    message="该平台暂未接入。",
                )

            attempt_id = uuid4()
            accepted = connection.model_copy(
                update={
                    "status": "checking",
                    "guidance": "none",
                    "active_attempt_id": attempt_id,
                }
            )
            self._connections[connection.platform] = accepted
            self._current_task = asyncio.create_task(
                self._run_attempt(auth_platform, attempt_id),
                name=f"platform-connection-{connection.platform}-{attempt_id}",
            )
            return PlatformConnectionAttemptResponse(
                attempt_id=attempt_id,
                platform=accepted.model_copy(),
            )

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

    async def _run_attempt(self, platform: AuthPlatformId, attempt_id: UUID) -> None:
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
            current = await self._get_connection(platform)
            if current.guidance == "complete_login":
                terminal_status = "disconnected"
            elif current.guidance in {
                "enable_remote_debugging",
                "approve_connection",
            }:
                terminal_guidance = "enable_remote_debugging"
        except asyncio.CancelledError:
            was_cancelled = True
        except AuthWorkerError:
            terminal_status = "failed"
            terminal_guidance = "retry"
        except Exception:
            # Worker output and exception details are never logged or exposed.
            terminal_status = "failed"
            terminal_guidance = "retry"

        await self._finish_attempt(
            platform, attempt_id, terminal_status, terminal_guidance
        )
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
            current = await self._get_connection(platform)
            if current.guidance in {
                "enable_remote_debugging",
                "approve_connection",
            }:
                return "failed", current.guidance
            return "failed", "enable_remote_debugging"
        return "failed", "retry"

    async def _set_progress(
        self,
        attempt_id: UUID,
        platform: AuthPlatformId,
        phase: AuthProgressPhase,
    ) -> None:
        status: Literal["checking", "action_required"]
        guidance: PlatformConnectionGuidance
        if phase == "waiting_for_browser":
            status, guidance = "action_required", "enable_remote_debugging"
        elif phase == "waiting_for_approval":
            status, guidance = "action_required", "approve_connection"
        elif phase == "waiting_for_login":
            status, guidance = "action_required", "complete_login"
        else:
            status, guidance = "checking", "none"

        async with self._lock:
            connection = self._connections[platform]
            if connection.active_attempt_id != attempt_id:
                return
            self._connections[platform] = connection.model_copy(
                update={"status": status, "guidance": guidance}
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
                        "guidance": "retry",
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

    async def _get_connection(self, platform: PlatformId) -> PlatformConnection:
        async with self._lock:
            return self._connections[platform].model_copy()


def _initial_catalog() -> dict[PlatformId, PlatformConnection]:
    return {
        "wb": PlatformConnection(
            platform="wb",
            display_name="微博",
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
        "dy": PlatformConnection(
            platform="dy",
            display_name="抖音",
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
        "ks": PlatformConnection(
            platform="ks",
            display_name="快手",
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
        "xhs": PlatformConnection(
            platform="xhs",
            display_name="小红书",
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
        "toutiao": PlatformConnection(
            platform="toutiao",
            display_name="今日头条",
            availability="enabled",
            status="not_checked",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
    }


def _default_media_crawler_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "third_party" / "MediaCrawler"
