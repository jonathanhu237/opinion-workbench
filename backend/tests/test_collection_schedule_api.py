"""Strict no-store/local-only scheduling API with zero implicit operations."""

import asyncio
from datetime import datetime, timedelta

import pytest
from collection_schedule_fixtures import payload
from fastapi.testclient import TestClient
from test_content_analysis_api import api_fixture

from longtian_api.main import _shutdown_services
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS
from longtian_api.services.collection_schedule_errors import ERRORS

ROOT = "/api/v1/collection-schedules"


def assert_error(response, code):
    status, message = {**AI_ERROR_CONTRACTS, **ERRORS}[code]
    assert response.status_code == status, response.text
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert response.headers["cache-control"] == "no-store"


def test_crud_history_guarded_update_and_rollout_off(tmp_path):
    app, _, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(ROOT).json() == {"schedules": [], "next_before_id": None}
        response = client.post(ROOT, json=payload())
        assert (
            response.status_code == 201
            and response.headers["cache-control"] == "no-store"
        )
        saved = response.json()
        assert not saved["enabled"] and not saved["available"]
        assert saved["rule_state"] == "enabled" and saved["latest_occurrence"] is None
        path = f"{ROOT}/{saved['id']}"
        assert client.get(path).json() == saved
        assert client.get(f"{path}/occurrences").json() == {
            "occurrences": [],
            "next_before_id": None,
        }
        update = {**payload(), "expected_revision": 1, "enabled": True}
        response = client.put(path, json=update)
        assert response.status_code == 200
        changed = response.json()
        assert changed["enabled"] and not changed["available"]
        assert (
            changed["revision"] == 2 and changed["next_due_at"] > changed["anchor_at"]
        )
        assert_error(client.put(path, json=update), "collection_schedule_changed")
        assert client.get(ROOT).json()["schedules"] == [changed]
        assert model.calls == media.calls == []
        assert app.state.collection_schedule_service._task is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"enabled": True},
        {"prompt": "not allowed"},
        {"monitoring_rule_id": True},
        {"monitoring_rule_id": 9007199254740992},
        {"interval": {"value": 1.5, "unit": "hours"}},
        {"interval": {"value": "1", "unit": "minutes"}},
        {"interval": {"value": True, "unit": "minutes"}},
        {"interval": {"value": 0, "unit": "minutes"}},
        {"interval": {"value": 1, "unit": "days"}},
        {"platforms": []},
        {"platforms": ["wb", "wb"]},
        {"platforms": ["unknown"]},
        {"max_results_per_term": 51},
        {"max_results_per_term": "1"},
    ],
)
def test_structural_input_rejected_without_schedule(tmp_path, mutation):
    app, _, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert_error(client.post(ROOT, json=payload(**mutation)), "invalid_request")
        assert client.get(ROOT).json()["schedules"] == []
        assert model.calls == media.calls == []


@pytest.mark.parametrize(
    "suffix", ["/0", "/9007199254740992", "?limit=101", "?before_id=0", "?limit=no"]
)
def test_bad_ids_queries_have_no_store(tmp_path, suffix):
    app, *_ = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert_error(client.get(ROOT + suffix), "invalid_request")


