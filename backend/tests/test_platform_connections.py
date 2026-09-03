import asyncio
import json
import os
import signal
import threading
from collections import deque
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from longtian_api.main import create_app
from longtian_api.schemas.platform_connections import PlatformConnection
from longtian_api.services import media_crawler_auth_worker as worker_module
from longtian_api.services import platform_connections as service_module
from longtian_api.services.media_crawler_auth_worker import (
    AUTH_COMMAND_PREFIX,
    AUTH_EVENT_PREFIX,
    AuthWorkerError,
)
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService

FIXED_NOW = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)
AUTH_PLATFORMS = ("wb", "dy", "ks", "xhs", "toutiao")
CROSS_AUTH_PLATFORM_PAIRS = tuple(
    (expected, received)
    for expected in AUTH_PLATFORMS
    for received in AUTH_PLATFORMS
    if expected != received
)

MonitoringRuleServiceFactory = Callable[[], MonitoringRuleService]


@pytest.fixture
def monitoring_rule_service_factory(tmp_path: Path) -> MonitoringRuleServiceFactory:
    return lambda: MonitoringRuleService(
        database_path=tmp_path / "platform-connections.sqlite3"
    )


def worker_event(event: str, **fields: object) -> bytes:
    payload = {"version": 2, "type": "event", "event": event, **fields}
    return (
        AUTH_EVENT_PREFIX + json.dumps(payload, separators=(",", ":")).encode() + b"\n"
    )


def progress_event(request_id: str, platform: str, phase: str) -> bytes:
    return worker_event(
        "progress", request_id=request_id, platform=platform, phase=phase
    )


def result_event(
    request_id: str,
    platform: str,
    outcome: str = "connected",
    reason: str = "none",
) -> bytes:
    return worker_event(
        "result",
        request_id=request_id,
        platform=platform,
        outcome=outcome,
        reason=reason,
    )


def expected_worker_command() -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--frozen",
        "--project",
        "/repo/third_party/MediaCrawler",
        "python",
        "-m",
        "tools.auth_worker",
    )


class FakeLineReader:
    def __init__(self, lines: Iterable[bytes] = ()) -> None:
        self._lines = deque(lines)
        self._closed = False
        self._available = asyncio.Event()
        if self._lines:
            self._available.set()

    async def readline(self) -> bytes:
        while not self._lines and not self._closed:
            self._available.clear()
            await self._available.wait()
        if self._lines:
            line = self._lines.popleft()
            if self._lines:
                self._available.set()
            return line
        return b""

    async def read(self, size: int = -1) -> bytes:
        chunk = await self.readline()
        if size < 0 or len(chunk) <= size:
            return chunk
        self._lines.appendleft(chunk[size:])
        self._available.set()
        return chunk[:size]

    def feed(self, line: bytes) -> None:
        if self._closed:
            return
        self._lines.append(line)
        self._available.set()

    def close(self) -> None:
        self._closed = True
        self._available.set()


class FakeWriter:
    def __init__(self, process: "FakeProcess") -> None:
        self._process = process
        self.fail_drain = False

    def write(self, data: bytes) -> None:
        self._process.receive_command(data)

    async def drain(self) -> None:
        if self.fail_drain:
            raise BrokenPipeError


Plan = Callable[["FakeProcess", dict[str, object]], None]


class FakeProcess:
    _next_pid = 91000

    def __init__(
        self,
        *plans: Plan,
        emit_ready: bool = True,
        stderr: Iterable[bytes] = (),
        cancel_ack: bool = True,
        shutdown_ack: bool = True,
    ) -> None:
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self.returncode: int | None = None
        self.stdin = FakeWriter(self)
        self.stdout = FakeLineReader()
        self.stderr = FakeLineReader(stderr)
        self._plans = deque(plans)
        self._emit_ready = emit_ready
        self._cancel_ack = cancel_ack
        self._shutdown_ack = shutdown_ack
        self._finished = asyncio.Event()
        self.commands: list[dict[str, object]] = []
        self.raw_commands: list[bytes] = []
        self.current_request: tuple[str, str] | None = None

    def start(self) -> None:
        if self._emit_ready:
            self.stdout.feed(worker_event("ready"))

    def receive_command(self, data: bytes) -> None:
        self.raw_commands.append(data)
        assert data.startswith(AUTH_COMMAND_PREFIX)
        command = json.loads(data[len(AUTH_COMMAND_PREFIX) :])
        self.commands.append(command)
        action = command["command"]
        if action == "check":
            self.current_request = (command["request_id"], command["platform"])
            if self._plans:
                self._plans.popleft()(self, command)
        elif action == "cancel" and self._cancel_ack:
            assert self.current_request is not None
            request_id, platform = self.current_request
            self.stdout.feed(
                result_event(
                    request_id,
                    platform,
                    outcome="cancelled",
                    reason="cancelled",
                )
            )
            self.current_request = None
        elif action == "shutdown" and self._shutdown_ack:
            self.stdout.feed(worker_event("stopped"))
            self.finish(0)

    def feed(self, line: bytes) -> None:
        self.stdout.feed(line)

    async def wait(self) -> int:
        await self._finished.wait()
        assert self.returncode is not None
        return self.returncode

    def finish(self, returncode: int) -> None:
        if self.returncode is not None:
            return
        self.returncode = returncode
        self.stdout.close()
        self.stderr.close()
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
        process = self._processes.popleft()
        process.start()
        self.started.set()
        return process


