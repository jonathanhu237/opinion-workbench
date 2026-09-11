"""Retired media capacity settings are not part of the current product."""

from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_media_cache import image_post
from test_native_text_report import native_environment
from test_report_generations import generation_request
from topic_report_fixtures import finish


def test_capacity_settings_cannot_be_changed_or_trigger_media_work(tmp_path):
    app, _, _, requests = native_environment(tmp_path, response=image_post)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert client.get("/api/v1/media-cache-settings").status_code == 404
        assert (
            client.put(
                "/api/v1/media-cache-settings",
                json={
                    "retention_days": 30,
                    "capacity_mib": 1,
                    "expected_revision": 0,
                },
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/media-cache-settings/cleanup",
                json={"expected_revision": 0},
            ).status_code
            == 404
        )
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        attempt = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()["items"][0]
        assert attempt["input"]["assets"] == []
        assert len(requests) == 1
