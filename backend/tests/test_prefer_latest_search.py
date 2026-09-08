"""Latest search is optional, and fallback must not interrupt discovery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_native_weibo_discovery import BrowserFixture
from test_platform_search_cards import XHS

from longtian_api.services.native_browser_contracts import BrowserUnavailable
from longtian_api.services.native_chrome import ManagedChrome
from longtian_api.services.native_weibo import NativeWeiboCollector


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("latest_available", [True, False])
def test_collection_uses_optional_sort_before_reading_cards(enabled, latest_available):
    class Browser(BrowserFixture):
        calls = 0

        async def prefer_latest_search(self, platform):
            assert platform == "xhs"
            self.calls += 1
            if latest_available:
                self.html = XHS.replace(
                    "65b363f7000000002c03d319", "65b363f7000000002c03d320"
                )
            return latest_available

    async def run():
        browser = Browser([XHS])
        items = []

        async def ignore(*args):
            pass

        async def admit(position, item):
            items.append(item.content_id)

        result = await NativeWeiboCollector(
            browser=browser, latest_first=enabled
        ).search(
            request_id="test",
            platform="xhs",
            terms=["社区"],
            max_results_per_term=1,
            on_progress=ignore,
            on_item=admit,
            on_term_completed=ignore,
        )
        assert result.outcome == "completed_with_results"
        assert browser.calls == int(enabled)
        assert items == [
            (
                "65b363f7000000002c03d320"
                if enabled and latest_available
                else "65b363f7000000002c03d319"
            )
        ]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["missing_control", "stale_results", None])
def test_browser_sort_refresh_and_default_fallback(tmp_path, failure):
    async def run():
        browser = ManagedChrome(profile=tmp_path)
        browser._browser = SimpleNamespace(is_connected=lambda: True)
        locator = Mock()
        locator.first = locator.last = locator
        locator.hover = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.click = AsyncMock()
        locator.evaluate_all = AsyncMock(return_value=["old-id"])
        page = Mock()
        page.url = "https://www.douyin.com/search/test?type=general"
        page.is_closed.return_value = False
        page.locator.return_value = page.get_by_text.return_value = locator
        page.wait_for_function = AsyncMock()
        browser._page = page
        browser.navigate = AsyncMock()
        if failure == "missing_control":
            locator.hover.side_effect = TimeoutError()
        if failure == "stale_results":
            page.wait_for_function.side_effect = TimeoutError()
        assert await browser.prefer_latest_search("dy") is (failure is None)
        if failure:
            browser.navigate.assert_awaited_once_with(page.url)
        else:
            browser.navigate.assert_not_awaited()
            assert page.wait_for_function.call_args.kwargs["arg"]["before"] == [
                "old-id"
            ]
        browser._browser.is_connected = lambda: False
        with pytest.raises(BrowserUnavailable):
            await browser.prefer_latest_search("dy")
        assert await browser.prefer_latest_search("ks") is False

    asyncio.run(run())


def test_xhs_detail_lookup_finds_selected_card_deeper_in_latest_results(tmp_path):
    async def run():
        browser = ManagedChrome(profile=tmp_path)
        browser._browser = SimpleNamespace(is_connected=lambda: True)
        card = Mock()
        card.first = card
        card.wait_for = AsyncMock(side_effect=[TimeoutError()] * 9 + [None])
        card.click = AsyncMock()
        cards = Mock()
        cards.last = cards
        cards.scroll_into_view_if_needed = AsyncMock()
        page = Mock()
        page.is_closed.return_value = False
        page.locator.side_effect = lambda selector: (
            cards if selector == "section.note-item" else card
        )
        browser._page = page
        browser.navigate = AsyncMock()
        browser.prefer_latest_search = AsyncMock(return_value=True)
        identity = "6a4b59ca000000001702f46e"
        assert await browser.open_xhs_search_result(
            "https://www.xiaohongshu.com/search_result?keyword=test", identity
        )
        browser.prefer_latest_search.assert_awaited_once_with("xhs")
        assert cards.scroll_into_view_if_needed.await_count == 8
        card.click.assert_awaited_once()

    asyncio.run(run())
