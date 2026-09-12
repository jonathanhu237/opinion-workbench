"""Latest-first discovery and one durable, cross-keyword collection budget."""

import asyncio
import sqlite3
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from fixture_support import initialize_database
from test_automation_workflows import _repository, _task_payload
from test_native_weibo_discovery import EMPTY, BrowserFixture, card, environment
from test_search_batches import _control, _wait_for_batch
from test_search_recovery import _item, control
from test_search_runs import _wait_for_terminal

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.search_batches import SearchBatchRepository
from opinion_workbench_api.repositories.search_runs import (
    SearchRunNotActiveError,
    SearchRunRepository,
)
from opinion_workbench_api.schemas.automation_workflows import AutomationTaskReplace
from opinion_workbench_api.services.native_weibo import NativeWeiboCollector
from opinion_workbench_api.services.weibo_dom import read_search_page

A, B, C, D = (str(5012345678901234 + i) for i in range(4))


def run_collector(pages, *, limit=3, previous=(), **options):
    async def run():
        browser = BrowserFixture(pages)
        worker = NativeWeiboCollector(
            browser=browser, delay_seconds=0, ready_polls=1, **options
        )
        observations, completions = [], []

        async def progress(*args):
            pass

        async def item(position, value):
            observations.append((position, value.content_id))

        async def completed(*args):
            completions.append(args)

        result = await worker.search(
            request_id="latest-test",
            platform="wb",
            terms=("a", "b"),
            max_results_per_term=1,
            max_total_results=limit,
            previous_content_ids=previous,
            on_progress=progress,
            on_item=item,
            on_term_completed=completed,
        )
        return result, browser, observations, completions

    return asyncio.run(run())


def test_latest_parser_keeps_sort_on_pagination_and_rejects_fallback():
    url = "https://s.weibo.com/realtime?q=a&rd=realtime&tw=realtime"
    page = card(A, "最新", next_url="/realtime?q=a&page=2")
    parsed = read_search_page(url, page, 200, "a", latest=True)
    assert parsed.next_url == "https://s.weibo.com/realtime?q=a&page=2"
    assert (
        read_search_page(
            url.replace("/realtime?", "/weibo?"), page, 200, "a", latest=True
        ).state
        == "search_context_unavailable"
    )
    bad = page.replace('href="/realtime?', 'href="/weibo?')
    assert (
        read_search_page(url, bad, 200, "a", latest=True).state
        == "search_pagination_incompatible"
    )


def test_keywords_rotate_and_duplicates_share_one_slot():
    result, browser, items, completed = run_collector(
        [
            card(A, "a 最新") + card(B, "a 次新"),
            card(A, "重复") + card(C, "b 最新") + card(D, "不能超限"),
        ]
    )
    assert result.outcome == "completed_with_results"
    assert items == [(0, A), (1, A), (1, C), (0, B)]
    assert completed == [(0, 2, None), (1, 2, None)]
    assert len({identity for _, identity in items}) == 3
    assert [parse_qs(urlsplit(url).query)["q"] for url in browser.visits] == [
        ["a"],
        ["b"],
    ]
    assert all(urlsplit(url).path == "/realtime" for url in browser.visits)


def test_duplicate_only_page_yields_to_other_keyword_before_paging():
    result, browser, items, _ = run_collector(
        [
            card(A, "之前已有", next_url="/realtime?q=a&page=2"),
            card(B, "另一个词的新内容"),
        ],
        previous=(A,),
        limit=2,
    )
    assert result.outcome == "completed_with_results"
    assert items == [(0, A), (1, B)]
    assert len(browser.visits) == 2


def test_resume_at_cap_never_navigates_or_expands_budget():
    result, browser, items, completed = run_collector([], previous=(A, B, C))
    assert result.outcome == "completed_with_results"
    assert browser.visits == items == []
    assert completed == [(0, 0, None), (1, 0, None)]


def test_latest_pagination_has_a_hard_page_budget_and_keeps_partial_items():
    result, browser, items, completed = run_collector(
        [
            card(A, "第一页", next_url="/realtime?q=a&page=2"),
            EMPTY,
        ],
        max_pages=2,
    )
    assert result.outcome == "timed_out" and result.execution_limit == "pages"
    assert items == [(0, A)]
    assert completed == [(1, 0, None)]


def test_new_run_api_uses_total_limit_independent_of_legacy_per_term(tmp_path):
    app, browser = environment(
        tmp_path, [card(A, "一") + card(B, "二"), card(C, "三"), EMPTY, EMPTY, EMPTY]
    )
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "max_results_per_term": 1,
                "max_total_results": 3,
            },
        )
        assert started.status_code == 202, started.text
        result = _wait_for_terminal(client, started.json()["id"])
        assert result["status"] == "completed_with_results", result
        assert result["total_count"] == result["max_total_results"] == 3
        assert result["max_results_per_term"] == 1
        assert client.get("/api/v1/report-generations").json()["items"] == []
        assert client.get("/api/v1/content-analysis-jobs").json()["jobs"] == []
        assert all(urlsplit(url).path == "/realtime" for url in browser.visits)


