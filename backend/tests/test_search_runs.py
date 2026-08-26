import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.main import create_app
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
)
from longtian_api.schemas.search_runs import SearchRunCreate
from longtian_api.services.browser_operations import (
    BrowserOperationCoordinator,
    BrowserOperationOwner,
)
from longtian_api.services.media_crawler_auth_worker import (
    SearchWorkerItem,
    SearchWorkerResult,
)
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import (
    PlatformConnectionError,
    PlatformConnectionService,
)
from longtian_api.services.search_runs import SearchRunError, SearchRunService


def _content(
    *, observed_at: str, title: str = "龙田街道现场情况"
) -> SearchContentInput:
    return SearchContentInput(
        platform_content_id="news-100",
        content_type="article",
        title=title,
        snippet="公开页面摘要",
        creator_hash="0123456789abcdef",
        publisher_name="本***察",
        published_at_text="刚刚",
        content_url="https://www.toutiao.com/article/100/",
        observed_at=observed_at,
    )


def test_repository_preserves_cross_term_and_cross_run_deduplication(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "search.sqlite3")
    repository = SearchRunRepository(database)
    repository.initialize()

    first = repository.create_run(
        monitoring_rule_id=1,
        platform="toutiao",
        rule_name="重点区域",
        terms=("龙田街道", "坪山大道"),
        max_results_per_term=10,
    )
    repository.mark_running(first.id)
    repository.observe_item(
        run_id=first.id,
        term_position=0,
        item=_content(observed_at="2026-08-25T08:00:00+00:00"),
    )
    repository.observe_item(
        run_id=first.id,
        term_position=0,
        item=_content(observed_at="2026-08-25T08:01:00+00:00"),
    )
    repository.observe_item(
        run_id=first.id,
        term_position=1,
        item=_content(observed_at="2026-08-25T08:02:00+00:00"),
    )
    first_done = repository.finish(first.id, "completed_with_results")

    assert (
        first_done.new_count,
        first_done.repeated_count,
        first_done.total_count,
    ) == (
        1,
        0,
        1,
    )
    first_results, first_total = repository.list_results(
        run_id=first.id, kind="all", limit=50, offset=0
    )
    assert first_total == 1
    assert first_results[0].discovery_kind == "new"
    assert first_results[0].matched_terms == ("龙田街道", "坪山大道")
    assert first_results[0].first_seen_at == "2026-08-25T08:00:00+00:00"
    assert first_results[0].last_seen_at == "2026-08-25T08:02:00+00:00"

    second = repository.create_run(
        monitoring_rule_id=1,
        platform="toutiao",
        rule_name="重点区域",
        terms=("龙田街道",),
        max_results_per_term=5,
    )
    repository.mark_running(second.id)
    repository.observe_item(
        run_id=second.id,
        term_position=0,
        item=_content(
            observed_at="2026-08-26T08:00:00+00:00", title="更新后的公开标题"
        ),
    )
    second_done = repository.finish(second.id, "completed_with_results")
    repeated, total = repository.list_results(
        run_id=second.id, kind="repeated", limit=50, offset=0
    )

    assert (second_done.new_count, second_done.repeated_count, total) == (0, 1, 1)
    assert repeated[0].title == "更新后的公开标题"
    assert repeated[0].first_seen_at == "2026-08-25T08:00:00+00:00"
    assert repeated[0].last_seen_at == "2026-08-26T08:00:00+00:00"
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM search_contents").fetchone()[0]
            == 1
        )


def test_migration_reconciliation_rule_deletion_and_failed_item_rollback(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "migrate.sqlite3")
    repository = SearchRunRepository(database)
    repository.initialize()
    queued = repository.create_run(
        monitoring_rule_id=1,
        platform="toutiao",
        rule_name="快照名称",
        terms=("龙田街道",),
        max_results_per_term=10,
    )

    reopened = SearchRunRepository(database)
    reopened.initialize()
    assert reopened.get(queued.id).status == "internal_error"
    assert reopened.get(queued.id).finished_at is not None

    active = reopened.create_run(
        monitoring_rule_id=1,
        platform="toutiao",
        rule_name="新规则",
        terms=("竹坑社区",),
        max_results_per_term=10,
    )
    reopened.mark_running(active.id)

    with database.connect() as connection:
        connection.execute("DELETE FROM monitoring_rules WHERE id = 1")
    persisted = reopened.get(queued.id)
    assert persisted.monitoring_rule_id is None
    assert persisted.rule_name == "快照名称"
    assert persisted.terms == ("龙田街道",)

    try:
        reopened.observe_item(
            run_id=active.id,
            term_position=9,
            item=_content(observed_at="2026-08-26T08:00:00+00:00"),
        )
    except SearchRunRepositoryUnavailableError:
        pass
    else:
        raise AssertionError("invalid term position should fail atomically")
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM search_contents").fetchone()[0]
            == 0
        )


