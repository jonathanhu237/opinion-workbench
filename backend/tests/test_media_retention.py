"""Retired media retention settings are not mounted in the runtime."""

from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_media_cache import image_post
from test_native_text_report import native_environment


def test_retention_settings_and_cleanup_are_not_available(tmp_path):
    app, _, _, requests = native_environment(tmp_path, response=image_post)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        for method, path, payload in (
            ("get", "/api/v1/media-cache-settings", None),
            (
                "put",
                "/api/v1/media-cache-settings",
                {
                    "retention_days": 1,
                    "capacity_mib": 1,
                    "expected_revision": 0,
                },
            ),
            (
                "post",
                "/api/v1/media-cache-settings/cleanup",
                {"expected_revision": 0},
            ),
        ):
            response = (
                getattr(client, method)(path, json=payload)
                if payload
                else getattr(client, method)(path)
            )
            assert response.status_code == 404
        assert not requests
        assert not hasattr(app.state, "media_cache")


def test_historical_media_does_not_create_a_retention_runtime(tmp_path):
    app, _, _, requests = native_environment(tmp_path, response=image_post)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert client.get("/api/v1/media-cache-settings").status_code == 404
        assert not requests
