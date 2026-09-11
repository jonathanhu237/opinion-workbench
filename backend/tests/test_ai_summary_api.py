"""Local-only manual routes, strict public shapes and no automatic work."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from summary_fixtures import BASE, KEY, MODEL, MediaWorker, ModelClient, seed_run

from longtian_api.api.v1.ai_summaries import get_summary_service
from longtian_api.database import Database
from longtian_api.main import create_app
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.content_enrichment import ContentEnrichmentService
from longtian_api.services.enrichment_staging import MediaSpool
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_access import (
    PlatformAccessCoordinator,
    PlatformAccessService,
)
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.summary_errors import SUMMARY_ERRORS


def api_fixture(tmp_path):
    database = Database(tmp_path / "api.sqlite3")
    database.initialize()
    source = seed_run(database, 2)
    model = ModelClient()
    media = MediaWorker()

    platform = PlatformConnectionService()
    virtual_monotonic = [0.0]
    virtual_wall = [datetime(2026, 1, 1, tzinfo=UTC)]

    async def virtual_sleep(seconds):
        virtual_monotonic[0] += seconds
        virtual_wall[0] += timedelta(seconds=seconds)

    def access_factory(db):
        service = PlatformAccessService(db)
        service.coordinator = PlatformAccessCoordinator(
            service.repository,
            clock=lambda: virtual_monotonic[0],
            wall_clock=lambda: virtual_wall[0],
            sleep=virtual_sleep,
        )
        return service

    def enrichment_factory(db, platform_service):
        model.coordinator = platform_service.browser_operations
        return ContentEnrichmentService(
            repository=SearchRunRepository(db),
            worker=media,
            browser_operations=platform_service.browser_operations,
            spool=MediaSpool(tmp_path / "media"),
        )

    app = create_app(
        platform_connection_service_factory=lambda: platform,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database.path
        ),
        platform_access_service_factory=access_factory,
        ai_settings_service_factory=lambda db: AISettingsService(db, client=model),
        content_enrichment_service_factory=enrichment_factory,
    )
    return app, source, model, media


def body(**overrides):
    return {
        "request_id": str(uuid4()),
        "force_refresh": False,
        "configuration_revision": 1,
        **overrides,
    }


def saved(client):
    response = client.put(
        "/api/v1/ai-settings", json={"base_url": BASE, "model": MODEL, "api_key": KEY}
    )
    assert response.status_code == 200


def assert_error(response, code):
    status, message = ({**AI_ERROR_CONTRACTS, **SUMMARY_ERRORS})[code]
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert KEY not in response.text


def test_api_manual_full_scope_history_items_and_replay(tmp_path):
    app, source, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        history = f"/api/v1/search-runs/{source}/ai-summaries"
        assert client.get(history).json() == {"summaries": [], "next_before_id": None}
        assert not (tmp_path / "media").exists()
        assert model.calls == media.calls == []
        payload = body()
        response = client.post(history, json=payload)
        assert (
            response.status_code == 202
            and response.headers["cache-control"] == "no-store"
        )
        summary_id = response.json()["id"]

        async def wait():
            await asyncio.wait_for(app.state.ai_summary_service._runner, 5)

        client.portal.call(wait)
        result = client.get(f"/api/v1/ai-summaries/{summary_id}")
        assert result.status_code == 200 and result.json()["status"] == "completed"
        assert result.json()["counts"]["total"] == 2
        assert result.json()["base_url"] == BASE and result.json()["model"] == MODEL
        items = client.get(
            f"/api/v1/ai-summaries/{summary_id}/items", params={"limit": 1, "offset": 1}
        ).json()
        assert items["total"] == 2 and len(items["items"]) == 1 and items["offset"] == 1
        assert items["items"][0]["source"]["source_run_id"] == source
        assert client.post(history, json=payload).json() == result.json()
        assert (
            client.post(f"/api/v1/ai-summaries/{summary_id}/cancel", json={}).json()
            == result.json()
        )
        assert len(model.calls) == 3 and len(media.calls) == 2
        assert KEY not in result.text and "blob_ref" not in str(items)
        for _ in range(2):
            client.get(history)
            client.get(f"/api/v1/ai-summaries/{summary_id}")
            client.get(f"/api/v1/ai-summaries/{summary_id}/items")
        assert len(model.calls) == 3
    assert model.closed


@pytest.mark.parametrize(
    "payload",
    [
        {},
        body(request_id="not-a-uuid"),
        body(request_id=str(uuid4()).upper()),
        body(force_refresh="false"),
        body(configuration_revision=True),
        body(configuration_revision=0),
        body(unexpected="value"),
    ],
)
def test_strict_create_body_rejects_before_work(tmp_path, payload):
    app, source, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        assert_error(
            client.post(f"/api/v1/search-runs/{source}/ai-summaries", json=payload),
            "invalid_request",
        )
        assert model.calls == media.calls == []


def test_read_errors_revision_and_mutation_security_are_exact(tmp_path):
    app, source, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        path = f"/api/v1/search-runs/{source}/ai-summaries"
        assert_error(client.post(path, json=body()), "ai_configuration_required")
        saved(client)
        assert_error(
            client.post(path, json=body(configuration_revision=2)),
            "ai_configuration_changed",
        )
        assert_error(client.get("/api/v1/ai-summaries/999"), "ai_summary_not_found")
        assert_error(
            client.get("/api/v1/ai-summaries/999/items"), "ai_summary_not_found"
        )
        assert_error(
            client.get("/api/v1/search-runs/999/ai-summaries"), "search_run_not_found"
        )
        assert_error(
            client.post(path, json=body(), headers={"Origin": "https://evil.example"}),
            "ai_request_forbidden",
        )
        assert_error(client.post(path, content="{}"), "ai_json_required")
        assert_error(
            client.post("/api/v1/ai-summaries/999/cancel", json={}),
            "ai_summary_not_found",
        )
        assert_error(
            client.post("/api/v1/ai-summaries/999/cancel", json={"force": True}),
            "invalid_request",
        )
        for suffix in ("?limit=0", "?limit=51", "?before_id=0"):
            assert_error(client.get(path + suffix), "invalid_request")
        assert model.calls == media.calls == []


def test_openapi_summary_models_and_zero_work_startup(tmp_path):
    app, _, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        document = client.get("/openapi.json").json()
        operation = document["paths"][
            "/api/v1/search-runs/{source_run_id}/ai-summaries"
        ]["post"]
        assert set(operation["responses"]) >= {
            "202",
            "403",
            "404",
            "409",
            "415",
            "422",
            "503",
        }
        assert set(document["components"]["schemas"]["SummaryCreate"]["required"]) == {
            "request_id",
            "force_refresh",
            "configuration_revision",
        }
        assert model.calls == media.calls == []
        assert not (tmp_path / "media").exists()


def test_summary_errors_are_no_store_including_dependency_and_validation_failures(
    tmp_path,
):
    app, source, model, media = api_fixture(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        path = f"/api/v1/search-runs/{source}/ai-summaries"
        responses = [
            client.get("/api/v1/ai-summaries/999"),
            client.get("/api/v1/ai-summaries/0"),
            client.post(path, json=body()),
            client.post(path, json={}),
            client.post(path, content="{}"),
            client.post(path, json=body(), headers={"Origin": "https://evil.example"}),
        ]
        assert [response.status_code for response in responses] == [
            404,
            422,
            409,
            422,
            415,
            403,
        ]
        assert_error(responses[1], "invalid_request")
        assert_error(responses[3], "invalid_request")
        assert [response.headers.get("cache-control") for response in responses] == [
            "no-store"
        ] * len(responses)
        assert model.calls == media.calls == []


def test_summary_no_store_keeps_existing_http_error_status_detail_and_headers(tmp_path):
    app, _, model, media = api_fixture(tmp_path)
    detail = {
        "code": "ai_summary_unavailable",
        "message": "汇总服务暂时不可用，请稍后重试。",
    }

    def unavailable():
        raise HTTPException(
            status_code=503,
            detail=detail,
            headers={"Retry-After": "5", "cache-control": "max-age=60"},
        )

    app.dependency_overrides[get_summary_service] = unavailable
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/v1/ai-summaries/1")
        assert response.status_code == 503 and response.json() == {"detail": detail}
        assert response.headers.get_list("cache-control") == ["no-store"]
        assert response.headers["retry-after"] == "5"
        assert model.calls == media.calls == []
