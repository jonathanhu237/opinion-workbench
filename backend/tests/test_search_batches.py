import asyncio
import sqlite3
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from fixture_support import (
    ensure_test_rule,
    initialize_database,
    initialize_repository,
)
from schema_fixtures import create_legacy_schema, seed_legacy_rule

from opinion_workbench_api.database import CURRENT_DATABASE_VERSION, Database
from opinion_workbench_api.main import create_app
from opinion_workbench_api.repositories.search_batches import (
    SearchBatchRepository,
    SearchBatchRepositoryUnavailableError,
)
from opinion_workbench_api.repositories.search_runs import SearchRunRepository
from opinion_workbench_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from opinion_workbench_api.services.collector_contracts import (
    ManualPageWorkerResult,
    OpenResultWorkerResult,
    SearchWorkerItem,
    SearchWorkerResult,
)
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService
from opinion_workbench_api.services.platform_connections import (
    PlatformConnectionService,
)
from opinion_workbench_api.services.search_batches import SearchBatchService
from opinion_workbench_api.services.search_runs import SearchRunService


class PlannedSearchWorker:
    def __init__(self, outcomes: dict[str, list[str]]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []
        self.term_calls: list[tuple[str, ...]] = []
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
        on_term_completed: Callable[[int, int], Awaitable[None]],
    ) -> SearchWorkerResult:
        del request_id, max_results_per_term, on_item
        self.calls.append(platform)
        self.term_calls.append(tuple(terms))
        await on_progress(0, len(terms))
        index = self.counts[platform]
        self.counts[platform] += 1
        plan = self.outcomes.get(platform, ["completed_empty"])
        outcome = plan[min(index, len(plan) - 1)]
        if outcome == "completed_empty":
            await on_term_completed(0, 0)
            for position in range(1, len(terms)):
                await on_progress(position, len(terms))
                await on_term_completed(position, 0)
        return SearchWorkerResult(outcome)  # type: ignore[arg-type]

    async def manual_page(self, *, action, **kwargs):
        return ManualPageWorkerResult(
            "opened_existing" if action == "show" else "closed"
        )

    async def discard_session(self):
        pass

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
    # Keep the historical five-term worker scenarios explicit in the fixture;
    # the product itself still creates fresh databases without rules.
    database = Database(database_path)
    database.initialize()
    ensure_test_rule(
        database,
        name="搜索批次回归规则",
        monitoring_objects=("龙田街道", "龙田社区", "老坑社区", "竹坑社区", "南布社区"),
    )

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


def _control(client, batch_id):
    batch = client.get(f"/api/v1/search-batches/{batch_id}").json()
    item = batch["items"][batch["current_item_position"]]
    return {
        "item_position": item["position"],
        "expected_revision": batch["control_revision"],
        "expected_run_id": item["latest_attempt"]["run"]["id"]
        if item["latest_attempt"]
        else None,
    }


def test_version_seven_migration_and_batch_constraints(tmp_path: Path) -> None:
    database = Database(tmp_path / "batch.sqlite3")
    initialize_database(database)
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
        platforms=("wb",),
        max_results_per_term=10,
    )
    assert [item.platform for item in first.items] == ["wb"]
    try:
        repository.create_batch(
            monitoring_rule_id=1,
            rule_name="另一个批次",
            terms=("龙田街道",),
            platforms=("wb",),
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
    create_legacy_schema(database, 6)
    seed_legacy_rule(database)
    with database.connect() as connection:
        connection.execute("""INSERT INTO search_runs
            (id, monitoring_rule_id, platform, rule_name, max_results_per_term,
             status, current_term_position, created_at, started_at, finished_at)
            VALUES (1, 1, 'wb', '迁移前任务', 5, 'completed_empty', 0,
                    '2026-08-01T00:00:00Z','2026-08-01T00:00:00Z','2026-08-01T00:00:01Z')""")
        connection.execute("INSERT INTO search_run_terms VALUES (1, 0, '龙田街道')")

    initialize_database(database)
    initialize_database(database)

    assert SearchRunRepository(database).get(1).platform == "wb"
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0] == 0
        )