class FakeSearchWorker:
    def __init__(
        self,
        *,
        outcome: str = "completed_with_results",
        emit_item: bool = True,
    ) -> None:
        self.calls: list[tuple[UUID, tuple[str, ...], int]] = []
        self.outcome = outcome
        self.emit_item = emit_item

    async def search(
        self,
        *,
        request_id: UUID,
        terms: Sequence[str],
        max_results_per_term: int,
        on_progress: Callable[[int, int], Awaitable[None]],
        on_item: Callable[[int, SearchWorkerItem], Awaitable[None]],
    ) -> SearchWorkerResult:
        self.calls.append((request_id, tuple(terms), max_results_per_term))
        await on_progress(0, len(terms))
        if self.emit_item:
            await on_item(
                0,
                SearchWorkerItem(
                    content_id="news-100",
                    content_type="article",
                    title="龙田街道公开信息",
                    snippet="来自公开搜索页面",
                    creator_hash="0123456789abcdef",
                    publisher_name="本***察",
                    published_at_text="刚刚",
                    content_url="https://www.toutiao.com/article/100/",
                    discovered_at=1_777_000_000_000,
                ),
            )
        return SearchWorkerResult(self.outcome)  # type: ignore[arg-type]


class BlockingSearchWorker:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = 0

    async def search(self, **_kwargs: object) -> SearchWorkerResult:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        raise AssertionError("blocking worker unexpectedly resumed")


def _search_app(database_path: Path, worker: FakeSearchWorker):
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


def _wait_for_terminal(client: TestClient, run_id: int) -> dict[str, object]:
    for _ in range(100):
        payload = client.get(f"/api/v1/search-runs/{run_id}").json()
        if payload["status"] not in {"queued", "running"}:
            return payload
        time.sleep(0.005)
    raise AssertionError("search run did not become terminal")


def test_http_search_vertical_slice_is_non_blocking_durable_and_deduplicated(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "http.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        first_response = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "toutiao",
                "max_results_per_term": 7,
            },
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        assert first["status"] == "completed_with_results"
        assert (first["new_count"], first["repeated_count"], first["total_count"]) == (
            1,
            0,
            1,
        )
        assert first["terms"] == [
            "龙田街道",
            "龙田社区",
            "老坑社区",
            "竹坑社区",
            "南布社区",
        ]
        first_results = client.get(f"/api/v1/search-runs/{first['id']}/results").json()
        assert first_results["total"] == 1
        assert first_results["results"][0]["kind"] == "new"
        assert first_results["results"][0]["matched_terms"] == ["龙田街道"]

        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "toutiao"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])
        assert (
            second["new_count"],
            second["repeated_count"],
            second["total_count"],
        ) == (
            0,
            1,
            1,
        )
        repeated = client.get(
            f"/api/v1/search-runs/{second['id']}/results",
            params={"kind": "repeated", "limit": 1, "offset": 0},
        ).json()
        assert repeated["total"] == 1
        assert repeated["results"][0]["kind"] == "repeated"
        assert len(worker.calls) == 2

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM search_contents"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM search_runs").fetchone() == (2,)


def test_http_search_validation_and_error_contracts(tmp_path: Path) -> None:
    database_path = tmp_path / "errors.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        assert client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": "1", "platform": "toutiao"},
        ).json() == {
            "detail": {"code": "invalid_request", "message": "请求内容不正确。"}
        }
        missing = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 999, "platform": "toutiao"},
        )
        assert (missing.status_code, missing.json()["detail"]["code"]) == (
            404,
            "monitoring_rule_not_found",
        )
        client.put(
            "/api/v1/monitoring-rules/1",
            json={
                "name": "已停用",
                "terms": ["龙田街道"],
                "enabled": False,
            },
        )
        disabled = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "toutiao"},
        )
        assert (disabled.status_code, disabled.json()["detail"]["code"]) == (
            409,
            "monitoring_rule_disabled",
        )
        client.put(
            "/api/v1/monitoring-rules/1",
            json={
                "name": "搜索词过多",
                "terms": [f"搜索词{index}" for index in range(21)],
                "enabled": True,
            },
        )
        oversized = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "toutiao"},
        )
        assert (oversized.status_code, oversized.json()["detail"]["code"]) == (
            422,
            "too_many_search_terms",
        )
        assert client.get("/api/v1/search-runs/999").status_code == 404
        assert (
            client.get(
                "/api/v1/search-runs/1/results", params={"limit": 51}
            ).status_code
            == 422
        )
        assert client.get(
            "/api/v1/search-runs/1/results",
            params={"offset": 9_223_372_036_854_775_808},
        ).json() == {
            "detail": {"code": "invalid_request", "message": "请求内容不正确。"}
        }