class FakeTerminator:
    def __init__(self) -> None:
        self.calls: list[tuple[FakeProcess, float]] = []

    async def __call__(self, process: FakeProcess, grace: float) -> None:
        self.calls.append((process, grace))
        process.finish(-15)


def connected_plan(
    process: FakeProcess, command: dict[str, object], *, approval: bool = False
) -> None:
    request_id = str(command["request_id"])
    platform = str(command["platform"])
    if approval:
        process.feed(progress_event(request_id, platform, "waiting_for_approval"))
    process.feed(progress_event(request_id, platform, "checking"))
    process.feed(result_event(request_id, platform))
    process.current_request = None


def disconnected_plan(process: FakeProcess, command: dict[str, object]) -> None:
    request_id = str(command["request_id"])
    platform = str(command["platform"])
    process.feed(progress_event(request_id, platform, "checking"))
    process.feed(progress_event(request_id, platform, "waiting_for_login"))
    process.feed(progress_event(request_id, platform, "checking"))
    process.feed(
        result_event(
            request_id,
            platform,
            outcome="disconnected",
            reason="login_required",
        )
    )
    process.current_request = None


def hanging_plan(process: FakeProcess, command: dict[str, object]) -> None:
    process.feed(
        progress_event(str(command["request_id"]), str(command["platform"]), "checking")
    )


def login_hanging_plan(process: FakeProcess, command: dict[str, object]) -> None:
    request_id = str(command["request_id"])
    platform = str(command["platform"])
    process.feed(progress_event(request_id, platform, "checking"))
    process.feed(progress_event(request_id, platform, "waiting_for_login"))


async def wait_for_terminal(
    service: PlatformConnectionService, platform: str = "wb"
) -> dict[str, object]:
    for _ in range(500):
        connections = (await service.list_connections()).platforms
        connection = next(item for item in connections if item.platform == platform)
        if connection.status in {"connected", "disconnected", "failed"}:
            return connection.model_dump(mode="json")
        await asyncio.sleep(0.001)
    raise AssertionError("connection attempt did not reach a terminal state")


def build_service(
    *processes: FakeProcess,
    timeout: float = 1.0,
    ready_timeout: float = 1.0,
    cancel_timeout: float = 0.01,
    shutdown_timeout: float = 0.05,
) -> tuple[PlatformConnectionService, FakeLauncher, FakeTerminator]:
    launcher = FakeLauncher(*processes)
    terminator = FakeTerminator()
    service = PlatformConnectionService(
        media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
        process_launcher=launcher,
        process_group_terminator=terminator,
        attempt_timeout_seconds=timeout,
        worker_ready_timeout_seconds=ready_timeout,
        cancel_timeout_seconds=cancel_timeout,
        worker_shutdown_timeout_seconds=shutdown_timeout,
        termination_grace_seconds=0.01,
        clock=lambda: FIXED_NOW,
    )
    return service, launcher, terminator


def test_product_worker_uses_ignored_managed_browser_profile_by_default() -> None:
    service, _, _ = build_service(FakeProcess())
    expected = (
        Path(__file__).resolve().parents[2] / "runtime" / "browser" / "managed-chrome"
    )

    assert service_module._default_browser_profile_dir() == expected
    assert service._browser_profile_dir == expected
    assert service.worker._browser_profile_dir == expected


def command_actions(process: FakeProcess) -> list[str]:
    return [str(command["command"]) for command in process.commands]


def test_startup_and_get_launch_no_worker_and_catalog_is_unchanged(
    monitoring_rule_service_factory: MonitoringRuleServiceFactory,
) -> None:
    service, launcher, _ = build_service(FakeProcess())

    with TestClient(
        create_app(
            platform_connection_service_factory=lambda: service,
            monitoring_rule_service_factory=monitoring_rule_service_factory,
        )
    ) as client:
        response = client.get("/api/v1/platform-connections")

    assert response.status_code == 200
    assert response.json() == {
        "platforms": [
            {
                "platform": platform,
                "display_name": display_name,
                "availability": "enabled",
                "status": "not_checked",
                "guidance": "none",
                "last_checked_at": None,
                "active_attempt_id": None,
            }
            for platform, display_name in zip(
                AUTH_PLATFORMS,
                ("微博", "抖音", "快手", "小红书", "今日头条"),
                strict=True,
            )
        ]
    }
    assert launcher.calls == []


