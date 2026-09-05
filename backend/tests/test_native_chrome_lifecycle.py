"""Product entrypoint with fake OS/browser SDK only; real adapter and database."""

import asyncio
import os
import socket

import pytest
from fastapi.testclient import TestClient
from test_native_weibo_discovery import CARD
from test_search_runs import _wait_for_terminal

from longtian_api.main import create_app
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.native_chrome import ManagedChrome
from longtian_api.services.native_weibo import NativeWeiboCollector
from longtian_api.services.platform_connections import PlatformConnectionService


@pytest.mark.parametrize("alive", [False, True])
def test_local_chrome_lock_recovery_requires_dead_owner(tmp_path, monkeypatch, alive):
    profile = tmp_path / "runtime/browser/managed-chrome"
    profile.mkdir(parents=True, mode=0o700)
    lock = profile / "SingletonLock"
    lock.symlink_to(f"{socket.gethostname()}-12345")
    browser = ManagedChrome(profile=profile)

    def probe(pid, signal):
        assert (pid, signal) == (12345, 0)
        if not alive:
            raise ProcessLookupError()

    monkeypatch.setattr(os, "kill", probe)
    from longtian_api.services.native_browser_contracts import BrowserUnavailable

    if alive:
        with pytest.raises(BrowserUnavailable):
            browser._prepare_profile()
    else:
        browser._prepare_profile()
        os.close(browser._lease)
        browser._lease = None
    assert lock.is_symlink() == alive


def test_stale_cleanup_removes_only_links_and_retains_login_files(
    tmp_path, monkeypatch
):
    profile = tmp_path / "runtime/browser/managed-chrome"
    profile.mkdir(parents=True, mode=0o700)
    (profile / "SingletonLock").symlink_to(f"{socket.gethostname()}-12345")
    (profile / "SingletonCookie").symlink_to("cookie-marker")
    (profile / "SingletonSocket").symlink_to("/tmp/longtian-test-nonexistent-socket")
    marker = profile / "Login Data"
    marker.write_text("retained-fixture")

    def dead(pid, signal):
        raise ProcessLookupError()

    monkeypatch.setattr(os, "kill", dead)
    browser = ManagedChrome(profile=profile)
    browser._prepare_profile()
    os.close(browser._lease)
    browser._lease = None
    assert not any(
        os.path.lexists(profile / name)
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket")
    )
    assert marker.read_text() == "retained-fixture"
    assert (profile / ".longtian-browser-owner.lock").is_file()


def test_live_socket_blocks_cleanup_even_if_lock_pid_is_dead(tmp_path, monkeypatch):
    from longtian_api.services.native_browser_contracts import BrowserUnavailable

    profile = tmp_path / "runtime/browser/managed-chrome"
    profile.mkdir(parents=True, mode=0o700)
    lock = profile / "SingletonLock"
    lock.symlink_to(f"{socket.gethostname()}-12345")
    (profile / "SingletonSocket").symlink_to("synthetic-socket")

    def dead(pid, signal):
        raise ProcessLookupError()

    class LiveSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def connect(self, path):
            pass

    monkeypatch.setattr(os, "kill", dead)
    monkeypatch.setattr(socket, "socket", lambda *args: LiveSocket())
    with pytest.raises(BrowserUnavailable):
        ManagedChrome(profile=profile)._prepare_profile()
    assert lock.is_symlink()


def test_native_browser_refuses_daily_profile_without_starting_a_process(tmp_path):
    launched = []

    async def launch(*args, **kwargs):
        launched.append(args)
        raise AssertionError("daily browser must not be launched")

    browser = ManagedChrome(profile=tmp_path / "Chrome" / "Default", launcher=launch)
    runtime = NativeWeiboCollector(browser=browser)
    app = create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            collector_factory=lambda **kwargs: runtime
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
            },
        )
        run = _wait_for_terminal(client, created.json()["id"])
        assert run["status"] == "browser_unavailable"
        assert not launched
        assert str(tmp_path) not in str(run)


class ChromeSDK:
    """Simulate the external Chrome/CDP protocol, never the product's parser."""

    def __init__(self, profile):
        self.profile = profile
        self.launches = []
        self.approved = []
        self.denied = []
        self.events = {}
        self.url = "about:blank"
        self.returncode = None
        self.page_closed = False
        self.stopped = False
        self.extra_url = None
        self.contexts = [self]
        self.chromium = self

    async def launch(self, *args, **kwargs):
        self.launches.append((args, kwargs))
        (self.profile / "DevToolsActivePort").write_text(
            "19499\n/devtools/browser/fixture-id\n"
        )
        return self

    async def start(self):
        return self

    async def stop(self):
        self.stopped = True

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def is_connected(self):
        return not self.stopped

    def is_closed(self):
        return self.page_closed

    async def close(self):
        self.page_closed = True

    async def bring_to_front(self):
        pass

    def set_default_timeout(self, value):
        pass

    def on(self, event, handler):
        self.events[event] = handler

    async def connect_over_cdp(self, url, **options):
        assert url == "ws://127.0.0.1:19499/devtools/browser/fixture-id"
        assert options["no_defaults"] is True
        return self

    async def new_page(self):
        return self

    async def new_cdp_session(self, page):
        return self

    async def route_web_socket(self, *args):
        pass

    async def send(self, method, params=None):
        if method == "Fetch.continueRequest":
            self.approved.append(params["requestId"])
        if method == "Fetch.failRequest":
            self.denied.append(params["requestId"])

    async def goto(self, url, **kwargs):
        self.url = url
        for suffix in ("document", "image-1", "image-2"):
            self.events["Fetch.requestPaused"](
                {
                    "requestId": url + ":" + suffix,
                    "request": {"url": url},
                }
            )
        if self.extra_url:
            self.events["Fetch.requestPaused"](
                {
                    "requestId": "out-of-scope",
                    "request": {"url": self.extra_url},
                }
            )
        await asyncio.sleep(0)

    async def content(self):
        await asyncio.sleep(0)
        return CARD


