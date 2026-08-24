"""Coordinate bounded, authentication-only MediaCrawler subprocesses."""

import asyncio
import json
import os
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from longtian_api.schemas.platform_connections import (
    PlatformConnection,
    PlatformConnectionAttemptResponse,
    PlatformConnectionErrorCode,
    PlatformConnectionGuidance,
    PlatformConnectionListResponse,
    PlatformId,
)

AUTH_EVENT_PREFIX = b"__MEDIACRAWLER_AUTH_EVENT__"
MAX_AUTH_EVENT_LINE_BYTES = 1024
MAX_CHILD_OUTPUT_LINE_BYTES = 64 * 1024

CONNECTED_EXIT_CODE = 0
AUTH_DISCONNECTED_EXIT_CODE = 20
BROWSER_UNAVAILABLE_EXIT_CODE = 21

_AUTH_COMMAND_SUFFIX = (
    "--type",
    "auth",
    "--lt",
    "qrcode",
    "--headless",
    "no",
    "--get_comment",
    "no",
    "--get_sub_comment",
    "no",
    "--save_data_option",
    "jsonl",
)

AuthPlatformId = Literal["wb", "ks"]
_AUTH_PLATFORM_BY_ID: dict[PlatformId, AuthPlatformId] = {
    "wb": "wb",
    "ks": "ks",
}

AuthPhase = Literal[
    "waiting_for_browser",
    "waiting_for_approval",
    "checking",
    "waiting_for_login",
    "connected",
    "disconnected",
]


class _AuthEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    platform: AuthPlatformId
    phase: AuthPhase


class _AsyncLineReader(Protocol):
    async def readline(self) -> bytes: ...


class ManagedProcess(Protocol):
    """The asyncio subprocess surface required by this service."""

    pid: int
    returncode: int | None
    stdout: _AsyncLineReader | None
    stderr: _AsyncLineReader | None

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessLauncher = Callable[[tuple[str, ...], Path], Awaitable[ManagedProcess]]
ProcessGroupTerminator = Callable[[ManagedProcess, float], Awaitable[None]]
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


class _ProtocolError(Exception):
    """A deliberately detail-free child protocol failure."""