@pytest.mark.parametrize(
    ("platform", "status_code", "code"),
    [
        ("unknown", 404, "platform_not_found"),
        ("ks --type search", 404, "platform_not_found"),
    ],
)
def test_unknown_platform_starts_no_worker(
    platform: str,
    status_code: int,
    code: str,
    monitoring_rule_service_factory: MonitoringRuleServiceFactory,
) -> None:
    service, launcher, _ = build_service(FakeProcess())

    with TestClient(
        create_app(
            platform_connection_service_factory=lambda: service,
            monitoring_rule_service_factory=monitoring_rule_service_factory,
        )
    ) as client:
        response = client.post(f"/api/v1/platform-connections/{platform}/attempts")

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert launcher.calls == []


def test_known_unavailable_platform_starts_no_worker() -> None:
    service, launcher, _ = build_service(FakeProcess())
    current = service._connections["xhs"]
    service._connections["xhs"] = current.model_copy(
        update={"availability": "coming_soon", "status": "coming_soon"}
    )

    with pytest.raises(service_module.PlatformConnectionError) as raised:
        asyncio.run(service.start_attempt("xhs"))

    assert raised.value.code == "platform_not_available"
    assert launcher.calls == []


@pytest.mark.parametrize("platform", AUTH_PLATFORMS)
def test_start_returns_exact_202_and_fixed_worker_command(
    platform: str,
    monitoring_rule_service_factory: MonitoringRuleServiceFactory,
) -> None:
    process = FakeProcess(hanging_plan)
    service, launcher, terminator = build_service(process)

    with TestClient(
        create_app(
            platform_connection_service_factory=lambda: service,
            monitoring_rule_service_factory=monitoring_rule_service_factory,
        )
    ) as client:
        response = client.post(f"/api/v1/platform-connections/{platform}/attempts")
        assert launcher.started.wait(timeout=1)

    body = response.json()
    assert response.status_code == 202
    assert str(UUID(body["attempt_id"])) == body["attempt_id"]
    assert body == {
        "attempt_id": body["attempt_id"],
        "platform": {
            "platform": platform,
            "display_name": dict(
                zip(
                    AUTH_PLATFORMS,
                    ("微博", "抖音", "快手", "小红书", "今日头条"),
                    strict=True,
                )
            )[platform],
            "availability": "enabled",
            "status": "checking",
            "guidance": "none",
            "last_checked_at": None,
            "active_attempt_id": body["attempt_id"],
        },
    }
    assert launcher.calls == [
        (expected_worker_command(), Path("/repo/third_party/MediaCrawler"))
    ]
    assert command_actions(process) == ["check", "cancel", "shutdown"]
    assert terminator.calls == [(process, 0.01)]


def test_concurrent_attempt_preserves_exact_409_and_one_check(
    monitoring_rule_service_factory: MonitoringRuleServiceFactory,
) -> None:
    process = FakeProcess(hanging_plan)
    service, launcher, _ = build_service(process)

    with TestClient(
        create_app(
            platform_connection_service_factory=lambda: service,
            monitoring_rule_service_factory=monitoring_rule_service_factory,
        )
    ) as client:
        accepted = client.post("/api/v1/platform-connections/wb/attempts")
        assert launcher.started.wait(timeout=1)
        conflict = client.post("/api/v1/platform-connections/ks/attempts")

    assert accepted.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": {
            "code": "connection_attempt_active",
            "message": "已有平台连接任务正在进行，请稍后重试。",
        }
    }
    assert command_actions(process).count("check") == 1
    assert len(launcher.calls) == 1


def test_two_platforms_reuse_one_process_and_distinct_request_ids() -> None:
    async def scenario() -> None:
        process = FakeProcess(connected_plan, connected_plan)
        service, launcher, terminator = build_service(process)

        first = await service.start_attempt("wb")
        assert (await wait_for_terminal(service, "wb"))["status"] == "connected"
        second = await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"

        checks = [item for item in process.commands if item["command"] == "check"]
        assert first.attempt_id != second.attempt_id
        assert [item["platform"] for item in checks] == ["wb", "ks"]
        assert [item["request_id"] for item in checks] == [
            str(first.attempt_id),
            str(second.attempt_id),
        ]
        assert all(
            set(item) == {"version", "type", "command", "request_id", "platform"}
            and item["version"] == 2
            and item["type"] == "command"
            for item in checks
        )
        assert len(launcher.calls) == 1
        assert terminator.calls == []
        await service.shutdown()

    asyncio.run(scenario())


