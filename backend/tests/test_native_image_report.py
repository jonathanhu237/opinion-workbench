"""Actual fixed image bytes cross the native acquisition and model boundaries."""

import base64
import json

import httpx
import pytest
from enrichment_fixtures import PNG
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment, wait_status
from test_report_generations import generation_request
from topic_report_fixtures import finish


@pytest.mark.parametrize(
    "caption,count,failed",
    [
        ("", 1, None),
        ("龙田现场图文", 1, None),
        ("龙田现场多图", 3, None),
        ("龙田现场，一图缺失", 2, 1),
    ],
)
def test_actual_images_reach_summary_and_report_with_honest_gaps(
    tmp_path, caption, count, failed
):
    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text_raw": caption,
                    "text": caption,
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": [str(i) for i in range(count)],
                    "pic_infos": {
                        str(i): {
                            "largest": {"url": f"https://wx1.sinaimg.cn/large/{i}.png"}
                        }
                        for i in range(count)
                    },
                },
            )
        assert "cookie" not in request.headers
        if request.url.path.endswith(f"/{failed}.png"):
            return httpx.Response(404)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        value = client.get(f"/api/v1/report-generations/{result['id']}").json()
        assert value["status"] == "completed", value
        attempts = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"]
        evidence = attempts[0]["input"]
        ready = count - int(failed is not None)
        assert [a["status"] for a in evidence["assets"]].count("ready") == ready
        assert evidence["text"]["coverage"] == "complete"
        assert evidence["status"] == ("partial" if failed is not None else "ready")
        initial = next(
            messages for stage, messages in model.calls if stage == "initial"
        )
        parts = initial[1]["content"]
        images = [p for p in parts if p["type"] == "image_url"]
        assert len(images) == ready
        assert all(
            base64.b64decode(p["image_url"]["url"].split(",")[1]) == PNG for p in images
        )
        payload = json.loads(parts[0]["text"])
        assert payload["evidence_coverage"]["image"]["ready"] == ready
        sources = client.get(
            f"/api/v1/topic-reports/{value['report']['id']}/sources"
        ).json()["items"]
        assert sources[0]["evidence_coverage"]["image"]["ready"] == ready
        assert len(requests) == count + 1


@pytest.mark.parametrize(
    "url,status,mime,data,issue,external_calls",
    [
        ("https://127.0.0.1/secret.png", 200, "image/png", PNG, "unsafe_media_url", 0),
        (
            "https://wx1.sinaimg.cn.evil.example/one.png",
            200,
            "image/png",
            PNG,
            "unsafe_media_url",
            0,
        ),
        ("https://wx1.sinaimg.cn/one.png", 302, "image/png", PNG, "media_redirect", 1),
        (
            "https://wx1.sinaimg.cn/one.png",
            200,
            "image/png",
            b"<html>not an image</html>",
            "invalid_media",
            1,
        ),
        (
            "https://wx1.sinaimg.cn/one.png",
            200,
            "text/html",
            PNG,
            "unsupported_media_type",
            1,
        ),
    ],
)
def test_unsafe_or_invalid_image_keeps_body_but_never_fabricates_media(
    tmp_path, url, status, mime, data, issue, external_calls
):
    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田正文仍然可用",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one"],
                    "pic_infos": {"one": {"largest": {"url": url}}},
                },
            )
        return httpx.Response(
            status,
            content=data,
            headers={"content-type": mime, "location": "https://127.0.0.1/secret"},
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        value = client.get(f"/api/v1/report-generations/{result['id']}").json()
        assert value["status"] == "completed"
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["assets"][0]["issue_code"] == issue
        assert attempt["input"]["assets"][0]["status"] != "ready"
        assert len(requests) == 1 + external_calls
        message = next(
            messages for stage, messages in model.calls if stage == "initial"
        )[1]["content"]
        assert isinstance(message, str)
        assert json.loads(message)["source"]["body"] == "龙田正文仍然可用"


def test_media_challenge_keeps_text_and_downloaded_image_until_explicit_continue(
    tmp_path,
):
    resolved = False

    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田两张现场图",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one", "two"],
                    "pic_infos": {
                        name: {"largest": {"url": f"https://wx1.sinaimg.cn/{name}.png"}}
                        for name in ("one", "two")
                    },
                },
            )
        if request.url.path == "/two.png" and not resolved:
            return httpx.Response(403)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        service = app.state.report_generation_service
        paused = client.portal.call(
            wait_status, service, result["id"], "paused_for_manual_action"
        )
        assert paused.pause_reason == "manual_challenge_required"
        assert len(requests) == 3 and not model.calls
        with service.repository.database.connect() as connection:
            material = json.loads(
                connection.execute(
                    "SELECT input_json FROM content_materials"
                ).fetchone()[0]
            )
            assert material["text"]["body"] == "龙田两张现场图"
            assert material["assets"][0]["status"] == "ready"
        resolved = True
        response = client.post(
            f"/api/v1/report-generations/{result['id']}/continue",
            json={"expected_revision": paused.control_revision},
        )
        assert response.status_code == 200
        client.portal.call(finish, service)
        assert (
            client.get(f"/api/v1/report-generations/{result['id']}").json()["status"]
            == "completed"
        )
        assert [request.url.path for request in requests] == [
            "/ajax/statuses/show",
            "/one.png",
            "/two.png",
            "/two.png",
        ]
        assert model.counts["initial"] == 1


def test_failed_bytes_still_consume_the_selected_post_download_budget(tmp_path):
    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田现场正文",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one", "two"],
                    "pic_infos": {
                        name: {"largest": {"url": f"https://wx1.sinaimg.cn/{name}.png"}}
                        for name in ("one", "two")
                    },
                },
            )
        return httpx.Response(
            200, content=b"x" * (6 * 1024 * 1024), headers={"content-type": "image/png"}
        )

    app, _, _, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{result['analysis']['id']}/items"
        ).json()["items"][0]
        assert [a["issue_code"] for a in attempt["input"]["assets"]] == [
            "invalid_media",
            "media_limit",
        ]
        assert len(requests) == 2
