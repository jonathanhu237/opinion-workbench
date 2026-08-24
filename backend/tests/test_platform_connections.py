import asyncio
import os
import signal
import threading
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from longtian_api.main import create_app
from longtian_api.services import platform_connections as service_module
from longtian_api.services.platform_connections import PlatformConnectionService

PREFIX = b"__MEDIACRAWLER_AUTH_EVENT__"
FIXED_NOW = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)
AUTH_PLATFORMS = ("wb", "dy", "ks", "toutiao")
CROSS_AUTH_PLATFORM_PAIRS = tuple(
    (expected, received)
    for expected in AUTH_PLATFORMS
    for received in AUTH_PLATFORMS
    if expected != received
)


def auth_event(phase: str, *, platform: str = "wb", **extra: object) -> bytes:
    fields = {"version": 1, "platform": platform, "phase": phase, **extra}
    import json

    return PREFIX + json.dumps(fields).encode() + b"\n"


def expected_auth_command(platform: str) -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--frozen",
        "--project",
        "/repo/third_party/MediaCrawler",
        "python",
        "main.py",
        "--platform",
        platform,
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


class FakeLineReader:
    def __init__(self, lines: Iterable[bytes] = (), *, block_at_end: bool = False):
        self._lines = deque(lines)
        self._block_at_end = block_at_end
        self._released = asyncio.Event()

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.popleft()
        if self._block_at_end:
            await self._released.wait()
        return b""

    def release(self) -> None:
        self._released.set()


class FakeProcess:
    _next_pid = 91000

    def __init__(
        self,
        *,
        stdout: Iterable[bytes] = (),
        stderr: Iterable[bytes] = (),
        exit_code: int = 0,
        hang: bool = False,
    ) -> None:
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self.returncode: int | None = None
        self.stdout = FakeLineReader(stdout, block_at_end=hang)
        self.stderr = FakeLineReader(stderr, block_at_end=hang)
        self._exit_code = exit_code
        self._hang = hang
        self._finished = asyncio.Event()

    async def wait(self) -> int:
        if self._hang:
            await self._finished.wait()
        if self.returncode is None:
            self.returncode = self._exit_code
        return self.returncode

    def finish(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout.release()
        self.stderr.release()
        self._finished.set()

    def terminate(self) -> None:
        self.finish(-15)

    def kill(self) -> None:
        self.finish(-9)


class FakeLauncher:
    def __init__(self, *processes: FakeProcess) -> None:
        self._processes = deque(processes)
        self.calls: list[tuple[tuple[str, ...], Path]] = []
        self.started = threading.Event()

    async def __call__(self, command: tuple[str, ...], cwd: Path) -> FakeProcess:
        self.calls.append((command, cwd))
        self.started.set()
        return self._processes.popleft()


class FakeTerminator:
    def __init__(self) -> None:
        self.calls: list[tuple[FakeProcess, float]] = []

    async def __call__(self, process: FakeProcess, grace: float) -> None:
        self.calls.append((process, grace))
        process.finish(-15)


async def wait_for_terminal(
    service: PlatformConnectionService, platform: str = "wb"
) -> dict[str, object]:
    for _ in range(200):
        connections = (await service.list_connections()).platforms
        connection = next(item for item in connections if item.platform == platform)
        if connection.status in {"connected", "disconnected", "failed"}:
            return connection.model_dump(mode="json")
        await asyncio.sleep(0.001)
    raise AssertionError("connection attempt did not reach a terminal state")


def build_service(
    process: FakeProcess,
    *,
    timeout: float = 1.0,
) -> tuple[PlatformConnectionService, FakeLauncher, FakeTerminator]:
    launcher = FakeLauncher(process)
    terminator = FakeTerminator()
    service = PlatformConnectionService(
        media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
        process_launcher=launcher,
        process_group_terminator=terminator,
        attempt_timeout_seconds=timeout,
        termination_grace_seconds=0.01,
        clock=lambda: FIXED_NOW,
    )
    return service, launcher, terminator


def test_list_returns_exact_ordered_catalog() -> None:
    process = FakeProcess()
    service, _, _ = build_service(process)

    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        response = client.get("/api/v1/platform-connections")

    assert response.status_code == 200
    assert response.json() == {
        "platforms": [
            {
                "platform": "wb",
                "display_name": "微博",
                "availability": "enabled",
                "status": "not_checked",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            },
            {
                "platform": "dy",
                "display_name": "抖音",
                "availability": "enabled",
                "status": "not_checked",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            },
            {
                "platform": "ks",
                "display_name": "快手",
                "availability": "enabled",
                "status": "not_checked",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            },
            {
                "platform": "xhs",
                "display_name": "小红书",
                "availability": "coming_soon",
                "status": "coming_soon",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            },
            {
                "platform": "toutiao",
                "display_name": "今日头条",
                "availability": "enabled",
                "status": "not_checked",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            },
        ]
    }


@pytest.mark.parametrize(
    ("platform", "status_code", "code", "message"),
    [
        ("unknown", 404, "platform_not_found", "未找到该平台。"),
        (
            "unknown-platform-identifier-that-is-not-in-the-catalog",
            404,
            "platform_not_found",
            "未找到该平台。",
        ),
        ("ks --type search", 404, "platform_not_found", "未找到该平台。"),
        ("xhs", 409, "platform_not_available", "该平台暂未接入。"),
    ],
)
def test_start_rejects_unknown_and_unavailable_platforms(
    platform: str, status_code: int, code: str, message: str
) -> None:
    service, launcher, _ = build_service(FakeProcess())

    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        response = client.post(f"/api/v1/platform-connections/{platform}/attempts")

    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert launcher.calls == []


def test_start_returns_202_and_rejects_concurrent_attempt() -> None:
    process = FakeProcess(hang=True)
    service, launcher, terminator = build_service(process)

    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        accepted = client.post("/api/v1/platform-connections/wb/attempts")
        assert launcher.started.wait(timeout=1)
        conflict = client.post("/api/v1/platform-connections/ks/attempts")
        unavailable_during_attempt = client.post(
            "/api/v1/platform-connections/dy/attempts"
        )
        current_catalog = client.get("/api/v1/platform-connections").json()

    body = accepted.json()
    assert accepted.status_code == 202
    assert body["attempt_id"] == body["platform"]["active_attempt_id"]
    assert body["platform"]["status"] == "checking"
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": {
            "code": "connection_attempt_active",
            "message": "已有平台连接任务正在进行，请稍后重试。",
        }
    }
    assert unavailable_during_attempt.status_code == 409
    assert unavailable_during_attempt.json()["detail"]["code"] == (
        "connection_attempt_active"
    )
    assert current_catalog["platforms"][0]["status"] == "checking"
    assert current_catalog["platforms"][2]["status"] == "not_checked"
    assert len(launcher.calls) == 1
    assert terminator.calls == [(process, 0.01)]


