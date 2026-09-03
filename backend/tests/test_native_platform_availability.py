"""Native manual entry rejects unsupported platforms without touching accounts."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_native_text_report import native_environment
from test_native_weibo_discovery import environment
from test_report_generations import generation_request, save_body
from test_search_batches import PlannedSearchWorker, _app, _control, _wait_for_batch
from topic_report_fixtures import finish

from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
)


def seed_history(database, platform, identity):
    repository = SearchRunRepository(database)
    run = repository.create_run(
        monitoring_rule_id=1,
        platform=platform,
        rule_name="历史规则",
        terms=("龙田",),
        max_results_per_term=1,
    )
    repository.mark_running(run.id)
    repository.set_progress(run.id, 0)
    templates = {
        "dy": "https://www.douyin.com/video/",
        "ks": "https://www.kuaishou.com/short-video/",
        "xhs": "https://www.xiaohongshu.com/explore/",
        "toutiao": "https://www.toutiao.com/article/",
    }
    repository.observe_item(
        run_id=run.id,
        term_position=0,
        item=SearchContentInput(
            identity,
            "post",
            "历史搜索摘要",
            "不是完整正文",
            "",
            "",
            "",
            templates[platform] + identity + ("/" if platform == "toutiao" else ""),
            "2026-08-28T00:00:00+00:00",
        ),
    )
    repository.complete_term(run.id, 0, 1)
    repository.finish(run.id, "completed_with_results")
    with database.connect() as connection:
        return connection.execute(
            "SELECT id FROM search_contents WHERE platform=? AND platform_content_id=?",
            (platform, identity),
        ).fetchone()[0]


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "toutiao"])
def test_unsupported_history_reuses_saved_content_and_keeps_url_only_gaps(
    tmp_path,
    platform,
):
    def forbidden(request):
        raise AssertionError("historical materials must not access any platform")

    app, browser, model, requests = native_environment(tmp_path, response=forbidden)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        database = app.state.report_generation_service.repository.database
        save_body(database, 1)
        ready = seed_history(database, platform, "1" * 24)
        pending = seed_history(database, "dy", "1234567890")
        save_body(database, ready)
        first = client.post(
            "/api/v1/report-generations", json=generation_request([1, ready])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        assert (
            client.get(f"/api/v1/report-generations/{first['id']}").json()["status"]
            == "completed"
        )
        repeat = client.post(
            "/api/v1/report-generations", json=generation_request([ready, pending])
        ).json()
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{repeat['id']}").json()
        assert (
            result["status"] == "completed"
            and result["analysis"]["counts"]["reused"] == 1
        )
        attempts = client.get(
            f"/api/v1/content-analysis-jobs/{repeat['analysis']['id']}/items"
        ).json()["items"]
        assert attempts[1]["status"] == "unsupported"
        assert attempts[1]["error"]["code"] == "platform_not_supported"
        library = generation_request([pending])
        library["selection"] = {"kind": "library_pending", "include_failed": True}
        library["request_id"] = str(uuid4())
        selected = client.post("/api/v1/report-generations", json=library).json()
        assert selected["selection"]["result_ids"] == [pending]
        client.portal.call(finish, app.state.report_generation_service)
        for path in (
            "/api/v1/results?limit=1",
            "/api/v1/results?limit=1&offset=1",
            f"/api/v1/results/{ready}/origins",
            f"/api/v1/topic-reports/{result['report']['id']}",
        ):
            assert client.get(path).status_code == 200
        assert model.counts["initial"] == 2 and not requests and browser.visits == []


@pytest.mark.parametrize("unsupported_current", [True, False])
def test_paused_batch_cannot_resume_unsupported_current_or_future_platform(
    tmp_path, unsupported_current
):
    current = "xhs" if unsupported_current else "wb"
    worker = PlannedSearchWorker({current: ["manual_challenge_required"]})
    app = _app(tmp_path / "capability-drift.sqlite3", worker)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["xhs"] if unsupported_current else ["wb", "xhs"],
                "max_results_per_term": 1,
            },
        )
        assert response.status_code == 202
        identity = response.json()["id"]
        _wait_for_batch(client, identity, {"paused_for_manual_action"})
        control = _control(client, identity)
        # Simulate a capability change while a legacy batch retains its intent.
        worker.supported_platforms = frozenset({"wb"})
        resumed = client.post(
            f"/api/v1/search-batches/{identity}/continue", json=control
        )
        assert resumed.status_code == 409
        assert resumed.json()["detail"]["code"] == "search_platform_not_available"
        if unsupported_current:
            shown = client.post(
                f"/api/v1/search-batches/{identity}/manual-page", json=control
            )
            assert shown.status_code == 409
        assert worker.calls == [current]
        assert (
            client.post(
                f"/api/v1/search-batches/{identity}/cancel",
                json={"expected_revision": control["expected_revision"]},
            ).status_code
            == 202
        )


def test_native_catalog_exposes_only_weibo_without_browser_or_network(tmp_path):
    app, browser = environment(tmp_path, [])
    with TestClient(app) as client:
        response = client.get("/api/v1/platform-connections")
        assert response.status_code == 200
        values = {value["platform"]: value for value in response.json()["platforms"]}
        assert values["wb"]["availability"] == "enabled"
        assert all(
            values[p]["availability"] == "coming_soon"
            and values[p]["status"] == "coming_soon"
            for p in ("xhs", "dy", "ks", "toutiao")
        )
        assert browser.visits == []


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "toutiao"])
def test_native_unsupported_search_and_connection_are_rejected_before_admission(
    tmp_path, platform
):
    app, browser = environment(tmp_path, [])
    with TestClient(app, base_url="http://127.0.0.1") as client:
        connection = client.post(
            f"/api/v1/platform-connections/{platform}/attempts", json={}
        )
        assert connection.status_code == 409, connection.text
        single = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": platform,
                "max_results_per_term": 1,
            },
        )
        assert (
            single.status_code == 409
            and single.json()["detail"]["code"] == "search_platform_not_available"
        )
        batch = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb", platform],
                "max_results_per_term": 1,
            },
        )
        assert (
            batch.status_code == 409
            and batch.json()["detail"]["code"] == "search_platform_not_available"
        )
        assert client.get("/api/v1/search-runs").json()["runs"] == []
        assert client.get("/api/v1/search-batches").json()["batches"] == []
        assert browser.visits == []
