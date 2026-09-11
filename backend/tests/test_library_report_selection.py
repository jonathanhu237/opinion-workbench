"""Library eligibility is neither page membership nor discovery novelty."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from initial_analysis_fixtures import UNDERSTANDING
from summary_fixtures import seed_run
from test_content_analysis_api import body, saved
from test_report_generations import generation_request, save_body
from topic_report_fixtures import api_environment, finish


def test_full_library_selection_includes_previous_failures_across_old_batches(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=3)
    seed_run(database, 29, start=2000, rule_name="历史另一次采集")
    media.media = False
    model.answers["initial"] = ["invalid"] * 4 + [UNDERSTANDING, UNDERSTANDING]
    for identity in range(5, 33):
        save_body(database, identity)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert (
            client.post(
                "/api/v1/content-analysis-jobs",
                json=body(
                    client, selection={"kind": "explicit", "result_ids": [1, 2, 3, 4]}
                ),
            ).status_code
            == 202
        )
        client.portal.call(finish, app.state.content_analysis_service)
        assert (
            client.post(
                "/api/v1/content-analysis-jobs",
                json=body(client, selection={"kind": "retry", "result_ids": [2]}),
            ).status_code
            == 202
        )
        client.portal.call(finish, app.state.content_analysis_service)
        baseline = model.counts.copy(), len(media.calls)
        stats = client.get("/api/v1/report-generations/eligibility")
        assert stats.status_code == 200, stats.text
        assert stats.json() == {"pending": 31, "failed": 1, "active": 0}
        assert model.counts == baseline[0]
        intent = {
            **generation_request([1]),
            "selection": {"kind": "library_pending"},
        }
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 202, response.text
        expected = list(range(1, 33))
        assert response.json()["selection"]["result_ids"] == expected
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "completed", result
        assert result["report"]["coverage"]["total"] == len(expected)
        assert model.counts["initial"] == baseline[0]["initial"] + 29
        assert result["analysis"]["counts"]["reused"] == 3
        assert len(media.calls) == baseline[1]
        assert client.post("/api/v1/report-generations", json=intent).json() == result
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 0,
            "failed": 0,
            "active": 0,
        }


def test_empty_library_admission_is_explicit_and_creates_no_work(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        intent = {
            **generation_request([1]),
            "selection": {"kind": "library_pending"},
        }
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "no_eligible_contents"
        assert client.get("/api/v1/report-generations").json()["items"] == []
        assert not model.calls and not media.calls


def test_legacy_include_failed_flag_is_rejected_without_side_effects(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        intent = {
            **generation_request([1]),
            "selection": {"kind": "library_pending"},
            "include_failed": True,
        }
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 422
        assert client.get("/api/v1/report-generations").json()["items"] == []
        assert not model.calls and not media.calls


def test_library_selection_is_not_truncated_to_explicit_or_page_limits(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=0)
    for offset in range(0, 1001, 150):
        seed_run(database, min(150, 1001 - offset), start=1000 + offset)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        intent = {
            **generation_request([1]),
            "selection": {"kind": "library_pending"},
        }
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 202, response.text
        assert response.json()["selection"]["result_ids"] == list(range(1, 1002))
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "failed", result
        assert result["report"] is None
        assert not model.calls and not media.calls


def test_selection_preview_freezes_concrete_membership_without_creating_work(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=3)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations/selection-preview",
            json={"kind": "library"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "selection": {"kind": "explicit", "result_ids": [1, 2, 3]},
            "counts": {
                "total": 3,
                "pending": 3,
                "already_summarized": 0,
                "failed": 0,
                "active": 0,
            },
        }
        assert client.get("/api/v1/report-generations").json()["items"] == []
        assert not model.calls and not media.calls


def test_selection_preview_treats_legacy_completed_without_latest_attempt_as_pending(
    tmp_path,
):
    app, database, model, media = api_environment(tmp_path, count=1)
    with database.connect() as connection:
        connection.execute(
            """UPDATE content_analysis_claims
            SET legacy_state='legacy_completed', first_attempt_id=NULL,
                latest_attempt_id=NULL
            WHERE content_id=1"""
        )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations/selection-preview",
            json={"kind": "explicit", "result_ids": [1]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["counts"] == {
            "total": 1,
            "pending": 1,
            "already_summarized": 0,
            "failed": 0,
            "active": 0,
        }
        assert not model.calls and not media.calls


def test_named_manual_report_rejects_a_second_active_submission(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=2)
    save_body(database)
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        first = {**generation_request([1]), "name": "第一份报告"}
        created = client.post("/api/v1/report-generations", json=first)
        assert created.status_code == 202
        assert created.json()["name"] == "第一份报告"
        second = {**generation_request([2]), "name": "第二份报告"}
        response = client.post("/api/v1/report-generations", json=second)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "report_generation_active"
        assert len(client.get("/api/v1/report-generations").json()["items"]) == 1


@pytest.mark.parametrize("failed_report", [False, True])
@pytest.mark.parametrize("count", [9, 10])
def test_only_successful_report_citations_remove_library_members(
    tmp_path, failed_report, count
):
    app, database, model, _ = api_environment(tmp_path, count=count)
    for identity in range(1, count + 1):
        save_body(database, identity)
    # Exercise leaf and overview roots. The unrelated last source is selected
    # and summarized but must not count as included in the report.
    model.decisions[count] = "irrelevant"
    if failed_report:
        model.answers["leaf"] = ["invalid"] * 2
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations",
            json=generation_request(list(range(1, count + 1))),
        )
        assert created.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        report = client.get(f"/api/v1/report-generations/{created.json()['id']}").json()
        assert report["status"] == ("failed" if failed_report else "completed")
        expected = list(range(1, count + 1)) if failed_report else [count]
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": len(expected),
            "failed": 0,
            "active": 0,
        }
        preview = client.post(
            "/api/v1/report-generations/selection-preview", json={"kind": "library"}
        )
        assert preview.status_code == 200
        assert preview.json()["selection"]["result_ids"] == expected
        assert preview.json()["counts"]["already_summarized"] == len(expected)
        # Explicit selection of previously cited content remains available.
        assert (
            client.post(
                "/api/v1/report-generations/selection-preview",
                json={"kind": "explicit", "result_ids": [1]},
            ).status_code
            == 200
        )


def test_active_report_excludes_summarized_sources_until_cancelled(tmp_path):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database, 1)
    model.block_stage = "judgment"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert created.status_code == 202
        client.portal.call(asyncio.wait_for, model.entered.wait(), 5)
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 0,
            "failed": 0,
            "active": 1,
        }
        current = client.get(
            f"/api/v1/report-generations/{created.json()['id']}"
        ).json()
        cancelled = client.post(
            f"/api/v1/report-generations/{created.json()['id']}/cancel",
            json={"expected_revision": current["control_revision"]},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 1,
            "failed": 0,
            "active": 0,
        }
