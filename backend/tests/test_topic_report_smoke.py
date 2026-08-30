"""Actual API acceptance fixture: passive reads, >100 evidence, report-only retry."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_content_analysis_api import body
from topic_report_fixtures import finish, interval_request
from topic_report_smoke import (
    COUNTERS_PATH,
    LEGACY_RESULT_ID,
    LEGACY_RUN_ID,
    LEGACY_SUMMARY_ID,
    UI_ORIGIN,
    ForbiddenCollectionWorker,
    create_smoke_app,
)

BASE_URL = "http://127.0.0.1:46082"
ZERO_COUNTERS = {
    "synthetic_collection_calls": 0,
    "synthetic_browser_calls": 0,
    "synthetic_media_calls": 0,
    "synthetic_initial_calls": 0,
    "synthetic_judgment_calls": 0,
    "synthetic_leaf_calls": 0,
    "synthetic_overview_calls": 0,
    "synthetic_composition_calls": 0,
    "synthetic_model_calls": 0,
    "legacy_generation_requests": 0,
}


def counters(client):
    response = client.get(COUNTERS_PATH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def settled_report(client, app, report_id):
    client.portal.call(finish, app.state.topic_report_service)
    response = client.get(f"/api/v1/topic-reports/{report_id}")
    assert response.status_code == 200, response.text
    return response.json()


def start_initial(client, app):
    response = client.post("/api/v1/content-analysis-jobs", json=body(client))
    assert response.status_code == 202, response.text
    assert response.json()["admitted_count"] == 103
    job_id = response.json()["job"]["id"]
    client.portal.call(finish, app.state.content_analysis_service)
    admitted = client.post(
        "/api/v1/topic-reports",
        json=interval_request(app.state.monitoring_rule_service.database).model_dump(),
    )
    assert admitted.status_code == 202, admitted.text
    client.portal.call(finish, app.state.topic_report_service)
    report = client.get(f"/api/v1/topic-reports/{admitted.json()['id']}").json()
    return job_id, report


def test_smoke_reads_exact_origin_and_legacy_history_start_no_operations():
    app = create_smoke_app()
    with TestClient(app, base_url=BASE_URL) as client:
        database_path = app.state.monitoring_rule_service.database.path
        assert database_path.is_file()
        response = client.get("/api/v1/results", headers={"Origin": UI_ORIGIN})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == UI_ORIGIN
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["total"] == 104
        assert response.json()["eligible_count"] == 103
        settings = client.get("/api/v1/analysis-settings").json()
        assert settings["automation"]["available"]
        assert not settings["automation"]["enabled"]
        assert client.get("/api/v1/content-analysis-jobs").json()["jobs"] == []
        assert client.get("/api/v1/topic-reports").json()["reports"] == []
        assert client.get("/api/v1/collection-schedules").status_code == 404
        assert client.get("/api/v1/automation-tasks").json()["tasks"] == []
        result = client.get(f"/api/v1/results/{LEGACY_RESULT_ID}").json()
        assert result["analysis_state"] == "legacy_completed"
        legacy = client.get(f"/api/v1/search-runs/{LEGACY_RUN_ID}/ai-summaries").json()[
            "summaries"
        ]
        assert len(legacy) == 1 and legacy[0]["id"] == LEGACY_SUMMARY_ID
        assert legacy[0]["status"] == "completed"
        assert legacy[0]["document"]["items"][0]["source_ids"] == [LEGACY_RESULT_ID]
        items = client.get(f"/api/v1/ai-summaries/{LEGACY_SUMMARY_ID}/items").json()
        assert items["items"][0]["source"]["source_run_id"] == LEGACY_RUN_ID
        assert items["items"][0]["input_status"] == "ready"
        for origin in ("http://127.0.0.1:46083", "http://localhost:46081"):
            untrusted = client.get("/api/v1/results", headers={"Origin": origin})
            assert "access-control-allow-origin" not in untrusted.headers
        assert counters(client) == ZERO_COUNTERS
    assert not database_path.exists()


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_smoke_cors_preflight_is_exact_and_passive(method):
    with TestClient(create_smoke_app(), base_url=BASE_URL) as client:
        headers = {
            "Origin": UI_ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        }
        response = client.options("/api/v1/topic-reports", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == UI_ORIGIN
        assert response.headers["access-control-allow-methods"] == "GET, POST, PUT"
        assert "access-control-allow-credentials" not in response.headers
        for override in (
            {"Origin": "https://untrusted.example"},
            {"Access-Control-Request-Method": "DELETE"},
            {"Access-Control-Request-Headers": "authorization"},
        ):
            assert (
                client.options(
                    "/api/v1/topic-reports", headers={**headers, **override}
                ).status_code
                == 400
            )
        assert counters(client) == ZERO_COUNTERS


def test_smoke_normal_handoff_cross_page_citations_and_report_only_override_retry():
    app = create_smoke_app()
    with TestClient(app, base_url=BASE_URL) as client:
        defaults = client.get("/api/v1/analysis-settings").json()
        later_page = client.get("/api/v1/results?limit=50&offset=100").json()
        assert len(later_page["items"]) == 4
        assert counters(client) == ZERO_COUNTERS
        job_id, original = start_initial(client, app)
        job = client.get(f"/api/v1/content-analysis-jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["counts"]["total"] == 103
        assert job["counts"]["completed"] == 101
        assert job["counts"]["input_incomplete"] == 2
        assert original["status"] == "completed"
        assert original["trigger"] == "interval"
        assert original["request_id"] is not None
        assert original["coverage"] == {
            "total": 104,
            "ready": 101,
            "unavailable": 3,
            "pending": 0,
            "judging": 0,
            "relevant": 96,
            "irrelevant": 3,
            "uncertain": 2,
            "failed": 0,
            "cancelled": 0,
            "interrupted": 0,
        }
        report_id = original["id"]
        sources = []
        for offset in (0, 50, 100):
            page = client.get(
                f"/api/v1/topic-reports/{report_id}/sources?limit=50&offset={offset}"
            ).json()
            assert page["total"] == 104
            sources.extend(page["items"])
        assert len(sources) == 104
        assert {item["source"]["source_run_id"] for item in sources} == {
            2,
            3,
            LEGACY_RUN_ID,
        }
        assert {item["source"]["result_id"] for item in sources} == set(range(1, 105))
        assert sources[-1]["position"] == 103
        assert sources[-1]["source"]["result_id"] == LEGACY_RESULT_ID
        analysed_source = next(
            item for item in sources if item["source"]["result_id"] == 103
        )
        initial = client.get(
            f"/api/v1/content-analyses/{analysed_source['initial_attempt_id']}"
        ).json()
        assert initial["status"] == "completed" and initial["output"] is not None
        leaves = []
        for offset in (0, 5, 10):
            page = client.get(
                f"/api/v1/topic-reports/{report_id}/sections?kind=leaf&limit=5&offset={offset}"
            ).json()
            assert page["total"] == 12
            leaves.extend(page["sections"])
        citations = {
            source_id
            for leaf in leaves
            for paragraph in leaf["document"]["items"]
            for source_id in paragraph["source_ids"]
        }
        assert citations == {
            item["source"]["result_id"]
            for item in sources
            if item["state"] == "relevant"
        }
        assert 103 in citations and LEGACY_RESULT_ID not in citations
        root = client.get(
            f"/api/v1/topic-reports/{report_id}/sections/{original['root_section_id']}"
        ).json()
        assert root["kind"] == "overview" and root["source_count"] == 96
        assert root["sources"] == [] and len(root["children"]) == 2
        baseline = counters(client)
        assert baseline == {
            **ZERO_COUNTERS,
            "synthetic_media_calls": 103,
            "synthetic_initial_calls": 101,
            "synthetic_judgment_calls": 101,
            "synthetic_leaf_calls": 12,
            "synthetic_overview_calls": 3,
            "synthetic_composition_calls": 15,
            "synthetic_model_calls": 217,
        }
        assert job["usage"]["attempted_requests"] == 101
        assert original["usage"]["judgment"]["attempted_requests"] == 101
        assert original["usage"]["composition"]["attempted_requests"] == 15
        assert client.get("/api/v1/analysis-settings").json() == defaults
        assert counters(client) == baseline

        override = "验收：失败一次。仅根据本次保存文本生成报告，保留不确定性。"
        intent = {
            "request_id": str(uuid4()),
            "expected_revision": original["revision"],
            "configuration_revision": original["configuration_revision"],
            "instructions_override": override,
        }
        response = client.post(f"/api/v1/topic-reports/{report_id}/retry", json=intent)
        assert response.status_code == 202, response.text
        failed = settled_report(client, app, response.json()["id"])
        assert failed["status"] == "failed"
        assert failed["error"]["stage"] == "composition"
        assert failed["error"]["code"] == "internal_error"
        failed_leaf = client.get(
            f"/api/v1/topic-reports/{failed['id']}/sections?kind=leaf&limit=1"
        ).json()["sections"][0]
        assert failed_leaf["status"] == "failed"
        assert failed_leaf["error"]["code"] == "invalid_citations"
        assert failed["prompt"]["origin"] == "override"
        assert failed["prompt"]["instructions"] == override
        assert failed["coverage"] == original["coverage"]
        failed_calls = counters(client)
        assert failed_calls == {
            **baseline,
            "synthetic_judgment_calls": 202,
            "synthetic_leaf_calls": 24,
            "synthetic_composition_calls": 27,
            "synthetic_model_calls": 330,
        }
        replay = client.post(f"/api/v1/topic-reports/{report_id}/retry", json=intent)
        assert replay.status_code == 202 and replay.json() == failed
        assert counters(client) == failed_calls

        response = client.post(
            f"/api/v1/topic-reports/{failed['id']}/retry",
            json={
                "request_id": str(uuid4()),
                "expected_revision": failed["revision"],
                "configuration_revision": failed["configuration_revision"],
                "instructions_override": None,
            },
        )
        assert response.status_code == 202, response.text
        retried = settled_report(client, app, response.json()["id"])
        assert retried["status"] == "completed"
        assert retried["prompt"] == failed["prompt"]
        assert retried["coverage"] == original["coverage"]
        assert retried["usage"]["judgment"]["attempted_requests"] == 0
        assert retried["usage"]["composition"]["attempted_requests"] == 4
        assert retried["nodes"]["judgments"]["reused"] == 101
        assert retried["nodes"]["composition"]["reused"] == 11
        after = counters(client)
        assert after == {
            **failed_calls,
            "synthetic_leaf_calls": 25,
            "synthetic_overview_calls": 6,
            "synthetic_composition_calls": 31,
            "synthetic_model_calls": 334,
        }
        assert client.get("/api/v1/analysis-settings").json() == defaults
        assert client.get(f"/api/v1/topic-reports/{report_id}").json() == original
        assert client.get(f"/api/v1/topic-reports/{failed['id']}").json() == failed
        assert len(client.get("/api/v1/content-analysis-jobs").json()["jobs"]) == 1
        history = client.get("/api/v1/topic-reports").json()
        assert len(history["reports"]) == 3
        assert sum(item["trigger"] == "interval" for item in history["reports"]) == 1
        assert counters(client) == after


def test_smoke_counts_rejected_legacy_generation_requests_without_work():
    with TestClient(create_smoke_app(), base_url=BASE_URL) as client:
        response = client.post(
            f"/api/v1/search-runs/{LEGACY_RUN_ID}/ai-summaries",
            headers={"Origin": "https://untrusted.example"},
            json={},
        )
        assert response.status_code == 403
        assert counters(client) == {**ZERO_COUNTERS, "legacy_generation_requests": 1}


def test_smoke_collection_worker_is_counted_and_fail_closed():
    import asyncio

    worker = ForbiddenCollectionWorker()
    with pytest.raises(AssertionError, match="forbids collection"):
        asyncio.run(worker.search())
    assert worker.collection_calls == 1
    with pytest.raises(AssertionError, match="forbids browser opening"):
        asyncio.run(worker.open_result())
    assert worker.browser_calls == 1
