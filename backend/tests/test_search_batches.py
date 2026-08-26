import asyncio
import sqlite3
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.main import create_app
from longtian_api.repositories.search_batches import (
    SearchBatchRepository,
    SearchBatchRepositoryUnavailableError,
)
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.media_crawler_auth_worker import (
    OpenResultWorkerResult,
    SearchWorkerItem,
    SearchWorkerResult,
)
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.search_batches import SearchBatchService
from longtian_api.services.search_runs import SearchRunService


class PlannedSearchWorker:
    def __init__(self, outcomes: dict[str, list[str]]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []
        self.counts: defaultdict[str, int] = defaultdict(int)

    async def search(
        self,
        *,
        request_id: UUID,
        platform: str,
        terms: Sequence[str],
        max_results_per_term: int,
        on_progress: Callable[[int, int], Awaitable[None]],
        on_item: Callable[[int, SearchWorkerItem], Awaitable[None]],
    ) -> SearchWorkerResult:
        del request_id, max_results_per_term, on_item
        self.calls.append(platform)
        await on_progress(0, len(terms))
        index = self.counts[platform]
        self.counts[platform] += 1
        plan = self.outcomes.get(platform, ["completed_empty"])
        outcome = plan[min(index, len(plan) - 1)]
        return SearchWorkerResult(outcome)  # type: ignore[arg-type]

    async def open_result(self, **_kwargs: object) -> OpenResultWorkerResult:
        return OpenResultWorkerResult("opened")


class BlockingSearchWorker(PlannedSearchWorker):
    def __init__(self) -> None:
        super().__init__({})
        self.started = False
        self.cancelled = 0

    async def search(self, *, platform: str, **_kwargs: object) -> SearchWorkerResult:
        self.calls.append(platform)
        self.started = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        raise AssertionError("blocking worker unexpectedly resumed")


def _app(database_path: Path, worker: object):
    def search_factory(
        monitoring_rules: MonitoringRuleService,
        platform_connections: PlatformConnectionService,
    ) -> SearchRunService:
        return SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,  # type: ignore[arg-type]
            browser_operations=platform_connections.browser_operations,
            database_path=database_path,
        )

    return create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database_path
        ),
        search_run_service_factory=search_factory,
    )


def _wait_for_batch(
    client: TestClient, batch_id: int, statuses: set[str]
) -> dict[str, object]:
    for _ in range(200):
        response = client.get(f"/api/v1/search-batches/{batch_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in statuses:
            return payload
        time.sleep(0.005)
    raise AssertionError("search batch did not reach the expected status")


def test_version_seven_migration_and_batch_constraints(tmp_path: Path) -> None:
    database = Database(tmp_path / "batch.sqlite3")
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "search_batches",
            "search_batch_terms",
            "search_batch_items",
            "search_batch_attempts",
        } <= tables

    repository = SearchBatchRepository(database)
    first = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="重点区域",
        terms=("龙田街道",),
        platforms=("toutiao", "wb"),
        max_results_per_term=10,
    )
    assert [item.platform for item in first.items] == ["toutiao", "wb"]
    try:
        repository.create_batch(
            monitoring_rule_id=1,
            rule_name="另一个批次",
            terms=("龙田街道",),
            platforms=("ks",),
            max_results_per_term=10,
        )
    except SearchBatchRepositoryUnavailableError:
        pass
    else:
        raise AssertionError("only one durable active batch should be admitted")


def test_version_six_upgrade_preserves_existing_runs_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "version-six.sqlite3")
    runs = SearchRunRepository(database)
    runs.initialize()
    existing = runs.create_run(
        monitoring_rule_id=1,
        platform="xhs",
        rule_name="迁移前任务",
        terms=("龙田街道",),
        max_results_per_term=5,
    )
    runs.finish(existing.id, "completed_empty")
    with database.connect() as connection:
        for table in (
            "search_batch_attempts",
            "search_batch_items",
            "search_batch_terms",
            "search_batches",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version = 6")

    database.initialize()
    database.initialize()

    assert SearchRunRepository(database).get(existing.id).platform == "xhs"
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0] == 0
        )


