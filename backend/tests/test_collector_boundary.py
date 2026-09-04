"""The application accepts a project-owned collection runtime, without a subprocess."""

from fastapi.testclient import TestClient
from test_search_runs import FakeSearchWorker, _wait_for_terminal

from longtian_api.main import create_app
from longtian_api.services.collector_contracts import AuthWorkerResult
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService


class LocalRuntime(FakeSearchWorker):
    browser_session_available = True

    def __init__(self):
        super().__init__()
        self.checks = []
        self.closed = False

    def configure_media_spool(self, root):
        self.spool = root

    async def check(self, *, request_id, platform):
        self.checks.append(platform)
        return AuthWorkerResult("connected", "none")

    async def shutdown(self):
        self.closed = True


def test_replaceable_runtime_search_persists_without_legacy_worker(tmp_path):
    runtime = LocalRuntime()
    service = PlatformConnectionService(collector_factory=lambda **kwargs: runtime)
    app = create_app(
        platform_connection_service_factory=lambda: service,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/platform-connections").status_code == 200
        assert runtime.calls == []
        assert runtime.checks == []
        started = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "wb", "max_results_per_term": 3},
        )
        assert started.status_code == 202
        run_id = started.json()["id"]
        assert _wait_for_terminal(client, run_id)["status"] == "completed_with_results"
        results = client.get(f"/api/v1/search-runs/{run_id}/results").json()
        assert results["total"] == 1
        assert (
            results["results"][0]["content_url"]
            == "https://m.weibo.cn/detail/5012345678901234"
        )
        for _ in range(2):
            assert client.get(f"/api/v1/search-runs/{run_id}").status_code == 200
        assert len(runtime.calls) == 1
        assert runtime.checks == []
    assert runtime.closed


def test_replacement_login_barrier_never_falls_back_to_legacy(tmp_path):
    runtime = LocalRuntime()
    runtime.outcome = "login_required"
    runtime.emit_item = False
    service = PlatformConnectionService(collector_factory=lambda **kwargs: runtime)
    app = create_app(
        platform_connection_service_factory=lambda: service,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-runs", json={"monitoring_rule_id": 1, "platform": "wb"}
        )
        run_id = response.json()["id"]
        assert _wait_for_terminal(client, run_id)["status"] == "login_required"
        assert (
            client.get(f"/api/v1/search-runs/{run_id}").json()["status"]
            == "login_required"
        )
        assert len(runtime.calls) == 1
        assert runtime.checks == []
