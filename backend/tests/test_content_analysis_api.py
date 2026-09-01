"""Strict public HTTP contract, read-only inspection and explicit saved intent."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from initial_analysis_fixtures import UnderstandingClient, finish
from summary_fixtures import BASE, KEY, MODEL, MediaWorker, seed_run

from longtian_api.database import Database
from longtian_api.main import create_app
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.analysis_errors import ERRORS
from longtian_api.services.content_enrichment import ContentEnrichmentService
from longtian_api.services.enrichment_staging import MediaSpool
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService


def api_fixture(tmp_path, count=2, **app_options):
    # A/B contract fixture keeps the prior partial-rollout gate explicit. C
    # integration opts into its complete fake pipeline separately.
    app_options = {
        "analysis_automation_available": False,
        "collection_automation_available": False,
        "topic_reports_available": False,
        **app_options,
    }
    database = Database(tmp_path / "api.sqlite3")
    database.initialize()
    seed_run(database, count)
    model, media = UnderstandingClient(), MediaWorker()

    async def forbidden_launcher(*args, **kwargs):
        raise AssertionError("isolated tests cannot start a real browser worker")

    platform = PlatformConnectionService(process_launcher=forbidden_launcher)

    def enrichment_factory(db, owner):
        model.coordinator = owner.browser_operations
        return ContentEnrichmentService(
            repository=SearchRunRepository(db),
            worker=media,
            browser_operations=owner.browser_operations,
            spool=MediaSpool(tmp_path / "media"),
        )

    app = create_app(
        platform_connection_service_factory=lambda: platform,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database.path
        ),
        ai_settings_service_factory=lambda db: AISettingsService(db, client=model),
        content_enrichment_service_factory=enrichment_factory,
        ai_frontend_origins=("http://127.0.0.1:46081",),
        **app_options,
    )
    return app, database, model, media


def saved(client):
    assert (
        client.put(
            "/api/v1/ai-settings",
            json={"base_url": BASE, "model": MODEL, "api_key": KEY},
        ).status_code
        == 200
    )


def body(client, **overrides):
    return {
        "request_id": str(uuid4()),
        "configuration_revision": 1,
        "initial_prompt": {"mode": "default"},
        "force_refresh": False,
        "selection": {"kind": "all_never_started"},
        **overrides,
    }


def assert_error(response, code):
    status, message = ({**AI_ERROR_CONTRACTS, **ERRORS})[code]
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text


def test_public_contract_freezes_full_scope_and_reads_saved_text(tmp_path):
    app, database, model, media = api_fixture(tmp_path, 0)
    source = seed_run(database, 101)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        results = client.get("/api/v1/results?limit=1&offset=100").json()
        assert results["total"] == results["eligible_count"] == 101
        assert len(results["items"]) == 1
        settings = client.get("/api/v1/analysis-settings").json()
        assert settings["automation"]["available"] is False
        assert model.calls == media.calls == []
        payload = body(client)
        response = client.post("/api/v1/content-analysis-jobs", json=payload)
        assert response.status_code == 202, response.text
        job = response.json()["job"]
        assert (
            job["counts"]["total"] == 101
            and job["initial_prompt"] == settings["initial_prompt"]
        )
        client.portal.call(finish, app.state.content_analysis_service)
        current = client.get(f"/api/v1/content-analysis-jobs/{job['id']}").json()
        assert current["counts"]["completed"] == 101
        assert current["usage"]["attempted_requests"] == 101
        items = client.get(
            f"/api/v1/content-analysis-jobs/{job['id']}/items?limit=1&offset=100"
        ).json()
        attempt = items["items"][0]
        assert attempt["position"] == 100 and items["total"] == 101
        assert client.get(f"/api/v1/content-analyses/{attempt['id']}").json() == attempt
        assert client.get(
            f"/api/v1/results/{attempt['source']['result_id']}/analyses"
        ).json()["items"] == [attempt]
        assert (
            client.get("/api/v1/results/1/origins").json()["items"][0]["source_run_id"]
            == source
        )
        assert source != job["id"]
        replay = client.post("/api/v1/content-analysis-jobs", json=payload).json()
        assert replay["job"] == current and replay["admitted_count"] == 101
        assert KEY not in str(items) and "blob_ref" not in str(items)
        assert len(model.calls) == len(media.calls) == 101


@pytest.mark.parametrize(
    "overrides",
    [
        {"configuration_revision": True},
        {"unknown": 1},
        {"request_id": "not-a-uuid"},
        {"selection": {"kind": "all_never_started", "result_ids": [1]}},
        {"selection": {"kind": "explicit", "result_ids": [1, 1]}},
        {"selection": {"kind": "retry", "result_ids": []}},
        {"force_refresh": "false"},
    ],
)
def test_invalid_admissions_have_no_work_and_no_store(tmp_path, overrides):
    app, _, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert_error(
            client.post(
                "/api/v1/content-analysis-jobs", json=body(client, **overrides)
            ),
            "invalid_request",
        )
        assert model.calls == media.calls == []


def test_prompts_are_read_only_and_authorization_keeps_revision_guards(tmp_path):
    app, _, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        old = client.get("/api/v1/analysis-settings").json()
        assert client.put(
            "/api/v1/analysis-settings/prompts/initial",
            json={"expected_version_id": 1, "instructions": "已停用"},
        ).status_code == 404
        assert client.get("/api/v1/analysis-settings").json() == old
        policy = client.put(
            "/api/v1/analysis-settings/automation",
            json={"expected_revision": 1, "enabled": True, "configuration_revision": 1},
        ).json()
        assert policy["automation"]["enabled"] and not policy["automation"]["available"]
        assert policy["automation"]["revision"] == 2
        assert_error(
            client.put(
                "/api/v1/analysis-settings/automation",
                json={
                    "expected_revision": 1,
                    "enabled": False,
                    "configuration_revision": None,
                },
            ),
            "analysis_policy_changed",
        )
        assert_error(
            client.post(
                "/api/v1/content-analysis-jobs",
                json=body(client),
                headers={"Origin": "https://evil.example"},
            ),
            "ai_request_forbidden",
        )
        assert_error(
            client.post("/api/v1/content-analysis-jobs", content="{}"),
            "ai_json_required",
        )
        assert_error(client.get("/api/v1/results/900000"), "result_not_found")
        assert_error(
            client.get("/api/v1/content-analyses/900000"), "content_analysis_not_found"
        )
        assert_error(
            client.get(
                "/api/v1/results?first_seen_from=2026-08-30T00:00:00Z&first_seen_to=2026-08-29T00:00:00Z"
            ),
            "invalid_result_interval",
        )
        assert model.calls == media.calls == []


def test_unexpected_storage_error_is_constant_and_reads_never_start_work(
    tmp_path, monkeypatch, caplog
):
    app, _, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:

        def broken(*args, **kwargs):
            raise RuntimeError("secret /private/path SELECT personal source")

        monkeypatch.setattr(app.state.results_service.repository, "list", broken)
        response = client.get("/api/v1/results")
        assert_error(response, "analysis_storage_unavailable")
        assert "personal" not in response.text + caplog.text
        assert model.calls == media.calls == []