def test_version_seven_migration_rolls_back_every_partial_schema_change(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "migration-rollback.sqlite3")
    create_legacy_schema(database, 6)
    with database.connect() as connection:
        connection.execute("CREATE TABLE search_batch_terms (sentinel TEXT)")

    with pytest.raises(sqlite3.Error):
        initialize_database(database)

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
    initialize_repository(repository)
    batch = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="重点区域",
        terms=("龙田街道", "竹坑社区"),
        platforms=("wb",),
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


def test_http_weibo_batch_hides_attempts_from_primary_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ordered.sqlite3"
    worker = PlannedSearchWorker({"wb": ["login_required"]})
    with TestClient(_app(database_path, worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 3,
            },
        )
        assert response.status_code == 202
        batch_id = response.json()["id"]
        _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert worker.calls == ["wb"]
        assert (
            client.post(
                f"/api/v1/search-batches/{batch_id}/skip",
                json=_control(client, batch_id),
            ).status_code
            == 202
        )
        batch = _wait_for_batch(client, batch_id, {"completed_with_failures"})
        assert worker.calls == ["wb"]
        assert [item["platform"] for item in batch["items"]] == ["wb"]
        assert [item["status"] for item in batch["items"]] == ["skipped"]
        assert batch["terminal_item_count"] == 1
        assert client.get("/api/v1/search-runs?scope=standalone").json()["runs"] == []
        assert len(client.get("/api/v1/search-runs").json()["runs"]) == 1


def test_composed_batch_snapshot_survives_rule_edits_and_deletion(
    tmp_path: Path,
) -> None:
    worker = PlannedSearchWorker(
        {"wb": ["manual_challenge_required", "completed_empty"]}
    )
    payload = {
        "name": "组合批次",
        "monitoring_objects": ["甲", "乙"],
        "issue_keywords": ["噪音", "积水"],
        "enabled": True,
    }
    terms = ["甲 噪音", "甲 积水", "乙 噪音", "乙 积水"]
    with TestClient(_app(tmp_path / "composed-batch.sqlite3", worker)) as client:
        rule = client.post("/api/v1/monitoring-rules", json=payload).json()
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": rule["id"],
                "platforms": ["wb"],
                "max_results_per_term": 1,
            },
        )
        assert response.status_code == 202
        batch_id = response.json()["id"]
        paused = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert paused["terms"] == terms
        assert (
            client.put(
                f"/api/v1/monitoring-rules/{rule['id']}",
                json={
                    **payload,
                    "monitoring_objects": ["修改后对象"],
                    "issue_keywords": ["新问题"],
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/search-batches/{batch_id}/continue",
                json=_control(client, batch_id),
            ).status_code
            == 202
        )
        completed = _wait_for_batch(client, batch_id, {"completed"})
        assert completed["terms"] == terms
        assert worker.calls == ["wb", "wb"]
        assert worker.term_calls == [tuple(terms)] * 2
        runs = client.get("/api/v1/search-runs").json()["runs"]
        assert len(runs) == 2
        assert (
            client.delete(f"/api/v1/monitoring-rules/{rule['id']}").status_code == 204
        )
        for run in runs:
            detail = client.get(f"/api/v1/search-runs/{run['id']}").json()
            assert detail["terms"] == terms
            assert detail["rule_name"] == "组合批次"
            assert detail["monitoring_rule_id"] is None
        assert client.get(f"/api/v1/search-batches/{batch_id}").json()["terms"] == terms


@pytest.mark.parametrize(
    ("object_count", "issue_count", "status"), [(5, 4, 202), (7, 3, 422)]
)
def test_batch_admission_counts_effective_queries(
    tmp_path: Path, object_count: int, issue_count: int, status: int
) -> None:
    worker = PlannedSearchWorker({})
    with TestClient(_app(tmp_path / "batch-limit.sqlite3", worker)) as client:
        rule = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "组合数量",
                "monitoring_objects": [f"对象{index}" for index in range(object_count)],
                "issue_keywords": [f"问题{index}" for index in range(issue_count)],
            },
        ).json()
        response = client.post(
            "/api/v1/search-batches",
            json={"monitoring_rule_id": rule["id"], "platforms": ["wb"]},
        )
        assert response.status_code == status
        if status == 202:
            _wait_for_batch(client, response.json()["id"], {"completed"})
            assert len(worker.term_calls[0]) == 20
        else:
            assert response.json()["detail"]["code"] == "too_many_search_terms"
            assert worker.calls == []
            assert client.get("/api/v1/search-batches").json()["batches"] == []


