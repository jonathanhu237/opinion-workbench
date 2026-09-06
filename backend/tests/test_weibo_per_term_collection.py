"""Latest-first per-keyword limits and rendered empty-page regression tests."""

import asyncio
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_native_weibo_discovery import EMPTY, BrowserFixture, card, environment
from test_search_batches import _control, _wait_for_batch
from test_search_runs import _wait_for_terminal

from longtian_api.services.native_weibo import NativeWeiboCollector
from longtian_api.services.weibo_dom import read_search_page

A, B = "5012345678901234", "5012345678901235"


def empty_page(*, number=2, next_page=3):
    # Sanitized structure observed in the real /realtime search page, including
    # an empty feed area followed by a pager that still offers a next page.
    previous = (
        f'<a class="prev" href="/realtime?q=a&amp;page={number - 1}">b</a>'
        if number > 1
        else ""
    )
    following = (
        f'<a class="next" href="/realtime?q=a&amp;page={next_page}">a</a>'
        if next_page is not None
        else ""
    )
    return f"""<div id="pl_feedlist_index" class="main-full"><div></div>
      <div class="m-page2">{previous}<ul class="page-list">
      <li class="cur"><a href="/realtime?q=a&amp;page={number}">{number}</a></li>
      {following}</ul></div><div class="m-footer"></div></div>"""


def collect(
    pages,
    *,
    limit=10,
    terms=("a", "b"),
    browser_type=BrowserFixture,
    previous=(),
    **options,
):
    async def run():
        browser = browser_type(pages)
        worker = NativeWeiboCollector(
            browser=browser, delay_seconds=0, **{"ready_polls": 1, **options}
        )
        items, completions = [], []

        async def progress(*args):
            pass

        async def item(position, value):
            items.append((position, value.content_id))

        async def completed(*args):
            completions.append(args)

        result = await worker.search(
            request_id="per-term",
            platform="wb",
            terms=terms,
            max_results_per_term=limit,
            previous_content_ids_by_term=previous,
            on_progress=progress,
            on_item=item,
            on_term_completed=completed,
        )
        return result, browser, items, completions

    return asyncio.run(run())


@pytest.mark.parametrize("second_count", [0, 2, 15])
def test_default_is_latest_and_each_term_gets_its_own_ten(second_count):
    first = "".join(card(str(int(A) + i), "第一词") for i in range(15))
    # Overlap is still attributed to each matching keyword; it does not stop
    # subsequent keywords or turn their independent limits into a shared cap.
    second = "".join(card(str(int(A) + i + 5), "第二词") for i in range(second_count))
    result, browser, items, completed = collect([first, second or EMPTY])
    assert result.outcome == "completed_with_results"
    assert completed == [(0, 10, None), (1, min(second_count, 10), None)]
    assert len(items) == 10 + min(second_count, 10)
    assert all(urlsplit(url).path == "/realtime" for url in browser.visits)
    assert [parse_qs(urlsplit(url).query)["q"] for url in browser.visits] == [
        ["a"],
        ["b"],
    ]


def test_empty_middle_page_does_not_discard_later_results():
    result, browser, items, completed = collect(
        [
            card(A, "第一页", next_url="/realtime?q=a&page=2"),
            empty_page(),
            card(B, "第三页"),
        ],
        terms=("a",),
        ready_polls=2,
    )
    assert result.outcome == "completed_with_results"
    assert items == [(0, A), (0, B)]
    assert completed == [(0, 2, None)]
    assert len(browser.visits) == 3
    assert browser.frozen


def test_empty_last_page_finishes_with_actual_count():
    result, _, items, completed = collect(
        [
            card(A, "第一页", next_url="/realtime?q=a&page=2"),
            empty_page(next_page=None),
        ],
        terms=("a",),
    )
    assert result.outcome == "completed_with_results"
    assert items == [(0, A)] and completed == [(0, 1, None)]


@pytest.mark.parametrize("with_cards", [False, True])
def test_disabled_next_link_is_normal_last_page_not_pagination_failure(with_cards):
    disabled = '<a href="javascript:void(0);" class="next disabled"><i>a</i></a>'
    page = empty_page(next_page=None).replace("</ul>", disabled + "</ul>")
    if with_cards:
        page += card(A, "最后一条")
    parsed = read_search_page(
        "https://s.weibo.com/realtime?q=a&page=2",
        page,
        200,
        "a",
        latest=True,
    )
    assert parsed.state == ("results" if with_cards else "empty_page")
    assert parsed.next_url is None
    # A still-enabled arbitrary navigation remains an error.
    assert (
        read_search_page(
            "https://s.weibo.com/realtime?q=a&page=2",
            page.replace('class="next disabled"', 'class="next"'),
            200,
            "a",
            latest=True,
        ).state
        == "search_pagination_incompatible"
    )


def test_waits_for_late_cards_before_skipping_empty_page():
    class DelayedCards(BrowserFixture):
        async def snapshot(self):
            before = self.html
            self.html = card(B, "延迟加载")
            return self.url, before, 200

    result, _, items, _ = collect(
        [empty_page(number=1, next_page=2)],
        terms=("a",),
        browser_type=DelayedCards,
        ready_polls=2,
    )
    assert result.outcome == "completed_with_results"
    assert items == [(0, B)]


