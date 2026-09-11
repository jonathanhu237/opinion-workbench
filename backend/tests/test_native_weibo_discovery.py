"""User collection requests with rendered-browser fixtures, no platform access."""

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import quote_plus, urlencode

import pytest
from fastapi.testclient import TestClient
from test_search_batches import _control, _wait_for_batch
from test_search_runs import _wait_for_terminal

from longtian_api.main import create_app
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.collector_contracts import AuthWorkerResult
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.native_weibo import (
    NativeWeiboCollector,
    _classify_connection_page,
    _generic_detail_text,
)
from longtian_api.services.platform_access import (
    PlatformAccessCoordinator,
    PlatformAccessService,
)
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.weibo_dom import barrier, document, read_search_page

CARD = """<div class="card-wrap" action-type="feed_list_item" mid="3501756485200075">
  <div class="content"><a class="name" href="//weibo.com/1234567890">样本发布者</a>
  <p node-type="feed_list_content">龙田街道道路施工公告</p>
  <p class="from"><a href="//weibo.com/1234567890/z0JH2lOMb">今天 12:00</a></p>
  </div></div>"""
EMPTY = '<div class="card-no-result">抱歉，未找到相关结果。</div>'


def card(mid: str, body: str, *, next_url: str | None = None) -> str:
    next_link = f'<a class="next" href="{next_url}">下一页</a>' if next_url else ""
    return f"""<div class="card-wrap" action-type="feed_list_item" mid="{mid}">
      <div class="content"><a class="name" href="//weibo.com/1234567890">样本发布者</a>
      <p node-type="feed_list_content">{body}</p>
      <p class="from"><a href="https://m.weibo.cn/detail/{mid}">今天 12:00</a></p>
      </div></div>{next_link}"""


def omitted_page(term: str) -> str:
    # Verified against the rendered page: #pl_feedlist_index .m-error contains
    # the omission text and the "查看全部搜索结果" link.
    encoded = quote_plus(term)
    return f"""<div id="pl_feedlist_index" class="main-full">
      <div class="m-error">
      找到 40 条结果，部分相似结果已省略
      <a href="https://s.weibo.com/weibo?q={encoded}&amp;nodup=1">查看全部搜索结果</a>
      </div>
    </div>"""


def loading_page() -> str:
    return "<main>正在加载</main>"


def test_omission_parser_requires_notice_and_same_keyword_view_all_link():
    term = "龙田街道"
    url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
    parsed = read_search_page(url, omitted_page(term), 200, term)
    assert parsed.state == "omitted"
    assert parsed.view_all_url == url + "&nodup=1"

    assert read_search_page(url, loading_page(), 200, term).state == "pending"
    wrong_keyword = omitted_page("竹坑社区")
    assert read_search_page(url, wrong_keyword, 200, term).state == "pending"
    invalid_target = omitted_page(term).replace(
        "https://s.weibo.com/weibo?q=", "https://example.com/weibo?q="
    )
    assert read_search_page(url, invalid_target, 200, term).state == "pending"


def test_omission_text_in_a_post_does_not_trigger_recovery():
    term = "龙田街道"
    url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
    page = card("5012345678901234", "用户说：部分相似结果已省略")
    parsed = read_search_page(url, page, 200, term)
    assert parsed.state == "results"
    assert parsed.view_all_url is None


def test_unrelated_visible_notice_does_not_trigger_recovery():
    term = "龙田街道"
    url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
    page = omitted_page(term).replace(
        'id="pl_feedlist_index" class="main-full"', 'class="sidebar-promo"'
    )
    parsed = read_search_page(url, page, 200, term)
    assert parsed.state == "pending"
    assert parsed.view_all_url is None


def test_plain_browser_403_is_not_security_verification_without_evidence():
    url = "https://s.weibo.com/weibo?q=" + quote_plus("龙田街道")
    assert barrier(document("<main>暂时无法访问</main>"), url, 403) == (
        "search_context_unavailable"
    )
    assert read_search_page(url, "", 403, "龙田街道").state == (
        "search_context_unavailable"
    )
    challenge = "<title>安全验证</title>"
    assert barrier(document(challenge), url, 403) == "manual_challenge_required"


