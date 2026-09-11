"""Cancel at external boundaries; preserve finished members and stop owners."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient
from summary_fixtures import seed_run
from test_content_analysis_api import saved
from test_native_text_report import native_environment, wait_status
from test_report_generations import generation_request, save_body
from topic_report_fixtures import api_environment, finish


def test_concurrent_cancels_wait_for_the_same_owned_cleanup(tmp_path):
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cleanup_calls = []

    async def response(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_calls.append(True)
            cleaning.set()
            await release.wait()

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(asyncio.wait_for, entered.wait(), 5)
        barrier = Barrier(3)

        def cancel():
            barrier.wait(timeout=5)
            return client.post(
                f"/api/v1/report-generations/{value['id']}/cancel",
                json={"expected_revision": value["control_revision"]},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(cancel) for _ in range(2)]
            barrier.wait(timeout=5)
            try:
                client.portal.call(asyncio.wait_for, cleaning.wait(), 5)
                assert all(not future.done() for future in futures)
            finally:
                client.portal.call(release.set)
            results = [future.result(timeout=5) for future in futures]
        assert all(result.status_code == 200 for result in results)
        assert results[0].json() == results[1].json()
        assert cleanup_calls == [True] and len(requests) == 1 and not model.calls


def test_cancel_during_url_lookup_keeps_reuse_and_waits_for_external_cleanup(tmp_path):
    entered = asyncio.Event()
    stopped = []
    blocked = True

    async def response(request):
        if blocked:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)
        identity = request.url.params["id"]
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": int(identity),
                "idstr": identity,
                "text": "龙田道路维修公告",
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": [],
            },
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        service = app.state.report_generation_service
        database = service.repository.database
        save_body(database, 1)
        first = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(wait_status, service, first["id"], "completed")
        seed_run(database, 1, start=3600375418559888)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1, 2])
        ).json()
        client.portal.call(asyncio.wait_for, entered.wait(), 5)
        path = f"/api/v1/report-generations/{value['id']}/cancel"
        cancelled = client.post(
            path, json={"expected_revision": value["control_revision"]}
        )
        assert cancelled.status_code == 200, cancelled.text
        result = cancelled.json()
        assert result["status"] == "cancelled" and result["report"] is None
        assert result["analysis"]["counts"]["reused"] == 1
        assert result["analysis"]["counts"]["cancelled"] == 1
        assert stopped == [True] and len(requests) == 1
        assert model.counts["initial"] == 1
        assert (
            client.post(
                path, json={"expected_revision": value["control_revision"]}
            ).json()
            == result
        )
        # A subsequent explicit task proves both browser and model owners freed.
        blocked = False
        retry = client.post(
            "/api/v1/report-generations", json=generation_request([2])
        ).json()
        client.portal.call(finish, service)
        assert (
            client.get(f"/api/v1/report-generations/{retry['id']}").json()["status"]
            == "completed"
        )
        assert len(requests) == 2 and model.counts["initial"] == 2


@pytest.mark.parametrize("stage", ["initial", "leaf"])
def test_cancel_stops_model_stage_without_starting_later_members_or_reports(
    tmp_path, stage
):
    app, database, model, _ = api_environment(tmp_path, count=2)
    save_body(database, 1)
    save_body(database, 2)
    model.block_stage = stage
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        request = generation_request([1, 2])
        request["summary_concurrency"] = 1
        value = client.post("/api/v1/report-generations", json=request).json()
        client.portal.call(asyncio.wait_for, model.entered.wait(), 5)
        current = client.get(f"/api/v1/report-generations/{value['id']}").json()
        result = client.post(
            f"/api/v1/report-generations/{value['id']}/cancel",
            json={"expected_revision": current["control_revision"]},
        )
        assert result.status_code == 200, result.text
        final = result.json()
        assert final["status"] == "cancelled"
        if stage == "initial":
            assert final["analysis"]["counts"]["cancelled"] == 2
            assert final["report"] is None
            assert model.counts["initial"] == 1
        else:
            assert final["analysis"]["counts"]["completed"] == 2
            assert final["report"]["status"] == "cancelled"
            assert model.counts["leaf"] == 1
        calls = model.counts.copy()
        client.portal.call(model.gate.set)
        client.portal.call(finish, app.state.report_generation_service)
        assert client.get(f"/api/v1/report-generations/{value['id']}").json() == final
        assert model.counts == calls


def test_cancel_paused_child_also_settles_parent_and_releases_browser(tmp_path):
    app, _, model, requests = native_environment(
        tmp_path,
        response=lambda request: httpx.Response(403, content="安全验证".encode()),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        service = app.state.report_generation_service
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(
            wait_status, service, value["id"], "paused_for_manual_action"
        )
        cancelled = client.post(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/cancel", json={}
        )
        assert cancelled.status_code == 200
        assert (
            client.get(f"/api/v1/report-generations/{value['id']}").json()["status"]
            == "cancelled"
        )
        retry = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(
            wait_status, service, retry["id"], "paused_for_manual_action"
        )
        assert len(requests) == 2 and not model.calls


def test_cancel_after_text_only_acquisition_keeps_body_without_media_request(tmp_path):
    async def response(request):
        assert request.url.host == "weibo.com"
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": "龙田正文已取得，图片不应下载",
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": ["one"],
                "pic_infos": {
                    "one": {"largest": {"url": "https://wx1.sinaimg.cn/one.png"}}
                },
            },
        )

    app, _, model, requests = native_environment(tmp_path, response=response)
    model.block_stage = "initial"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        service = app.state.report_generation_service
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(asyncio.wait_for, model.entered.wait(), 5)
        result = client.post(
            f"/api/v1/report-generations/{value['id']}/cancel",
            json={"expected_revision": value["control_revision"]},
        )
        assert result.status_code == 200
        assert len(requests) == 1 and len(model.calls) == 1
        with service.repository.database.connect() as connection:
            saved_input = connection.execute(
                "SELECT input_json FROM content_materials WHERE content_id=1"
            ).fetchone()
            assert saved_input is not None
            assert (
                json.loads(saved_input[0])["text"]["body"]
                == "龙田正文已取得，图片不应下载"
            )