def test_kuaishou_start_returns_exact_202_projection() -> None:
    process = FakeProcess(hang=True)
    service, launcher, terminator = build_service(process)

    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        response = client.post("/api/v1/platform-connections/ks/attempts")
        assert launcher.started.wait(timeout=1)

    body = response.json()
    assert response.status_code == 202
    assert str(UUID(body["attempt_id"])) == body["attempt_id"]
    assert body == {
        "attempt_id": body["attempt_id"],
        "platform": {
            "platform": "ks",
            "display_name": "快手",
            "availability": "enabled",
            "status": "checking",
            "guidance": "none",
            "last_checked_at": None,
            "active_attempt_id": body["attempt_id"],
        },
    }
    assert launcher.calls[0][0] == expected_auth_command("ks")
    assert terminator.calls == [(process, 0.01)]


def test_douyin_start_returns_exact_202_projection() -> None:
    process = FakeProcess(hang=True)
    service, launcher, terminator = build_service(process)

    assert service._worker_command("dy") == expected_auth_command("dy")
    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        response = client.post("/api/v1/platform-connections/dy/attempts")
        assert launcher.started.wait(timeout=1)

    body = response.json()
    assert response.status_code == 202
    assert str(UUID(body["attempt_id"])) == body["attempt_id"]
    assert body == {
        "attempt_id": body["attempt_id"],
        "platform": {
            "platform": "dy",
            "display_name": "抖音",
            "availability": "enabled",
            "status": "checking",
            "guidance": "none",
            "last_checked_at": None,
            "active_attempt_id": body["attempt_id"],
        },
    }
    assert launcher.calls[0][0] == expected_auth_command("dy")
    assert terminator.calls == [(process, 0.01)]


