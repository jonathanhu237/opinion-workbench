"""The retired media cache is absent from the current runtime boundary."""

import httpx
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment
from test_report_generations import generation_request
from topic_report_fixtures import finish

from longtian_api.database import Database


def image_post(request):
    if request.url.host == "weibo.com":
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": "龙田正文，图片仅作为历史元数据",
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": ["one"],
                "pic_infos": {
                    "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                },
                "page_info": {
                    "media_info": {"stream_url": "https://f.video.weibocdn.com/one.mp4"}
                },
            },
        )
    raise AssertionError(
        f"retired media acquisition made an unexpected request: {request}"
    )


def test_text_report_does_not_create_or_expose_media_cache(tmp_path):
    app, _, model, requests = native_environment(tmp_path, response=image_post)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{value['id']}").json()
        assert result["status"] == "completed"
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["assets"] == []
        assert attempt["input"]["detected_modalities"] == ["text"]
        assert len(requests) == 1
        assert not hasattr(app.state, "media_cache")
        assert client.get("/api/v1/media-cache-settings").status_code == 404
        assert (
            client.get(
                f"/api/v1/content-analyses/{attempt['id']}/media-cache"
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media/0").status_code
            == 404
        )
        assert not model.calls or all(
            "image_url" not in str(messages) and "video_url" not in str(messages)
            for _, messages in model.calls
        )


def test_fresh_schema_has_no_media_cache_runtime_tables(tmp_path):
    database = Database(tmp_path / "fresh.sqlite3")
    database.initialize()
    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert not tables & {
        "media_cache_owner",
        "media_cache_policy",
        "media_cache_entries",
        "media_cache_bindings",
    }