def test_generic_detail_text_rejects_page_chrome_and_untrusted_metadata():
    root = document(
        '<meta property="og:description" content="搜索摘要"><main>导航 推荐内容</main>'
    )
    assert _generic_detail_text(root) == ("", False)


def test_generic_detail_text_marks_limits_and_preserves_quoted_attribution():
    root = document(
        '<div class="post-content">自己的正文 '
        "<blockquote>被引用的原文</blockquote></div>"
    )
    body, truncated = _generic_detail_text(root, max_chars=20)
    assert body == "自己的正文\n\n【转发附带原帖】\n被引用的"
    assert truncated


def test_manual_report_recovery_opens_the_affected_post_context():
    async def run():
        browser = BrowserFixture([EMPTY])
        browser.page_present = False
        target = "https://m.weibo.cn/detail/3501756485200075"
        collector = NativeWeiboCollector(
            browser=browser,
            enricher=SimpleNamespace(manual_target_url=target),
        )
        result = await collector.manual_page(
            request_id="request",
            platform="wb",
            action="show",
        )
        return result, browser

    result, browser = asyncio.run(run())
    assert result.outcome == "opened_homepage"
    assert browser.visits == ["https://m.weibo.cn/detail/3501756485200075"]


class BrowserFixture:
    """The external browser returns DOM, not pre-parsed collection results."""

    available = True

    def __init__(self, pages):
        self.pages = deque(pages)
        self.check_pages = deque(pages)
        self.visits = []
        self.check_visits = []
        self.html = ""
        self.check_html = ""
        self.url = "about:blank"
        self.check_url = "about:blank"
        self.closed = False
        self.check_closed = False
        self.page_present = False
        self.block_at = None
        self.check_block = False
        self.entered = asyncio.Event()
        self.fronted = False

    async def start(self):
        self.page_present = True

    async def navigate(self, url):
        self.visits.append(url)
        if len(self.visits) == self.block_at:
            self.entered.set()
            await asyncio.Event().wait()
        self.url = url
        self.html = self.pages.popleft()

    async def bring_to_front(self):
        self.fronted = True

    async def snapshot(self):
        return self.url, self.html, 200

    async def start_check_page(self):
        self.check_closed = False

    async def navigate_check(self, url):
        self.check_visits.append(url)
        if self.check_block:
            self.entered.set()
            await asyncio.Event().wait()
        self.check_url = url
        self.check_html = self.check_pages.popleft()

    async def snapshot_check(self):
        return self.check_url, self.check_html, 200

    async def close_check_page(self):
        self.check_closed = True

    async def show(self):
        self.fronted = True
        self.page_present = True

    async def close_page(self):
        self.closed = True
        self.page_present = False

    async def shutdown(self):
        self.closed = True


class _VirtualPacingClock:
    """Advance durable pacing without making DOM fixtures sleep in real time."""

    def __init__(self):
        self.monotonic_value = 0.0
        self.wall_value = datetime(2026, 1, 1, tzinfo=UTC)

    def monotonic(self):
        return self.monotonic_value

    def wall(self):
        return self.wall_value

    async def sleep(self, seconds):
        self.monotonic_value += max(0.0, seconds)
        self.wall_value += timedelta(seconds=max(0.0, seconds))
        await asyncio.sleep(0)


def environment(tmp_path, pages, *, model=None, **runtime_options):
    # These fixtures explicitly cover the historical comprehensive-search DOM.
    # Latest-first default/per-term behavior is exercised in test_latest_collection.
    runtime_options.setdefault("latest_first", False)
    browser = BrowserFixture(pages)
    runtime = NativeWeiboCollector(
        browser=browser, delay_seconds=0, ready_polls=2, **runtime_options
    )
    service = PlatformConnectionService(collector_factory=lambda **kwargs: runtime)
    pacing_clock = _VirtualPacingClock()
    app = create_app(
        platform_connection_service_factory=lambda: service,
        platform_access_service_factory=lambda database: PlatformAccessService(
            database,
            coordinator=PlatformAccessCoordinator(
                database=database,
                clock=pacing_clock.monotonic,
                wall_clock=pacing_clock.wall,
                sleep=pacing_clock.sleep,
            ),
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "db.sqlite3"
        ),
        ai_settings_service_factory=(
            (lambda db: AISettingsService(db, client=model)) if model else None
        ),
    )
    return app, browser


