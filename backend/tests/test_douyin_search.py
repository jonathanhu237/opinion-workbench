"""Rendered Douyin search contracts; no account data or live requests."""

import asyncio
from urllib.parse import unquote, urlsplit

import pytest
from test_native_weibo_discovery import BrowserFixture

from opinion_workbench_api.services.native_weibo import (
    _PLATFORM_SEARCH,
    NativeWeiboCollector,
    _read_generic_page,
)
from opinion_workbench_api.services.search_runs import project_worker_outcome

URL = _PLATFORM_SEARCH["dy"]("龙田街道 投诉")


def card(identity="7440079663466073398", text="道路施工 #街道"):
    # Structural sample from the current public search card; names and text
    # are synthetic. Hashed presentation classes are intentionally omitted.
    return f"""<div id="waterfall_item_{identity}">
      <div class="search-result-card"><div><div>
        <div class="videoImage"><span>图文</span><span>73</span></div>
        <div><div><div>{text}</div><div>
          <span><span>@</span><span>测试作者</span></span>
          <span> · 2024年11月22日</span>
        </div></div></div>
      </div></div></div></div>"""


def test_search_url_uses_observed_route_and_encodes_path_not_query():
    term = "龙田街道 投诉+A/B?#"
    url = _PLATFORM_SEARCH["dy"](term)
    assert unquote(urlsplit(url).path.removeprefix("/jingxuan/search/")) == term
    assert "%20" in url and "%2B" in url and "%2F" in url
    assert urlsplit(url).query == "type=general"


@pytest.mark.parametrize("url", [URL, URL.replace("/jingxuan/search/", "/search/")])
def test_waterfall_cards_are_read_without_anchors_or_hashed_classes(url):
    state, items = _read_generic_page("dy", url, card() + card(), "龙田街道 投诉")
    assert state == "results"
    assert len(items) == 1
    item = items[0]
    assert item.title == "道路施工 #街道"
    assert item.snippet == item.title
    assert item.publisher_name == "测***者"
    assert item.creator_hash
    assert item.published_at_text == "2024年11月22日"
    assert item.content_url == "https://www.douyin.com/video/7440079663466073398"
    assert item.hashtags == ("街道",)
    assert item.interaction_stats == {}


@pytest.mark.parametrize(
    "raw",
    [
        "<main>正在加载</main>",
        card("invalid"),
        card().replace('class="search-result-card"', 'class="recommendation"'),
    ],
)
def test_missing_or_unrecognized_cards_are_not_reported_empty(raw):
    assert _read_generic_page("dy", URL, raw, "词")[0] == "pending"


def test_explicit_empty_state_is_empty():
    assert _read_generic_page("dy", URL, "<main><p>暂无搜索结果</p></main>", "词") == (
        "empty",
        (),
    )


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_gateway_errors_project_to_search_unavailable(status):
    state, items = _read_generic_page(
        "dy", URL, "<title>Bad Gateway</title>", "词", status
    )
    assert items == ()
    assert state == "search_context_unavailable"
    assert project_worker_outcome(state).failure_reason == "search_context_unavailable"


def test_search_waits_for_cards_and_keeps_per_term_cap():
    class HydratingBrowser(BrowserFixture):
        async def snapshot(self):
            value = await super().snapshot()
            self.html = card() + card("7440079663466073399", "另一条内容")
            return value

    async def run():
        browser = HydratingBrowser(["<main>正在加载</main>"])
        items, completed = [], []

        async def progress(*args):
            pass

        async def admit(position, item):
            items.append(item)

        async def finish(*args):
            completed.append(args)

        result = await NativeWeiboCollector(browser=browser).search(
            request_id="test",
            platform="dy",
            terms=["龙田街道 投诉"],
            max_results_per_term=1,
            on_progress=progress,
            on_item=admit,
            on_term_completed=finish,
        )
        assert result.outcome == "completed_with_results"
        assert len(items) == 1
        assert completed == [(0, 1, None)]
        assert browser.visits == [URL]

    asyncio.run(run())


def test_loading_timeout_never_completes_the_term_as_empty():
    async def run():
        browser = BrowserFixture(["<main>正在加载</main>"])
        completed = []

        async def ignore(*args):
            pass

        async def finish(*args):
            completed.append(args)

        result = await NativeWeiboCollector(
            browser=browser, timeout_seconds=0.01
        ).search(
            request_id="test",
            platform="dy",
            terms=["词"],
            max_results_per_term=10,
            on_progress=ignore,
            on_item=ignore,
            on_term_completed=finish,
        )
        assert result.outcome == "page_state_unrecognized"
        assert completed == []

    asyncio.run(run())
