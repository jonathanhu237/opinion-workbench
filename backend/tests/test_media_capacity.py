"""Quota reclamation is ordered and cannot unlink non-owned files."""

import io
import os
import random
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from summary_fixtures import seed_run
from test_content_analysis_api import saved
from test_media_cache import generate, image_response
from test_native_text_report import native_environment


@pytest.mark.parametrize("when", ["admission", "policy_change"])
def test_capacity_evicts_oldest_owned_originals_in_a_deterministic_order(
    tmp_path, when
):
    samples = {}
    for identity in (3600375418559878, 3600375418559888, 3600375418559889):
        buffer = io.BytesIO()
        Image.frombytes(
            "RGB", (1024, 256), random.Random(identity).randbytes(1024 * 256 * 3)
        ).save(buffer, format="PNG")
        samples[str(identity)] = buffer.getvalue()

    def response(request):
        if request.url.host == "weibo.com":
            identity = request.url.params["id"]
            value = image_response(request).json()
            value.update(id=int(identity), idstr=identity)
            value["pic_infos"]["one"]["largest"]["url"] = (
                f"https://wx1.sinaimg.cn/{identity}.png"
            )
            return httpx.Response(200, json=value)
        return httpx.Response(
            200,
            content=samples[request.url.path[1:-4]],
            headers={"content-type": "image/png"},
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    now = [int(time.time())]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        cache = app.state.media_cache
        cache.clock = lambda: now[0]
        seed_run(cache.database, 2, start=3600375418559888)
        assert (
            client.put(
                "/api/v1/media-cache-settings",
                json={
                    "retention_days": 30,
                    "capacity_mib": 2 if when == "admission" else 3,
                    "expected_revision": 0,
                },
            ).status_code
            == 200
        )
        attempts = []
        for identity in (1, 2, 3):
            now[0] += 1
            result, attempt = generate(client, app, [identity])
            assert result["status"] == "completed"
            attempts.append(attempt)
        if when == "policy_change":
            changed = client.put(
                "/api/v1/media-cache-settings",
                json={"retention_days": 30, "capacity_mib": 1, "expected_revision": 1},
            )
            assert changed.json()["cleanup"]["removed_files"] == 2
        states = [
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache").json()[
                "items"
            ][0]["state"]
            for attempt in attempts
        ]
        assert states == (
            ["cleared", "cached", "cached"]
            if when == "admission"
            else ["cleared", "cleared", "cached"]
        )
        policy = client.get("/api/v1/media-cache-settings").json()
        assert policy["reserved_bytes"] <= policy["capacity_mib"] * 1048576
        assert len(requests) == 6 and model.counts["initial"] == 3


def test_unowned_file_replacement_cannot_be_deleted_by_retention(tmp_path):
    app, _, _, _ = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        _, attempt = generate(client, app)
        cache = app.state.media_cache
        file = next(cache.root.iterdir())
        file.unlink()
        outside = tmp_path / "unowned.bin"
        outside.write_bytes(b"not application-owned")
        os.link(outside, file)
        cache.clock = lambda: int(time.time()) + 32 * 86400
        result = client.post(
            "/api/v1/media-cache-settings/cleanup", json={"expected_revision": 0}
        )
        assert result.status_code == 200 and result.json()["cleanup"]["deferred"]
        assert result.json()["cleanup"]["removed_files"] == 0
        assert outside.read_bytes() == b"not application-owned" and file.exists()
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache").json()[
                "items"
            ][0]["state"]
            == "corrupt"
        )
