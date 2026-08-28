"""Independent synthetic HTTP acceptance; use a fresh isolated preview database."""

import time

from fastapi.testclient import TestClient
from preview_app import app, database_path, worker


def wait_paused(client, batch_id, position):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/search-batches/{batch_id}")
        assert response.status_code == 200
        payload = response.json()
        if (
            payload["status"] == "paused_for_manual_action"
            and payload["current_item_position"] == position
        ):
            return payload
        time.sleep(0.01)
    raise AssertionError("Synthetic batch did not pause at the expected platform.")


def control(batch, position):
    attempt = batch["items"][position]["latest_attempt"]
    return {
        "item_position": position,
        "expected_run_id": attempt["run"]["id"] if attempt else None,
        "expected_revision": batch["control_revision"],
    }


def verify():
    assert not database_path.exists(), (
        "Use a fresh isolated database for each verification."
    )
    with TestClient(app) as client:
        rule_response = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "人工恢复验收（模拟）",
                "monitoring_objects": [f"对象 {index}" for index in range(1, 9)],
                "issue_keywords": [],
                "enabled": True,
            },
        )
        assert rule_response.status_code == 201
        created = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": rule_response.json()["id"],
                "platforms": ["toutiao", "wb"],
                "max_results_per_term": 10,
            },
        )
        assert created.status_code == 202
        batch_id = created.json()["id"]
        base = f"/api/v1/search-batches/{batch_id}"
        paused = wait_paused(client, batch_id, 0)
        first = paused["items"][0]
        assert first["completed_term_count"] == 6
        assert first["remaining_term_count"] == 2
        assert first["next_term_position"] == 6
        assert first["total_count"] == 2
        assert first["latest_attempt"]["run"]["status"] == "structure_changed"
        assert paused["items"][1]["attempt_count"] == 0
        original_control = control(paused, 0)

        stale = {
            **original_control,
            "expected_revision": paused["control_revision"] + 1,
        }
        rejected = client.post(base + "/continue", json=stale)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "search_batch_state_changed"
        shown = client.post(base + "/manual-page", json=original_control)
        assert shown.status_code == 200
        assert shown.json() == {"outcome": "opened_homepage"}
        assert worker.toutiao_attempts == 1
        assert client.get(base).json()["items"][0]["attempt_count"] == 1

        continued = client.post(base + "/continue", json=original_control)
        assert continued.status_code == 202
        next_pause = wait_paused(client, batch_id, 1)
        complete = next_pause["items"][0]
        assert complete["status"] == "completed"
        assert complete["attempt_count"] == 2
        assert complete["completed_term_count"] == 8
        assert complete["remaining_term_count"] == 0
        assert complete["next_term_position"] is None
        assert worker.toutiao_terms == [
            tuple(f"对象 {index}" for index in range(1, 9)),
            ("对象 7", "对象 8"),
        ]
        assert (
            complete["new_count"],
            complete["repeated_count"],
            complete["total_count"],
        ) == (3, 0, 3)
        attempts = client.get(base + "/items/0/attempts").json()["attempts"]
        assert [attempt["attempt_number"] for attempt in attempts] == [2, 1]
        attempts = sorted(attempts, key=lambda attempt: attempt["attempt_number"])
        assert [attempt["run"]["status"] for attempt in attempts] == [
            "structure_changed",
            "completed_with_results",
        ]
        assert [attempt["run"]["total_count"] for attempt in attempts] == [2, 2]
        results = client.get(base + "/items/0/results?kind=all&limit=50&offset=0")
        assert results.status_code == 200
        page = results.json()
        assert page["total"] == 3
        by_id = {item["platform_content_id"]: item for item in page["results"]}
        assert set(by_id) == {"900001", "900002", "900003"}
        assert by_id["900001"]["source_run_id"] == attempts[0]["run"]["id"]
        assert by_id["900002"]["source_run_id"] == attempts[0]["run"]["id"]
        assert by_id["900003"]["source_run_id"] == attempts[1]["run"]["id"]
        assert by_id["900002"]["matched_terms"] == ["对象 7"]
        assert all(item["kind"] == "new" for item in by_id.values())

        rejected = client.post(base + "/skip", json=original_control)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "search_batch_state_changed"
        skipped = client.post(base + "/skip", json=control(next_pause, 1))
        assert skipped.status_code == 202
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            final = client.get(base).json()
            if final["status"] == "completed_with_failures":
                break
            time.sleep(0.01)
        assert final["status"] == "completed_with_failures"
        assert final["items"][1]["status"] == "skipped"
        assert final["terminal_item_count"] == 2
        assert final["items"][0]["total_count"] == 3
        assert worker.toutiao_attempts == 2

    with TestClient(app) as client:
        restarted = client.get(base).json()
        assert restarted["status"] == "completed_with_failures"
        assert worker.toutiao_attempts == 2
    print(
        "PASS: seventh-term recovery, partial-result union, stale controls, show-only, skip and restart persistence (synthetic HTTP)."
    )


if __name__ == "__main__":
    verify()
