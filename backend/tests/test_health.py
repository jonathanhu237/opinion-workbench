from pathlib import Path

from fastapi.testclient import TestClient

from opinion_workbench_api.main import create_app
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService


def test_health_returns_stable_contract(tmp_path: Path) -> None:
    with TestClient(
        create_app(
            monitoring_rule_service_factory=lambda: MonitoringRuleService(
                database_path=tmp_path / "health.sqlite3"
            )
        )
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "opinion-workbench-api",
    }
