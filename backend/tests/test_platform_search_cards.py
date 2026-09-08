"""Current public search DOM contracts, using synthetic content only."""

import asyncio
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from test_native_weibo_discovery import BrowserFixture

from longtian_api.services.native_browser_contracts import BrowserUnavailable
from longtian_api.services.native_weibo import (
    _PLATFORM_SEARCH,
    NativeWeiboCollector,
    _generic_content_identity,
    _read_generic_page,
)


def jump(target):
    landing = "https://article.zlink.toutiao.com/J4dQM?" + urlencode({"h5_url": target})
    return "https://so.toutiao.com/search/jump?" + urlencode({"url": landing})


def test_toutiao_search_uses_the_observed_news_tab_and_preserves_keyword():
    url = _PLATFORM_SEARCH["toutiao"]("社区 投诉+A&B")
    assert parse_qs(urlsplit(url).query) == {
        "keyword": ["社区 投诉+A&B"],
        "pd": ["information"],
    }


KS = """<div class="video-list"><div class="photo-card">
 <div class="cover"><img class="cover-img"
 src="https://p1.a.yximgs.com/upic/test.jpg?clientCacheKey=3x123456789abcd_ccc.jpg"></div>
 <div class="caption">社区道路施工 #民生</div>
 <div class="info"><span class="user"><span class="name">测试作者</span></span>
 <div class="like">1.2万</div></div></div></div>"""
XHS_ID = "65b363f7000000002c03d319"
XHS = f"""<section class="note-item"><div>
 <a href="/explore/{XHS_ID}" style="display:none"></a>
 <a class="cover" href="/search_result/{XHS_ID}"></a>
 <div class="footer"><a class="title" href="/search_result/{XHS_ID}">社区施工投诉</a>
 <a class="author"><div class="name">测试作者</div><div class="time">04-27</div></a>
 <span class="like-wrapper"><span class="count">8</span></span></div></div></section>"""


def test_kuaishou_cards_without_anchors_have_correct_public_identity():
    state, items = _read_generic_page(
        "ks", "https://www.kuaishou.com/search/video", KS + KS, "社区"
    )
    assert state == "results"
    assert len(items) == 1
    assert items[0].content_id == "3x123456789abcd"
    assert (
        items[0].content_url == "https://www.kuaishou.com/short-video/3x123456789abcd"
    )
    assert items[0].title == "社区道路施工 #民生"
    assert items[0].publisher_name == "测***者"
    assert items[0].interaction_stats == {"likes": 12000}


@pytest.mark.parametrize(
    "raw",
    [
        KS.replace("p1.a.yximgs.com", "evil.example"),
        KS.replace("clientCacheKey", "unknown"),
        KS.replace("3x123456789abcd_ccc.jpg", "unrecognized.jpg"),
        KS.replace('class="video-list"', 'class="recommendations"'),
    ],
)
def test_kuaishou_unrecognized_cards_are_not_reported_empty(raw):
    assert (
        _read_generic_page("ks", "https://www.kuaishou.com/search/video", raw, "社区")[
            0
        ]
        == "pending"
    )


@pytest.mark.parametrize(
    ("target", "canonical"),
    [
        (
            "https://toutiao.com/group/7624497277990437428/",
            "https://www.toutiao.com/article/7624497277990437428/",
        ),
        (
            "https://weitoutiao.zjurl.cn/ugc/share/wap/thread/1619425803776014/?source=search",
            "https://www.toutiao.com/w/1619425803776014/",
        ),
        (
            "https://www.toutiao.com/video/7624497277990437428/",
            "https://www.toutiao.com/video/7624497277990437428/",
        ),
    ],
)
def test_toutiao_public_jump_links_resolve_without_tracking_parameters(
    target, canonical
):
    href = jump(target)
    identity = _generic_content_identity(
        "toutiao", href, "https://so.toutiao.com/search"
    )
    assert identity[2] == canonical
    state, items = _read_generic_page(
        "toutiao",
        "https://so.toutiao.com/search",
        f'<a href="{href}">社区新闻</a>',
        "社区",
    )
    assert state == "results"
    assert items[0].title == "社区新闻"
    assert items[0].content_url == canonical