def test_open_browser_is_separate_from_login_status_check(tmp_path):
    logged_in = '<header><a href="/u/123456">退出</a></header>'
    app, browser = environment(tmp_path, [logged_in])
    with TestClient(app) as client:
        opened = client.post("/api/v1/platform-connections/browser")
        assert opened.status_code == 200
        assert opened.json() == {"outcome": "opened_homepage"}
        assert browser.visits == []

        started = client.post("/api/v1/platform-connections/wb/attempts")
        assert started.status_code == 202
        for _ in range(30):
            connection = client.get("/api/v1/platform-connections").json()["platforms"][
                0
            ]
            if connection["status"] != "checking":
                break
            client.portal.call(asyncio.sleep, 0.01)

    assert connection["status"] == "connected"
    assert browser.check_visits == ["https://weibo.com/"]
    assert browser.check_closed
    assert browser.fronted


def test_open_browser_reuses_existing_window_and_reopens_after_close(tmp_path):
    app, browser = environment(tmp_path, [EMPTY])
    with TestClient(app) as client:
        first = client.post("/api/v1/platform-connections/browser")
        second = client.post("/api/v1/platform-connections/browser")
        assert first.json() == {"outcome": "opened_homepage"}
        assert second.json() == {"outcome": "opened_existing"}

        client.portal.call(browser.close_page)
        reopened = client.post("/api/v1/platform-connections/browser")
        assert reopened.json() == {"outcome": "opened_homepage"}

    assert browser.closed


def test_open_platform_browser_navigates_only_the_selected_homepage(tmp_path):
    app, browser = environment(tmp_path, [EMPTY, EMPTY])
    with TestClient(app) as client:
        opened = client.post("/api/v1/platform-connections/browser")
        assert opened.status_code == 200
        assert browser.visits == []
        douyin = client.post("/api/v1/platform-connections/dy/browser")
        assert douyin.status_code == 200
        assert douyin.json() == {"outcome": "opened_existing"}
        xiaohongshu = client.post("/api/v1/platform-connections/xhs/browser")
        assert xiaohongshu.status_code == 200
        assert xiaohongshu.json() == {"outcome": "opened_existing"}
        visits = list(browser.visits)
        client.post("/api/v1/platform-connections/browser")
        assert browser.visits == visits
        unknown = client.post("/api/v1/platform-connections/unknown/browser")
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "platform_not_found"

    assert browser.visits == [
        "https://www.douyin.com/",
        "https://www.xiaohongshu.com/",
    ]


def test_open_browser_failure_is_sanitized_and_releases_admission(tmp_path):
    app, browser = environment(tmp_path, [EMPTY])

    async def fail_show():
        from longtian_api.services.native_browser_contracts import BrowserUnavailable

        raise BrowserUnavailable()

    browser.show = fail_show
    with TestClient(app) as client:
        failed = client.post("/api/v1/platform-connections/browser")
        assert failed.status_code == 503
        assert failed.json() == {
            "detail": {
                "code": "browser_open_failed",
                "message": "专用浏览器打开失败，请重试。",
            }
        }

        # The failed opener must release the shared browser admission.  Restore
        # the real async method before retrying the same service instance.
        async def recover_show():
            browser.fronted = True
            browser.page_present = True

        browser.show = recover_show
        recovered = client.post("/api/v1/platform-connections/browser")
        assert recovered.status_code == 200


