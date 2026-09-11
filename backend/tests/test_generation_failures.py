"""Failure is local to its stage; systemic faults stop owned manual queues."""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from initial_analysis_fixtures import UNDERSTANDING
from test_content_analysis_api import body, saved
from test_report_generations import generation_request, save_body
from topic_report_fixtures import api_environment, finish

from longtian_api.repositories.content_materials import ContentMaterialRepository
from longtian_api.services.ai_errors import AIError
from longtian_api.services.enrichment_models import EnrichedContent


@pytest.mark.parametrize("report_failure", [False, True])
def test_two_failed_sources_do_not_block_other_eighteen_or_pollute_report_retry(
    tmp_path,
    report_failure,
):
    app, database, model, media = api_environment(tmp_path, count=20)
    for identity in range(1, 21):
        save_body(database, identity)
    model.answers["initial"] = ["invalid"] * 4 + [UNDERSTANDING] * 18
    if report_failure:
        model.answers["leaf"] = ["invalid"] * 2
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request(list(range(1, 21)))
        )
        assert response.status_code == 202, response.text
        client.portal.call(finish, app.state.report_generation_service)
        generation = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert generation["status"] == ("failed" if report_failure else "completed"), (
            generation
        )
        assert generation["analysis"]["counts"]["completed"] == 18
        assert generation["analysis"]["counts"]["failed"] == 2
        report = generation["report"]
        assert report["coverage"]["total"] == 20
        assert report["coverage"]["ready"] == 18
        baseline = model.counts["initial"], len(media.calls)
        intent = generation_request([1])
        retry = client.post(
            f"/api/v1/topic-reports/{report['id']}/retry",
            json={
                "request_id": intent["request_id"],
                "configuration_revision": 1,
                "expected_revision": report["revision"],
            },
        )
        assert retry.status_code == 202, retry.text
        client.portal.call(finish, app.state.topic_report_service)
        repaired = client.get(f"/api/v1/topic-reports/{retry.json()['id']}").json()
        assert repaired["status"] == "completed", repaired
        assert repaired["parent_report_id"] == report["id"]
        assert repaired["coverage"]["ready"] == 18
        assert (model.counts["initial"], len(media.calls)) == baseline
        assert (
            client.get(f"/api/v1/report-generations/{generation['id']}").json()
            == generation
        )


def test_authentication_failure_stops_current_and_queued_manual_generations(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=20)
    for identity in range(1, 21):
        save_body(database, identity)
    model.answers["initial"] = [AIError("ai_authentication_failed")]
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        first_request = generation_request(list(range(1, 11)))
        first_request["summary_concurrency"] = 1
        first = client.post("/api/v1/report-generations", json=first_request)
        assert first.status_code == 202
        client.portal.call(asyncio.wait_for, model.entered.wait(), 2)
        second_request = generation_request(list(range(11, 21)))
        second_request["summary_concurrency"] = 1
        second = client.post("/api/v1/report-generations", json=second_request)
        assert second.status_code == 202
        client.portal.call(model.gate.set)
        client.portal.call(finish, app.state.report_generation_service)
        for response in (first, second):
            result = client.get(
                f"/api/v1/report-generations/{response.json()['id']}"
            ).json()
            assert result["status"] == "configuration_blocked", result
            assert result["report"] is None
        assert model.counts["initial"] == 1
        assert not model.counts["judgment"] and not media.calls


def test_all_irrelevant_is_empty_not_a_failed_or_fabricated_report(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=2)
    for identity in (1, 2):
        save_body(database, identity)
        model.decisions[identity] = "irrelevant"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1, 2])
        )
        assert response.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "empty"
        assert result["report"]["empty_reason"] == "no_relevant_sources"
        assert result["analysis"]["counts"]["completed"] == 2
        assert not model.counts["leaf"] and not media.calls


def test_all_failed_analysis_does_not_create_empty_report(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=2)
    for identity in (1, 2):
        save_body(database, identity)
    model.answers["initial"] = ["invalid"] * 4
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1, 2])
        )
        assert response.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "failed"
        assert result["report"] is None
        assert result["analysis"]["counts"]["failed"] == 2
        assert not model.counts["leaf"]


