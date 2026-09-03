"""Configured retention cleans only owned originals, not report evidence."""

import time

import pytest
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_media_cache import generate, image_response
from test_native_text_report import native_environment


def test_policy_update_cleans_expired_report_source_without_rewriting_history(tmp_path):
    app, _, model, requests = native_environment(tmp_path, response=image_response)
    now = [int(time.time())]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        cache = app.state.media_cache
        cache.clock = lambda: now[0]
        policy = client.get("/api/v1/media-cache-settings")
        assert policy.status_code == 200
        assert policy.json() == {
            "retention_days": 30,
            "capacity_mib": 1024,
            "revision": 0,
            "reserved_bytes": 0,
            "files": 0,
            "pending_files": 0,
        }
        assert not cache.root.exists()
        result, attempt = generate(client, app)
        report_path = f"/api/v1/topic-reports/{result['report']['id']}"
        report = client.get(report_path).json()
        now[0] += 2 * 86400
        cache_path = f"/api/v1/content-analyses/{attempt['id']}/media-cache"
        assert client.get(cache_path).json()["items"][0]["state"] == "cached"
        changed = client.put(
            "/api/v1/media-cache-settings",
            json={"retention_days": 1, "capacity_mib": 1024, "expected_revision": 0},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["cleanup"]["removed_files"] == 1
        assert changed.json()["policy"]["reserved_bytes"] == 0
        assert not list(cache.root.iterdir())
        assert client.get(cache_path).json()["items"][0]["state"] == "cleared"
        assert client.get(f"/api/v1/content-analyses/{attempt['id']}").json() == attempt
        assert client.get(report_path).json() == report
        repeated, _ = generate(client, app)
        assert repeated["analysis"]["counts"]["reused"] == 1
        assert len(requests) == 2 and model.counts["initial"] == 1
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/media-cache-settings").json()["retention_days"] == 1
        assert client.get(cache_path).json()["items"][0]["state"] == "cleared"


@pytest.mark.parametrize(
    "values",
    [
        {"retention_days": 0, "capacity_mib": 1024, "expected_revision": 0},
        {"retention_days": 30, "capacity_mib": 20481, "expected_revision": 0},
        {"retention_days": True, "capacity_mib": 1, "expected_revision": 0},
        {"retention_days": 30, "capacity_mib": 1.1, "expected_revision": 0},
    ],
)
def test_invalid_policy_does_not_touch_files_or_platform(tmp_path, values):
    app, _, _, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert (
            client.put("/api/v1/media-cache-settings", json=values).status_code == 422
        )
        assert not app.state.media_cache.root.exists() and not requests


def test_active_original_lease_defers_cleanup_until_released(tmp_path):
    app, _, _, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        _, attempt = generate(client, app)
        cache = app.state.media_cache
        material = cache.material(
            app.state.content_analysis_service.repository.attempt(attempt["id"])
        )
        lease = cache.acquire(1, material.assets)
        cache.clock = lambda: int(time.time()) + 32 * 86400
        try:
            changed = client.put(
                "/api/v1/media-cache-settings",
                json={"retention_days": 1, "capacity_mib": 1, "expected_revision": 0},
            )
            assert changed.status_code == 200
            assert changed.json()["cleanup"]["deferred"] is True
            assert changed.json()["cleanup"]["removed_files"] == 0
            assert next(cache.root.iterdir()).read_bytes() == lease.data[0]
        finally:
            lease.close()
        cleaned = client.post(
            "/api/v1/media-cache-settings/cleanup", json={"expected_revision": 1}
        )
        assert cleaned.status_code == 200
        assert cleaned.json()["cleanup"]["removed_files"] == 1
        assert len(requests) == 2


def test_stale_policy_and_replaced_root_never_delete_external_data(tmp_path):
    app, _, _, _ = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        _, attempt = generate(client, app)
        cache = app.state.media_cache
        outside = tmp_path / "external"
        cache.root.rename(outside)
        cache.root.symlink_to(outside, target_is_directory=True)
        cache.clock = lambda: int(time.time()) + 32 * 86400
        changed = client.put(
            "/api/v1/media-cache-settings",
            json={"retention_days": 1, "capacity_mib": 1, "expected_revision": 0},
        )
        assert changed.status_code == 200 and changed.json()["cleanup"]["deferred"]
        stale = client.put(
            "/api/v1/media-cache-settings",
            json={"retention_days": 30, "capacity_mib": 1024, "expected_revision": 0},
        )
        assert stale.status_code == 409
        assert len(list(outside.iterdir())) == 1
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache").json()[
                "items"
            ][0]["state"]
            == "unavailable"
        )