@pytest.mark.parametrize("fault", ["driver_stop", "close_timeout", "process_exit"])
def test_shutdown_settles_owned_process_even_when_sdk_cleanup_fails(tmp_path, fault):
    async def run():
        profile = tmp_path / "runtime/browser/managed-chrome"
        profile.mkdir(parents=True, mode=0o700)
        sdk = ChromeSDK(profile)
        browser = ManagedChrome(
            profile=profile,
            launcher=sdk.launch,
            playwright_factory=lambda: sdk,
            control_timeout_seconds=0.02,
        )
        await browser.start(max_requests=5)
        if fault == "driver_stop":

            async def fail():
                raise RuntimeError("fixture driver failed")

            sdk.stop = fail
        elif fault == "close_timeout":

            async def hang():
                await asyncio.Event().wait()

            sdk.close = hang
        else:

            def exited():
                sdk.returncode = 0
                raise ProcessLookupError()

            sdk.terminate = exited
        await asyncio.wait_for(browser.shutdown(), 1)
        assert sdk.returncode is not None
        assert browser._lease is None and not browser.available

    asyncio.run(run())


def test_browser_request_budget_preserves_first_page_and_owns_only_dedicated_process(
    tmp_path,
):
    profile = tmp_path / "runtime/browser/managed-chrome"
    profile.mkdir(parents=True, mode=0o700)
    marker = profile / "keep-login-fixture"
    marker.write_text("synthetic marker, not a real session")
    chrome = ChromeSDK(profile)
    browser = ManagedChrome(
        profile=profile, launcher=chrome.launch, playwright_factory=lambda: chrome
    )
    runtime = NativeWeiboCollector(browser=browser, delay_seconds=0, max_requests=4)
    app = create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            collector_factory=lambda **kwargs: runtime
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
                "max_results_per_term": 1,
            },
        )
        run = _wait_for_terminal(client, created.json()["id"])
        assert (run["status"], run["execution_limit"], run["new_count"]) == (
            "timed_out",
            "requests",
            1,
        )
        assert len(chrome.approved) == 4
        assert len(chrome.denied) == 2
    assert marker.read_text() == "synthetic marker, not a real session"
    assert chrome.returncode == 0 and chrome.stopped
    assert len(chrome.launches) == 1
    args, options = chrome.launches[0]
    assert f"--user-data-dir={profile}" in args
    assert "--remote-debugging-address=127.0.0.1" in args
    assert "--no-startup-window" in args
    assert not any("headless" in arg or "AutomationControlled" in arg for arg in args)


@pytest.mark.parametrize("obstacle", ["symlink", "non_private", "owned"])
def test_unsafe_or_already_owned_profile_is_not_repaired_or_launched(
    tmp_path, obstacle
):
    profile = tmp_path / "runtime/browser/managed-chrome"
    profile.mkdir(parents=True, mode=0o700)
    marker = profile / "user-marker"
    marker.write_text("retain")
    if obstacle == "non_private":
        profile.chmod(0o755)
    if obstacle == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path / "runtime", target_is_directory=True)
        profile = alias / "browser/managed-chrome"
    if obstacle == "owned":
        (profile / "SingletonLock").symlink_to("fixture-pid-12345")
    chrome = ChromeSDK(profile)
    browser = ManagedChrome(profile=profile, launcher=chrome.launch)
    runtime = NativeWeiboCollector(browser=browser)
    app = create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            collector_factory=lambda **kwargs: runtime
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-runs", json={"monitoring_rule_id": 1, "platform": "wb"}
        )
        assert (
            _wait_for_terminal(client, response.json()["id"])["status"]
            == "browser_unavailable"
        )
    assert not chrome.launches
    assert marker.read_text() == "retain"


def test_legacy_collector_backend_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("LONGTIAN_COLLECTOR_BACKEND", "legacy")
    with pytest.raises(ValueError, match="Only the native Weibo collector"):
        PlatformConnectionService(
            browser_profile_dir=tmp_path / "runtime" / "browser" / "managed-chrome"
        )


@pytest.mark.parametrize(
    "external",
    [
        "https://www.xiaohongshu.com/explore/123",
        "http://127.0.0.1:8000/api/v1/results",
        "https://weibo.com.attacker.invalid/",
    ],
)
def test_native_page_cannot_issue_requests_outside_the_reviewed_weibo_hosts(
    tmp_path, external
):
    profile = tmp_path / "runtime/browser/managed-chrome"
    chrome = ChromeSDK(profile)
    chrome.extra_url = external
    browser = ManagedChrome(
        profile=profile, launcher=chrome.launch, playwright_factory=lambda: chrome
    )
    runtime = NativeWeiboCollector(browser=browser, delay_seconds=0, max_pages=1)
    app = create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            collector_factory=lambda **kwargs: runtime
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
                "max_results_per_term": 1,
            },
        )
        _wait_for_terminal(client, created.json()["id"])
    assert "out-of-scope" not in chrome.approved
    assert "out-of-scope" in chrome.denied
