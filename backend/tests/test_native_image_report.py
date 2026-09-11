"""Native text-only acquisition ignores media metadata and URLs."""

import json

import httpx
import pytest
from enrichment_fixtures import PNG
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment
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
def test_native_report_saves_text_without_media_acquisition(
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
                    "text_raw": caption or "龙田正文",
                    "text": caption or "龙田正文",
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
        raise AssertionError(
            f"text-only acquisition made an unexpected request: {request}"
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        value = client.get(f"/api/v1/report-generations/{result['id']}").json()
        assert value["status"] == "completed", value
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        evidence = attempt["input"]
        assert evidence["status"] == "ready"
        assert evidence["detected_modalities"] == ["text"]
        assert evidence["assets"] == []
        assert evidence["media_inventory_complete"] is True
        assert evidence["text"]["coverage"] == "complete"
        initial = next(
            messages for stage, messages in model.calls if stage == "initial"
        )
        content = initial[1]["content"]
        assert isinstance(content, str)
        payload = json.loads(content)
        assert (
            payload["source"]["body"] == caption
            or payload["source"]["body"] == "龙田正文"
        )
        assert "image_url" not in str(model.calls)
        assert "video_url" not in str(model.calls)
        assert len(requests) == 1


@pytest.mark.parametrize(
    "url,status,mime,data",
    [
        ("https://127.0.0.1/secret.png", 200, "image/png", PNG),
        ("https://wx1.sinaimg.cn.evil.example/one.png", 200, "image/png", PNG),
        ("https://wx1.sinaimg.cn/one.png", 302, "image/png", PNG),
        ("https://wx1.sinaimg.cn/one.png", 200, "image/png", b"not an image"),
        ("https://wx1.sinaimg.cn/one.png", 200, "text/html", PNG),
    ],
)
def test_media_urls_and_responses_are_not_requested(tmp_path, url, status, mime, data):
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
        assert attempt["input"]["assets"] == []
        assert attempt["input"]["text"]["body"] == "龙田正文仍然可用"
        assert "image_url" not in str(model.calls)
        assert len(requests) == 1


def test_media_challenge_does_not_pause_text_only_report(tmp_path):
    def response(request):
        if request.url.host == "weibo.com":
            return httpx.Response(
                200,
                json={
                    "ok": 1,
                    "id": 3600375418559878,
                    "idstr": "3600375418559878",
                    "text": "龙田三张现场图",
                    "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                    "pic_ids": ["one", "two", "three"],
                    "pic_infos": {
                        name: {"largest": {"url": f"https://wx1.sinaimg.cn/{name}.png"}}
                        for name in ("one", "two", "three")
                    },
                },
            )
        return httpx.Response(403, content="安全验证".encode())

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        value = client.get(f"/api/v1/report-generations/{result['id']}").json()
        assert value["status"] == "completed"
        assert model.counts["initial"] == 1
        assert len(requests) == 1
        assert [request.url.path for request in requests] == ["/ajax/statuses/show"]


def test_plain_media_status_cannot_change_text_only_evidence(tmp_path):
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
                    "pic_infos": {
                        "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                    },
                },
            )
        return httpx.Response(403)

    app, browser, model, requests = native_environment(tmp_path, response=response)
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
        assert attempt["input"]["status"] == "ready"
        assert attempt["input"]["assets"] == []
        assert model.counts["initial"] == 1
        assert browser.shown == 0
        assert len(requests) == 1


def test_media_byte_budget_is_not_entered_for_text_only_reports(tmp_path):
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
            200,
            content=b"x" * (6 * 1024 * 1024),
            headers={"content-type": "image/png"},
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
        assert attempt["input"]["assets"] == []
        assert len(requests) == 1
