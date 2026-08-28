"""Fixture shape and origin boundaries, with no real services or accounts."""

from collection_schedule_smoke import create_smoke_app
from fastapi.testclient import TestClient


def test_smoke_has_multiple_history_pages_and_only_fake_collection():
    app = create_smoke_app()
    origin = {"origin": "http://127.0.0.1:46081"}
    with TestClient(app, base_url="http://127.0.0.1:46082") as client:
        response = client.get("/api/v1/collection-schedules", headers=origin)
        assert response.headers["access-control-allow-origin"] == origin["origin"]
        schedule = response.json()["schedules"][0]
        assert not schedule["enabled"] and schedule["available"]
        first = client.get(
            f"/api/v1/collection-schedules/{schedule['id']}/occurrences"
        ).json()
        assert len(first["occurrences"]) == 50 and first["next_before_id"] is not None
        second = client.get(
            f"/api/v1/collection-schedules/{schedule['id']}/occurrences?before_id={first['next_before_id']}"
        ).json()
        assert len(second["occurrences"]) == 7
        statuses = {item["status"] for item in first["occurrences"]}
        assert {"skipped", "dispatched", "missed", "interrupted"} <= statuses
        for occurrence in first["occurrences"]:
            if occurrence["batch_id"] is not None:
                assert (
                    client.get(
                        f"/api/v1/search-batches/{occurrence['batch_id']}"
                    ).status_code
                    == 200
                )
        counts = client.get("/api/v1/collection-schedule-smoke/counters").json()
        assert counts == {
            "synthetic_collection_calls": 2,
            "synthetic_model_calls": 0,
            "synthetic_media_calls": 0,
        }
        client.get("/api/v1/collection-schedules")
        assert client.get("/api/v1/collection-schedule-smoke/counters").json() == counts
        denied = client.options(
            "/api/v1/collection-schedules",
            headers={
                "origin": "http://127.0.0.1:46083",
                "access-control-request-method": "PUT",
            },
        )
        assert denied.status_code == 400