def test_toutiao_start_returns_exact_202_projection() -> None:
    process = FakeProcess(hang=True)
    service, launcher, terminator = build_service(process)

    assert service._worker_command("toutiao") == expected_auth_command("toutiao")
    with TestClient(
        create_app(platform_connection_service_factory=lambda: service)
    ) as client:
        response = client.post("/api/v1/platform-connections/toutiao/attempts")
        assert launcher.started.wait(timeout=1)

    body = response.json()
    assert response.status_code == 202
    assert str(UUID(body["attempt_id"])) == body["attempt_id"]
    assert body == {
        "attempt_id": body["attempt_id"],
        "platform": {
            "platform": "toutiao",
            "display_name": "今日头条",
            "availability": "enabled",
            "status": "checking",
            "guidance": "none",
            "last_checked_at": None,
            "active_attempt_id": body["attempt_id"],
        },
    }
    assert launcher.calls[0][0] == expected_auth_command("toutiao")
    assert terminator.calls == [(process, 0.01)]


def test_toutiao_success_uses_its_trusted_platform_command() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[
                auth_event("waiting_for_approval", platform="toutiao"),
                auth_event("checking", platform="toutiao"),
                auth_event("connected", platform="toutiao"),
            ],
            exit_code=0,
        )
        service, launcher, terminator = build_service(process)

        accepted = await service.start_attempt("toutiao")
        result = await wait_for_terminal(service, "toutiao")

        assert result["status"] == "connected"
        assert result["guidance"] == "none"
        assert result["last_checked_at"] == "2026-08-24T12:30:00Z"
        assert accepted.platform.platform == "toutiao"
        assert launcher.calls == [
            (expected_auth_command("toutiao"), Path("/repo/third_party/MediaCrawler"))
        ]
        assert terminator.calls == []

    asyncio.run(scenario())


def test_douyin_success_uses_its_trusted_platform_command() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[
                auth_event("checking", platform="dy"),
                auth_event("connected", platform="dy"),
            ],
            exit_code=0,
        )
        service, launcher, terminator = build_service(process)

        accepted = await service.start_attempt("dy")
        result = await wait_for_terminal(service, "dy")

        assert result["status"] == "connected"
        assert result["guidance"] == "none"
        assert result["last_checked_at"] == "2026-08-24T12:30:00Z"
        assert accepted.platform.platform == "dy"
        assert launcher.calls == [
            (expected_auth_command("dy"), Path("/repo/third_party/MediaCrawler"))
        ]
        assert terminator.calls == []

    asyncio.run(scenario())


def test_success_requires_connected_event_and_zero_exit() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[
                b"ordinary crawler output is discarded\n",
                auth_event("checking"),
                auth_event("waiting_for_login"),
                auth_event("checking"),
                auth_event("connected"),
            ],
            stderr=[b"ordinary stderr is also discarded\n"],
            exit_code=0,
        )
        service, launcher, terminator = build_service(process)

        accepted = await service.start_attempt("wb")
        result = await wait_for_terminal(service)

        assert result == {
            "platform": "wb",
            "display_name": "微博",
            "availability": "enabled",
            "status": "connected",
            "guidance": "none",
            "last_checked_at": "2026-08-24T12:30:00Z",
            "active_attempt_id": None,
        }
        command, cwd = launcher.calls[0]
        assert cwd == Path("/repo/third_party/MediaCrawler")
        assert command == expected_auth_command("wb")
        assert accepted.attempt_id is not None
        assert terminator.calls == []

    asyncio.run(scenario())


def test_kuaishou_success_uses_its_trusted_platform_command() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[
                auth_event("checking", platform="ks"),
                auth_event("connected", platform="ks"),
            ],
            exit_code=0,
        )
        service, launcher, terminator = build_service(process)

        accepted = await service.start_attempt("ks")
        result = await wait_for_terminal(service, "ks")

        assert result == {
            "platform": "ks",
            "display_name": "快手",
            "availability": "enabled",
            "status": "connected",
            "guidance": "none",
            "last_checked_at": "2026-08-24T12:30:00Z",
            "active_attempt_id": None,
        }
        assert accepted.platform.platform == "ks"
        assert launcher.calls == [
            (
                expected_auth_command("ks"),
                Path("/repo/third_party/MediaCrawler"),
            )
        ]
        assert terminator.calls == []

    asyncio.run(scenario())