class PlatformConnectionService:
    """Own in-memory status and one authentication subprocess at a time."""

    def __init__(
        self,
        *,
        media_crawler_dir: Path | None = None,
        process_launcher: ProcessLauncher | None = None,
        process_group_terminator: ProcessGroupTerminator | None = None,
        attempt_timeout_seconds: float = 300.0,
        termination_grace_seconds: float = 3.0,
        clock: Clock | None = None,
    ) -> None:
        self._media_crawler_dir = media_crawler_dir or _default_media_crawler_dir()
        self._process_launcher = process_launcher or _launch_process
        self._process_group_terminator = (
            process_group_terminator or _terminate_owned_process_group
        )
        self._attempt_timeout_seconds = attempt_timeout_seconds
        self._termination_grace_seconds = termination_grace_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[None] | None = None
        self._current_process: ManagedProcess | None = None
        self._connections = _initial_catalog()

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
            if self._current_task is not None and not self._current_task.done():
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
        """Cancel the owned task and stop only its owned process group."""
        async with self._lock:
            task = self._current_task

        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
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
            self._current_process = None

    async def _run_attempt(self, platform: AuthPlatformId, attempt_id: UUID) -> None:
        terminal_status: Literal["connected", "disconnected", "failed"] = "failed"
        terminal_guidance: PlatformConnectionGuidance = "retry"
        was_cancelled = False
        try:
            async with asyncio.timeout(self._attempt_timeout_seconds):
                terminal_status, terminal_guidance = await self._execute_worker(
                    platform, attempt_id
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
        except Exception:
            # Child output and exception details are never logged or exposed.
            terminal_status = "failed"
            terminal_guidance = "retry"
        finally:
            process = await self._get_current_process()
            if process is not None and process.returncode is None:
                try:
                    await self._process_group_terminator(
                        process, self._termination_grace_seconds
                    )
                except Exception:
                    terminal_status = "failed"
                    terminal_guidance = "retry"

        await self._finish_attempt(
            platform, attempt_id, terminal_status, terminal_guidance
        )
        if was_cancelled:
            raise asyncio.CancelledError

    async def _execute_worker(
        self, platform: AuthPlatformId, attempt_id: UUID
    ) -> tuple[
        Literal["connected", "disconnected", "failed"],
        PlatformConnectionGuidance,
    ]:
        command = self._worker_command(platform)
        process = await self._process_launcher(command, self._media_crawler_dir)
        async with self._lock:
            self._current_process = process

        if process.stdout is None or process.stderr is None:
            raise _ProtocolError

        stderr_task = asyncio.create_task(_drain(process.stderr))
        final_phase: AuthPhase | None = None
        previous_phase: AuthPhase | None = None
        try:
            while line := await process.stdout.readline():
                event = _parse_auth_event(line, expected_platform=platform)
                if event is None:
                    continue
                _validate_transition(previous_phase, event.phase)
                previous_phase = event.phase
                if event.phase in {"connected", "disconnected"}:
                    final_phase = event.phase
                else:
                    await self._set_progress(platform, attempt_id, event.phase)

            return_code = await process.wait()
            await stderr_task
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

        if return_code == CONNECTED_EXIT_CODE and final_phase == "connected":
            return "connected", "none"
        if return_code == AUTH_DISCONNECTED_EXIT_CODE and final_phase == "disconnected":
            return "disconnected", "retry"
        if return_code == BROWSER_UNAVAILABLE_EXIT_CODE and final_phase != "connected":
            return "failed", "enable_remote_debugging"
        return "failed", "retry"

    async def _set_progress(
        self, platform: PlatformId, attempt_id: UUID, phase: AuthPhase
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

    async def _finish_attempt(
        self,
        platform: PlatformId,
        attempt_id: UUID,
        status: Literal["connected", "disconnected", "failed"],
        guidance: PlatformConnectionGuidance,
    ) -> None:
        async with self._lock:
            connection = self._connections[platform]
            if connection.active_attempt_id != attempt_id:
                return
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
                self._current_process = None

    async def _get_connection(self, platform: PlatformId) -> PlatformConnection:
        async with self._lock:
            return self._connections[platform].model_copy()

    async def _get_current_process(self) -> ManagedProcess | None:
        async with self._lock:
            return self._current_process

    def _worker_command(self, platform: AuthPlatformId) -> tuple[str, ...]:
        return (
            "uv",
            "run",
            "--frozen",
            "--project",
            str(self._media_crawler_dir),
            "python",
            "main.py",
            "--platform",
            platform,
            *_AUTH_COMMAND_SUFFIX,
        )


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
            availability="coming_soon",
            status="coming_soon",
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
            availability="coming_soon",
            status="coming_soon",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
        "toutiao": PlatformConnection(
            platform="toutiao",
            display_name="今日头条",
            availability="coming_soon",
            status="coming_soon",
            guidance="none",
            last_checked_at=None,
            active_attempt_id=None,
        ),
    }


def _parse_auth_event(
    line: bytes, *, expected_platform: AuthPlatformId
) -> _AuthEvent | None:
    if not line.startswith(AUTH_EVENT_PREFIX):
        return None
    if len(line) > MAX_AUTH_EVENT_LINE_BYTES:
        raise _ProtocolError

    payload = line[len(AUTH_EVENT_PREFIX) :].strip()
    try:
        raw_event = json.loads(payload)
        event = _AuthEvent.model_validate(raw_event)
        if event.platform != expected_platform:
            raise _ProtocolError
        return event
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
        ValueError,
    ):
        raise _ProtocolError from None


def _validate_transition(previous: AuthPhase | None, current: AuthPhase) -> None:
    allowed: dict[AuthPhase | None, set[AuthPhase]] = {
        None: {"waiting_for_browser", "waiting_for_approval", "checking"},
        "waiting_for_browser": {"waiting_for_approval"},
        "waiting_for_approval": {"checking"},
        "checking": {"waiting_for_login", "connected", "disconnected"},
        "waiting_for_login": {"checking"},
        "connected": set(),
        "disconnected": set(),
    }
    if current not in allowed[previous]:
        raise _ProtocolError


async def _drain(reader: _AsyncLineReader) -> None:
    while await reader.readline():
        pass


async def _launch_process(command: tuple[str, ...], cwd: Path) -> ManagedProcess:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_CHILD_OUTPUT_LINE_BYTES,
        start_new_session=os.name == "posix",
    )
    return cast(ManagedProcess, process)


async def _terminate_owned_process_group(
    process: ManagedProcess, grace_seconds: float
) -> None:
    if process.returncode is not None:
        return

    _send_process_group_signal(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=grace_seconds,
        )
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


def _default_media_crawler_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "third_party" / "MediaCrawler"