def test_version_seven_migration_rolls_back_every_partial_schema_change(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "migration-rollback.sqlite3")
    database.initialize()
    with database.connect() as connection:
        for table in (
            "search_batch_attempts",
            "search_batch_items",
            "search_batch_terms",
            "search_batches",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("CREATE TABLE search_batch_terms (sentinel TEXT)")
        connection.execute("PRAGMA user_version = 6")

    with pytest.raises(sqlite3.Error):
        database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "search_batches" not in tables
        assert "search_batch_terms" in tables


def test_attempt_creation_rolls_back_run_terms_and_item_transition(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "attempt-rollback.sqlite3")
    repository = SearchBatchRepository(database)
    repository.initialize()
    batch = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="重点区域",
        terms=("龙田街道", "竹坑社区"),
        platforms=("toutiao",),
        max_results_per_term=2,
    )
    repository.mark_running(batch.id)
    with database.connect() as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
        connection.execute(
            """
            CREATE TRIGGER reject_batch_attempt
            BEFORE INSERT ON search_batch_attempts
            BEGIN
              SELECT RAISE(ABORT, 'sentinel');
            END
            """
        )

    with pytest.raises(SearchBatchRepositoryUnavailableError):
        repository.create_attempt(batch.id, 0)

    recovered = repository.get(batch.id)
    assert recovered.items[0].status == "queued"
    assert recovered.items[0].attempt_count == 0
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
            == run_count
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM search_run_terms").fetchone()[0]
            == 0
        )


def test_http_batch_orders_platforms_and_hides_attempts_from_primary_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ordered.sqlite3"
    worker = PlannedSearchWorker(
        {
            "toutiao": ["completed_empty"],
            "wb": ["login_required"],
            "xhs": ["completed_empty"],
        }
    )
    with TestClient(_app(database_path, worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["xhs", "wb", "toutiao"],
                "max_results_per_term": 3,
            },
        )
        assert response.status_code == 202
        batch = _wait_for_batch(
            client, response.json()["id"], {"completed_with_failures"}
        )
        assert worker.calls == ["toutiao", "wb", "xhs"]
        assert [item["platform"] for item in batch["items"]] == [
            "toutiao",
            "wb",
            "xhs",
        ]
        assert [item["status"] for item in batch["items"]] == [
            "completed",
            "failed",
            "completed",
        ]
        assert batch["terminal_item_count"] == 3
        assert client.get("/api/v1/search-runs?scope=standalone").json()["runs"] == []
        assert len(client.get("/api/v1/search-runs").json()["runs"]) == 3


def test_manual_challenge_pauses_and_continue_creates_a_new_attempt(
    tmp_path: Path,
) -> None:
    worker = PlannedSearchWorker(
        {
            "toutiao": ["completed_empty"],
            "wb": [
                "manual_challenge_required",
                "manual_challenge_required",
                "completed_empty",
            ],
            "ks": ["completed_empty"],
        }
    )
    with TestClient(_app(tmp_path / "pause.sqlite3", worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["toutiao", "wb", "ks"],
                "max_results_per_term": 2,
            },
        )
        batch_id = response.json()["id"]
        paused = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert worker.calls == ["toutiao", "wb"]
        assert paused["items"][1]["attempt_count"] == 1

        continued = client.post(f"/api/v1/search-batches/{batch_id}/continue")
        assert continued.status_code == 202
        paused_again = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert worker.calls == ["toutiao", "wb", "wb"]
        assert paused_again["items"][1]["attempt_count"] == 2

        continued_again = client.post(f"/api/v1/search-batches/{batch_id}/continue")
        assert continued_again.status_code == 202
        completed = _wait_for_batch(client, batch_id, {"completed"})
        assert worker.calls == ["toutiao", "wb", "wb", "wb", "ks"]
        assert completed["items"][1]["attempt_count"] == 3
        attempts = client.get(
            f"/api/v1/search-batches/{batch_id}/items/1/attempts"
        ).json()["attempts"]
        assert [attempt["attempt_number"] for attempt in attempts] == [3, 2, 1]
        assert attempts[0]["run"]["status"] == "completed_empty"
        assert attempts[1]["run"]["status"] == "manual_challenge_required"
        assert attempts[2]["run"]["status"] == "manual_challenge_required"


def test_cancel_batch_stops_current_attempt_and_never_starts_later_platforms(
    tmp_path: Path,
) -> None:
    worker = BlockingSearchWorker()
    with TestClient(_app(tmp_path / "cancel.sqlite3", worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["toutiao", "wb"],
                "max_results_per_term": 2,
            },
        )
        batch_id = response.json()["id"]
        for _ in range(100):
            if worker.started:
                break
            time.sleep(0.005)
        account_attempt = client.post("/api/v1/platform-connections/wb/attempts")
        assert account_attempt.status_code == 409
        assert account_attempt.json()["detail"]["code"] == "connection_attempt_active"
        standalone_run = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
                "max_results_per_term": 2,
            },
        )
        assert standalone_run.status_code == 409
        assert standalone_run.json()["detail"]["code"] == "browser_operation_active"
        cancel = client.post(f"/api/v1/search-batches/{batch_id}/cancel")
        assert cancel.status_code == 202
        assert cancel.json()["status"] == "cancelled"
        assert worker.calls == ["toutiao"]
        assert worker.cancelled == 1
        assert [item["status"] for item in cancel.json()["items"]] == [
            "cancelled",
            "cancelled",
        ]