def test_search_and_account_checks_share_one_atomic_browser_admission(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "admission.sqlite3"
        monitoring_rules = MonitoringRuleService(database_path=database_path)
        monitoring_rules.initialize()
        coordinator = BrowserOperationCoordinator()
        platform_service = PlatformConnectionService(
            browser_operation_coordinator=coordinator
        )
        search_service = SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=FakeSearchWorker(),  # type: ignore[arg-type]
            browser_operations=coordinator,
            database_path=database_path,
        )
        search_service.initialize()

        platform_owner = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(platform_owner)
        with pytest.raises(SearchRunError) as search_conflict:
            await search_service.start_run(
                SearchRunCreate(monitoring_rule_id=1, platform="toutiao")
            )
        assert search_conflict.value.code == "browser_operation_active"
        await coordinator.release(platform_owner)

        search_owner = BrowserOperationOwner("search_run", uuid4())
        assert await coordinator.try_claim(search_owner)
        with pytest.raises(PlatformConnectionError) as connection_conflict:
            await platform_service.start_attempt("wb")
        assert connection_conflict.value.code == "connection_attempt_active"
        await coordinator.release(search_owner)
        await search_service.shutdown()
        await platform_service.shutdown()

    asyncio.run(scenario())


def test_cancellation_is_durable_and_releases_browser_admission(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "cancel.sqlite3"
        monitoring_rules = MonitoringRuleService(database_path=database_path)
        monitoring_rules.initialize()
        coordinator = BrowserOperationCoordinator()
        worker = BlockingSearchWorker()
        service = SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,  # type: ignore[arg-type]
            browser_operations=coordinator,
            database_path=database_path,
        )
        service.initialize()
        started = await service.start_run(
            SearchRunCreate(monitoring_rule_id=1, platform="toutiao")
        )
        await worker.started.wait()

        cancelled = await service.cancel_run(started.id)

        assert cancelled.status == "cancelled"
        assert cancelled.finished_at is not None
        assert worker.cancelled == 1
        next_owner = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(next_owner)
        await coordinator.release(next_owner)
        await service.shutdown()

    asyncio.run(scenario())


def test_timeout_is_durable_and_releases_browser_admission(tmp_path: Path) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "timeout.sqlite3"
        monitoring_rules = MonitoringRuleService(database_path=database_path)
        monitoring_rules.initialize()
        coordinator = BrowserOperationCoordinator()
        worker = BlockingSearchWorker()
        service = SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,  # type: ignore[arg-type]
            browser_operations=coordinator,
            database_path=database_path,
            search_timeout_seconds=0.01,
        )
        service.initialize()
        started = await service.start_run(
            SearchRunCreate(monitoring_rule_id=1, platform="toutiao")
        )
        await worker.started.wait()

        for _ in range(100):
            terminal = await service.get_run(started.id)
            if terminal.status not in {"queued", "running"}:
                break
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("timed-out search run did not become terminal")

        assert terminal.status == "timed_out"
        assert terminal.finished_at is not None
        assert worker.cancelled == 1
        next_owner = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(next_owner)
        await coordinator.release(next_owner)
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("worker_outcome", "expected_status"),
    [
        ("completed_empty", "completed_empty"),
        ("login_required", "login_required"),
        ("manual_challenge_required", "manual_challenge_required"),
        (
            "platform_blocked_or_rate_limited",
            "platform_blocked_or_rate_limited",
        ),
        ("structure_changed", "structure_changed"),
        ("browser_unavailable", "browser_unavailable"),
        ("browser_disconnected", "browser_unavailable"),
        ("cancelled", "cancelled"),
        ("internal_error", "internal_error"),
    ],
)
def test_worker_terminal_outcomes_are_projected_without_losing_partial_items(
    tmp_path: Path, worker_outcome: str, expected_status: str
) -> None:
    database_path = tmp_path / f"{worker_outcome}.sqlite3"
    has_partial_item = worker_outcome != "completed_empty"
    worker = FakeSearchWorker(outcome=worker_outcome, emit_item=has_partial_item)
    with TestClient(_search_app(database_path, worker)) as client:
        started = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "toutiao"},
        )
        terminal = _wait_for_terminal(client, started.json()["id"])
        results = client.get(f"/api/v1/search-runs/{terminal['id']}/results").json()

    assert terminal["status"] == expected_status
    assert terminal["total_count"] == int(has_partial_item)
    assert results["total"] == int(has_partial_item)


def test_fresh_database_contains_all_search_tables_and_indexes(tmp_path: Path) -> None:
    database = Database(tmp_path / "schema.sqlite3")
    database.initialize()
    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert tables >= {
        "search_runs",
        "search_run_terms",
        "search_contents",
        "search_run_contents",
        "search_run_content_terms",
    }
    assert indexes >= {
        "ix_search_runs_status_id",
        "ix_search_runs_rule_id",
        "ix_search_run_contents_kind_observed",
    }


def test_version_one_database_upgrades_without_reseeding_monitoring_rules(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "upgrade.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for table in (
            "search_run_content_terms",
            "search_run_contents",
            "search_contents",
            "search_run_terms",
            "search_runs",
        ):
            connection.execute(f"DROP TABLE {table}")  # noqa: S608 - closed names.
        connection.execute("UPDATE monitoring_rules SET name = '保留的旧规则'")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("COMMIT")

    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT name FROM monitoring_rules WHERE id = 1"
            ).fetchone()[0]
            == "保留的旧规则"
        )
        assert connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0] == 0
