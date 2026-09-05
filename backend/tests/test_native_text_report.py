"""Selected URL -> real parser -> saved body -> model -> report, isolated IO."""

import asyncio
import inspect

import httpx
import pytest
from fastapi.testclient import TestClient
from summary_fixtures import seed_run
from test_content_analysis_api import saved
from test_native_weibo_discovery import BrowserFixture
from test_report_generations import generation_request, save_body
from topic_report_fixtures import TextPipelineClient, finish

from longtian_api.database import Database
from longtian_api.main import create_app
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.native_weibo import NativeWeiboCollector
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.weibo_enrichment import WeiboEnricher


class OwnedSession(BrowserFixture):
    shown = 0

    async def show(self):
        self.shown += 1
        await super().show()

    async def weibo_cookies(self):
        return {"SUB": "synthetic-weibo-session"}


def native_environment(tmp_path, *, response):
    database = Database(tmp_path / "api.sqlite3")
    database.initialize()
    seed_run(database, 1, start=3600375418559878)
    model = TextPipelineClient()
    browser = OwnedSession([])
    requests = []

    async def send(request):
        requests.append(request)
        result = response(request)
        return await result if inspect.isawaitable(result) else result

    enricher = WeiboEnricher(browser=browser, transport=httpx.MockTransport(send))
    runtime = NativeWeiboCollector(browser=browser, enricher=enricher)
    app = create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            collector_factory=lambda **kwargs: runtime
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database.path
        ),
        ai_settings_service_factory=lambda db: AISettingsService(db, client=model),
    )
    return app, browser, model, requests


@pytest.mark.parametrize(
    "original",
    [
        {"text_raw": "原帖说明：龙田道路已恢复通行。"},
        {"text": ""},
    ],
)
def test_repost_includes_embedded_body_or_marks_a_gap_without_more_lookups(
    tmp_path, original
):
    # A deleted embedded original must not turn a repost caption into full coverage.
    def response(request):
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text_raw": "转发供参考，请阅读全文",
                "isLongText": False,
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "retweeted_status": {"id": 3501756485200075, **original},
            },
        )

    app, browser, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        items = client.get(
            f"/api/v1/content-analysis-jobs/{created['analysis']['id']}/items"
        ).json()["items"]
        content = items[0]["input"]
        assert "转发供参考，请阅读全文" in content["text"]["body"]
        if original.get("text_raw"):
            assert "转发附带原帖" in content["text"]["body"]
            assert original["text_raw"] in content["text"]["body"]
            assert content["text"]["coverage"] == "complete"
        else:
            assert content["text"]["coverage"] == "partial"
            assert "text_incomplete" in content["issues"]
        assert len(requests) == 1 and not browser.visits


def test_selected_url_saves_full_body_and_delivers_report_without_legacy_enrichment(
    tmp_path,
):
    def response(request):
        assert request.headers["cookie"] == "SUB=synthetic-weibo-session"
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": "龙田街道道路维修已完成，现场恢复通行。",
                "isLongText": False,
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": [],
            },
        )

    app, browser, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert created.status_code == 202, created.text
        client.portal.call(finish, app.state.report_generation_service)
        current = client.get(
            f"/api/v1/report-generations/{created.json()['id']}"
        ).json()
        assert current["status"] == "completed"
        assert current["analysis"]["counts"]["completed"] == 1
        assert current["report"]["coverage"]["ready"] == 1
        assert model.counts["initial"] == 1 and model.counts["judgment"] == 1
        assert len(requests) == 1
        assert (
            str(requests[0].url)
            == "https://weibo.com/ajax/statuses/show?id=3600375418559878&isGetLongText=true"
        )
        assert browser.visits == []
        # A new report with the same selected successful summary needs no lookup.
        second = client.post("/api/v1/report-generations", json=generation_request([1]))
        client.portal.call(finish, app.state.report_generation_service)
        repeated = client.get(
            f"/api/v1/report-generations/{second.json()['id']}"
        ).json()
        assert repeated["status"] == "completed"
        assert repeated["analysis"]["counts"]["reused"] == 1
        assert len(requests) == 1 and model.counts["initial"] == 1