def test_full_five_platform_sequence_uses_one_worker() -> None:
    async def scenario() -> None:
        process = FakeProcess(*(connected_plan for _ in AUTH_PLATFORMS))
        service, launcher, _ = build_service(process)

        for platform in AUTH_PLATFORMS:
            await service.start_attempt(platform)
            assert (await wait_for_terminal(service, platform))["status"] == "connected"

        assert len(launcher.calls) == 1
        assert [
            command["platform"]
            for command in process.commands
            if command["command"] == "check"
        ] == list(AUTH_PLATFORMS)
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("phases", "expected_status", "expected_guidance"),
    [
        (["waiting_for_browser"], "checking", "starting_browser"),
        (["waiting_for_browser", "checking"], "checking", "none"),
        (["waiting_for_approval"], "action_required", "approve_connection"),
        (["checking"], "checking", "none"),
        (["checking", "waiting_for_login"], "action_required", "complete_login"),
    ],
)
def test_progress_updates_visible_projection(
    phases: list[str], expected_status: str, expected_guidance: str
) -> None:
    def plan(process: FakeProcess, command: dict[str, object]) -> None:
        for phase in phases:
            process.feed(
                progress_event(
                    str(command["request_id"]), str(command["platform"]), phase
                )
            )

    async def scenario() -> None:
        process = FakeProcess(plan)
        service, _, _ = build_service(process)
        await service.start_attempt("wb")

        for _ in range(200):
            row = (await service.list_connections()).platforms[0]
            if row.status == expected_status and row.guidance == expected_guidance:
                break
            await asyncio.sleep(0.001)
        else:
            raise AssertionError("progress was not projected")
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("outcome", "reason", "expected_status", "expected_guidance"),
    [
        ("connected", "none", "connected", "none"),
        ("disconnected", "login_required", "disconnected", "retry"),
        ("failed", "browser_unavailable", "failed", "retry_browser"),
        ("failed", "browser_disconnected", "failed", "retry_browser"),
        ("failed", "internal_error", "failed", "retry"),
    ],
)
def test_result_projection_matrix(
    outcome: str,
    reason: str,
    expected_status: str,
    expected_guidance: str,
) -> None:
    def plan(process: FakeProcess, command: dict[str, object]) -> None:
        request_id = str(command["request_id"])
        platform = str(command["platform"])
        process.feed(progress_event(request_id, platform, "checking"))
        process.feed(result_event(request_id, platform, outcome, reason))

    async def scenario() -> None:
        service, _, _ = build_service(FakeProcess(plan))
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)
        assert result["status"] == expected_status
        assert result["guidance"] == expected_guidance
        assert result["last_checked_at"] == "2026-08-24T12:30:00Z"
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("attempt_platform", "event_platform"), CROSS_AUTH_PLATFORM_PAIRS
)
def test_all_cross_platform_events_fail_closed_without_foreign_mutation(
    attempt_platform: str, event_platform: str
) -> None:
    def plan(process: FakeProcess, command: dict[str, object]) -> None:
        process.feed(
            progress_event(str(command["request_id"]), event_platform, "checking")
        )

    async def scenario() -> None:
        process = FakeProcess(plan)
        service, _, terminator = build_service(process)
        await service.start_attempt(attempt_platform)
        result = await wait_for_terminal(service, attempt_platform)

        assert result["status"] == "failed"
        rows = (await service.list_connections()).platforms
        for row in rows:
            if row.platform != attempt_platform:
                assert row.status == "not_checked"
                assert row.active_attempt_id is None
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "invalid_frame_factory",
    [
        lambda _request, _platform: b"ordinary output\n",
        lambda _request, _platform: AUTH_EVENT_PREFIX + b"not-json\n",
        lambda _request, _platform: worker_event("ready", extra="secret-marker"),
        lambda request, platform: (
            AUTH_EVENT_PREFIX
            + (
                '{"version":2,"type":"event","event":"progress",'
                f'"request_id":"{request}","platform":"{platform}",'
                '"phase":"checking","phase":"checking"}\n'
            ).encode()
        ),
        lambda request, platform: (
            progress_event(request, platform, "checking") + b"x" * 1024
        ),
        lambda _request, platform: progress_event(str(uuid4()), platform, "checking"),
        lambda request, platform: worker_event(
            "progress",
            request_id=request,
            platform=platform,
            phase="checking",
            detail="credential-sentinel",
        ),
    ],
)
def test_malformed_protocol_recycles_worker_without_leaking_raw_output(
    invalid_frame_factory: Callable[[str, str], bytes],
) -> None:
    def invalid_plan(process: FakeProcess, command: dict[str, object]) -> None:
        process.feed(
            invalid_frame_factory(str(command["request_id"]), str(command["platform"]))
        )

    async def scenario() -> None:
        first = FakeProcess(invalid_plan)
        second = FakeProcess(connected_plan)
        service, launcher, terminator = build_service(first, second)
        await service.start_attempt("wb")
        attempt_task = service._current_task
        failed = await wait_for_terminal(service)
        assert failed["status"] == "failed"
        assert "credential-sentinel" not in str(failed)
        assert terminator.calls == [(first, 0.01)]

        # Terminal publication precedes browser-owner release. This test checks
        # reuse after the owned finalizer, not a request racing that finalizer.
        assert attempt_task is not None
        await attempt_task
        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        assert len(launcher.calls) == 2
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "phases",
    [
        ["checking", "checking"],
        ["checking", "waiting_for_approval"],
        ["checking", "waiting_for_login", "checking", "waiting_for_login"],
    ],
)
def test_invalid_progress_order_recycles_worker(phases: list[str]) -> None:
    def plan(process: FakeProcess, command: dict[str, object]) -> None:
        for phase in phases:
            process.feed(
                progress_event(
                    str(command["request_id"]), str(command["platform"]), phase
                )
            )

    async def scenario() -> None:
        process = FakeProcess(plan)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize("missing_stream", ["stdin", "stdout", "stderr"])
