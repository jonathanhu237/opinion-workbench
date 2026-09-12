import asyncio
import socket
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from opinion_workbench_api import launcher as launcher_module
from opinion_workbench_api.launcher import LauncherConfig, LaunchError, LocalApplication
from opinion_workbench_api.main import create_app
from opinion_workbench_api.services.application_lifecycle import ApplicationLifecycle
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService


def test_empty_page_shutdown_waits_for_grace_and_refresh_keeps_process_alive():
    async def scenario():
        expired = asyncio.Event()
        lifecycle = ApplicationLifecycle(
            enabled=True,
            grace_seconds=0.03,
            on_expired=expired.set,
        )
        first = await lifecycle.register()
        await lifecycle.release(first)
        second = await lifecycle.register()
        await asyncio.sleep(0.05)
        assert not expired.is_set()
        assert await lifecycle.heartbeat(second)
        await lifecycle.release(second)
        await asyncio.wait_for(expired.wait(), 1)
        await lifecycle.shutdown()

    asyncio.run(scenario())


def test_multiple_pages_only_expire_after_the_last_page_releases():
    async def scenario():
        expired = asyncio.Event()
        lifecycle = ApplicationLifecycle(
            enabled=True,
            grace_seconds=0.02,
            on_expired=expired.set,
        )
        first = await lifecycle.register()
        second = await lifecycle.register()
        await lifecycle.release(first)
        await asyncio.sleep(0.04)
        assert not expired.is_set()
        await lifecycle.release(second)
        await asyncio.wait_for(expired.wait(), 1)
        assert lifecycle.active_count == 0
        await lifecycle.shutdown()

    asyncio.run(scenario())


def test_packaged_entry_serves_static_api_and_requires_local_same_origin(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>OpinionWorkbench</title>")
    (static / "assets").mkdir()
    app = create_app(
        static_dir=static,
        packaged=True,
        lifecycle_enabled=True,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "app.sqlite3"
        ),
    )

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/v1/does-not-exist").status_code == 404
        assert client.get("/assets/does-not-exist.js").status_code == 404

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/v1/lifecycle/ws",
                headers={
                    "host": "127.0.0.1:8765",
                    "origin": "https://example.com",
                },
            ):
                pass

        headers = {
            "host": "127.0.0.1:8765",
            "origin": "http://127.0.0.1:8765",
        }
        with client.websocket_connect("/api/v1/lifecycle/ws", headers=headers) as first:
            assert first.receive_json()["type"] == "ready"
            with client.websocket_connect(
                "/api/v1/lifecycle/ws", headers=headers
            ) as second:
                assert second.receive_json()["type"] == "ready"
                first.close()
                second.send_json({"type": "heartbeat"})
                assert second.receive_json() == {"type": "heartbeat", "ok": True}


def test_packaged_startup_does_not_resume_automation_runs(tmp_path):
    class StartupSpy:
        def __init__(self):
            self.resume_arguments = []

        def initialize(self):
            pass

        async def start(self, *, resume_active_runs):
            self.resume_arguments.append(resume_active_runs)

        async def shutdown(self):
            pass

    spy = StartupSpy()
    app = create_app(
        packaged=True,
        lifecycle_enabled=False,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "app.sqlite3"
        ),
        automation_workflow_service_factory=lambda _database: spy,
        automation_resume_on_startup=False,
    )
    with TestClient(app):
        assert spy.resume_arguments == [False]


def test_launcher_reports_a_real_occupied_port(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    messages = []
    monkeypatch.setattr(launcher_module, "_show_launch_error", messages.append)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        local = LocalApplication(
            LauncherConfig(
                port=port,
                open_browser=False,
                data_root=tmp_path / "data",
                static_dir=static,
            )
        )

        assert local.run() == 1

    assert messages == ["本地服务无法占用指定端口，请关闭占用该端口的程序后重试。"]
    assert not local.paths.server_record_path.exists()


def test_launcher_cleans_server_when_browser_never_reaches_first_page(
    tmp_path, monkeypatch
):
    class FakeServer:
        instances = []

        def __init__(self, _config):
            self.should_exit = False
            self.__class__.instances.append(self)

        async def serve(self, _sockets=None):
            while not self.should_exit:
                await asyncio.sleep(0)

    fake_uvicorn = SimpleNamespace(
        Config=lambda *_args, **_kwargs: object(),
        Server=FakeServer,
    )
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    application = SimpleNamespace(
        state=SimpleNamespace(
            application_lifecycle=SimpleNamespace(
                wait_for_first_page=lambda _timeout: asyncio.sleep(0, result=False)
            )
        )
    )
    monkeypatch.setattr(launcher_module, "create_app", lambda **_kwargs: application)
    monkeypatch.setattr(
        launcher_module.webbrowser, "open", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(launcher_module, "STARTUP_PAGE_TIMEOUT_SECONDS", 0.01)

    local = LocalApplication(
        LauncherConfig(
            open_browser=True,
            data_root=tmp_path / "data",
            static_dir=static,
        )
    )
    monkeypatch.setattr(local, "_ready", lambda _host, _port: True)

    async def run():
        with pytest.raises(LaunchError, match="未能打开系统页面"):
            await local.run_async()

    asyncio.run(run())
    assert FakeServer.instances[-1].should_exit is True
    assert not local.paths.server_record_path.exists()
