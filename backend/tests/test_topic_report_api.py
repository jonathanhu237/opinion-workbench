"""Real HTTP contract: no polling admissions, bounded history and explicit intent."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_content_analysis_api import body, saved
from topic_report_fixtures import api_environment, finish, interval_request

from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS
from longtian_api.services.analysis_errors import ERRORS as ANALYSIS_ERRORS
from longtian_api.services.topic_report_errors import ERRORS


def assert_error(response, code):
    status, message = {**AI_ERROR_CONTRACTS, **ANALYSIS_ERRORS, **ERRORS}[code]
    assert response.status_code == status, response.text
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert response.headers["cache-control"] == "no-store"


def initial_report(client, app):
    admitted = client.post("/api/v1/content-analysis-jobs", json=body(client))
    assert admitted.status_code == 202, admitted.text
    job_id = admitted.json()["job"]["id"]
    client.portal.call(finish, app.state.content_analysis_service)
    client.portal.call(finish, app.state.topic_report_service)
    reports = client.get(f"/api/v1/topic-reports?initial_job_id={job_id}")
    assert reports.status_code == 200, reports.text
    return reports.json()["reports"][0]


def test_auto_report_selection_frozen_pages_and_new_version_ids(tmp_path):
    app, db, model, media = api_environment(tmp_path, count=10)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        settings = client.get("/api/v1/analysis-settings").json()
        assert (
            settings["automation"]["available"]
            and not settings["automation"]["enabled"]
        )
        assert client.get("/api/v1/topic-reports").json() == {
            "reports": [],
            "next_before_id": None,
        }
        assert not model.calls and not media.calls
        original = initial_report(client, app)
        assert original["status"] == "completed"
        report_id = original["id"]
        sources = client.get(
            f"/api/v1/topic-reports/{report_id}/sources?limit=1&offset=9"
        ).json()
        assert sources["total"] == 10 and sources["items"][0]["position"] == 9
        root = client.get(
            f"/api/v1/topic-reports/{report_id}/sections/{original['root_section_id']}"
        ).json()
        assert root["kind"] == "overview" and root["source_count"] == 10
        assert root["sources"] == [] and len(root["children"]) == 2
        leaf = client.get(
            f"/api/v1/topic-reports/{report_id}/sections?kind=leaf&limit=1&offset=1"
        ).json()
        assert leaf["total"] == 2 and len(leaf["sections"]) == 1
        assert leaf["sections"][0]["position"] == 1
        baseline = model.counts.copy(), len(media.calls)
        payload = {
            "request_id": str(uuid4()),
            "expected_revision": original["revision"],
            "configuration_revision": 1,
            "instructions_override": None,
        }
        response = client.post(f"/api/v1/topic-reports/{report_id}/retry", json=payload)
        assert response.status_code == 202, response.text
        retry_id = response.json()["id"]
        client.portal.call(finish, app.state.topic_report_service)
        retry = client.get(f"/api/v1/topic-reports/{retry_id}").json()
        assert (
            retry["status"] == "completed"
            and retry["usage"]["total"]["attempted_requests"] == 0
        )
        assert (model.counts, len(media.calls)) == baseline
        assert_error(
            client.get(f"/api/v1/topic-reports/{retry_id}/sections/{root['id']}"),
            "topic_report_section_not_found",
        )
        latest = client.get(
            f"/api/v1/topic-reports?initial_job_id={original['initial_job_id']}&limit=1"
        ).json()
        assert (
            latest["reports"][0]["id"] == retry_id
            and latest["next_before_id"] == retry_id
        )
        older = client.get(
            f"/api/v1/topic-reports?before_id={retry_id}&result_id=10"
        ).json()
        assert [item["id"] for item in older["reports"]] == [report_id]
        replay = client.post(f"/api/v1/topic-reports/{report_id}/retry", json=payload)
        assert replay.status_code == 202 and replay.json() == retry
        assert_error(
            client.post(
                f"/api/v1/topic-reports/{report_id}/retry",
                json={**payload, "instructions_override": "changed"},
            ),
            "topic_report_request_conflict",
        )
        assert_error(
            client.post(
                f"/api/v1/topic-reports/{report_id}/cancel",
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": original["revision"],
                },
            ),
            "topic_report_not_active",
        )


@pytest.mark.parametrize(
    "override",
    [
        {"unknown": 1},
        {"configuration_revision": True},
        {"request_id": "not-uuid"},
        {"report_prompt_version_id": 0},
        {"selection": {"kind": "initial_job", "job_id": 1}},
        {
            "selection": {
                "kind": "first_seen_interval",
                "first_seen_from": "2026-01-01",
                "first_seen_to": "2027-01-01",
            }
        },
    ],
)
def test_invalid_http_intents_have_no_work(tmp_path, override):
    app, db, model, media = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        payload = interval_request(db).model_dump()
        assert_error(
            client.post("/api/v1/topic-reports", json={**payload, **override}),
            "invalid_request",
        )
        assert not model.calls and not media.calls
        assert client.get("/api/v1/topic-reports").json()["reports"] == []


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "offset=9007199254740992"]
)
def test_invalid_history_pagination_is_strict(tmp_path, query):
    app, _, model, _ = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert_error(
            client.get(f"/api/v1/topic-reports/1/sources?{query}"), "invalid_request"
        )
        assert not model.calls


@pytest.mark.parametrize("text", ["", " ", "a" * 8001, "x\x00y", "\ud800"])
def test_invalid_one_off_override_is_not_saved_or_admitted(tmp_path, text):
    import json

    app, db, model, _ = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        payload = interval_request(db).model_dump()
        payload["instructions_override"] = text
        response = client.post(
            "/api/v1/topic-reports",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert_error(response, "invalid_analysis_prompt")
        assert not model.calls


def test_interval_empty_override_defaults_and_replay_precedes_config(tmp_path):
    app, db, model, _ = api_environment(tmp_path, count=0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        settings = client.get("/api/v1/analysis-settings").json()
        payload = interval_request(
            db, instructions_override="  单次范围  "
        ).model_dump()
        response = client.post("/api/v1/topic-reports", json=payload)
        assert response.status_code == 202, response.text
        report_id = response.json()["id"]
        client.portal.call(finish, app.state.topic_report_service)
        report = client.get(f"/api/v1/topic-reports/{report_id}").json()
        assert (
            report["status"] == "empty" and report["empty_reason"] == "no_ready_sources"
        )
        assert (
            report["prompt"]["instructions"] == "  单次范围  "
            and report["prompt"]["version_id"] is None
        )
        assert client.get("/api/v1/analysis-settings").json() == settings
        # Replay remains readable even while the service is closed or unavailable.
        app.state.topic_report_service.available = False
        replay = client.post("/api/v1/topic-reports", json=payload)
        assert replay.status_code == 202 and replay.json() == report
        assert_error(
            client.post(
                "/api/v1/topic-reports", json={**payload, "request_id": str(uuid4())}
            ),
            "topic_report_unavailable",
        )
        assert not model.calls


@pytest.mark.parametrize("field", ["first_seen_from", "first_seen_to"])
def test_interval_rejects_sub_microsecond_precision_without_admission(tmp_path, field):
    app, db, model, media = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        payload = interval_request(db).model_dump()
        payload["selection"][field] = "2026-08-29T00:00:00.1234567Z"
        assert_error(
            client.post("/api/v1/topic-reports", json=payload), "invalid_request"
        )
        assert client.get("/api/v1/topic-reports").json()["reports"] == []
        assert not model.calls and not media.calls


def test_active_revision_cancel_and_retry_contracts(tmp_path):
    app, _, model, _ = api_environment(tmp_path, count=1)
    model.block_stage = "judgment"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admission = client.post("/api/v1/content-analysis-jobs", json=body(client))
        client.portal.call(finish, app.state.content_analysis_service)
        client.portal.call(model.entered.wait)
        report = client.get("/api/v1/topic-reports").json()["reports"][0]
        assert report["initial_job_id"] == admission.json()["job"]["id"]
        report_id = report["id"]
        assert_error(
            client.post(
                f"/api/v1/topic-reports/{report_id}/retry",
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": report["revision"],
                    "configuration_revision": 1,
                    "instructions_override": None,
                },
            ),
            "topic_report_not_terminal",
        )
        assert_error(
            client.post(
                f"/api/v1/topic-reports/{report_id}/cancel",
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": report["revision"] + 1,
                },
            ),
            "topic_report_changed",
        )
        intent = {"request_id": str(uuid4()), "expected_revision": report["revision"]}
        response = client.post(f"/api/v1/topic-reports/{report_id}/cancel", json=intent)
        assert response.status_code == 200 and response.json()["status"] == "cancelled"
        assert response.json()["coverage"]["judging"] == 0
        assert (
            client.post(f"/api/v1/topic-reports/{report_id}/cancel", json=intent).json()
            == response.json()
        )


def test_interval_semantics_prompt_cas_and_storage_errors(tmp_path, monkeypatch):
    app, db, model, _ = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert_error(client.get("/api/v1/topic-reports/1"), "topic_report_not_found")
        payload = interval_request(db).model_dump()
        payload["selection"]["first_seen_to"] = payload["selection"]["first_seen_from"]
        assert_error(
            client.post("/api/v1/topic-reports", json=payload),
            "invalid_report_interval",
        )
        payload = interval_request(db).model_dump()
        payload["report_prompt_version_id"] += 100
        assert_error(
            client.post("/api/v1/topic-reports", json=payload),
            "analysis_prompt_changed",
        )
        assert not model.calls

        def broken(_id):
            raise RuntimeError("private sentinel SQL /secret.sqlite3 raw source")

        monkeypatch.setattr(app.state.topic_report_service.repository, "read", broken)
        response = client.get("/api/v1/topic-reports/1")
        assert_error(response, "topic_report_storage_unavailable")
        assert "sentinel" not in response.text and "sqlite3" not in response.text


def test_real_lifespan_stops_scheduler_then_all_owners_after_report_failure(tmp_path):
    app, _, _, _ = api_environment(tmp_path, count=0)
    names = [
        "collection_schedule_service",
        "content_analysis_service",
        "topic_report_service",
        "ai_summary_service",
        "content_enrichment_service",
        "ai_settings_service",
        "search_batch_service",
        "search_run_service",
        "platform_connection_service",
    ]
    observed = []
    with pytest.raises(RuntimeError, match="synthetic report cleanup failure"):
        with TestClient(app, base_url="http://127.0.0.1"):
            for name in names:
                owner = getattr(app.state, name)
                original = owner.shutdown

                async def shutdown(name=name, original=original):
                    observed.append(name)
                    await original()
                    if name == "topic_report_service":
                        raise RuntimeError("synthetic report cleanup failure")

                owner.shutdown = shutdown
    assert observed == names