def test_missing_worker_pipe_fails_closed_and_terminates(missing_stream: str) -> None:
    async def scenario() -> None:
        process = FakeProcess(emit_ready=False)
        setattr(process, missing_stream, None)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_worker_launch_failure_is_detail_free() -> None:
    async def failing_launcher(_command: tuple[str, ...], _cwd: Path) -> FakeProcess:
        raise RuntimeError("credential-sentinel")

    async def scenario() -> None:
        service = PlatformConnectionService(
            media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
            process_launcher=failing_launcher,
            attempt_timeout_seconds=1,
            clock=lambda: FIXED_NOW,
        )
        await service.start_attempt("wb")
        row = await wait_for_terminal(service)
        assert row["status"] == "failed"
        assert "credential-sentinel" not in str(row)
        await service.shutdown()

    asyncio.run(scenario())


def test_duplicate_result_after_terminal_recycles_and_fails_closed() -> None:
    def plan(process: FakeProcess, command: dict[str, object]) -> None:
        request_id = str(command["request_id"])
        platform = str(command["platform"])
        process.feed(progress_event(request_id, platform, "checking"))
        process.feed(result_event(request_id, platform))
        process.feed(result_event(request_id, platform))

    async def scenario() -> None:
        process = FakeProcess(plan)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_ready_timeout_recycles_and_next_attempt_launches_again() -> None:
    async def scenario() -> None:
        first = FakeProcess(emit_ready=False)
        second = FakeProcess(connected_plan)
        service, launcher, terminator = build_service(first, second, ready_timeout=0.01)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert terminator.calls == [(first, 0.01)]

        await service.start_attempt("dy")
        assert (await wait_for_terminal(service, "dy"))["status"] == "connected"
        assert len(launcher.calls) == 2
        await service.shutdown()

    asyncio.run(scenario())


def test_whole_attempt_timeout_during_worker_start_recycles_generation() -> None:
    async def scenario() -> None:
        process = FakeProcess(emit_ready=False)
        service, _, terminator = build_service(
            process,
            timeout=0.01,
            ready_timeout=1,
        )
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_writer_failure_recycles_without_exposing_exception() -> None:
    async def scenario() -> None:
        process = FakeProcess(hanging_plan)
        process.stdin.fail_drain = True
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        result = await wait_for_terminal(service)
        assert result["status"] == "failed"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


@pytest.mark.parametrize("emit_ready", [False, True])
def test_unexpected_eof_before_or_after_ready_recycles(emit_ready: bool) -> None:
    async def scenario() -> None:
        process = FakeProcess(emit_ready=emit_ready)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        for _ in range(100):
            if process.commands or not emit_ready:
                break
            await asyncio.sleep(0)
        process.finish(7)
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert process.returncode == 7
        # A dead worker leader can still leave a managed Chrome descendant in
        # its owned process group, so the generation terminator is invoked even
        # after the leader's return code is known.
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_managed_guidance_requires_matching_public_status() -> None:
    base = {
        "platform": "wb",
        "display_name": "微博",
        "availability": "enabled",
        "last_checked_at": None,
        "active_attempt_id": None,
    }

    with pytest.raises(ValidationError):
        PlatformConnection(**base, status="failed", guidance="starting_browser")
    with pytest.raises(ValidationError):
        PlatformConnection(**base, status="checking", guidance="retry_browser")

    assert (
        PlatformConnection(
            **base, status="checking", guidance="starting_browser"
        ).guidance
        == "starting_browser"
    )
    assert (
        PlatformConnection(**base, status="failed", guidance="retry_browser").guidance
        == "retry_browser"
    )


def test_late_callback_from_recycled_generation_cannot_mutate_current_state() -> None:
    def invalid_plan(process: FakeProcess, _command: dict[str, object]) -> None:
        process.feed(b"invalid\n")

    async def scenario() -> None:
        first = FakeProcess(invalid_plan)
        second = FakeProcess(connected_plan)
        service, _, _ = build_service(first, second)
        old_attempt = await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"

        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        stale = worker_module._parse_event(
            progress_event(str(old_attempt.attempt_id), "wb", "checking")
        )
        await service._worker._handle_event(1, stale)
        rows = (await service.list_connections()).platforms
        assert next(row for row in rows if row.platform == "ks").status == "connected"
        assert next(row for row in rows if row.platform == "wb").status == "failed"
        await service.shutdown()

    asyncio.run(scenario())