def test_login_status_check_finishes_as_not_logged_in_without_waiting(tmp_path):
    login_page = '<form>请先登录<input type="password"></form>'
    app, browser = environment(tmp_path, [login_page])
    with TestClient(app) as client:
        assert client.post("/api/v1/platform-connections/browser").status_code == 200
        started = client.post("/api/v1/platform-connections/wb/attempts")
        assert started.status_code == 202
        for _ in range(30):
            connection = client.get("/api/v1/platform-connections").json()["platforms"][
                0
            ]
            if connection["status"] != "checking":
                break
            client.portal.call(asyncio.sleep, 0.01)

    assert connection["status"] == "disconnected"
    assert connection["guidance"] == "retry"
    assert browser.check_closed


def test_login_status_check_requires_an_open_managed_browser(tmp_path):
    app, browser = environment(tmp_path, [EMPTY])
    browser.available = False
    with TestClient(app) as client:
        response = client.post("/api/v1/platform-connections/wb/attempts")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "browser_not_open"
    assert browser.check_visits == []


@pytest.mark.parametrize(
    ("platform", "marker"),
    [
        ("wb", '<a href="/u/123456">我的主页</a>'),
        ("dy", "创作中心"),
        ("ks", "创作者服务"),
        ("xhs", "发布笔记"),
        ("toutiao", "发布文章"),
    ],
)
def test_platform_specific_authenticated_markers_are_connected(platform, marker):
    result = _classify_connection_page(
        platform,
        f"https://example.test/{platform}",
        f"<main>{marker}</main>",
        200,
    )
    assert result == AuthWorkerResult("connected", "none")


@pytest.mark.parametrize(
    ("platform", "marker"),
    [
        ("wb", '<a href="/u/123456">我的主页</a>'),
        ("dy", "创作中心"),
        ("ks", "创作者服务"),
        ("xhs", "发布笔记"),
        ("toutiao", "发布文章"),
    ],
)
def test_http_error_with_authenticated_shell_marker_is_not_connected(platform, marker):
    result = _classify_connection_page(
        platform,
        f"https://example.test/{platform}",
        f"<main>{marker}</main>",
        500,
    )
    assert result == AuthWorkerResult("failed", "check_failed")


@pytest.mark.parametrize(
    ("url", "raw"),
    [
        ("https://weibo.com/", "<header><a>登录</a></header>"),
        ("https://weibo.com/", "<main>请登录</main>"),
        ("https://weibo.com/login", "<main>登录</main>"),
    ],
)
def test_weibo_compact_anonymous_shell_is_not_logged_in(url, raw):
    result = _classify_connection_page("wb", url, raw, 200)
    assert result == AuthWorkerResult("disconnected", "login_required")


def test_platform_challenge_wins_over_authenticated_shell_marker():
    result = _classify_connection_page(
        "xhs",
        "https://www.xiaohongshu.com/",
        "<title>安全验证</title><main>创作中心</main>",
        200,
    )
    assert result == AuthWorkerResult("failed", "manual_challenge")


def test_browser_disconnect_marks_connected_rows_as_requiring_reopen(tmp_path):
    app, browser = environment(tmp_path, [EMPTY])
    with TestClient(app) as client:
        service = app.state.platform_connection_service
        service._connections["wb"] = service._connections["wb"].model_copy(
            update={"status": "connected", "guidance": "none"}
        )
        client.portal.call(service._invalidate_connected, None)
        connection = client.get("/api/v1/platform-connections").json()["platforms"][0]

    assert connection["status"] == "failed"
    assert connection["guidance"] == "retry_browser"


def test_login_status_check_timeout_covers_navigation_and_cleans_check_page():
    async def run():
        browser = BrowserFixture([EMPTY])
        browser.check_block = True
        collector = NativeWeiboCollector(browser=browser, check_timeout_seconds=0.01)
        result = await asyncio.wait_for(
            collector.check(request_id="request", platform="wb"),
            timeout=0.2,
        )
        return result, browser

    result, browser = asyncio.run(run())
    assert result == AuthWorkerResult("failed", "check_failed")
    assert browser.check_closed


