"""The active product boundary exposes and admits Weibo only."""

from fastapi.testclient import TestClient
from test_native_weibo_discovery import environment

from longtian_api.schemas.automation_workflows import AutomationTaskCreateRequest
from longtian_api.schemas.search_batches import SearchBatchCreate
from longtian_api.schemas.search_runs import SearchRunCreate


def test_platform_catalog_contains_only_weibo(tmp_path):
    app, browser = environment(tmp_path, [])
    with TestClient(app) as client:
        response = client.get("/api/v1/platform-connections")

    assert response.status_code == 200
    assert response.json()["platforms"]
    assert [item["platform"] for item in response.json()["platforms"]] == ["wb"]
    assert response.json()["platforms"][0]["availability"] == "enabled"
    assert browser.visits == []


def test_unsupported_connection_is_not_admitted(tmp_path):
    app, browser = environment(tmp_path, [])
    with TestClient(app) as client:
        response = client.post("/api/v1/platform-connections/xhs/attempts")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "platform_not_found"
    assert browser.visits == []


def test_unsupported_search_payload_is_rejected_before_collection(tmp_path):
    app, browser = environment(tmp_path, [])
    with TestClient(app) as client:
        single = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "xhs",
                "max_results_per_term": 1,
            },
        )
        batch = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb", "xhs"],
                "max_results_per_term": 1,
            },
        )

    assert single.status_code == 422
    assert batch.status_code == 422
    assert browser.visits == []


def test_collection_and_workflow_create_payloads_default_to_weibo():
    search = SearchRunCreate(monitoring_rule_id=1)
    batch = SearchBatchCreate(monitoring_rule_id=1)
    task = AutomationTaskCreateRequest.model_validate(
        {
            "name": "微博值守",
            "monitoring_rule_id": 1,
            "initial_prompt": {"mode": "default"},
            "report_prompt": {"mode": "default"},
            "schedule": {"kind": "interval", "interval_minutes": 10},
        }
    )

    assert search.platform == "wb"
    assert batch.platforms == ["wb"]
    assert task.platforms == ["wb"]