def test_idle_worker_crash_invalidates_connected_and_next_post_relaunches() -> None:
    async def scenario() -> None:
        first = FakeProcess(connected_plan)
        second = FakeProcess(connected_plan)
        service, launcher, _ = build_service(first, second)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"

        first.finish(9)
        for _ in range(200):
            row = (await service.list_connections()).platforms[0]
            if row.status == "failed":
                break
            await asyncio.sleep(0.001)
        assert row.guidance == "retry"
        assert row.last_checked_at.isoformat() == "2026-08-24T12:30:00+00:00"

        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        assert len(launcher.calls) == 2
        await service.shutdown()

    asyncio.run(scenario())


def test_post_racing_idle_exit_runs_on_fresh_generation() -> None:
    async def scenario() -> None:
        first = FakeProcess(connected_plan)
        second = FakeProcess(connected_plan)
        service, launcher, _ = build_service(first, second)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"

        first.finish(9)
        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        assert len(launcher.calls) == 2
        await service.shutdown()

    asyncio.run(scenario())


def test_idle_session_disconnect_invalidates_but_reuses_healthy_worker() -> None:
    async def scenario() -> None:
        process = FakeProcess(connected_plan, connected_plan)
        service, launcher, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"

        process.feed(
            worker_event("session", state="disconnected", reason="browser_disconnected")
        )
        for _ in range(200):
            row = (await service.list_connections()).platforms[0]
            if row.status == "failed":
                break
            await asyncio.sleep(0.001)
        assert row.guidance == "retry"

        await service.start_attempt("dy")
        assert (await wait_for_terminal(service, "dy"))["status"] == "connected"
        assert len(launcher.calls) == 1
        assert terminator.calls == []
        await service.shutdown()

    asyncio.run(scenario())


def test_queued_idle_disconnect_before_check_does_not_recycle_new_request() -> None:
    async def scenario() -> None:
        process = FakeProcess(connected_plan, connected_plan)
        service, launcher, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"

        # Queue the idle-session event without waking the reader. Writing the
        # next check wakes it after the client has installed the new active
        # request, reproducing the cross-task ordering race deterministically.
        process.stdout._lines.append(
            worker_event("session", state="disconnected", reason="browser_disconnected")
        )
        await service.start_attempt("dy")

        assert (await wait_for_terminal(service, "dy"))["status"] == "connected"
        rows = (await service.list_connections()).platforms
        assert next(row for row in rows if row.platform == "wb").status == "failed"
        assert len(launcher.calls) == 1
        assert terminator.calls == []
        await service.shutdown()

    asyncio.run(scenario())


def test_session_disconnect_after_request_progress_recycles_worker() -> None:
    def invalid_busy_disconnect(
        process: FakeProcess, command: dict[str, object]
    ) -> None:
        process.feed(
            progress_event(
                str(command["request_id"]), str(command["platform"]), "checking"
            )
        )
        process.feed(
            worker_event("session", state="disconnected", reason="browser_disconnected")
        )

    async def scenario() -> None:
        process = FakeProcess(invalid_busy_disconnect)
        service, _, terminator = build_service(process)
        await service.start_attempt("dy")

        row = await wait_for_terminal(service, "dy")
        assert row["status"] == "failed"
        assert row["guidance"] == "retry"
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_disconnect_after_connected_result_cannot_leave_false_connected_state() -> None:
    def racing_disconnect_plan(
        process: FakeProcess, command: dict[str, object]
    ) -> None:
        request_id = str(command["request_id"])
        platform = str(command["platform"])
        process.feed(progress_event(request_id, platform, "checking"))
        process.feed(result_event(request_id, platform))
        process.feed(
            worker_event("session", state="disconnected", reason="browser_disconnected")
        )

    async def scenario() -> None:
        process = FakeProcess(racing_disconnect_plan)
        service, _, _ = build_service(process)
        await service.start_attempt("wb")
        row = await wait_for_terminal(service)
        assert row["status"] == "failed"
        assert row["guidance"] == "retry"
        assert row["active_attempt_id"] is None
        await service.shutdown()

    asyncio.run(scenario())


def test_attempt_timeout_with_cancel_ack_keeps_worker_for_next_check() -> None:
    async def scenario() -> None:
        process = FakeProcess(login_hanging_plan, connected_plan)
        service, launcher, terminator = build_service(process, timeout=0.01)
        await service.start_attempt("wb")
        first = await wait_for_terminal(service)
        assert first["status"] == "disconnected"
        assert command_actions(process)[:2] == ["check", "cancel"]

        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        assert len(launcher.calls) == 1
        assert terminator.calls == []
        await service.shutdown()

    asyncio.run(scenario())