def collect(client, limit=1):
    response = client.post(
        "/api/v1/search-runs",
        json={
            "monitoring_rule_id": 1,
            "platform": "wb",
            "max_results_per_term": limit,
        },
    )
    assert response.status_code == 202, response.text
    return _wait_for_terminal(client, response.json()["id"])


def test_native_discovery_saves_aliases_across_terms_and_runs_without_analysis(
    tmp_path,
):
    alias = CARD.replace(
        "//weibo.com/1234567890/z0JH2lOMb",
        "https://m.weibo.cn/detail/3501756485200075?from=search",
    )
    app, browser = environment(
        tmp_path, [CARD, alias, EMPTY, EMPTY, EMPTY, alias, EMPTY, EMPTY, EMPTY, EMPTY]
    )
    with TestClient(app) as client:
        first = collect(client)
        assert first["status"] == "completed_with_results"
        assert (first["new_count"], first["repeated_count"]) == (1, 0)
        rows = client.get(f"/api/v1/search-runs/{first['id']}/results").json()
        assert rows["total"] == 1
        row = rows["results"][0]
        assert row["content_url"] == "https://m.weibo.cn/detail/3501756485200075"
        assert row["snippet"] == "龙田街道道路施工公告"
        assert len(row["matched_terms"]) == 2
        assert row["publisher_name"] == "样***者"
        second = collect(client)
        assert (second["new_count"], second["repeated_count"]) == (0, 1)
        assert client.get("/api/v1/report-generations").json()["items"] == []
        assert client.get("/api/v1/content-analysis-jobs").json()["jobs"] == []
        assert len(browser.visits) == 10
        assert all(
            url.startswith("https://s.weibo.com/weibo?") for url in browser.visits
        )
    assert browser.closed


def test_native_discovery_recovers_view_all_results_after_omitted_second_page(
    tmp_path,
):
    term = "龙田街道"
    first_page_url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
    ordinary_second_page = first_page_url + "&page=2"
    view_all_url = first_page_url + "&nodup=1"
    view_all_second_page = view_all_url + "&page=2"
    app, browser = environment(
        tmp_path,
        [
            card(
                "5012345678901234",
                "第一页 A",
                next_url=ordinary_second_page,
            )
            + card("5012345678901235", "第一页 B"),
            omitted_page(term),
            card(
                "5012345678901234",
                "第一页 A",
                next_url=view_all_second_page,
            )
            + card("5012345678901235", "第一页 B"),
            card("5012345678901236", "补救后的 C"),
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
        ],
    )

    with TestClient(app) as client:
        run = collect(client, limit=3)
        assert run["status"] == "completed_with_results"
        assert run["failure_reason"] is None
        assert (run["new_count"], run["repeated_count"], run["total_count"]) == (
            3,
            0,
            3,
        )
        assert run["incomplete_terms"] == []
        results = client.get(f"/api/v1/search-runs/{run['id']}/results").json()
        assert results["total"] == 3
        assert {item["platform_content_id"] for item in results["results"]} == {
            "5012345678901234",
            "5012345678901235",
            "5012345678901236",
        }
        assert browser.visits[:4] == [
            first_page_url,
            ordinary_second_page,
            view_all_url,
            view_all_second_page,
        ]
        assert len(browser.visits) == 8


def test_native_discovery_marks_unresolved_view_all_keyword_and_continues(
    tmp_path,
):
    term = "龙田街道"
    first_page_url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
    ordinary_second_page = first_page_url + "&page=2"
    app, browser = environment(
        tmp_path,
        [
            card("5012345678901234", "第一页 A", next_url=ordinary_second_page),
            omitted_page(term),
            loading_page(),
            card("5012345678901235", "下一个关键词 B"),
            EMPTY,
            EMPTY,
            EMPTY,
        ],
    )

    with TestClient(app) as client:
        run = collect(client, limit=3)
        assert run["status"] == "completed_with_incomplete"
        assert (run["new_count"], run["total_count"]) == (2, 2)
        assert run["incomplete_terms"] == [
            {
                "position": 0,
                "term": "龙田街道",
                "reason": "view_all_unresolved",
                "result_count": 1,
            }
        ]
        detail = client.get(f"/api/v1/search-runs/{run['id']}").json()
        assert detail["incomplete_terms"] == run["incomplete_terms"]
        assert len(browser.visits) == 7