def test_exact_domain_errors_deleted_rule_and_sanitized_storage(tmp_path, monkeypatch):
    app, _, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert_error(client.get(ROOT + "/99"), "collection_schedule_not_found")
        assert_error(
            client.get(ROOT + "/99/occurrences"), "collection_schedule_not_found"
        )
        assert_error(
            client.post(ROOT, json=payload(monitoring_rule_id=99)),
            "monitoring_rule_not_found",
        )
        assert_error(
            client.post(ROOT, json=payload(interval={"value": 721, "unit": "hours"})),
            "invalid_collection_interval",
        )
        saved = client.post(ROOT, json=payload()).json()
        path = f"{ROOT}/{saved['id']}"
        assert_error(client.put(path, json=payload()), "invalid_request")
        client.put(
            "/api/v1/monitoring-rules/1",
            json={
                "name": "规则",
                "monitoring_objects": ["对象"],
                "issue_keywords": [],
                "enabled": False,
            },
        )
        assert client.get(path).json()["rule_state"] == "disabled"
        assert_error(
            client.put(
                path, json={**payload(), "expected_revision": 1, "enabled": True}
            ),
            "monitoring_rule_disabled",
        )
        client.put(
            "/api/v1/monitoring-rules/1",
            json={
                "name": "规则",
                "monitoring_objects": [str(n) for n in range(21)],
                "issue_keywords": [],
                "enabled": True,
            },
        )
        assert client.get(path).json()["rule_state"] == "invalid"
        assert_error(
            client.put(
                path, json={**payload(), "expected_revision": 1, "enabled": True}
            ),
            "too_many_search_terms",
        )
        client.delete("/api/v1/monitoring-rules/1")
        assert client.get(path).json()["rule_state"] == "deleted"
        disabled = client.put(
            path,
            json={
                **payload(monitoring_rule_id=None),
                "expected_revision": 1,
                "enabled": False,
            },
        )
        assert disabled.status_code == 200

        def fail(*args, **kwargs):
            raise RuntimeError("SQL private-database-path credential-sentinel")

        monkeypatch.setattr(
            app.state.collection_schedule_service.repository, "list", fail
        )
        response = client.get(ROOT)
        assert_error(response, "collection_schedule_storage_unavailable")
        assert "private" not in response.text and "sentinel" not in response.text
        assert model.calls == media.calls == []


def test_mutation_origin_json_and_openapi_contract(tmp_path):
    app, *_ = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert_error(
            client.post(
                ROOT, json=payload(), headers={"origin": "https://evil.example"}
            ),
            "ai_request_forbidden",
        )
        assert_error(
            client.post(ROOT, json=payload(), headers={"host": "evil.example"}),
            "ai_request_forbidden",
        )
        assert_error(
            client.post(ROOT, content="{}", headers={"content-type": "text/plain"}),
            "ai_json_required",
        )
        assert_error(
            client.post(
                ROOT, content="{", headers={"content-type": "application/json"}
            ),
            "invalid_request",
        )
        responses = client.get("/openapi.json").json()["paths"][ROOT]["post"][
            "responses"
        ]
        assert {"201", "403", "404", "409", "415", "422", "503"} <= set(responses)


@pytest.mark.parametrize(
    "corruption",
    [
        "empty_platforms",
        "platform_order",
        "created_at",
        "anchor_at",
        "next_due_at",
        "rule_name",
        "missing_rule",
        "occurrence_date",
        "occurrence_range",
        "occurrence_state",
        "occurrence_link",
        "occurrence_count",
    ],
)
def test_corrupt_schedule_projections_fail_closed_without_work(tmp_path, corruption):
    app, _, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        config = payload(platforms=["wb", "xhs"])
        saved = client.post(ROOT, json=config).json()
        path = f"{ROOT}/{saved['id']}"
        saved = client.put(
            path, json={**config, "expected_revision": 1, "enabled": True}
        ).json()
        owner = app.state.collection_schedule_service
        due = datetime.fromisoformat(saved["next_due_at"])
        claim = owner.repository.advance_due(due)[0]
        with owner.repository.database.connect() as connection:
            if corruption == "empty_platforms":
                connection.execute("DELETE FROM collection_schedule_platforms")
            elif corruption == "platform_order":
                connection.execute(
                    "UPDATE collection_schedule_platforms SET position=4-position"
                )
            elif corruption == "created_at":
                connection.execute(
                    "UPDATE collection_schedules SET created_at=?",
                    ("private-path-credential-sentinel",),
                )
            elif corruption == "anchor_at":
                connection.execute(
                    "UPDATE collection_schedules SET anchor_at=?",
                    ("2026-08-29T08:00:00+08:00",),
                )
            elif corruption == "next_due_at":
                connection.execute(
                    "UPDATE collection_schedules SET next_due_at=anchor_at"
                )
            elif corruption == "rule_name":
                connection.execute("UPDATE collection_schedules SET rule_name=''")
            elif corruption == "missing_rule":
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute(
                    "UPDATE collection_schedules SET monitoring_rule_id=999"
                )
            elif corruption == "occurrence_date":
                connection.execute(
                    "UPDATE collection_occurrences SET due_at=? WHERE id=?",
                    ("private-path-credential-sentinel", claim.id),
                )
            elif corruption == "occurrence_range":
                connection.execute(
                    """UPDATE collection_occurrences SET status='missed',
                    reason='offline',missed_count=2,missed_until=? WHERE id=?""",
                    ((due - timedelta(minutes=1)).isoformat(), claim.id),
                )
            else:
                connection.execute("PRAGMA ignore_check_constraints=ON")
                if corruption == "occurrence_state":
                    connection.execute(
                        "UPDATE collection_occurrences SET reason='browser_unavailable'"
                    )
                elif corruption == "occurrence_link":
                    connection.execute(
                        "UPDATE collection_occurrences SET dispatched_at=?",
                        (due.isoformat(),),
                    )
                elif corruption == "occurrence_count":
                    connection.execute(
                        "UPDATE collection_occurrences SET missed_count=1"
                    )
        targets = [ROOT, path]
        if corruption.startswith("occurrence_"):
            targets.append(f"{path}/occurrences")
        for target in targets:
            response = client.get(target)
            assert_error(response, "collection_schedule_storage_unavailable")
            assert "private" not in response.text and "sentinel" not in response.text
        assert model.calls == media.calls == []
        assert client.get("/api/v1/search-batches").json()["batches"] == []