def test_partial_text_with_failed_image_is_reported_as_text_only(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=1)
    ContentMaterialRepository(database).save(
        1,
        EnrichedContent(
            schema_version=1,
            platform="wb",
            content_id="1000",
            content_url="https://m.weibo.cn/detail/1000",
            acquired_at=1788000000000,
            extractor_version="wb-enrichment-v1",
            status="partial",
            text={
                "title": "来源标题",
                "body": "已保存正文反映街道积水，图片下载失败。",
                "coverage": "complete",
            },
            detected_modalities=["text", "image"],
            media_inventory_complete=True,
            assets=[
                {
                    "asset_id": uuid4().hex,
                    "position": 0,
                    "kind": "image",
                    "role": "content",
                    "status": "failed",
                    "blob_ref": None,
                    "sha256": None,
                    "mime_type": None,
                    "byte_size": None,
                    "width": None,
                    "height": None,
                    "duration_ms": None,
                    "audio_track": "not_applicable",
                    "coverage": "unknown",
                    "issue_code": "download_failed",
                }
            ],
            issues=[{"code": "download_failed", "asset_position": 0}],
        ),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert response.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "completed", result
        sources = client.get(
            f"/api/v1/topic-reports/{result['report']['id']}/sources"
        ).json()["items"]
        coverage = sources[0]["evidence_coverage"]
        assert coverage["level"] == "detail_text"
        assert coverage["image"]["failed"] == 0 and coverage["image"]["ready"] == 0
        assert "download_failed" not in coverage["issues"]
        assert all(
            "download_failed" not in json.dumps(messages) for _, messages in model.calls
        )
        assert not media.calls


def test_report_auth_failure_stops_queued_manual_work_but_keeps_completed_summaries(
    tmp_path,
):
    app, database, model, media = api_environment(tmp_path, count=4)
    for identity in range(1, 5):
        save_body(database, identity)
    model.answers["judgment"] = [AIError("ai_authentication_failed")]
    model.block_stage = "judgment"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        first = client.post(
            "/api/v1/report-generations", json=generation_request([1, 2])
        )
        assert first.status_code == 202
        client.portal.call(asyncio.wait_for, model.entered.wait(), 2)
        second = client.post(
            "/api/v1/report-generations", json=generation_request([3, 4])
        )
        assert second.status_code == 202
        client.portal.call(model.gate.set)
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{first.json()['id']}").json()
        assert result["status"] == "configuration_blocked"
        assert result["analysis"]["counts"]["completed"] == 2
        assert result["report"]["error"]["code"] == "ai_authentication_failed"
        other = client.get(f"/api/v1/report-generations/{second.json()['id']}").json()
        assert other["status"] == "configuration_blocked" and other["report"] is None
        assert model.counts["initial"] == 2 and model.counts["judgment"] == 1
        assert not media.calls


def test_saved_media_metadata_without_bytes_is_not_presented_as_seen_media(tmp_path):
    app, _, model, media = api_environment(tmp_path, count=1)
    media.media = True
    model.answers["initial"] = ["invalid"] * 2
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        initial = client.post("/api/v1/content-analysis-jobs", json=body(client))
        assert initial.status_code == 202
        client.portal.call(finish, app.state.content_analysis_service)
        old_path = f"/api/v1/content-analysis-jobs/{initial.json()['job']['id']}/items"
        old = client.get(old_path).json()
        assert any(
            asset["status"] == "ready" for asset in old["items"][0]["input"]["assets"]
        )
        baseline = len(media.calls), len(model.calls)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert response.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()
        assert result["status"] == "completed", result
        sources = client.get(
            f"/api/v1/topic-reports/{result['report']['id']}/sources"
        ).json()["items"]
        assert sources[0]["evidence_coverage"]["image"]["ready"] == 0
        assert "asset_unavailable" in sources[0]["evidence_coverage"]["issues"]
        assert len(media.calls) == baseline[0]
        assert all(
            "data:image/" not in json.dumps(messages)
            for _, messages in model.calls[baseline[1] :]
        )
        assert client.get(old_path).json() == old