def test_batch_finishes_with_incomplete_coverage_instead_of_pausing(
    tmp_path,
):
    term = "龙田街道"
    ordinary_second_page = (
        "https://s.weibo.com/weibo?" + urlencode({"q": term}) + "&page=2"
    )
    app, browser = environment(
        tmp_path,
        [
            card("5012345678901234", "第一页 A", next_url=ordinary_second_page),
            omitted_page(term),
            loading_page(),
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
        ],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 3,
            },
        )
        assert response.status_code == 202
        batch = _wait_for_batch(
            client, response.json()["id"], {"completed_with_failures"}
        )
        assert batch["items"][0]["status"] == "completed"
        assert batch["items"][0]["latest_attempt"]["run"]["incomplete_terms"]


def test_all_incomplete_keywords_are_not_reported_as_successful_empty(
    tmp_path,
):
    terms = ["龙田街道", "龙田社区", "老坑社区", "竹坑社区", "南布社区"]
    pages = []
    for term in terms:
        pages.extend((omitted_page(term), loading_page()))
    app, browser = environment(tmp_path, pages)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
                "max_results_per_term": 3,
            },
        )
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(300):
            run = client.get(f"/api/v1/search-runs/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            client.portal.call(asyncio.sleep, 0.01)
        else:
            raise AssertionError("search run did not become terminal")
        assert run["status"] == "completed_with_incomplete"
        assert run["total_count"] == 0
        assert [item["term"] for item in run["incomplete_terms"]] == terms
        assert len(browser.visits) == len(pages)


def test_incomplete_keyword_remains_visible_after_later_manual_pause_and_resume(
    tmp_path,
):
    term = "龙田街道"
    ordinary_second_page = (
        "https://s.weibo.com/weibo?" + urlencode({"q": term}) + "&page=2"
    )
    challenge = '<div role="dialog">请完成验证</div>'
    app, browser = environment(
        tmp_path,
        [
            card("5012345678901234", "第一页 A", next_url=ordinary_second_page),
            omitted_page(term),
            loading_page(),
            challenge,
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
        ],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 3,
            },
        )
        assert response.status_code == 202
        identity = response.json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        assert paused["items"][0]["incomplete_terms"] == [
            {
                "position": 0,
                "term": "龙田街道",
                "reason": "view_all_unresolved",
                "result_count": 1,
            }
        ]
        control = _control(client, identity)
        browser.html = EMPTY
        assert (
            client.post(
                f"/api/v1/search-batches/{identity}/continue", json=control
            ).status_code
            == 202
        )
        finished = _wait_for_batch(client, identity, {"completed_with_failures"})
        assert finished["items"][0]["status"] == "completed"
        assert finished["items"][0]["incomplete_terms"][0]["term"] == "龙田街道"


def test_native_connection_check_does_not_foreground_the_login_page(tmp_path):
    logged_in = '<header><a href="/u/123456">已登录</a></header>'
    app, browser = environment(tmp_path, [logged_in] * 5)
    with TestClient(app) as client:
        response = client.post("/api/v1/platform-connections/wb/attempts")
        assert response.status_code == 202
        for _ in range(30):
            connection = client.get("/api/v1/platform-connections").json()["platforms"][
                0
            ]
            if connection["status"] != "checking":
                break
            client.portal.call(asyncio.sleep, 0.01)
        assert connection["status"] == "connected"
    assert not browser.fronted


