import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from longtian_api.database import (
    CURRENT_DATABASE_VERSION,
    Database,
    _migrate_to_version_1,
    _migrate_to_version_2,
    _migrate_to_version_3,
    _migrate_to_version_4,
    _migrate_to_version_5,
)
from longtian_api.main import create_app
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchResultNotFoundError,
    SearchRunNotActiveError,
    SearchRunRepository,
    SearchRunRepositoryUnavailableError,
)
from longtian_api.schemas.search_runs import SearchRunCreate
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


def _xhs_content(*, observed_at: str) -> SearchContentInput:
    content_id = "0123456789abcdef01234567"
    return SearchContentInput(
        platform_content_id=content_id,
        content_type="image",
        title="龙田街道公开信息",
        snippet="公开页面摘要",
        creator_hash="0123456789abcdef",
        publisher_name="本***察",
        published_at_text="",
        content_url=f"https://www.xiaohongshu.com/explore/{content_id}",
        observed_at=observed_at,
    )


def _observe(repository, *, run_id, term_position, item):
    """Supply ordered v2 start/completion evidence in repository result fixtures."""
    run = repository.get(run_id)
    if run.status == "running" and run.search_protocol_version == 2:
        current = run.current_term_position
        if current is None:
            current = run.execution_start_term_position
            repository.set_progress(run_id, current)
        while current < term_position:
            with repository._database.connect() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM search_run_content_terms "
                    "WHERE run_id = ? AND term_position = ?",
                    (run_id, current),
                ).fetchone()[0]
            repository.complete_term(run_id, current, count)
            current += 1
            repository.set_progress(run_id, current)
    repository.observe_item(run_id=run_id, term_position=term_position, item=item)


