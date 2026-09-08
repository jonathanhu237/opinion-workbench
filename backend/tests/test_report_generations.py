"""One manual start owns stored-text understanding and the exact final report."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from initial_analysis_fixtures import UNDERSTANDING
from test_content_analysis_api import body, saved
from topic_report_fixtures import api_environment, finish

from longtian_api.repositories.analysis_shared import source_snapshot
from longtian_api.repositories.content_materials import ContentMaterialRepository
from longtian_api.schemas.report_generations import GenerationCreate
from longtian_api.services import topic_report_engine
from longtian_api.services.enrichment_models import EnrichedContent


def generation_request(ids):
    return {
        "request_id": str(uuid4()),
        "configuration_revision": 1,
        "initial_prompt": {"mode": "default"},
        "report_prompt": {"mode": "default"},
        "selection": {"kind": "explicit", "result_ids": ids},
    }


def test_report_records_projection_keeps_manual_child_in_one_row(tmp_path):
    app, database, _, _ = api_environment(tmp_path, count=1)
    save_body(database, 1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert response.status_code == 202, response.text
        client.portal.call(finish, app.state.report_generation_service)

        records = client.get("/api/v1/report-generations/records")
        record = client.get("/api/v1/report-generations/records/report/1")

    assert records.status_code == 200, records.text
    assert record.status_code == 200, record.text
    assert records.json()["next_offset"] is None
    assert records.json()["items"] == [
        {
            "record_type": "generation",
            "record_id": 1,
            "generation_id": 1,
            "report_id": 1,
            "automation_run_id": None,
            "name": "报告 #1",
            "trigger": "manual",
            "status": "completed",
            "created_at": records.json()["items"][0]["created_at"],
            "selection_count": 1,
            "processed_count": 1,
            "failed_count": 0,
            "active_count": 0,
            "parent_report_id": None,
        }
    ]
    assert record.json() == records.json()["items"][0]


def test_one_start_reuses_three_summaries_and_analyses_seven_saved_bodies(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=11)
    media.media = False
    model.answers["initial"] = [UNDERSTANDING] * 3 + ["invalid"] * 14
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
        assert result["report"]["coverage"]["ready"] == 10
        assert result["report"]["coverage"]["unavailable"] == 0
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
    model.answers["initial"] = ["invalid", "invalid", UNDERSTANDING]
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
        assert model.counts["initial"] == 4
        assert client.get("/api/v1/report-generations/eligibility").json() == {
            "pending": 0,
            "failed": 0,
            "active": 0,
        }
        assert (
            client.post("/api/v1/report-generations", json=second_intent).json()
            == second_result
        )
        assert model.counts["initial"] == 4
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
        assert result["status"] == "failed", result
        assert result["analysis"]["counts"]["input_incomplete"] == 1
        items = client.get(
            f"/api/v1/content-analysis-jobs/{result['analysis']['id']}/items"
        ).json()
        assert items["items"][0]["error"]["code"] == "stored_content_unavailable"
        assert result["report"] is None
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


def test_new_generation_reacquires_saved_unavailable_text(tmp_path):
    app, database, _, _ = api_environment(tmp_path, count=1)
    save_body(database)
    with database.connect() as connection:
        raw = connection.execute(
            "SELECT content_json FROM content_materials WHERE content_id=1"
        ).fetchone()[0]
    content = EnrichedContent.model_validate_json(raw).model_dump()
    content["text"] = {"title": "", "body": "", "coverage": "unavailable"}
    content["status"] = "partial"
    content["issues"] = [{"code": "text_unavailable", "asset_position": None}]
    ContentMaterialRepository(database).save(1, EnrichedContent.model_validate(content))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        # Admission alone must leave this input open for a new acquisition.
        generation = app.state.report_generation_service.repository.create_generation(
            GenerationCreate.model_validate(generation_request([1]))
        )
        with database.connect() as connection:
            attempt = connection.execute(
                "SELECT input_json,status FROM content_analysis_attempts "
                "WHERE job_id=?",
                (generation.analysis.id,),
            ).fetchone()
        assert attempt["input_json"] is None
        assert attempt["status"] == "queued"


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


def test_overview_budget_upgrade_reuses_judgments_and_detailed_sections(
    tmp_path, monkeypatch
):
    app, database, model, _ = api_environment(tmp_path, count=10)
    for content_id in range(1, 11):
        save_body(database, content_id)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        with monkeypatch.context() as old_engine:
            old_engine.setattr(
                topic_report_engine,
                "OVERVIEW_ENGINE_VERSION",
                topic_report_engine.ENGINE_VERSION,
            )
            old_engine.setitem(
                topic_report_engine._OUTPUT_CONTRACTS,
                "overview",
                topic_report_engine._OUTPUT_CONTRACTS["overview"] + "旧版写作预算。",
            )
            response = client.post(
                "/api/v1/report-generations",
                json=generation_request(list(range(1, 11))),
            )
            client.portal.call(finish, app.state.report_generation_service)
            generation = client.get(
                f"/api/v1/report-generations/{response.json()['id']}"
            ).json()
            parent = generation["report"]
            assert parent["status"] == "completed"
        before = model.counts.copy()
        retry = client.post(
            f"/api/v1/topic-reports/{parent['id']}/retry",
            json={
                "request_id": str(uuid4()),
                "expected_revision": parent["revision"],
                "configuration_revision": 1,
            },
        )
        assert retry.status_code == 202, retry.text
        client.portal.call(finish, app.state.topic_report_service)
        report = client.get(f"/api/v1/topic-reports/{retry.json()['id']}").json()
        assert report["status"] == "completed", report
        assert report["nodes"]["judgments"]["reused"] == 10
        assert report["nodes"]["composition"]["reused"] == 2
        assert model.counts["initial"] == before["initial"]
        assert model.counts["judgment"] == before["judgment"]
        assert model.counts["leaf"] == before["leaf"]
        assert model.counts["overview"] == before["overview"] + 1