def test_batch_manual_recovery_shares_frozen_cap_and_prior_ids(tmp_path):
    app, browser = environment(
        tmp_path,
        [
            card(A, "第一次"),
            "<title>安全验证</title>",
            card(A, "重复") + card(B, "继续一"),
            card(C, "继续二"),
        ],
    )
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_total_results": 3,
            },
        )
        assert started.status_code == 202, started.text
        identity = started.json()["id"]
        assert started.json()["items"][0]["checkpoint_basis"] == "unknown"
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        assert paused["items"][0]["total_count"] == 1
        assert paused["max_total_results"] == 3
        resumed = client.post(
            f"/api/v1/search-batches/{identity}/continue",
            json=_control(client, identity),
        )
        assert resumed.status_code == 202, resumed.text
        done = _wait_for_batch(client, identity, {"completed"})
        assert done["items"][0]["total_count"] == 3
        assert done["items"][0]["attempt_count"] == 2
        assert done["items"][0]["latest_attempt"]["run"]["max_total_results"] == 3
        assert len(browser.visits) == 4
        assert client.get("/api/v1/content-analysis-jobs").json()["jobs"] == []


def test_repository_fences_total_limit_including_previous_attempt(tmp_path):
    db = Database(tmp_path / "cap.sqlite3")
    initialize_database(db)
    batches, runs = SearchBatchRepository(db), SearchRunRepository(db)
    batch = batches.create_batch(
        monitoring_rule_id=1,
        rule_name="范围",
        terms=("a", "b"),
        platforms=("wb",),
        max_results_per_term=1,
        max_total_results=2,
    )
    batches.mark_running(batch.id)
    run = batches.create_attempt(batch.id, 0)
    runs.mark_running(run.id)
    runs.set_progress(run.id, 1)
    runs.observe_item(run_id=run.id, term_position=1, item=_item(A))
    runs.finish(run.id, "login_required")
    paused = batches.finish_item(batch.id, 0, "login_required")
    batches.continue_batch(batch.id, **control(paused))
    retry = batches.create_attempt(batch.id, 0)
    runs.mark_running(retry.id)
    runs.set_progress(retry.id, 0)
    runs.observe_item(run_id=retry.id, term_position=0, item=_item(B))
    runs.observe_item(run_id=retry.id, term_position=0, item=_item(A))
    with pytest.raises(SearchRunNotActiveError):
        runs.observe_item(run_id=retry.id, term_position=0, item=_item(C))
    assert runs.collection_content_ids(retry.id) == {A, B}
    with db.connect() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM search_contents WHERE platform_content_id=?", (C,)
            ).fetchone()
            is None
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE search_batches SET max_total_results=3 WHERE id=?", (batch.id,)
            )


def test_automation_total_limit_is_saved_replaced_and_legacy_is_distinct(tmp_path):
    _, _, repo = _repository(tmp_path)
    now = datetime.now(UTC)
    legacy = repo.create_task(_task_payload(name="旧任务"), now=now)
    task = repo.create_task(_task_payload(max_total_results=25), now=now)
    assert legacy.max_total_results is None
    assert repo.get_task(task.id).max_total_results == 25
    payload = AutomationTaskReplace.model_validate(
        {
            **_task_payload(max_total_results=12).model_dump(),
            "enabled": False,
            "expected_revision": task.revision,
        }
    )
    replaced = repo.replace_task(
        task.id, payload, now=now, next_due_at=None, anchor_at=None
    )
    assert replaced.max_total_results == 12


def test_automation_freezes_total_limit_and_passes_it_to_collection(tmp_path):
    from test_automation_workflows import REQUEST, _FakeBatch, _NoModel, _NoReport

    from opinion_workbench_api.schemas.automation_workflows import AutomationRunNow
    from opinion_workbench_api.services.automation_workflows import (
        AutomationWorkflowService,
    )

    async def run():
        database, rules, repository = _repository(tmp_path)
        batches = _FakeBatch(["completed"])
        service = AutomationWorkflowService(
            database,
            monitoring_rules=rules,
            batches=batches,
            analyses=_NoModel(),
            reports=_NoReport(),
            repository=repository,
        )
        service.initialize()
        task = service.create_task(_task_payload(max_total_results=23))
        started = await service.run_now(task.id, AutomationRunNow(request_id=REQUEST))
        await asyncio.wait_for(asyncio.shield(service._run_tasks[started.id]), 2)
        assert service.get_run(started.id).snapshot.max_total_results == 23
        assert batches.calls[0]["max_total_results"] == 23
        await service.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("limit", [0, 51, -1, 1.5])
def test_total_limit_rejects_out_of_bounds_api_input(tmp_path, limit):
    app, browser = environment(tmp_path, [])
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/search-batches",
                json={"monitoring_rule_id": 1, "max_total_results": limit},
            ).status_code
            == 422
        )
        assert browser.visits == []