def test_repository_open_target_proves_relation_and_original_term_order(
    tmp_path: Path,
) -> None:
    repository = SearchRunRepository(Database(tmp_path / "open-target.sqlite3"))
    repository.initialize()
    run = repository.create_run(
        monitoring_rule_id=1,
        platform="xhs",
        rule_name="重点区域",
        terms=("第一个词", "第二个词", "第三个词"),
        max_results_per_term=10,
    )
    repository.mark_running(run.id)
    for position in (0, 1, 2):
        _observe(
            repository,
            run_id=run.id,
            term_position=position,
            item=_xhs_content(observed_at=f"2026-08-26T08:0{position}:00+00:00"),
        )
    repository.finish(run.id, "completed_with_results")
    results, _total = repository.list_results(
        run_id=run.id, kind="all", limit=50, offset=0
    )

    target = repository.get_result_open_target(run_id=run.id, result_id=results[0].id)

    assert target.platform == "xhs"
    assert target.platform_content_id == "0123456789abcdef01234567"
    assert target.matched_terms == ("第一个词", "第二个词", "第三个词")
    with pytest.raises(SearchResultNotFoundError):
        repository.get_result_open_target(run_id=run.id + 1, result_id=results[0].id)


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
    _observe(
        repository,
        run_id=first.id,
        term_position=0,
        item=_content(observed_at="2026-08-25T08:00:00+00:00"),
    )
    _observe(
        repository,
        run_id=first.id,
        term_position=0,
        item=_content(observed_at="2026-08-25T08:01:00+00:00"),
    )
    _observe(
        repository,
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
    _observe(
        repository,
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
    except SearchRunNotActiveError:
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
        open_outcome: str = "opened",
    ) -> None:
        self.calls: list[tuple[UUID, str, tuple[str, ...], int]] = []
        self.outcome = outcome
        self.emit_item = emit_item
        self.open_outcome = open_outcome
        self.open_calls: list[tuple[UUID, str, str]] = []

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
        self.calls.append((request_id, platform, tuple(terms), max_results_per_term))
        await on_progress(0, len(terms))
        if self.emit_item:
            content_id = (
                "7512345678901234567"
                if platform == "dy"
                else "0123456789abcdef01234567"
                if platform == "xhs"
                else "news-100"
            )
            await on_item(
                0,
                SearchWorkerItem(
                    content_id=content_id,
                    content_type=(
                        "article"
                        if platform == "toutiao"
                        else "video"
                        if platform in {"ks", "dy"}
                        else "image"
                        if platform == "xhs"
                        else "post"
                    ),
                    title="龙田街道公开信息",
                    snippet="来自公开搜索页面",
                    creator_hash="0123456789abcdef",
                    publisher_name="本***察",
                    published_at_text="刚刚",
                    content_url=(
                        "https://www.toutiao.com/article/100/"
                        if platform == "toutiao"
                        else (
                            "https://www.kuaishou.com/short-video/news-100"
                            if platform == "ks"
                            else (
                                "https://www.douyin.com/video/7512345678901234567"
                                if platform == "dy"
                                else (
                                    "https://www.xiaohongshu.com/explore/"
                                    "0123456789abcdef01234567"
                                    if platform == "xhs"
                                    else "https://m.weibo.cn/detail/news-100"
                                )
                            )
                        )
                    ),
                    discovered_at=1_777_000_000_000,
                ),
            )
        if self.outcome in {"completed_with_results", "completed_empty"}:
            await on_term_completed(0, int(self.emit_item))
            for position in range(1, len(terms)):
                await on_progress(position, len(terms))
                await on_term_completed(position, 0)
        return SearchWorkerResult(self.outcome)  # type: ignore[arg-type]

    async def open_result(
        self, *, request_id: UUID, term: str, content_id: str
    ) -> OpenResultWorkerResult:
        self.open_calls.append((request_id, term, content_id))
        return OpenResultWorkerResult(self.open_outcome)  # type: ignore[arg-type]


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


class BlockingOpenWorker(FakeSearchWorker):
    def __init__(self) -> None:
        super().__init__()
        self.open_started = asyncio.Event()
        self.open_cancelled = 0

    async def open_result(self, **_kwargs: object) -> OpenResultWorkerResult:
        self.open_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.open_cancelled += 1
            raise
        raise AssertionError("blocking open unexpectedly resumed")


def _seed_xhs_result(database_path: Path) -> tuple[int, int]:
    repository = SearchRunRepository(Database(database_path))
    repository.initialize()
    run = repository.create_run(
        monitoring_rule_id=1,
        platform="xhs",
        rule_name="重点区域",
        terms=("龙田街道",),
        max_results_per_term=10,
    )
    repository.mark_running(run.id)
    _observe(
        repository,
        run_id=run.id,
        term_position=0,
        item=_xhs_content(observed_at="2026-08-26T08:00:00+00:00"),
    )
    repository.finish(run.id, "completed_with_results")
    results, _total = repository.list_results(
        run_id=run.id, kind="all", limit=50, offset=0
    )
    return run.id, results[0].id


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


def test_composed_run_terms_are_frozen_and_deduplication_is_unchanged(
    tmp_path: Path,
) -> None:
    worker = FakeSearchWorker()
    payload = {
        "name": "组合规则",
        "monitoring_objects": ["甲", "乙"],
        "issue_keywords": ["噪音", "积水"],
        "enabled": True,
    }
    terms = ["甲 噪音", "甲 积水", "乙 噪音", "乙 积水"]
    with TestClient(_search_app(tmp_path / "composed.sqlite3", worker)) as client:
        rule = client.post("/api/v1/monitoring-rules", json=payload).json()
        first_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": rule["id"], "platform": "wb"},
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        assert first["terms"] == terms
        assert first["new_count"] == 1
        assert worker.calls[0][2] == tuple(terms)
        assert (
            client.put(
                f"/api/v1/monitoring-rules/{rule['id']}",
                json={
                    **payload,
                    "monitoring_objects": ["新 完整短语"],
                    "issue_keywords": [],
                },
            ).status_code
            == 200
        )
        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": rule["id"], "platform": "wb"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])
        assert second["terms"] == ["新 完整短语"]
        assert second["repeated_count"] == 1
        assert client.get(f"/api/v1/search-runs/{first['id']}").json()["terms"] == terms
        assert client.get(f"/api/v1/search-runs/{first['id']}/results").json()[
            "results"
        ][0]["matched_terms"] == [terms[0]]


def test_single_run_accepts_twenty_generated_queries(tmp_path: Path) -> None:
    worker = FakeSearchWorker(outcome="completed_empty", emit_item=False)
    with TestClient(_search_app(tmp_path / "composed-limit.sqlite3", worker)) as client:
        rule = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "二十个组合",
                "monitoring_objects": ["甲", "乙"],
                "issue_keywords": [str(index) for index in range(10)],
            },
        ).json()
        response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": rule["id"], "platform": "wb"},
        )
        assert response.status_code == 202
        result = _wait_for_terminal(client, response.json()["id"])
        assert result["term_count"] == 20
        assert worker.calls[0][2] == tuple(rule["terms"])


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
        assert [call[1] for call in worker.calls] == ["toutiao", "toutiao"]

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM search_contents"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM search_runs").fetchone() == (2,)


