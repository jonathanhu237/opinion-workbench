"""Application-owned original files survive temporary model input cleanup."""

import asyncio
import io
import os
import random

import httpx
import pytest
from enrichment_fixtures import PNG
from fastapi.testclient import TestClient
from PIL import Image
from test_content_analysis_api import saved
from test_native_text_report import native_environment
from test_report_generations import generation_request
from topic_report_fixtures import finish


def test_full_capacity_stops_new_cache_but_preserves_actual_model_input(tmp_path):
    data = io.BytesIO()
    Image.frombytes(
        "RGB", (1024, 512), random.Random(1).randbytes(1024 * 512 * 3)
    ).save(data, format="PNG")
    original = data.getvalue()
    assert 1024 * 1024 < len(original) < 6 * 1024 * 1024

    def response(request):
        if request.url.host == "weibo.com":
            return image_response(request)
        return httpx.Response(
            200, content=original, headers={"content-type": "image/png"}
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        with app.state.media_cache.connection(write=True) as connection:
            connection.execute("UPDATE media_cache_policy SET capacity_mib=1")
        result, attempt = generate(client, app)
        assert result["status"] == "completed"
        assert attempt["input"]["assets"][0]["status"] == "ready"
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache").json()[
                "items"
            ][0]["state"]
            == "not_stored"
        )
        assert len(requests) == 2 and model.counts["initial"] == 1
        assert not list(app.state.media_cache.root.iterdir())


def test_replaced_cache_root_is_not_adopted_or_followed(tmp_path):
    app, _, _, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        _, attempt = generate(client, app)
        root = app.state.media_cache.root
        displaced = tmp_path / "displaced-cache"
        root.rename(displaced)
        root.symlink_to(displaced, target_is_directory=True)
        response = client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache")
        assert response.json()["items"][0]["state"] == "unavailable"
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media/0").status_code
            == 404
        )
        assert next(displaced.iterdir()).read_bytes() == PNG and len(requests) == 2


def test_failed_file_commit_is_reserved_but_never_reported_as_ready(
    tmp_path, monkeypatch
):
    from longtian_api.services import media_cache

    original_fsync = os.fsync

    def fail_file_commit(fd):
        if os.fstat(fd).st_size == len(PNG):
            raise OSError("synthetic file commit failure")
        return original_fsync(fd)

    app, _, _, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        cache = app.state.media_cache
        save_one = cache._save_one

        def injected(*args):
            with monkeypatch.context() as patch:
                patch.setattr(media_cache.os, "fsync", fail_file_commit)
                return save_one(*args)

        monkeypatch.setattr(cache, "_save_one", injected)
        result, attempt = generate(client, app)
        assert result["status"] == "completed"
        path = f"/api/v1/content-analyses/{attempt['id']}/media-cache"
        assert client.get(path).json()["items"][0]["state"] == "unavailable"
        with cache.connection() as connection:
            row = connection.execute("SELECT * FROM media_cache_entries").fetchone()
            assert row["state"] == "pending" and row["byte_size"] == len(PNG)
            assert row["inode"] is not None
        assert len(requests) == 2


def image_response(request):
    if request.url.host == "weibo.com":
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": "",
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": ["one"],
                "pic_infos": {
                    "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                },
            },
        )
    return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})


def generate(client, app, ids=(1,)):
    value = client.post(
        "/api/v1/report-generations", json=generation_request(list(ids))
    ).json()
    client.portal.call(finish, app.state.report_generation_service)
    result = client.get(f"/api/v1/report-generations/{value['id']}").json()
    attempt = client.get(
        f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
    ).json()["items"][0]
    return result, attempt


def test_original_survives_analysis_cleanup_and_read_only_restart(tmp_path):
    app, _, model, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        result, attempt = generate(client, app)
        assert result["status"] == "completed"
        path = f"/api/v1/content-analyses/{attempt['id']}/media-cache"
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["items"][0]["state"] == "cached"
        assert not list((tmp_path / "media").iterdir())
        cache = app.state.media_cache
        files = [p for p in cache.root.iterdir() if p.is_file()]
        assert len(files) == 1 and files[0].read_bytes() == PNG
        original = client.get(f"/api/v1/content-analyses/{attempt['id']}/media/0")
        assert original.status_code == 200 and original.content == PNG
        assert original.headers["content-type"] == "image/png"
        calls = model.counts.copy()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(path).json()["items"][0]["state"] == "cached"
        assert len(requests) == 2 and model.counts == calls
        assert (
            client.get(f"/api/v1/topic-reports/{result['report']['id']}").status_code
            == 200
        )


@pytest.mark.parametrize(
    "change,state", [("missing", "missing"), ("corrupt", "corrupt")]
)
def test_missing_or_corrupt_original_never_changes_historical_success(
    tmp_path, change, state
):
    app, _, model, requests = native_environment(tmp_path, response=image_response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        _, attempt = generate(client, app)
        file = next(app.state.media_cache.root.iterdir())
        if change == "missing":
            file.unlink()
        else:
            file.write_bytes(b"x" * len(PNG))
        response = client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache")
        assert response.json()["items"][0]["state"] == state
        assert client.get(f"/api/v1/content-analyses/{attempt['id']}").json() == attempt
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media/0").status_code
            == 404
        )
        repeated, _ = generate(client, app)
        assert repeated["analysis"]["counts"]["reused"] == 1
        assert len(requests) == 2 and model.counts["initial"] == 1


def test_cancelled_model_can_explicitly_retry_from_cached_pure_image_without_browser(
    tmp_path,
):
    app, _, model, requests = native_environment(tmp_path, response=image_response)
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(asyncio.wait_for, model.entered.wait(), 5)
        cancelled = client.post(
            f"/api/v1/report-generations/{value['id']}/cancel",
            json={"expected_revision": 0},
        )
        assert cancelled.status_code == 200
        model.block_stage = None
        result, attempt = generate(client, app)
        assert result["status"] == "completed", result
        assert attempt["input"]["assets"][0]["status"] == "ready"
        assert len(requests) == 2 and model.counts["initial"] == 2
        assert (
            client.get(f"/api/v1/content-analyses/{attempt['id']}/media-cache").json()[
                "items"
            ][0]["state"]
            == "cached"
        )