def test_native_connection_accepts_user_marker_with_hidden_login_markup(tmp_path):
    logged_in = (
        '<div class="woo-avatar-hover"><a href="/u/123456">已登录</a></div>'
        '<div style="display:none"><form><input type="password"></form></div>'
    )
    app, browser = environment(tmp_path, [logged_in] * 5)
    with TestClient(app) as client:
        response = client.post("/api/v1/platform-connections/wb/attempts")
        assert response.status_code == 202
        for _ in range(30):
            connection = client.get("/api/v1/platform-connections").json()["platforms"][
                0
            ]
            if connection["status"] != "checking":
                break
            client.portal.call(asyncio.sleep, 0.01)
        assert connection["status"] == "connected"
    assert not browser.fronted


def test_search_budget_stops_instead_of_silently_reducing_configured_work(tmp_path):
    app, browser = environment(tmp_path, [CARD, EMPTY], max_pages=1)
    with TestClient(app) as client:
        run = collect(client, limit=50)
        assert run["status"] == "timed_out"
        assert run["execution_limit"] == "pages"
        assert run["max_results_per_term"] == 50
        assert run["new_count"] == 1
        assert len(browser.visits) == 1
        assert client.get(f"/api/v1/search-runs/{run['id']}").json() == run


@pytest.mark.parametrize(
    ("page", "status", "reason"),
    [
        (EMPTY, "completed_empty", None),
        ('<form>请先登录<input type="password"></form>', "login_required", None),
        (
            "<title>微博安全验证</title><main>请完成验证</main>",
            "manual_challenge_required",
            None,
        ),
        (
            '<div role="dialog">操作频繁，请稍后再试</div>',
            "platform_blocked_or_rate_limited",
            None,
        ),
        ("<main>正在加载</main>", "structure_changed", "page_state_unrecognized"),
        (
            CARD.replace('mid="3501756485200075"', 'mid="unknown"'),
            "structure_changed",
            "search_results_incompatible",
        ),
    ],
)
def test_native_page_states_are_not_mistaken_for_empty_results(
    tmp_path, page, status, reason
):
    app, browser = environment(tmp_path, [page] * 5)
    with TestClient(app) as client:
        run = collect(client)
        assert (run["status"], run["failure_reason"]) == (status, reason)
        assert run["total_count"] == 0
        assert len(browser.visits) == (5 if status == "completed_empty" else 1)


def test_security_pause_keeps_discoveries_and_requires_explicit_continue(tmp_path):
    challenge = '<div role="dialog">请完成验证</div>'
    app, browser = environment(tmp_path, [CARD, challenge] + [EMPTY] * 4)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 1,
            },
        )
        assert response.status_code == 202
        identity = response.json()["id"]
        paused = _wait_for_batch(client, identity, {"paused_for_manual_action"})
        assert paused["items"][0]["completed_term_count"] == 1
        assert paused["items"][0]["new_count"] == 1
        control = _control(client, identity)
        shown = client.post(
            f"/api/v1/search-batches/{identity}/manual-page", json=control
        )
        assert shown.json() == {"outcome": "opened_existing"}
        # Completing the challenge and polling the product never resumes collection.
        browser.html = EMPTY
        for _ in range(3):
            assert (
                client.get(f"/api/v1/search-batches/{identity}").json()["status"]
                == "paused_for_manual_action"
            )
        assert len(browser.visits) == 2
        resumed = client.post(
            f"/api/v1/search-batches/{identity}/continue", json=control
        )
        assert resumed.status_code == 202
        finished = _wait_for_batch(client, identity, {"completed"})
        assert finished["items"][0]["new_count"] == 1
        assert len(browser.visits) == 6


def test_mismatched_permalink_is_not_saved_as_another_posts_identity(tmp_path):
    bad = CARD.replace(
        "//weibo.com/1234567890/z0JH2lOMb", "https://m.weibo.cn/detail/3600375418559878"
    )
    app, browser = environment(tmp_path, [bad])
    with TestClient(app) as client:
        run = collect(client)
        assert (run["status"], run["failure_reason"]) == (
            "structure_changed",
            "search_results_incompatible",
        )
        assert run["total_count"] == 0