async def wait_status(service, generation_id, status):
    async with asyncio.timeout(5):
        while True:
            value = await asyncio.to_thread(
                service.repository.read_generation, generation_id
            )
            if value.status == status:
                return value
            await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    "response_status,reason",
    [
        (401, "login_required"),
        (403, "manual_challenge_required"),
        (429, "platform_blocked_or_rate_limited"),
    ],
)
def test_access_barrier_holds_task_and_browser_until_explicit_continue(
    tmp_path, response_status, reason
):
    allowed = False

    def response(request):
        if not allowed:
            if response_status == 403:
                return httpx.Response(403, content="请完成安全验证".encode())
            return httpx.Response(response_status)
        return httpx.Response(
            200,
            json={
                "ok": 1,
                "id": 3600375418559878,
                "idstr": "3600375418559878",
                "text": "龙田街道道路维修完成。",
                "isLongText": False,
                "created_at": "Thu Sep 03 10:00:00 +0800 2026",
                "pic_ids": [],
            },
        )

    app, browser, model, requests = native_environment(tmp_path, response=response)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        service = app.state.report_generation_service
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        generation_id = created["id"]
        paused = client.portal.call(
            wait_status, service, generation_id, "paused_for_manual_action"
        )
        assert paused.pause_reason == reason
        assert (
            paused.analysis.counts.failed
            == paused.analysis.counts.input_incomplete
            == 0
        )
        assert paused.analysis.counts.queued == 1
        assert len(requests) == 1 and model.counts["initial"] == 0
        control = {"expected_revision": paused.control_revision}
        shown = client.post(
            f"/api/v1/report-generations/{generation_id}/manual-page", json=control
        )
        assert shown.status_code == 200, shown.text
        assert browser.shown == 1
        for _ in range(3):
            assert (
                client.get(f"/api/v1/report-generations/{generation_id}").json()[
                    "status"
                ]
                == paused.status
            )
        assert len(requests) == 1
        # A browser-dependent queued task cannot block stored-only work.
        database = service.repository.database
        seed_run(database, 1, start=3600375418559888)
        seed_run(database, 1, start=3600375418559999)
        save_body(database, 3)
        queued = client.post(
            "/api/v1/report-generations", json=generation_request([2])
        ).json()
        offline = client.post(
            "/api/v1/report-generations", json=generation_request([3])
        ).json()
        client.portal.call(wait_status, service, offline["id"], "completed")
        waiting = client.get(f"/api/v1/report-generations/{queued['id']}").json()
        assert waiting["analysis"]["counts"]["queued"] == 1
        assert len(requests) == 1 and model.counts["initial"] == 1
        # Showing the window did not count as consent to resume.
        allowed = True
        resumed = client.post(
            f"/api/v1/report-generations/{generation_id}/continue", json=control
        )
        assert resumed.status_code == 200, resumed.text
        client.portal.call(wait_status, service, generation_id, "completed")
        assert model.counts["initial"] == 2
        # A replayed Continue may read progress, but cannot initiate fresh work.
        again = client.post(
            f"/api/v1/report-generations/{generation_id}/continue", json=control
        )
        assert again.status_code == 200, again.text
        assert again.json()["control_revision"] == paused.control_revision + 1


def test_plain_403_is_a_neutral_item_failure_and_never_requests_manual_verification(
    tmp_path,
):
    app, browser, model, requests = native_environment(
        tmp_path, response=lambda request: httpx.Response(403)
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        value = client.get(f"/api/v1/report-generations/{created['id']}").json()
        assert value["status"] in ("completed", "empty")
        item = client.get(
            f"/api/v1/content-analysis-jobs/{created['analysis']['id']}/items"
        ).json()["items"][0]
        assert item["error"]["code"] == "source_access_denied"
        assert item["status"] == "input_incomplete"
        assert model.calls == []
        assert browser.shown == 0
        assert len(requests) == 1


@pytest.mark.parametrize(
    "status,body,code",
    [
        (404, {}, "source_content_unavailable"),
        (200, {"ok": 0, "msg": "内容不存在"}, "source_content_unavailable"),
        (200, {"changed": True}, "source_structure_changed"),
    ],
)
def test_unreadable_posts_have_specific_failures_and_never_use_search_preview(
    tmp_path, status, body, code
):
    app, browser, model, requests = native_environment(
        tmp_path, response=lambda request: httpx.Response(status, json=body)
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        value = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        items = client.get(
            f"/api/v1/content-analysis-jobs/{value['analysis']['id']}/items"
        ).json()
        assert items["items"][0]["error"]["code"] == code
        assert model.counts["initial"] == 0
        assert len(requests) == 1


def test_old_continue_cannot_resume_a_new_challenge_and_restart_never_retries(tmp_path):
    app, _, model, requests = native_environment(
        tmp_path,
        response=lambda request: httpx.Response(403, content="请完成安全验证".encode()),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        created = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        ).json()
        service = app.state.report_generation_service
        paused = client.portal.call(
            wait_status, service, created["id"], "paused_for_manual_action"
        )
        path = f"/api/v1/report-generations/{created['id']}/continue"
        assert (
            client.post(
                path, json={"expected_revision": paused.control_revision}
            ).status_code
            == 200
        )
        second = client.portal.call(
            wait_status, service, created["id"], "paused_for_manual_action"
        )
        assert second.control_revision == paused.control_revision + 2
        assert (
            client.post(
                path, json={"expected_revision": paused.control_revision}
            ).status_code
            == 409
        )
        assert len(requests) == 2 and not model.calls
    # Same durable database, fresh runtime: reads do not touch either account or model.
    with TestClient(app, base_url="http://127.0.0.1") as client:
        value = client.get(f"/api/v1/report-generations/{created['id']}").json()
        assert value["status"] == "interrupted" and value["pause_reason"] is None
        assert value["analysis"]["counts"]["interrupted"] == 1
        assert len(requests) == 2