def test_deleted_schedule_retains_linked_pause_when_disabled(tmp_path):
    app, _, model, media = api_fixture(tmp_path, 0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved = client.post(ROOT, json=payload()).json()
        path = f"{ROOT}/{saved['id']}"
        saved = client.put(
            path, json={**payload(), "expected_revision": 1, "enabled": True}
        ).json()
        owner = app.state.collection_schedule_service
        due = datetime.fromisoformat(saved["next_due_at"])
        claim = owner.repository.advance_due(due)[0]
        batches = SearchBatchRepository(owner.repository.database)
        batch, _ = batches.create_scheduled_batch(
            claim.dispatch_token,
            app.state.monitoring_rule_service.list_enabled()[0],
            timestamp=due.isoformat(),
        )
        batches.reconcile_interrupted_items()
        owner.repository.reconcile_startup(due)
        assert client.delete("/api/v1/monitoring-rules/1").status_code == 204
        current = client.get(path).json()
        assert current["monitoring_rule_id"] is None
        assert current["rule_state"] == "deleted" and current["revision"] == 2
        occurrence = current["latest_occurrence"]
        assert occurrence["status"] == "interrupted"
        assert occurrence["batch_id"] == batch.id
        assert occurrence["batch_status"] == "paused_for_manual_action"
        response = client.put(
            path,
            json={
                **payload(monitoring_rule_id=None),
                "expected_revision": 2,
                "enabled": False,
            },
        )
        assert response.status_code == 200
        disabled = response.json()
        assert not disabled["enabled"] and disabled["revision"] == 3
        assert disabled["rule_name"] == saved["rule_name"]
        assert disabled["latest_occurrence"] == occurrence
        assert client.get(f"{path}/occurrences").json()["occurrences"] == [occurrence]
        assert model.calls == media.calls == []


def test_shutdown_order_stops_admission_first_even_when_cleanup_fails():
    async def run():
        order = []

        class Owner:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail

            async def shutdown(self):
                order.append(self.name)
                if self.fail:
                    raise RuntimeError("synthetic cleanup failure")

        with pytest.raises(RuntimeError):
            await _shutdown_services(
                [
                    Owner("scheduler", True),
                    Owner("analysis", True),
                    Owner("batch"),
                    Owner("browser"),
                ]
            )
        assert order == ["scheduler", "analysis", "batch", "browser"]

    asyncio.run(run())