def test_manual_challenge_pauses_and_continue_creates_a_new_attempt(
    tmp_path: Path,
) -> None:
    worker = PlannedSearchWorker(
        {
            "wb": [
                "manual_challenge_required",
                "manual_challenge_required",
                "completed_empty",
            ],
        }
    )
    with TestClient(_app(tmp_path / "pause.sqlite3", worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 2,
            },
        )
        batch_id = response.json()["id"]
        paused = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert worker.calls == ["wb"]
        assert paused["items"][0]["attempt_count"] == 1

        continued = client.post(
            f"/api/v1/search-batches/{batch_id}/continue",
            json=_control(client, batch_id),
        )
        assert continued.status_code == 202
        paused_again = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})
        assert worker.calls == ["wb", "wb"]
        assert paused_again["items"][0]["attempt_count"] == 2

        continued_again = client.post(
            f"/api/v1/search-batches/{batch_id}/continue",
            json=_control(client, batch_id),
        )
        assert continued_again.status_code == 202
        completed = _wait_for_batch(client, batch_id, {"completed"})
        assert worker.calls == ["wb", "wb", "wb"]
        assert completed["items"][0]["attempt_count"] == 3
        attempts = client.get(
            f"/api/v1/search-batches/{batch_id}/items/0/attempts"
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
                "platforms": ["wb"],
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
        cancel = client.post(
            f"/api/v1/search-batches/{batch_id}/cancel",
            json={"expected_revision": _control(client, batch_id)["expected_revision"]},
        )
        assert cancel.status_code == 202
        assert cancel.json()["status"] == "cancelled"
        assert worker.calls == ["wb"]
        assert worker.cancelled == 1
        assert [item["status"] for item in cancel.json()["items"]] == [
            "cancelled",
        ]


def test_cancel_releases_owner_when_runner_was_cancelled_before_start(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "cancel-before-start.sqlite3")
    repository = SearchBatchRepository(database)
    initialize_repository(repository)
    batch = repository.create_batch(
        monitoring_rule_id=1,
        rule_name="重点区域",
        terms=("龙田街道",),
        platforms=("wb",),
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

        from opinion_workbench_api.schemas.search_batches import SearchBatchCancel

        cancelled = await service.cancel_batch(
            batch.id, SearchBatchCancel(expected_revision=batch.control_revision)
        )

        assert cancelled.status == "cancelled"
        contender = BrowserOperationOwner("search_run", uuid4())
        assert await coordinator.try_claim(contender)

    asyncio.run(scenario())


def test_restart_pauses_interrupted_attempt_without_continuing_queue(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.sqlite3"
    interrupted_worker = BlockingSearchWorker()
    with TestClient(_app(database_path, interrupted_worker)) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
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
        recovered = _wait_for_batch(client, batch_id, {"paused_for_manual_action"})

    assert interrupted_worker.cancelled == 1
    assert resumed_worker.calls == []
    assert [item["status"] for item in recovered["items"]] == [
        "paused_for_manual_action",
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
                "monitoring_objects": current["monitoring_objects"],
                "issue_keywords": current["issue_keywords"],
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