def test_kuaishou_explicit_disconnected_event_maps_to_retry() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[
                auth_event("checking", platform="ks"),
                auth_event("waiting_for_login", platform="ks"),
                auth_event("checking", platform="ks"),
                auth_event("disconnected", platform="ks"),
            ],
            exit_code=20,
        )
        service, _, terminator = build_service(process)

        await service.start_attempt("ks")
        result = await wait_for_terminal(service, "ks")

        assert result["status"] == "disconnected"
        assert result["guidance"] == "retry"
        assert result["last_checked_at"] == "2026-08-24T12:30:00Z"
        assert terminator.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("attempt_platform", "event_platform"),
    CROSS_AUTH_PLATFORM_PAIRS,
)
def test_cross_platform_auth_event_fails_the_active_attempt(
    attempt_platform: str, event_platform: str
) -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[auth_event("checking", platform=event_platform)],
            hang=True,
        )
        service, launcher, terminator = build_service(process)

        await service.start_attempt(attempt_platform)
        result = await wait_for_terminal(service, attempt_platform)

        assert result["platform"] == attempt_platform
        assert result["status"] == "failed"
        assert result["guidance"] == "retry"
        other_auth_platforms = [
            connection
            for connection in (await service.list_connections()).platforms
            if connection.platform in AUTH_PLATFORMS
            and connection.platform != attempt_platform
        ]
        assert len(other_auth_platforms) == 3
        for other in other_auth_platforms:
            assert other.status == "not_checked"
            assert other.active_attempt_id is None
            assert other.last_checked_at is None
        assert launcher.calls[0][0] == expected_auth_command(attempt_platform)
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("expected_platform", "event_platform"),
    CROSS_AUTH_PLATFORM_PAIRS,
)
def test_every_supported_cross_platform_event_is_rejected(
    expected_platform: str, event_platform: str
) -> None:
    with pytest.raises(service_module._ProtocolError):
        service_module._parse_auth_event(
            auth_event("checking", platform=event_platform),
            expected_platform=expected_platform,
        )


@pytest.mark.parametrize("platform", AUTH_PLATFORMS)
def test_auth_event_is_valid_only_for_matching_attempt(platform: str) -> None:
    event = service_module._parse_auth_event(
        auth_event("checking", platform=platform),
        expected_platform=platform,
    )

    assert event is not None
    assert event.platform == platform
    assert event.phase == "checking"


