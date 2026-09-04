"""One manual start owns stored-text understanding and the exact final report."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from initial_analysis_fixtures import UNDERSTANDING
from test_content_analysis_api import body, saved
from topic_report_fixtures import api_environment, finish

from longtian_api.repositories.analysis_shared import source_snapshot
from longtian_api.repositories.content_materials import ContentMaterialRepository
from longtian_api.services.enrichment_models import EnrichedContent


def generation_request(ids):
    return {
        "request_id": str(uuid4()),
        "configuration_revision": 1,
        "initial_prompt": {"mode": "default"},
        "report_prompt": {"mode": "default"},
        "selection": {"kind": "explicit", "result_ids": ids},
    }


def test_one_start_reuses_three_summaries_and_analyses_seven_saved_bodies(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=11)
    media.media = False
    model.answers["initial"] = [UNDERSTANDING] * 3 + ["invalid"] * 7
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        ids = list(range(1, 11))
        initial = client.post(
            "/api/v1/content-analysis-jobs",
            json=body(client, selection={"kind": "explicit", "result_ids": ids}),
        )
        assert initial.status_code == 202
        client.portal.call(finish, app.state.content_analysis_service)
        baseline = len(media.calls), model.counts["initial"]
        intent = generation_request(ids)
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 202, response.text
        generation_id = response.json()["id"]
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "completed", result
        assert result["analysis"]["counts"]["completed"] == 10
        assert result["analysis"]["counts"]["reused"] == 3
        assert len(media.calls) == baseline[0]
        assert model.counts["initial"] == baseline[1] + 7
        report_id = result["report"]["id"]
        sources = client.get(f"/api/v1/topic-reports/{report_id}/sources").json()
        assert [s["source"]["result_id"] for s in sources["items"]] == ids
        calls = model.counts.copy()
        assert client.post("/api/v1/report-generations", json=intent).json() == result
        assert (
            client.get(f"/api/v1/report-generations/{generation_id}").json() == result
        )
        assert model.counts == calls


def test_new_report_retries_each_failed_source_once_and_clears_eligibility(
    tmp_path,
):
    app, database, model, media = api_environment(tmp_path, count=2)
    save_body(database, 1)
    save_body(database, 2)
    model.answers["initial"] = ["invalid", UNDERSTANDING]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        first = client.post(
            "/api/v1/report-generations", json=generation_request([1, 2])
        )
        assert first.status_code == 202, first.text
        client.portal.call(finish, app.state.report_generation_service)
        first_result = client.get(
            f"/api/v1/report-generations/{first.json()['id']}"
        ).json()
        assert first_result["analysis"]["counts"]["failed"] == 1
        assert first_result["analysis"]["counts"]["completed"] == 1
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 0,
            "failed": 1,
            "active": 0,
        }

        model.answers["initial"] = [UNDERSTANDING]
        second_intent = generation_request([1, 2])
        second = client.post("/api/v1/report-generations", json=second_intent)
        assert second.status_code == 202, second.text
        client.portal.call(finish, app.state.report_generation_service)
        second_result = client.get(
            f"/api/v1/report-generations/{second.json()['id']}"
        ).json()
        assert second_result["analysis"]["counts"]["reused"] == 1
        assert second_result["analysis"]["counts"]["completed"] == 2
        assert second_result["analysis"]["counts"]["failed"] == 0
        assert model.counts["initial"] == 3
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 0,
            "failed": 0,
            "active": 0,
        }
        assert (
            client.post("/api/v1/report-generations", json=second_intent).json()
            == second_result
        )
        assert model.counts["initial"] == 3
        assert not media.calls


def test_url_only_without_stored_body_does_not_access_legacy_accounts(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert response.status_code == 202, response.text
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "empty", result
        assert result["analysis"]["counts"]["input_incomplete"] == 1
        items = client.get(
            f"/api/v1/content-analysis-jobs/{result['analysis']['id']}/items"
        ).json()
        assert items["items"][0]["error"]["code"] == "stored_content_unavailable"
        assert result["report"]["empty_reason"] == "no_ready_sources"
        assert not media.calls and not model.calls


def save_body(database, content_id=1):
    with database.connect() as connection:
        source, _ = source_snapshot(connection, content_id)
    ContentMaterialRepository(database).save(
        content_id,
        EnrichedContent(
            schema_version=1,
            platform=source.platform,
            content_id=source.platform_content_id,
            content_url=source.content_url,
            acquired_at=1788000000000,
            extractor_version=f"{source.platform}-enrichment-v1",
            status="ready",
            text={
                "title": "已保存标题",
                "body": "已保存的完整正文，描述街道积水。",
                "coverage": "complete",
            },
            detected_modalities=["text"],
            media_inventory_complete=True,
            assets=[],
            issues=[],
        ),
    )


def test_never_started_stored_body_runs_offline_and_freezes_selection(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=2)
    save_body(database)
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        intent = generation_request([1])
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 202
        generation_id = response.json()["id"]
        client.portal.call(asyncio.wait_for, model.entered.wait(), 2)
        running = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert running["status"] == "summarising"
        assert running["analysis"]["counts"]["analysing"] == 1
        assert running["report"] is None
        assert client.post("/api/v1/report-generations", json=intent).json() == running
        # A different saved source arrives after admission and must not join.
        save_body(database, 2)
        client.portal.call(model.gate.set)
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "completed"
        assert result["report"]["coverage"]["total"] == 1
        assert model.counts["initial"] == 1 and not media.calls


def test_restart_preserves_interrupted_selection_without_automatic_model_retry(
    tmp_path,
):
    app, database, model, media = api_environment(tmp_path, count=1)
    save_body(database)
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        intent = generation_request([1])
        response = client.post("/api/v1/report-generations", json=intent)
        assert response.status_code == 202
        generation_id = response.json()["id"]
        client.portal.call(asyncio.wait_for, model.entered.wait(), 2)
    baseline = model.counts.copy()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "interrupted"
        assert result["analysis"]["counts"]["interrupted"] == 1
        assert client.post("/api/v1/report-generations", json=intent).json() == result
        assert model.counts == baseline and not media.calls