def test_http_weibo_search_threads_platform_and_deduplicates_repeated_runs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "weibo-http.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        first_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "wb"},
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        first_results = client.get(f"/api/v1/search-runs/{first['id']}/results").json()

        assert first["platform"] == "wb"
        assert first["status"] == "completed_with_results"
        assert first_results["results"][0]["platform"] == "wb"
        assert (
            first_results["results"][0]["content_url"]
            == "https://m.weibo.cn/detail/news-100"
        )

        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "wb"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])

    assert (second["new_count"], second["repeated_count"]) == (0, 1)
    assert [call[1] for call in worker.calls] == ["wb", "wb"]


def test_http_kuaishou_search_threads_platform_and_deduplicates_repeated_runs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "kuaishou-http.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        first_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "ks"},
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        first_results = client.get(f"/api/v1/search-runs/{first['id']}/results").json()

        assert first["platform"] == "ks"
        assert first["status"] == "completed_with_results"
        assert first_results["results"][0]["platform"] == "ks"
        assert (
            first_results["results"][0]["content_url"]
            == "https://www.kuaishou.com/short-video/news-100"
        )

        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "ks"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])

    assert (second["new_count"], second["repeated_count"]) == (0, 1)
    assert [call[1] for call in worker.calls] == ["ks", "ks"]


def test_http_douyin_search_threads_platform_and_deduplicates_repeated_runs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "douyin-http.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        first_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "dy"},
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        first_results = client.get(f"/api/v1/search-runs/{first['id']}/results").json()

        assert first["platform"] == "dy"
        assert first["status"] == "completed_with_results"
        assert first_results["results"][0]["platform"] == "dy"
        assert first_results["results"][0]["content_url"] == (
            "https://www.douyin.com/video/7512345678901234567"
        )

        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "dy"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])

    assert (second["new_count"], second["repeated_count"]) == (0, 1)
    assert [call[1] for call in worker.calls] == ["dy", "dy"]


def test_http_xhs_search_threads_platform_and_deduplicates_repeated_runs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "xhs-http.sqlite3"
    worker = FakeSearchWorker()
    with TestClient(_search_app(database_path, worker)) as client:
        first_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "xhs"},
        )
        assert first_response.status_code == 202
        first = _wait_for_terminal(client, first_response.json()["id"])
        first_results = client.get(f"/api/v1/search-runs/{first['id']}/results").json()

        assert first["platform"] == "xhs"
        assert first["status"] == "completed_with_results"
        assert first_results["results"][0]["platform"] == "xhs"
        assert first_results["results"][0]["content_url"] == (
            "https://www.xiaohongshu.com/explore/0123456789abcdef01234567"
        )

        second_response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "xhs"},
        )
        second = _wait_for_terminal(client, second_response.json()["id"])

    assert (second["new_count"], second["repeated_count"]) == (0, 1)
    assert [call[1] for call in worker.calls] == ["xhs", "xhs"]


