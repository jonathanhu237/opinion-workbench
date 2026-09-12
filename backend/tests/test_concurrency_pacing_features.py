"""Focused regression tests for report concurrency and platform pacing."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fixture_support import initialize_database, initialize_repository
from initial_analysis_fixtures import environment as initial_environment
from initial_analysis_fixtures import finish as finish_analysis
from initial_analysis_fixtures import request as analysis_request
from summary_fixtures import seed_run
from test_content_analysis_api import saved
from test_report_generations import generation_request, save_body
from topic_report_fixtures import api_environment
from topic_report_fixtures import finish as finish_report

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.platform_access import PlatformAccessRepository
from opinion_workbench_api.schemas.platform_access import (
    PlatformAccessDiagnostic,
    PlatformAccessSnapshot,
    PlatformIntervals,
)
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.platform_access import (
    PlatformAccessBlockedError,
    PlatformAccessCoordinator,
    PlatformCooldownActiveError,
)


async def wait_for_count(values, count):
    # The assertion is about the bounded first wave, not a sub-second
    # scheduling guarantee.  A full backend run can legitimately be busy with
    # SQLite worker threads from preceding isolated TestClient lifespans.
    for _ in range(2_000):
        if len(values) >= count:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"expected {count} values, got {len(values)}")


def test_model_summary_runs_concurrently_after_serial_enrichment(tmp_path):
    async def exercise():
        database, _, service, _, model, worker, _ = initial_environment(
            tmp_path, count=3, media=False
        )
        model.gate = asyncio.Event()
        admission = await service.create(analysis_request(database))
        await model.entered.wait()

        # The producer owns one browser/enrichment session and continues to
        # acquire the next items while the first model request is blocked.
        await wait_for_count(worker.calls, 2)
        assert len(model.calls) == 1

        model.gate.set()
        await finish_analysis(service)
        job = service.repository.read(admission.job.id)
        assert job.status == "completed"
        assert len(worker.calls) == 3
        assert len(model.calls) == 3
        await service.shutdown()

    asyncio.run(exercise())


def test_report_admission_freezes_summary_concurrency_and_access_snapshot(tmp_path):
    app, database, model, _ = api_environment(tmp_path, count=8)
    for result_id in range(1, 9):
        save_body(database, result_id)
    model.block_stage = "initial"
    model.gate = asyncio.Event()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        initial_settings = client.get("/api/v1/platform-access-pacing")
        assert initial_settings.status_code == 200
        assert initial_settings.json()["interval_seconds"] == {
            "wb": 5,
            "dy": 5,
            "ks": 5,
            "xhs": 5,
            "toutiao": 5,
        }
        response = client.post(
            "/api/v1/report-generations",
            json=generation_request(list(range(1, 9))),
        )
        # The helper returns a list; keep the request readable without making
        # the API test depend on a client-side default.
        assert response.status_code == 202, response.text
        generation_id = response.json()["id"]

        client.portal.call(wait_for_count, model.calls, 8)
        running = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert running["analysis"]["summary_concurrency"] == 8
        assert running["analysis"]["platform_access_snapshot"] == {
            "interval_seconds": {
                "wb": 5,
                "dy": 5,
                "ks": 5,
                "xhs": 5,
                "toutiao": 5,
            },
            "basis": "explicit",
        }

        changed = client.put(
            "/api/v1/platform-access-pacing",
            json={
                "expected_revision": 1,
                "interval_seconds": {
                    "wb": 17,
                    "dy": 17,
                    "ks": 17,
                    "xhs": 17,
                    "toutiao": 17,
                },
            },
        )
        assert changed.status_code == 200, changed.text
        model.gate.set()
        client.portal.call(finish_report, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "completed"
        assert result["analysis"]["summary_concurrency"] == 8
        assert result["analysis"]["platform_access_snapshot"]["interval_seconds"] == {
            "wb": 5,
            "dy": 5,
            "ks": 5,
            "xhs": 5,
            "toutiao": 5,
        }
        assert model.counts["initial"] == 8


@pytest.mark.parametrize("summary_concurrency", [1, 2, 4, 8, 16])
def test_report_summary_concurrency_is_bounded_for_each_supported_option(
    tmp_path, summary_concurrency
):
    app, database, model, _ = api_environment(tmp_path, count=summary_concurrency)
    for result_id in range(1, summary_concurrency + 1):
        save_body(database, result_id)
    model.block_stage = "initial"
    model.gate = asyncio.Event()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations",
            json={
                **generation_request(list(range(1, summary_concurrency + 1))),
                "summary_concurrency": summary_concurrency,
            },
        )
        assert response.status_code == 202, response.text
        generation_id = response.json()["id"]

        # All first-wave calls are held before returning. A larger wave would
        # prove that the selected bound was not applied to the model stage.
        client.portal.call(wait_for_count, model.calls, summary_concurrency)
        client.portal.call(asyncio.sleep, 0.02)
        assert len(model.calls) == summary_concurrency
        running = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert running["analysis"]["summary_concurrency"] == summary_concurrency

        client.portal.call(model.gate.set)
        client.portal.call(finish_report, app.state.report_generation_service)
        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "completed"
        assert result["analysis"]["counts"]["completed"] == summary_concurrency
        assert model.counts["initial"] == summary_concurrency


def test_default_eight_processes_216_sources_once_and_hands_off_one_report(tmp_path):
    # ``seed_run`` caps one run at three 50-item terms; two runs provide the
    # requested 216-source synthetic boundary without any external service.
    app, database, model, _ = api_environment(tmp_path, count=150)
    seed_run(database, 66, start=3000)
    source_ids = list(range(1, 217))
    for result_id in source_ids:
        save_body(database, result_id)
    model.block_stage = "initial"
    model.gate = asyncio.Event()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations",
            json=generation_request(source_ids),
        )
        assert response.status_code == 202, response.text
        generation_id = response.json()["id"]
        analysis_id = response.json()["analysis"]["id"]

        client.portal.call(wait_for_count, model.calls, 8)
        client.portal.call(asyncio.sleep, 0.02)
        assert len(model.calls) == 8
        assert response.json()["analysis"]["summary_concurrency"] == 8
        client.portal.call(model.gate.set)
        client.portal.call(finish_report, app.state.report_generation_service)

        result = client.get(f"/api/v1/report-generations/{generation_id}").json()
        assert result["status"] == "completed"
        assert result["analysis"]["counts"]["completed"] == 216
        assert result["report"]["coverage"]["relevant"] == 216
        assert result["report"]["nodes"]["judgments"]["completed"] == 216
        assert model.counts["initial"] == 216
        assert model.counts["judgment"] == 216

        with database.connect() as connection:
            attempts = connection.execute(
                """SELECT COUNT(*),COUNT(DISTINCT content_id)
                   FROM content_analysis_attempts WHERE job_id=?""",
                (analysis_id,),
            ).fetchone()
            reports = connection.execute(
                """SELECT COUNT(*) FROM topic_report_runs
                   WHERE id=?""",
                (result["report"]["id"],),
            ).fetchone()
            judgments = connection.execute(
                """SELECT COUNT(*),COUNT(DISTINCT source_id)
                   FROM topic_report_node_sources n
                   JOIN topic_report_nodes node ON node.id=n.node_id
                   WHERE node.report_id=? AND node.kind='judgment'""",
                (result["report"]["id"],),
            ).fetchone()
        assert tuple(attempts) == (216, 216)
        assert tuple(reports) == (1,)
        assert tuple(judgments) == (216, 216)


def test_model_rate_limit_retry_keeps_unknown_attempts_in_usage(tmp_path):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database)
    model.answers["initial"] = [
        AIError(
            "ai_rate_limited",
            provider_status_code=429,
            provider_code="rate_limit",
            retry_after_seconds=0,
        )
    ]

    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        response = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert response.status_code == 202, response.text
        client.portal.call(finish_report, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{response.json()['id']}"
        ).json()

    usage = result["analysis"]["usage"]
    assert result["status"] == "completed"
    assert usage["attempted_requests"] == 2
    assert usage["accounted_requests"] == 1
    assert usage["complete"] is False
    assert result["analysis"]["model_retry_notice"]["action"] == "retrying"
    assert model.counts["initial"] == 2


def test_report_rejects_unsupported_summary_concurrency_without_work(tmp_path):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        payload = generation_request([1])
        payload["summary_concurrency"] = 3
        response = client.post("/api/v1/report-generations", json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"
        assert model.calls == []


def test_platform_access_settings_are_revisioned_and_atomic(tmp_path):
    app, _, _, _ = api_environment(tmp_path, count=0)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        current = client.get("/api/v1/platform-access-settings")
        assert current.status_code == 200
        update = {
            "expected_revision": current.json()["revision"],
            "interval_seconds": {
                "wb": 9,
                "dy": 8,
                "ks": 7,
                "xhs": 6,
                "toutiao": 5,
            },
        }
        changed = client.put("/api/v1/platform-access-settings", json=update)
        assert changed.status_code == 200
        assert changed.json()["revision"] == 2
        assert changed.json()["interval_seconds"] == update["interval_seconds"]

        stale = client.put("/api/v1/platform-access-settings", json=update)
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "platform_access_settings_conflict"

        invalid = client.put(
            "/api/v1/platform-access-settings",
            json={
                "expected_revision": 2,
                "interval_seconds": {
                    "wb": 0,
                    "dy": 8,
                    "ks": 7,
                    "xhs": 6,
                    "toutiao": 5,
                },
            },
        )
        assert invalid.status_code == 422
        assert (
            client.get("/api/v1/platform-access-settings").json()["interval_seconds"]
            == update["interval_seconds"]
        )


def test_platform_access_start_deadline_survives_coordinator_restart(tmp_path):
    database = Database(Path(tmp_path) / "restart.sqlite3")
    initialize_database(database)
    repository = PlatformAccessRepository(database)
    initialize_repository(repository)
    wall = [datetime(2026, 1, 1, tzinfo=UTC)]
    monotonic = [0.0]
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        wall[0] += timedelta(seconds=seconds)
        monotonic[0] += seconds

    long_snapshot = PlatformAccessSnapshot(
        interval_seconds=PlatformIntervals(wb=17, dy=5, ks=5, xhs=5, toutiao=5),
        basis="explicit",
    )
    short_snapshot = PlatformAccessSnapshot(
        interval_seconds=PlatformIntervals(wb=5, dy=5, ks=5, xhs=5, toutiao=5),
        basis="explicit",
    )

    async def exercise():
        first = PlatformAccessCoordinator(
            repository,
            clock=lambda: monotonic[0],
            wall_clock=lambda: wall[0],
            sleep=fake_sleep,
        )
        await first.wait_for_turn("wb", long_snapshot)

        # A fresh coordinator has no in-memory monotonic history. The durable
        # earliest boundary must still win over a shorter new task snapshot.
        restarted = PlatformAccessCoordinator(
            repository,
            clock=lambda: monotonic[0],
            wall_clock=lambda: wall[0],
            sleep=fake_sleep,
        )
        await restarted.wait_for_turn("wb", short_snapshot)

    asyncio.run(exercise())
    assert sleeps == [17]
    state = repository.state("wb")
    assert state["last_access_started_at"] == "2026-01-01T00:00:17+00:00"


def test_platform_access_preserves_diagnostics_and_requires_resume(tmp_path):
    database = Database(Path(tmp_path) / "platform.sqlite3")
    initialize_database(database)
    repository = PlatformAccessRepository(database)
    initialize_repository(repository)
    now = datetime.now(UTC)
    retry_after = now + timedelta(minutes=2)
    detailed = PlatformAccessDiagnostic(
        platform="wb",
        stage="detail",
        outcome="platform_blocked_or_rate_limited",
        basis="http_status",
        status_code=429,
        platform_code="RATE_LIMIT",
        retry_after_at=retry_after,
        manual_challenge_required=True,
        observed_at=now,
    )
    coordinator = PlatformAccessCoordinator(repository)
    coordinator.block("wb", detailed)
    generic = coordinator.block("wb")
    assert generic.status_code == 429
    assert generic.platform_code == "RATE_LIMIT"
    assert generic.retry_after_at == retry_after
    assert generic.manual_challenge_required is True

    async def assert_blocked():
        with pytest.raises(PlatformCooldownActiveError) as blocked:
            await coordinator.authorize_resume("wb")
        assert isinstance(blocked.value, PlatformAccessBlockedError)
        with pytest.raises(PlatformAccessBlockedError):
            await coordinator.wait_for_turn("wb")

    asyncio.run(assert_blocked())


def test_platform_access_wait_is_cancellable_on_shutdown(tmp_path):
    async def exercise():
        from opinion_workbench_api.database import Database

        database = Database(Path(tmp_path) / "shutdown.sqlite3")
        initialize_database(database)
        repository = PlatformAccessRepository(database)
        initialize_repository(repository)
        coordinator = PlatformAccessCoordinator(repository)
        await coordinator.wait_for_turn("wb")
        waiting = asyncio.Event()

        async def notify(*_args):
            waiting.set()

        task = asyncio.create_task(coordinator.wait_for_turn("wb", on_waiting=notify))
        await asyncio.wait_for(waiting.wait(), 1)
        coordinator.shutdown()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