def test_unacknowledged_cancel_recycles_worker() -> None:
    async def scenario() -> None:
        first = FakeProcess(hanging_plan, cancel_ack=False)
        second = FakeProcess(connected_plan)
        service, launcher, terminator = build_service(first, second, timeout=0.01)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "failed"
        assert command_actions(first) == ["check", "cancel"]
        assert terminator.calls == [(first, 0.01)]

        await service.start_attempt("ks")
        assert (await wait_for_terminal(service, "ks"))["status"] == "connected"
        assert len(launcher.calls) == 2
        await service.shutdown()

    asyncio.run(scenario())


def test_shutdown_cancels_active_request_then_stops_worker() -> None:
    async def scenario() -> None:
        process = FakeProcess(hanging_plan)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        for _ in range(100):
            if process.commands:
                break
            await asyncio.sleep(0)

        await service.shutdown()
        row = (await service.list_connections()).platforms[0]
        assert command_actions(process) == ["check", "cancel", "shutdown"]
        assert process.returncode == 0
        assert terminator.calls == [(process, 0.01)]
        assert row.status == "failed"
        assert row.active_attempt_id is None

    asyncio.run(scenario())


def test_unacknowledged_shutdown_uses_process_group_fallback() -> None:
    async def scenario() -> None:
        process = FakeProcess(connected_plan, shutdown_ack=False)
        service, _, terminator = build_service(process, shutdown_timeout=0.01)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"
        await service.shutdown()
        assert command_actions(process) == ["check", "shutdown"]
        assert terminator.calls == [(process, 0.01)]

    asyncio.run(scenario())


def test_stderr_credentials_are_discarded_and_never_projected() -> None:
    async def scenario() -> None:
        process = FakeProcess(
            connected_plan,
            stderr=[b"cookie=credential-sentinel authorization=secret\n"],
        )
        service, _, _ = build_service(process)
        await service.start_attempt("wb")
        row = await wait_for_terminal(service)
        catalog = (await service.list_connections()).model_dump(mode="json")
        assert "credential-sentinel" not in str(row)
        assert "credential-sentinel" not in str(catalog)
        assert "authorization" not in str(catalog).lower()
        await service.shutdown()

    asyncio.run(scenario())


def test_openapi_documents_exact_success_and_error_models(
    monitoring_rule_service_factory: MonitoringRuleServiceFactory,
) -> None:
    with TestClient(
        create_app(
            monitoring_rule_service_factory=monitoring_rule_service_factory,
        )
    ) as client:
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


@pytest.mark.parametrize(
    "line",
    [
        worker_event("ready", extra="x"),
        AUTH_EVENT_PREFIX
        + b'{"version":2,"type":"event","event":"ready","event":"ready"}\n',
        worker_event(
            "progress", request_id=str(uuid4()), platform="wb", phase="unknown"
        ),
        worker_event(
            "result",
            request_id=str(uuid4()),
            platform="wb",
            outcome="connected",
            reason="login_required",
        ),
        worker_event("session", state="connected", reason="browser_disconnected"),
        b"unprefixed\n",
        worker_event("ready").rstrip(b"\n"),
        AUTH_EVENT_PREFIX + b'{"version":2.0,"type":"event","event":"ready"}\n',
        AUTH_EVENT_PREFIX + b'{"version":NaN,"type":"event","event":"ready"}\n',
    ],
)
def test_v2_event_parser_rejects_invalid_exact_shapes(line: bytes) -> None:
    with pytest.raises(AuthWorkerError):
        worker_module._parse_event(line)


def test_default_launcher_uses_exec_with_duplex_pipes() -> None:
    async def scenario(monkeypatch: pytest.MonkeyPatch) -> None:
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
        result = await worker_module.launch_process(
            expected_worker_command(), Path("/repo/third_party/MediaCrawler")
        )
        assert result is process
        assert captured["command"] == expected_worker_command()
        assert captured["options"] == {
            "cwd": Path("/repo/third_party/MediaCrawler"),
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "limit": worker_module.MAX_CHILD_OUTPUT_LINE_BYTES,
            "start_new_session": os.name == "posix",
        }

    monkeypatch = pytest.MonkeyPatch()
    try:
        asyncio.run(scenario(monkeypatch))
    finally:
        monkeypatch.undo()


def test_managed_launcher_passes_only_trusted_profile_root_through_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        captured: dict[str, object] = {}
        profile = Path("/repo/runtime/browser/managed-chrome")

        async def fake_create_subprocess_exec(
            *command: str, **options: object
        ) -> FakeProcess:
            captured["command"] = command
            captured["options"] = options
            return process

        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", fake_create_subprocess_exec
        )
        await worker_module.launch_process(
            expected_worker_command(),
            Path("/repo/third_party/MediaCrawler"),
            browser_profile_dir=profile,
        )

        options = captured["options"]
        assert isinstance(options, dict)
        environment = options["env"]
        assert isinstance(environment, dict)
        assert environment[worker_module.LONGTIAN_BROWSER_PROFILE_DIR_ENV] == str(
            profile
        )
        assert (
            environment[worker_module.LONGTIAN_BROWSER_PROFILE_DIR_ENV]
            not in (captured["command"])
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "profile", [Path("relative/profile"), Path("/"), Path("/repo/../daily")]
)
def test_worker_rejects_unsafe_profile_configuration(profile: Path) -> None:
    async def progress(*_args: object) -> None:
        return None

    with pytest.raises(AuthWorkerError):
        worker_module.PersistentAuthWorkerClient(
            media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
            on_progress=progress,
            on_session_disconnected=progress,
            browser_profile_dir=profile,
        )