@pytest.mark.parametrize(
    "open_outcome",
    [
        "opened",
        "content_not_found",
        "content_unavailable",
        "login_required",
        "manual_challenge_required",
        "platform_blocked_or_rate_limited",
        "structure_changed",
        "browser_unavailable",
        "internal_error",
    ],
)
def test_http_xhs_open_returns_only_fixed_outcome_and_first_stored_term(
    tmp_path: Path, open_outcome: str
) -> None:
    worker = FakeSearchWorker(open_outcome=open_outcome)
    with TestClient(
        _search_app(tmp_path / f"open-{open_outcome}.sqlite3", worker)
    ) as client:
        started = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "xhs"},
        )
        run = _wait_for_terminal(client, started.json()["id"])
        result = client.get(f"/api/v1/search-runs/{run['id']}/results").json()[
            "results"
        ][0]

        response = client.post(
            f"/api/v1/search-runs/{run['id']}/results/{result['id']}/open"
        )

    assert response.status_code == 200
    assert response.json() == {"outcome": open_outcome}
    assert worker.open_calls[0][1:] == (
        "龙田街道",
        "0123456789abcdef01234567",
    )
    serialized = response.text
    assert "龙田街道" not in serialized
    assert "xsec" not in serialized
    assert "xiaohongshu.com" not in serialized


def test_http_open_rejects_unrelated_and_non_xhs_results(tmp_path: Path) -> None:
    worker = FakeSearchWorker()
    with TestClient(_search_app(tmp_path / "open-errors.sqlite3", worker)) as client:
        started = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "toutiao"},
        )
        run = _wait_for_terminal(client, started.json()["id"])
        result_id = client.get(f"/api/v1/search-runs/{run['id']}/results").json()[
            "results"
        ][0]["id"]

        unrelated = client.post(
            f"/api/v1/search-runs/{run['id'] + 1}/results/{result_id}/open"
        )
        unsupported = client.post(
            f"/api/v1/search-runs/{run['id']}/results/{result_id}/open"
        )
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/search-runs/{run_id}/results/{result_id}/open"
        ]["post"]

    assert unrelated.status_code == 404
    assert unrelated.json()["detail"]["code"] == "search_result_not_found"
    assert unsupported.status_code == 409
    assert unsupported.json()["detail"]["code"] == ("search_result_open_not_supported")
    assert worker.open_calls == []
    assert "requestBody" not in operation


def test_http_rejects_unknown_search_platform_without_starting_worker(
    tmp_path: Path,
) -> None:
    worker = FakeSearchWorker()
    app = _search_app(tmp_path / "unknown-platform.sqlite3", worker)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-runs",
            json={"monitoring_rule_id": 1, "platform": "bili"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "invalid_request", "message": "请求内容不正确。"}
    }
    assert worker.calls == []


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
                "monitoring_objects": ["龙田街道"],
                "issue_keywords": [],
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
                "monitoring_objects": [f"搜索词{index}" for index in range(7)],
                "issue_keywords": ["问题一", "问题二", "问题三"],
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


def test_open_timeout_is_bounded_and_releases_browser_admission(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "open-timeout.sqlite3"
        run_id, result_id = _seed_xhs_result(database_path)
        monitoring_rules = MonitoringRuleService(database_path=database_path)
        coordinator = BrowserOperationCoordinator()
        worker = BlockingOpenWorker()
        service = SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,  # type: ignore[arg-type]
            browser_operations=coordinator,
            database_path=database_path,
            open_timeout_seconds=0.01,
        )
        service.initialize()

        response = await service.open_result(run_id=run_id, result_id=result_id)

        assert response.outcome == "internal_error"
        assert worker.open_cancelled == 1
        next_owner = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(next_owner)
        await coordinator.release(next_owner)
        await service.shutdown()

    asyncio.run(scenario())