def test_cancel_releases_owner_when_runner_was_cancelled_before_start(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "cancel-before-start.sqlite3")
    repository = SearchBatchRepository(database)
    repository.initialize()
    batch = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="重点区域",
        terms=("龙田街道",),
        platforms=("toutiao",),
        max_results_per_term=1,
    )

    async def scenario() -> None:
        coordinator = BrowserOperationCoordinator()
        owner = BrowserOperationOwner("search_batch", uuid4())
        assert await coordinator.try_claim(owner)
        service = SearchBatchService(
            search_runs=object(),  # type: ignore[arg-type]
            browser_operations=coordinator,
            repository=repository,
        )
        runner = asyncio.create_task(asyncio.sleep(60))
        runner.cancel()
        service._active_batch_id = batch.id
        service._active_owner = owner
        service._current_task = runner

        cancelled = await service.cancel_batch(batch.id)

        assert cancelled.status == "cancelled"
        contender = BrowserOperationOwner("search_run", uuid4())
        assert await coordinator.try_claim(contender)

    asyncio.run(scenario())


def test_restart_recovers_after_interrupted_attempt_and_continues_queue(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.sqlite3"
    interrupted_worker = BlockingSearchWorker()
    with TestClient(_app(database_path, interrupted_worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["toutiao", "wb"],
                "max_results_per_term": 2,
            },
        )
        batch_id = response.json()["id"]
        for _ in range(100):
            if interrupted_worker.started:
                break
            time.sleep(0.005)
        assert interrupted_worker.started

    resumed_worker = PlannedSearchWorker({"wb": ["completed_empty"]})
    with TestClient(_app(database_path, resumed_worker)) as client:
        recovered = _wait_for_batch(client, batch_id, {"completed_with_failures"})

    assert interrupted_worker.cancelled == 1
    assert resumed_worker.calls == ["wb"]
    assert [item["status"] for item in recovered["items"]] == [
        "failed",
        "completed",
    ]


def test_batch_request_rejects_empty_duplicate_and_unknown_platforms(
    tmp_path: Path,
) -> None:
    with TestClient(
        _app(tmp_path / "validation.sqlite3", PlannedSearchWorker({}))
    ) as client:
        for platforms in ([], ["wb", "wb"], ["unknown"]):
            response = client.post(
                "/api/v1/search-batches",
                json={"monitoring_rule_id": 1, "platforms": platforms},
            )
            assert response.status_code == 422
            assert response.json() == {
                "detail": {
                    "code": "invalid_request",
                    "message": "请求内容不正确。",
                }
            }

        with Database(tmp_path / "validation.sqlite3").connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0]
                == 0
            )


def test_batch_start_translates_rule_errors_without_creating_work(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "rule-errors.sqlite3"
    worker = PlannedSearchWorker({})
    with TestClient(_app(database_path, worker)) as client:
        missing = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": 999, "platforms": ["wb"]},
        )
        assert missing.status_code == 404
        assert missing.json() == {
            "detail": {
                "code": "monitoring_rule_not_found",
                "message": "未找到该监控规则。",
            }
        }

        current = client.get("/api/v1/monitoring-rules").json()["rules"][0]
        disabled = client.put(
            f"/api/v1/monitoring-rules/{current['id']}",
            json={
                "name": current["name"],
                "terms": current["terms"],
                "enabled": False,
            },
        )
        assert disabled.status_code == 200
        rejected = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": current["id"], "platforms": ["wb"]},
        )
        assert rejected.status_code == 409
        assert rejected.json() == {
            "detail": {
                "code": "monitoring_rule_disabled",
                "message": "该监控规则已停用，请先启用后再采集。",
            }
        }

    assert worker.calls == []
    with Database(database_path).connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0] == 0
        )


def test_openapi_documents_batch_success_and_error_contracts(tmp_path: Path) -> None:
    with TestClient(
        _app(tmp_path / "openapi.sqlite3", PlannedSearchWorker({}))
    ) as client:
        paths = client.get("/openapi.json").json()["paths"]

    create = paths["/api/v1/search-batches"]["post"]
    assert create["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SearchBatchDetail"
    }
    assert create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SearchBatchCreate"
    }
    for operation, statuses in (
        (create, ("404", "409", "422", "503")),
        (
            paths["/api/v1/search-batches/{batch_id}/continue"]["post"],
            ("404", "409", "422", "503"),
        ),
        (
            paths["/api/v1/search-batches/{batch_id}/cancel"]["post"],
            ("404", "409", "422", "503"),
        ),
    ):
        for status_code in statuses:
            assert operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/SearchBatchErrorResponse"}