def test_cancel_stops_browser_work_and_keeps_saved_discoveries(tmp_path):
    app, browser = environment(tmp_path, [CARD])
    browser.block_at = 2
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/search-runs",
            json={
                "monitoring_rule_id": 1,
                "platform": "wb",
                "max_results_per_term": 1,
            },
        )
        identity = created.json()["id"]
        client.portal.call(browser.entered.wait)
        cancelled = client.post(f"/api/v1/search-runs/{identity}/cancel")
        assert cancelled.status_code == 202
        run = _wait_for_terminal(client, identity)
        assert (run["status"], run["new_count"]) == ("cancelled", 1)
        assert len(browser.visits) == 2
        assert (
            client.get(f"/api/v1/search-runs/{identity}/results").json()["total"] == 1
        )


def test_rediscovery_of_a_failed_summary_is_repeated_and_does_not_retry_analysis(
    tmp_path,
):
    from test_content_analysis_api import saved
    from test_report_generations import generation_request, save_body
    from topic_report_fixtures import TextPipelineClient, finish

    model = TextPipelineClient()
    model.answers["initial"] = ["invalid", "invalid"]
    app, browser = environment(
        tmp_path, [CARD] + [EMPTY] * 4 + [CARD] + [EMPTY] * 4, model=model
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        first = collect(client)
        assert first["new_count"] == 1
        save_body(app.state.search_run_service.database)
        saved(client)
        started = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        assert started.status_code == 202
        client.portal.call(finish, app.state.report_generation_service)
        generation = client.get(
            f"/api/v1/report-generations/{started.json()['id']}"
        ).json()
        assert generation["analysis"]["counts"]["failed"] == 1
        second = collect(client)
        assert (second["new_count"], second["repeated_count"]) == (0, 1)
        assert model.counts["initial"] == 2
        assert len(browser.visits) == 10


def test_batch_keeps_the_page_budget_cause_in_failed_platform(tmp_path):
    app, _ = environment(tmp_path, [CARD], max_pages=1)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/search-batches",
            json={
                "monitoring_rule_id": 1,
                "platforms": ["wb"],
                "max_results_per_term": 1,
            },
        )
        paused = _wait_for_batch(
            client, created.json()["id"], {"completed_with_failures"}
        )
        run = paused["items"][0]["latest_attempt"]["run"]
        assert (run["status"], run["execution_limit"]) == ("timed_out", "pages")


@pytest.mark.parametrize(
    ("platform", "initial", "hydrated"),
    [
        ("wb", "<main>正在加载</main>", "<header>我的主页</header>"),
        ("dy", "<main>正在加载</main>", "<nav>退出登录</nav>"),
        (
            "ks",
            "<main>登录</main>",
            '<div class="down-box login"><div class="user item">'
            '<div class="text-name">测试账号</div></div></div>',
        ),
    ],
)
def test_check_waits_for_existing_session_hydration(platform, initial, hydrated):
    class HydratingBrowser(BrowserFixture):
        async def wait_check_update(self):
            self.check_html = hydrated

    async def run():
        browser = HydratingBrowser([initial])
        result = await NativeWeiboCollector(browser=browser).check(
            request_id="hydrate", platform=platform
        )
        assert browser.check_closed
        assert not browser.visits
        return result

    assert asyncio.run(run()) == AuthWorkerResult("connected", "none")


def test_check_unresolved_hydration_remains_bounded():
    class LoadingBrowser(BrowserFixture):
        async def wait_check_update(self):
            await asyncio.sleep(0.001)

    async def run():
        browser = LoadingBrowser(["<main>正在加载</main>"])
        result = await NativeWeiboCollector(
            browser=browser, check_timeout_seconds=0.01
        ).check(request_id="loading", platform="wb")
        assert browser.check_closed
        return result

    assert asyncio.run(run()) == AuthWorkerResult("failed", "check_failed")


def test_kuaishou_feed_author_is_not_account_identity():
    assert _classify_connection_page(
        "ks",
        "https://www.kuaishou.com/",
        '<main><div class="user"><div class="text-name">视频作者</div></div></main>',
        200,
    ) == AuthWorkerResult("failed", "check_failed")