def test_open_obeys_global_contention_and_shutdown_cancels_no_orphan(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "open-shutdown.sqlite3"
        run_id, result_id = _seed_xhs_result(database_path)
        monitoring_rules = MonitoringRuleService(database_path=database_path)
        coordinator = BrowserOperationCoordinator()
        worker = BlockingOpenWorker()
        service = SearchRunService(
            monitoring_rules=monitoring_rules,
            worker=worker,  # type: ignore[arg-type]
            browser_operations=coordinator,
            database_path=database_path,
        )
        service.initialize()
        competing = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(competing)
        with pytest.raises(SearchRunError) as conflict:
            await service.open_result(run_id=run_id, result_id=result_id)
        assert conflict.value.code == "browser_operation_active"
        await coordinator.release(competing)

        open_task = asyncio.create_task(
            service.open_result(run_id=run_id, result_id=result_id)
        )
        await worker.open_started.wait()
        await service.shutdown()

        with pytest.raises(asyncio.CancelledError):
            await open_task
        assert worker.open_cancelled == 1
        next_owner = BrowserOperationOwner("platform_connection", uuid4())
        assert await coordinator.try_claim(next_owner)
        await coordinator.release(next_owner)

    asyncio.run(scenario())


def test_open_storage_failure_is_a_sanitized_503() -> None:
    class UnavailableOpenRepository:
        def initialize(self) -> None:
            pass

        def get_result_open_target(self, **_kwargs: object) -> object:
            raise SearchRunRepositoryUnavailableError

    async def scenario() -> None:
        service = SearchRunService(
            monitoring_rules=MonitoringRuleService(),
            worker=FakeSearchWorker(),  # type: ignore[arg-type]
            browser_operations=BrowserOperationCoordinator(),
            repository=UnavailableOpenRepository(),  # type: ignore[arg-type]
        )

        with pytest.raises(SearchRunError) as unavailable:
            await service.open_result(run_id=1, result_id=1)

        assert unavailable.value.status_code == 503
        assert unavailable.value.code == "search_storage_unavailable"
        assert "SQLite" not in unavailable.value.message

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


def test_version_two_migration_preserves_toutiao_and_isolates_weibo_identity(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-two.sqlite3"
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _migrate_to_version_1(connection)
        _migrate_to_version_2(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO search_runs (
              id, monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at, started_at, finished_at
            ) VALUES (41, 1, 'toutiao', '旧任务', 7, 'completed_with_results',
                      0, '2026-08-25T08:00:00+00:00',
                      '2026-08-25T08:00:01+00:00',
                      '2026-08-25T08:00:02+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_terms (run_id, position, value)
            VALUES (41, 0, '龙田街道')
            """
        )
        connection.execute(
            """
            INSERT INTO search_contents (
              id, platform, platform_content_id, content_type, title, snippet,
              creator_hash, publisher_name, published_at_text, content_url,
              first_seen_at, last_seen_at
            ) VALUES (
              99, 'toutiao', 'shared-100', 'article', '旧标题', '旧摘要',
              '0123456789abcdef', '本***察', '刚刚',
              'https://www.toutiao.com/article/shared-100/',
              '2026-08-25T08:00:01+00:00', '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_contents (
              run_id, search_content_id, discovery_kind,
              first_observed_at, last_observed_at
            ) VALUES (41, 99, 'new', '2026-08-25T08:00:01+00:00',
                      '2026-08-25T08:00:01+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms (
              run_id, search_content_id, term_position, observed_at
            ) VALUES (41, 99, 0, '2026-08-25T08:00:01+00:00')
            """
        )
        connection.execute("COMMIT")
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()
    repository = SearchRunRepository(database)
    preserved = repository.get(41)
    preserved_results, preserved_total = repository.list_results(
        run_id=41, kind="all", limit=50, offset=0
    )

    assert preserved.platform == "toutiao"
    assert preserved.terms == ("龙田街道",)
    assert preserved.created_at == "2026-08-25T08:00:00+00:00"
    assert preserved_total == 1
    assert preserved_results[0].id == 99
    assert preserved_results[0].matched_terms == ("龙田街道",)
    assert preserved_results[0].first_seen_at == "2026-08-25T08:00:01+00:00"

    weibo = repository.create_run(
        monitoring_rule_id=1,
        platform="wb",
        rule_name="微博任务",
        terms=("龙田街道",),
        max_results_per_term=7,
    )
    repository.mark_running(weibo.id)
    _observe(
        repository,
        run_id=weibo.id,
        term_position=0,
        item=SearchContentInput(
            platform_content_id="shared-100",
            content_type="post",
            title="微博标题",
            snippet="微博正文",
            creator_hash="0123456789abcdef",
            publisher_name="微***户",
            published_at_text="刚刚",
            content_url="https://m.weibo.cn/detail/shared-100",
            observed_at="2026-08-26T08:00:00+00:00",
        ),
    )
    completed = repository.finish(weibo.id, "completed_with_results")

    assert (completed.new_count, completed.repeated_count) == (1, 0)
    with database.connect() as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        rows = migrated.execute(
            """
            SELECT platform, id FROM search_contents
            WHERE platform_content_id = 'shared-100' ORDER BY platform
            """
        ).fetchall()
    assert [(row["platform"], row["id"]) for row in rows] == [
        ("toutiao", 99),
        ("wb", 100),
    ]


def test_version_one_database_upgrades_without_reseeding_monitoring_rules(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "upgrade.sqlite3")
    with database.connect() as connection:
        _migrate_to_version_1(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE monitoring_rules SET name = '保留的旧规则'")
        connection.execute("COMMIT")

    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert (
            connection.execute(
                "SELECT name FROM monitoring_rules WHERE id = 1"
            ).fetchone()[0]
            == "保留的旧规则"
        )
        assert connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0] == 0


def test_version_three_migration_preserves_rows_relations_and_sequences(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-three.sqlite3"
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _migrate_to_version_1(connection)
        _migrate_to_version_2(connection)
        _migrate_to_version_3(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO search_runs (
              id, monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at, started_at, finished_at
            ) VALUES (41, 1, 'wb', '微博旧任务', 7, 'completed_with_results',
                      0, '2026-08-25T08:00:00+00:00',
                      '2026-08-25T08:00:01+00:00',
                      '2026-08-25T08:00:02+00:00')
            """
        )
        connection.execute("INSERT INTO search_run_terms VALUES (41, 0, '龙田街道')")
        connection.execute(
            """
            INSERT INTO search_contents (
              id, platform, platform_content_id, content_type, title, snippet,
              creator_hash, publisher_name, published_at_text, content_url,
              first_seen_at, last_seen_at
            ) VALUES (
              99, 'wb', 'shared-100', 'post', '旧标题', '旧摘要',
              '0123456789abcdef', '微***户', '刚刚',
              'https://m.weibo.cn/detail/shared-100',
              '2026-08-25T08:00:01+00:00', '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_contents VALUES (
              41, 99, 'new', '2026-08-25T08:00:01+00:00',
              '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms VALUES (
              41, 99, 0, '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 75 WHERE name = 'search_runs'"
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 150 WHERE name = 'search_contents'"
        )
        before = {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in (
                "search_runs",
                "search_run_terms",
                "search_contents",
                "search_run_contents",
                "search_run_content_terms",
            )
        }
        connection.execute("COMMIT")
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()
    with database.connect() as migrated:
        after = {
            table: [tuple(row) for row in migrated.execute(f"SELECT * FROM {table}")]
            for table in before
        }
        sequences = dict(
            migrated.execute(
                """
                SELECT name, seq FROM sqlite_sequence
                WHERE name IN ('search_runs', 'search_contents')
                """
            ).fetchall()
        )
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []

    assert all(row[-2:] == (0, 1) for row in after["search_runs"])
    after["search_runs"] = [row[:-2] for row in after["search_runs"]]
    assert after == before
    assert sequences == {"search_contents": 150, "search_runs": 75}

    repository = SearchRunRepository(database)
    kuaishou = repository.create_run(
        monitoring_rule_id=1,
        platform="ks",
        rule_name="快手任务",
        terms=("龙田街道",),
        max_results_per_term=7,
    )
    repository.mark_running(kuaishou.id)
    _observe(
        repository,
        run_id=kuaishou.id,
        term_position=0,
        item=SearchContentInput(
            platform_content_id="shared-100",
            content_type="video",
            title="快手标题",
            snippet="快手正文",
            creator_hash="0123456789abcdef",
            publisher_name="快***户",
            published_at_text="2026-08-26 08:00",
            content_url="https://www.kuaishou.com/short-video/shared-100",
            observed_at="2026-08-26T08:00:00+00:00",
        ),
    )
    completed = repository.finish(kuaishou.id, "completed_with_results")
    assert kuaishou.id == 76
    assert (completed.new_count, completed.repeated_count) == (1, 0)
    with database.connect() as migrated:
        rows = migrated.execute(
            """
            SELECT platform, platform_content_id FROM search_contents
            WHERE platform_content_id = 'shared-100' ORDER BY platform
            """
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("ks", "shared-100"),
        ("wb", "shared-100"),
    ]


def test_version_four_migration_preserves_rows_and_isolates_douyin_identity(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-four.sqlite3"
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _migrate_to_version_1(connection)
        _migrate_to_version_2(connection)
        _migrate_to_version_3(connection)
        _migrate_to_version_4(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO search_runs (
              id, monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at, started_at, finished_at
            ) VALUES (41, 1, 'ks', '快手旧任务', 7, 'completed_with_results',
                      0, '2026-08-25T08:00:00+00:00',
                      '2026-08-25T08:00:01+00:00',
                      '2026-08-25T08:00:02+00:00')
            """
        )
        connection.execute("INSERT INTO search_run_terms VALUES (41, 0, '龙田街道')")
        connection.execute(
            """
            INSERT INTO search_contents (
              id, platform, platform_content_id, content_type, title, snippet,
              creator_hash, publisher_name, published_at_text, content_url,
              first_seen_at, last_seen_at
            ) VALUES (
              99, 'ks', '7512345678901234567', 'video', '旧标题', '旧摘要',
              '0123456789abcdef', '快***户', '2026-08-25 16:00',
              'https://www.kuaishou.com/short-video/7512345678901234567',
              '2026-08-25T08:00:01+00:00', '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_contents VALUES (
              41, 99, 'new', '2026-08-25T08:00:01+00:00',
              '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms VALUES (
              41, 99, 0, '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 75 WHERE name = 'search_runs'"
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 150 WHERE name = 'search_contents'"
        )
        before = {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in (
                "search_runs",
                "search_run_terms",
                "search_contents",
                "search_run_contents",
                "search_run_content_terms",
            )
        }
        connection.execute("COMMIT")
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()
    with database.connect() as migrated:
        after = {
            table: [tuple(row) for row in migrated.execute(f"SELECT * FROM {table}")]
            for table in before
        }
        sequences = dict(
            migrated.execute(
                """
                SELECT name, seq FROM sqlite_sequence
                WHERE name IN ('search_runs', 'search_contents')
                """
            ).fetchall()
        )
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []

    assert all(row[-2:] == (0, 1) for row in after["search_runs"])
    after["search_runs"] = [row[:-2] for row in after["search_runs"]]
    assert after == before
    assert sequences == {"search_contents": 150, "search_runs": 75}

    repository = SearchRunRepository(database)
    douyin = repository.create_run(
        monitoring_rule_id=1,
        platform="dy",
        rule_name="抖音任务",
        terms=("龙田街道",),
        max_results_per_term=7,
    )
    repository.mark_running(douyin.id)
    _observe(
        repository,
        run_id=douyin.id,
        term_position=0,
        item=SearchContentInput(
            platform_content_id="7512345678901234567",
            content_type="video",
            title="抖音标题",
            snippet="抖音正文",
            creator_hash="0123456789abcdef",
            publisher_name="抖***户",
            published_at_text="2026-08-26 16:00",
            content_url="https://www.douyin.com/video/7512345678901234567",
            observed_at="2026-08-26T08:00:00+00:00",
        ),
    )
    completed = repository.finish(douyin.id, "completed_with_results")

    assert douyin.id == 76
    assert (completed.new_count, completed.repeated_count) == (1, 0)
    with database.connect() as migrated:
        rows = migrated.execute(
            """
            SELECT platform, platform_content_id FROM search_contents
            WHERE platform_content_id = '7512345678901234567' ORDER BY platform
            """
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("dy", "7512345678901234567"),
        ("ks", "7512345678901234567"),
    ]


def test_version_five_migration_preserves_rows_sequences_and_adds_xhs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-five.sqlite3"
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _migrate_to_version_1(connection)
        _migrate_to_version_2(connection)
        _migrate_to_version_3(connection)
        _migrate_to_version_4(connection)
        _migrate_to_version_5(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO search_runs (
              id, monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at, started_at, finished_at
            ) VALUES (41, 1, 'dy', '抖音旧任务', 7, 'completed_with_results',
                      0, '2026-08-25T08:00:00+00:00',
                      '2026-08-25T08:00:01+00:00',
                      '2026-08-25T08:00:02+00:00')
            """
        )
        connection.execute("INSERT INTO search_run_terms VALUES (41, 0, '龙田街道')")
        connection.execute(
            """
            INSERT INTO search_contents (
              id, platform, platform_content_id, content_type, title, snippet,
              creator_hash, publisher_name, published_at_text, content_url,
              first_seen_at, last_seen_at
            ) VALUES (
              99, 'dy', '0123456789abcdef01234567', 'video', '旧标题', '旧摘要',
              '0123456789abcdef', '抖***户', '2026-08-25 16:00',
              'https://www.douyin.com/video/0123456789abcdef01234567',
              '2026-08-25T08:00:01+00:00', '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_contents VALUES (
              41, 99, 'new', '2026-08-25T08:00:01+00:00',
              '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms VALUES (
              41, 99, 0, '2026-08-25T08:00:01+00:00'
            )
            """
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 75 WHERE name = 'search_runs'"
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 150 WHERE name = 'search_contents'"
        )
        before = {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in (
                "search_runs",
                "search_run_terms",
                "search_contents",
                "search_run_contents",
                "search_run_content_terms",
            )
        }
        connection.execute("COMMIT")
    finally:
        connection.close()

    database = Database(database_path)
    database.initialize()
    with database.connect() as migrated:
        after = {
            table: [tuple(row) for row in migrated.execute(f"SELECT * FROM {table}")]
            for table in before
        }
        sequences = dict(
            migrated.execute(
                """
                SELECT name, seq FROM sqlite_sequence
                WHERE name IN ('search_runs', 'search_contents')
                """
            ).fetchall()
        )
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_DATABASE_VERSION
        )
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []

    assert all(row[-2:] == (0, 1) for row in after["search_runs"])
    after["search_runs"] = [row[:-2] for row in after["search_runs"]]
    assert after == before
    assert sequences == {"search_contents": 150, "search_runs": 75}

    repository = SearchRunRepository(database)
    xhs = repository.create_run(
        monitoring_rule_id=1,
        platform="xhs",
        rule_name="小红书任务",
        terms=("龙田街道",),
        max_results_per_term=7,
    )
    repository.mark_running(xhs.id)
    _observe(
        repository,
        run_id=xhs.id,
        term_position=0,
        item=SearchContentInput(
            platform_content_id="0123456789abcdef01234567",
            content_type="image",
            title="小红书标题",
            snippet="小红书标题",
            creator_hash="0123456789abcdef",
            publisher_name="小***户",
            published_at_text="",
            content_url=(
                "https://www.xiaohongshu.com/explore/0123456789abcdef01234567"
            ),
            observed_at="2026-08-26T08:00:00+00:00",
        ),
    )
    completed = repository.finish(xhs.id, "completed_with_results")

    assert xhs.id == 76
    assert (completed.new_count, completed.repeated_count) == (1, 0)
    with database.connect() as migrated:
        rows = migrated.execute(
            """
            SELECT platform, platform_content_id FROM search_contents
            WHERE platform_content_id = '0123456789abcdef01234567'
            ORDER BY platform
            """
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("dy", "0123456789abcdef01234567"),
        ("xhs", "0123456789abcdef01234567"),
    ]