def test_owned_process_group_is_killed_after_grace_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        sent_signals: list[signal.Signals] = []

        def fake_send_group_signal(
            target: FakeProcess, sent_signal: signal.Signals
        ) -> None:
            assert target is process
            sent_signals.append(sent_signal)
            if sent_signal == signal.SIGKILL:
                process.finish(-9)

        monkeypatch.setattr(
            worker_module, "_send_process_group_signal", fake_send_group_signal
        )
        await worker_module.terminate_owned_process_group(process, 0)
        assert sent_signals == [signal.SIGTERM, signal.SIGKILL]
        assert process.returncode == -9

    asyncio.run(scenario())


def test_owned_process_group_is_cleaned_after_worker_leader_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        process.finish(7)
        sent_signals: list[signal.Signals] = []

        def fake_send_group_signal(
            target: FakeProcess, sent_signal: signal.Signals
        ) -> None:
            assert target is process
            sent_signals.append(sent_signal)

        monkeypatch.setattr(
            worker_module, "_send_process_group_signal", fake_send_group_signal
        )
        group_states = iter((True, False))
        monkeypatch.setattr(
            worker_module,
            "_process_group_exists",
            lambda _pid: next(group_states, False),
        )
        await worker_module.terminate_owned_process_group(process, 0)
        assert sent_signals == [signal.SIGTERM, signal.SIGKILL]

    asyncio.run(scenario())


def test_owned_process_group_rechecks_after_kill_when_child_still_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        sent_signals: list[signal.Signals] = []

        def fake_send_group_signal(
            target: FakeProcess, sent_signal: signal.Signals
        ) -> None:
            assert target is process
            sent_signals.append(sent_signal)
            if sent_signal == signal.SIGKILL:
                process.finish(-9)

        # TERM leaves the leader/child group alive. The first KILL is observed
        # while the child is still settling, then the second KILL proves exit.
        # Keep the group present for the first bounded post-KILL poll so the
        # terminator must retry KILL; the next poll observes that it settled.
        group_states = iter((True, True, True, False))
        monkeypatch.setattr(
            worker_module, "_send_process_group_signal", fake_send_group_signal
        )
        monkeypatch.setattr(
            worker_module,
            "_process_group_exists",
            lambda _pid: next(group_states, False),
        )
        await worker_module.terminate_owned_process_group(process, 0)
        assert sent_signals == [signal.SIGTERM, signal.SIGKILL, signal.SIGKILL]
        assert process.returncode == -9

    asyncio.run(scenario())


def test_graceful_shutdown_cleans_known_group_before_detaching() -> None:
    async def scenario() -> None:
        process = FakeProcess(connected_plan)
        service, _, terminator = build_service(process)
        await service.start_attempt("wb")
        assert (await wait_for_terminal(service))["status"] == "connected"

        await service.shutdown()

        assert command_actions(process) == ["check", "shutdown"]
        assert process.returncode == 0
        assert terminator.calls == [(process, 0.01)]
        assert service.worker._process is None

    asyncio.run(scenario())


def test_unsettled_worker_group_keeps_ownership_and_blocks_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        first, replacement = FakeProcess(), FakeProcess()
        service, launcher, terminator = build_service(first, replacement)
        worker = service.worker
        await worker._ensure_worker()

        async def refuse_cleanup(process: FakeProcess, _grace: float) -> None:
            assert process is first
            raise worker_module.AuthWorkerError

        monkeypatch.setattr(worker, "_process_group_terminator", refuse_cleanup)
        try:
            await worker.discard_session()
            assert worker._process is first
            with pytest.raises(worker_module.AuthWorkerError):
                await worker._ensure_worker()
            assert worker._process is first
            assert len(launcher.calls) == 1
        finally:
            monkeypatch.setattr(worker, "_process_group_terminator", terminator)
            await service.shutdown()
        assert worker._process is None

    asyncio.run(scenario())


def test_owned_process_group_reports_unconfirmed_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        process = FakeProcess()
        process.finish(0)
        signals: list[signal.Signals] = []
        monkeypatch.setattr(
            worker_module,
            "_send_process_group_signal",
            lambda target, value: signals.append(value),
        )
        monkeypatch.setattr(worker_module, "_process_group_exists", lambda _pid: True)
        with pytest.raises(worker_module.AuthWorkerError):
            await worker_module.terminate_owned_process_group(process, 0)
        assert signals == [signal.SIGTERM, signal.SIGKILL, signal.SIGKILL]

    asyncio.run(scenario())