@pytest.mark.parametrize(
    "href",
    [
        jump("https://example.com/article/7624497277990437428/"),
        jump("https://toutiao.com.evil.example/group/7624497277990437428/"),
        jump("https://user:password@toutiao.com/group/7624497277990437428/"),
        jump("http://toutiao.com/group/7624497277990437428/"),
        jump("https://www.toutiao.com/c/user/5827361912/"),
        "https://evil.example/search/jump?"
        + urlencode({"url": "https://www.toutiao.com/article/7624497277990437428/"}),
        "https://so.toutiao.com/search/jump?url=one&url=two",
    ],
)
def test_toutiao_rejects_external_results_and_untrusted_wrappers(href):
    assert (
        _generic_content_identity("toutiao", href, "https://so.toutiao.com/search")
        is None
    )


def test_xiaohongshu_caption_and_metadata_are_read_from_the_note_not_page_title():
    state, items = _read_generic_page(
        "xhs",
        "https://www.xiaohongshu.com/search_result",
        "<title>搜索页面</title>" + XHS,
        "社区",
    )
    assert state == "results"
    assert len(items) == 1
    assert items[0].title == "社区施工投诉"
    assert items[0].publisher_name == "测***者"
    assert items[0].published_at_text == "04-27"
    assert items[0].interaction_stats == {"likes": 8}


@pytest.mark.parametrize("platform", ["ks", "xhs", "toutiao"])
def test_only_explicit_empty_state_completes_an_empty_search(platform):
    assert (
        _read_generic_page(
            platform, "https://example.com", "<main>正在加载</main>", "词"
        )[0]
        == "pending"
    )
    assert _read_generic_page(
        platform, "https://example.com", "<main><p>暂无搜索结果</p></main>", "词"
    ) == ("empty", ())


@pytest.mark.parametrize(
    ("platform", "html"),
    [
        ("ks", KS),
        ("xhs", XHS),
        (
            "toutiao",
            f'<a href="{jump("https://toutiao.com/group/7624497277990437428/")}">社区新闻</a>',
        ),
    ],
)
def test_collection_waits_for_results_before_marking_a_term_complete(platform, html):
    class HydratingBrowser(BrowserFixture):
        async def snapshot(self):
            value = await super().snapshot()
            self.html = html
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
            platform=platform,
            terms=["社区"],
            max_results_per_term=1,
            on_progress=progress,
            on_item=admit,
            on_term_completed=finish,
        )
        assert result.outcome == "completed_with_results"
        assert len(items) == 1
        assert completed == [(0, 1, None)]

    asyncio.run(run())


@pytest.mark.parametrize("platform", ["ks", "xhs", "toutiao"])
def test_unknown_page_never_records_a_successful_empty_checkpoint(platform):
    async def run():
        completed = []

        async def ignore(*args):
            pass

        async def finish(*args):
            completed.append(args)

        result = await NativeWeiboCollector(
            browser=BrowserFixture(["<main>未知结构</main>"]), timeout_seconds=0.01
        ).search(
            request_id="test",
            platform=platform,
            terms=["社区"],
            max_results_per_term=1,
            on_progress=ignore,
            on_item=ignore,
            on_term_completed=finish,
        )
        assert result.outcome == "page_state_unrecognized"
        assert completed == []

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failures", "connected", "max_pages", "outcome", "visits"),
    [
        (1, True, 40, "completed_with_results", 2),
        (2, True, 40, "browser_unavailable", 2),
        (1, False, 40, "browser_unavailable", 1),
        (1, True, 1, "timed_out", 1),
    ],
)
def test_initial_dom_read_retry_is_bounded_and_never_duplicates_results(
    failures, connected, max_pages, outcome, visits
):
    class SlowNavigationBrowser(BrowserFixture):
        async def snapshot(self):
            if len(self.visits) <= failures:
                self.available = connected
                raise BrowserUnavailable()
            return await super().snapshot()

    async def run():
        browser = SlowNavigationBrowser([XHS, XHS])
        items, completed = [], []

        async def ignore(*args):
            pass

        async def admit(position, item):
            items.append(item)

        async def finish(*args):
            completed.append(args)

        result = await NativeWeiboCollector(
            browser=browser, max_pages=max_pages
        ).search(
            request_id="test",
            platform="xhs",
            terms=["社区"],
            max_results_per_term=1,
            on_progress=ignore,
            on_item=admit,
            on_term_completed=finish,
        )
        assert result.outcome == outcome
        assert len(browser.visits) == visits
        assert len(items) == (1 if outcome == "completed_with_results" else 0)
        assert len(completed) == len(items)

    asyncio.run(run())