def test_terminal_attempt_releases_the_single_worker_slot() -> None:
    async def scenario() -> None:
        first_process = FakeProcess(
            stdout=[auth_event("checking"), auth_event("connected")]
        )
        second_process = FakeProcess(
            stdout=[
                auth_event("checking", platform="ks"),
                auth_event("connected", platform="ks"),
            ]
        )
        launcher = FakeLauncher(first_process, second_process)
        terminator = FakeTerminator()
        service = PlatformConnectionService(
            media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
            process_launcher=launcher,
            process_group_terminator=terminator,
            clock=lambda: FIXED_NOW,
        )

        first = await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"
        second = await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"

        assert first.attempt_id != second.attempt_id
        assert len(launcher.calls) == 2
        assert terminator.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("phases", "expected_status", "expected_guidance"),
    [
        (["waiting_for_browser"], "action_required", "enable_remote_debugging"),
        (["waiting_for_approval"], "action_required", "approve_connection"),
        (["checking"], "checking", "none"),
        (["checking", "waiting_for_login"], "action_required", "complete_login"),
    ],
)
@pytest.mark.parametrize("platform", ["wb", "ks"])
def test_protocol_phases_update_the_visible_projection(
    phases: list[str],
    expected_status: str,
    expected_guidance: str,
    platform: str,
) -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[auth_event(phase, platform=platform) for phase in phases],
            hang=True,
        )
        service, _, _ = build_service(process)
        await service.start_attempt(platform)

        for _ in range(100):
            connections = (await service.list_connections()).platforms
            connection = next(item for item in connections if item.platform == platform)
            if (
                connection.status == expected_status
                and connection.guidance == expected_guidance
            ):
                break
            await asyncio.sleep(0.001)
        else:
            raise AssertionError("phase was not projected")

        assert connection.last_checked_at is None
        assert connection.active_attempt_id is not None
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("event_lines", "exit_code", "expected_status", "expected_guidance"),
    [
        ([auth_event("checking")], 0, "failed", "retry"),
        ([auth_event("checking")], 20, "failed", "retry"),
        ([auth_event("checking"), auth_event("connected")], 20, "failed", "retry"),
        (
            [auth_event("checking"), auth_event("disconnected")],
            20,
            "disconnected",
            "retry",
        ),
        ([auth_event("waiting_for_browser")], 21, "failed", "enable_remote_debugging"),
        ([auth_event("checking")], 22, "failed", "retry"),
        ([auth_event("checking")], 79, "failed", "retry"),
    ],
)
def test_exit_and_terminal_event_matrix(
    event_lines: list[bytes],
    exit_code: int,
    expected_status: str,
    expected_guidance: str,
) -> None:
    async def scenario() -> None:
        service, _, _ = build_service(
            FakeProcess(stdout=event_lines, exit_code=exit_code)
        )
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)
        assert result["status"] == expected_status
        assert result["guidance"] == expected_guidance
        assert result["active_attempt_id"] is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid_event",
    [
        PREFIX + b"not-json\n",
        auth_event("checking", message="credential-sentinel"),
        PREFIX + b'{"version":2,"platform":"wb","phase":"checking"}\n',
        PREFIX + b'{"version":1,"platform":"dy","phase":"checking"}\n',
        auth_event("connected"),
        auth_event("checking") + b"x" * 1024,
    ],
)
def test_malformed_or_out_of_order_protocol_fails_closed(
    invalid_event: bytes,
) -> None:
    async def scenario() -> None:
        process = FakeProcess(stdout=[invalid_event], hang=True)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)

        assert result["status"] == "failed"
        assert result["guidance"] == "retry"
        assert "credential-sentinel" not in str(result)
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "phases",
    [
        ["checking", "waiting_for_approval"],
        ["waiting_for_browser", "checking"],
        ["checking", "waiting_for_login", "disconnected"],
    ],
)
def test_duplicate_regressing_or_skipped_phase_fails_closed(
    phases: list[str],
) -> None:
    async def scenario() -> None:
        process = FakeProcess(
            stdout=[auth_event(phase) for phase in phases],
            hang=True,
        )
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)

        assert result["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("phases", "expected_status", "expected_guidance"),
    [
        (["checking", "waiting_for_login"], "disconnected", "retry"),
        (["waiting_for_approval"], "failed", "enable_remote_debugging"),
        ([], "failed", "retry"),
    ],
)
def test_attempt_timeout_maps_to_safe_terminal_state(
    phases: list[str], expected_status: str, expected_guidance: str
) -> None:
    async def scenario() -> None:
        process = FakeProcess(stdout=[auth_event(phase) for phase in phases], hang=True)
        service, _, terminator = build_service(process, timeout=0.01)
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)

        assert result["status"] == expected_status
        assert result["guidance"] == expected_guidance
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_shutdown_cancels_task_and_terminates_owned_process() -> None:
    async def scenario() -> None:
        process = FakeProcess(stdout=[auth_event("checking")], hang=True)
        service, launcher, terminator = build_service(process)
        await service.start_attempt("wb")
        for _ in range(100):
            if launcher.calls:
                break
            await asyncio.sleep(0)

        await service.shutdown()
        result = (await service.list_connections()).platforms[0]

        assert terminator.calls == [(process, 0.01)]
        assert result.status == "failed"
        assert result.active_attempt_id is None

    asyncio.run(scenario())


def test_openapi_documents_exact_success_and_error_models() -> None:
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()

    operation = document["paths"]["/api/v1/platform-connections/{platform}/attempts"][
        "post"
    ]
    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PlatformConnectionAttemptResponse"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PlatformConnectionErrorResponse"
    }
    assert operation["responses"]["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PlatformConnectionErrorResponse"
    }


def test_default_launcher_uses_exec_without_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        captured: dict[str, object] = {}

        async def fake_create_subprocess_exec(
            *command: str, **options: object
        ) -> FakeProcess:
            captured["command"] = command
            captured["options"] = options
            return process

        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", fake_create_subprocess_exec
        )
        result = await service_module._launch_process(
            ("uv", "run", "--frozen"), Path("/repo/third_party/MediaCrawler")
        )

        assert result is process
        assert captured["command"] == ("uv", "run", "--frozen")
        assert captured["options"] == {
            "cwd": Path("/repo/third_party/MediaCrawler"),
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "limit": service_module.MAX_CHILD_OUTPUT_LINE_BYTES,
            "start_new_session": os.name == "posix",
        }

    asyncio.run(scenario())


def test_owned_process_group_is_killed_after_grace_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess(hang=True)
        sent_signals: list[signal.Signals] = []

        def fake_send_group_signal(
            target: FakeProcess, sent_signal: signal.Signals
        ) -> None:
            assert target is process
            sent_signals.append(sent_signal)
            if sent_signal == signal.SIGKILL:
                process.finish(-9)

        monkeypatch.setattr(
            service_module, "_send_process_group_signal", fake_send_group_signal
        )
        await service_module._terminate_owned_process_group(process, 0)

        assert sent_signals == [signal.SIGTERM, signal.SIGKILL]
        assert process.returncode == -9

    asyncio.run(scenario())
