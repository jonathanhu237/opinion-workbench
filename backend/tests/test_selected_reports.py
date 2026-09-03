"""Manual report selection is an exact, durable set across the content library."""

from uuid import uuid4

from fastapi.testclient import TestClient
from summary_fixtures import seed_run
from test_content_analysis_api import body, saved
from topic_report_fixtures import api_environment, finish


def selected_request(ids):
    return {
        "request_id": str(uuid4()),
        "configuration_revision": 1,
        "report_prompt": {"mode": "default"},
        "selection": {"kind": "explicit", "result_ids": ids},
    }


def test_selected_summaries_form_exact_report_without_reacquisition(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=3)
    seed_run(database, 2, start=2000, rule_name="另一批次")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert (
            client.post("/api/v1/content-analysis-jobs", json=body(client)).status_code
            == 202
        )
        client.portal.call(finish, app.state.content_analysis_service)
        baseline = model.counts["initial"], len(media.calls)
        intent = selected_request([2, 4])
        response = client.post("/api/v1/topic-reports", json=intent)
        assert response.status_code == 202, response.text
        report_id = response.json()["id"]
        client.portal.call(finish, app.state.topic_report_service)
        report = client.get(f"/api/v1/topic-reports/{report_id}").json()
        assert report["status"] == "completed"
        assert report["selection"] == intent["selection"]
        assert report["coverage"]["total"] == 2
        sources = client.get(f"/api/v1/topic-reports/{report_id}/sources").json()
        assert [item["source"]["result_id"] for item in sources["items"]] == [2, 4]
        assert (model.counts["initial"], len(media.calls)) == baseline
        assert model.counts["judgment"] == 2
        calls = model.counts.copy()
        replay = client.post("/api/v1/topic-reports", json=intent)
        assert replay.json() == report
        assert model.counts == calls


def test_selected_unanalysed_sources_remain_visible_without_hidden_model_calls(
    tmp_path,
):
    app, _, model, media = api_environment(tmp_path, count=3)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post("/api/v1/topic-reports", json=selected_request([3, 1]))
        assert response.status_code == 202
        report_id = response.json()["id"]
        client.portal.call(finish, app.state.topic_report_service)
        report = client.get(f"/api/v1/topic-reports/{report_id}").json()
        assert (report["status"], report["empty_reason"]) == (
            "empty",
            "no_ready_sources",
        )
        sources = client.get(f"/api/v1/topic-reports/{report_id}/sources").json()[
            "items"
        ]
        assert [item["source"]["result_id"] for item in sources] == [3, 1]
        assert [item["unavailable_reason"] for item in sources] == ["not_analysed"] * 2
        assert not model.calls and not media.calls


def test_missing_selection_is_rejected_atomically_without_a_partial_report(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post("/api/v1/topic-reports", json=selected_request([1, 99]))
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_report_selection"
        assert client.get("/api/v1/topic-reports").json()["reports"] == []
        assert not model.calls and not media.calls