@pytest.mark.parametrize(
    "page,expected",
    [
        ("<main>加载中</main>", "pending"),
        (empty_page().replace('id="pl_feedlist_index"', 'id="sidebar"'), "pending"),
        (empty_page(number=3), "pending"),
        (empty_page().replace("q=a", "q=other"), "pending"),
        (empty_page(next_page=2), "search_pagination_incompatible"),
        (
            empty_page().replace(
                'href="/realtime?q=a&amp;page=3"',
                'href="https://example.com/realtime?q=a&amp;page=3"',
            ),
            "search_pagination_incompatible",
        ),
        (empty_page() + "<title>安全验证</title>", "manual_challenge_required"),
        (empty_page() + '<form><input type="password"></form>', "login_required"),
    ],
)
def test_empty_page_requires_valid_platform_pager_and_respects_barriers(page, expected):
    assert (
        read_search_page(
            "https://s.weibo.com/realtime?q=a&page=2",
            page,
            200,
            "a",
            latest=True,
        ).state
        == expected
    )


def test_empty_page_navigation_is_still_bounded():
    result, browser, items, _ = collect(
        [card(A, "第一页", next_url="/realtime?q=a&page=2"), empty_page()],
        terms=("a",),
        max_pages=2,
    )
    assert result.outcome == "timed_out" and result.execution_limit == "pages"
    assert items == [(0, A)] and len(browser.visits) == 2


def test_api_per_term_limit_allows_more_than_ten_and_deduplicates_across_terms(
    tmp_path,
):
    first = "".join(card(str(int(A) + i), "一") for i in range(12))
    second = "".join(card(str(int(A) + i + 5), "二") for i in range(12))
    app, browser = environment(
        tmp_path, [first, second, EMPTY, EMPTY, EMPTY], latest_first=True
    )
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "max_results_per_term": 10,
            },
        )
        assert started.status_code == 202, started.text
        result = _wait_for_terminal(client, started.json()["id"])
        assert result["status"] == "completed_with_results", result
        assert result["total_count"] == 15
        assert result["max_total_results"] is None
        assert result["max_results_per_term"] == 10
        assert all(urlsplit(url).path == "/realtime" for url in browser.visits)
        assert client.get("/api/v1/content-analysis-jobs").json()["jobs"] == []


def test_resume_at_per_term_cap_does_not_navigate_or_start_a_fresh_budget():
    result, browser, items, completed = collect(
        [],
        limit=1,
        previous=((A,), (B,)),
    )
    assert result.outcome == "completed_with_results"
    assert browser.visits == items == []
    # Completion proofs count this attempt only; the batch retains prior items.
    assert completed == [(0, 0, None), (1, 0, None)]


def test_recovery_retains_partial_term_budget_and_gives_next_term_its_own_limit(
    tmp_path,
):
    c, d = str(int(A) + 2), str(int(A) + 3)
    app, browser = environment(
        tmp_path,
        [
            card(A, "暂停前", next_url="/realtime?q=龙田街道&page=2"),
            "<title>安全验证</title>",
            card(B, "续采新增") + card(c, "本词不能超限"),
            card(c, "另一词") + card(d, "另一词"),
            EMPTY,
            EMPTY,
            EMPTY,
        ],
        latest_first=True,
    )
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "max_results_per_term": 2,
            },
        )
        assert started.status_code == 202, started.text
        identity = started.json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        assert paused["items"][0]["total_count"] == 1
        assert browser.frozen
        resumed = client.post(
            f"/api/v1/search-batches/{identity}/continue",
            json=_control(client, identity),
        )
        assert resumed.status_code == 202, resumed.text
        done = _wait_for_batch(client, identity, {"completed"})
        assert done["items"][0]["total_count"] == 4
        with sqlite3.connect(tmp_path / "db.sqlite3") as connection:
            counts = connection.execute(
                """SELECT term_position, COUNT(DISTINCT search_content_id)
                   FROM search_run_content_terms
                   GROUP BY term_position ORDER BY term_position"""
            ).fetchall()
        assert counts == [(0, 2), (1, 2)]


def test_repository_enforces_per_term_cap_across_attempts_without_limiting_other_terms(
    tmp_path,
):
    from test_search_recovery import _item, control

    from longtian_api.database import Database
    from longtian_api.repositories.search_batches import SearchBatchRepository
    from longtian_api.repositories.search_runs import (
        SearchRunNotActiveError,
        SearchRunRepository,
    )

    database = Database(tmp_path / "cap.sqlite3")
    database.initialize()
    batches, runs = SearchBatchRepository(database), SearchRunRepository(database)
    batch = batches.create_batch(
        monitoring_rule_id=1,
        rule_name="每词上限",
        terms=("a", "b"),
        platforms=("wb",),
        max_results_per_term=1,
    )
    batches.mark_running(batch.id)
    first = batches.create_attempt(batch.id, 0)
    runs.mark_running(first.id)
    runs.set_progress(first.id, 0)
    runs.observe_item(run_id=first.id, term_position=0, item=_item(A))
    runs.finish(first.id, "login_required")
    paused = batches.finish_item(batch.id, 0, "login_required")
    batches.continue_batch(batch.id, **control(paused))
    retry = batches.create_attempt(batch.id, 0)
    runs.mark_running(retry.id)
    runs.set_progress(retry.id, 0)
    with pytest.raises(SearchRunNotActiveError):
        runs.observe_item(run_id=retry.id, term_position=0, item=_item(B))
    runs.observe_item(run_id=retry.id, term_position=0, item=_item(A))
    runs.complete_term(retry.id, 0, 1)
    runs.set_progress(retry.id, 1)
    runs.observe_item(run_id=retry.id, term_position=1, item=_item(B))
    assert runs.collection_term_content_ids(retry.id) == {0: {A}, 1: {B}}
