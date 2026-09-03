"""Project-owned, bounded rendered-browser discovery. No legacy fallback."""

import asyncio
from time import monotonic
from urllib.parse import urlencode

from longtian_api.services.collector_contracts import (
    AuthWorkerResult,
    ManualPageWorkerResult,
    OpenResultWorkerResult,
    SearchWorkerResult,
)
from longtian_api.services.native_browser_contracts import (
    BrowserBudgetExceeded,
    BrowserUnavailable,
    RenderedBrowser,
)
from longtian_api.services.weibo_dom import barrier, document, read_search_page

_SIGNED_IN_XPATH = (
    "//*[@node-type='gn_name']|//header//a[starts-with(@href,'/u/')]"
    "|//nav//a[starts-with(@href,'/u/')]"
    "|//*[contains(concat(' ', normalize-space(@class), ' '), ' woo-avatar-hover ')]"
)


class NativeWeiboCollector:
    def __init__(
        self,
        *,
        browser: RenderedBrowser,
        delay_seconds=2.0,
        ready_polls=20,
        max_pages=40,
        max_requests=1200,
        timeout_seconds=180,
        on_progress=None,
        enricher=None,
    ):
        self.browser = browser
        self.delay_seconds = delay_seconds
        self.ready_polls = ready_polls
        self.max_pages = max_pages
        self.max_requests = max_requests
        self.timeout_seconds = timeout_seconds
        self.on_progress = on_progress
        if enricher is None:
            from longtian_api.services.weibo_enrichment import WeiboEnricher

            enricher = WeiboEnricher(browser=browser)
        self.enricher = enricher

    supports_manual_acquisition = True
    supported_platforms = frozenset({"wb"})

    @property
    def browser_session_available(self):
        return self.browser.available

    def configure_media_spool(self, root):
        self.spool = root

    async def search(
        self,
        *,
        request_id,
        platform,
        terms,
        max_results_per_term,
        on_progress,
        on_item,
        on_term_completed,
    ):
        if platform != "wb":
            return SearchWorkerResult("browser_unavailable")
        found = False
        pages = 0
        deadline = monotonic() + self.timeout_seconds
        try:
            await self.browser.start(max_requests=self.max_requests)
            for position, term in enumerate(terms):
                await on_progress(position, len(terms))
                url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
                seen, visited = set(), set()
                while url:
                    if monotonic() >= deadline:
                        raise BrowserBudgetExceeded("time")
                    if pages >= self.max_pages:
                        raise BrowserBudgetExceeded("pages")
                    if url in visited:
                        return SearchWorkerResult("search_pagination_incompatible")
                    visited.add(url)
                    pages += 1
                    async with asyncio.timeout(max(0, deadline - monotonic())):
                        await self.browser.navigate(url)
                    for poll in range(self.ready_polls):
                        if monotonic() >= deadline:
                            raise BrowserBudgetExceeded("time")
                        parsed = read_search_page(
                            *(await self.browser.snapshot()), term
                        )
                        if parsed.state != "pending":
                            break
                        if poll + 1 < self.ready_polls:
                            await asyncio.sleep(0.25)
                    for item in parsed.items:
                        if (
                            item.content_id not in seen
                            and len(seen) < max_results_per_term
                        ):
                            await on_item(position, item)
                            seen.add(item.content_id)
                            found = True
                    if parsed.state not in ("results", "empty"):
                        state = (
                            "page_state_unrecognized"
                            if parsed.state == "pending"
                            else parsed.state
                        )
                        return SearchWorkerResult(state)
                    if len(seen) >= max_results_per_term or parsed.state == "empty":
                        break
                    url = parsed.next_url
                    if url:
                        await asyncio.sleep(self.delay_seconds)
                await on_term_completed(position, len(seen))
                if position + 1 < len(terms):
                    await asyncio.sleep(self.delay_seconds)
            return SearchWorkerResult(
                "completed_with_results" if found else "completed_empty"
            )
        except BrowserBudgetExceeded as error:
            return SearchWorkerResult("timed_out", execution_limit=error.limit)
        except TimeoutError:
            return SearchWorkerResult("timed_out", execution_limit="time")
        except BrowserUnavailable:
            return SearchWorkerResult("browser_unavailable")
        finally:
            await self.browser.freeze()

    async def discard_session(self):
        await self.browser.close_page()

    async def manual_page(self, *, request_id, platform, action):
        if platform != "wb":
            return ManualPageWorkerResult("browser_unavailable")
        try:
            if action == "close":
                await self.browser.close_page()
                return ManualPageWorkerResult("closed")
            existing = self.browser.available
            await self.browser.show()
            return ManualPageWorkerResult(
                "opened_existing" if existing else "opened_homepage"
            )
        except BrowserUnavailable:
            return ManualPageWorkerResult("browser_unavailable")

    async def check(self, *, request_id, platform):
        if platform != "wb":
            return AuthWorkerResult("failed", "browser_unavailable")
        try:
            if self.on_progress:
                await self.on_progress(request_id, platform, "waiting_for_browser")
            await self.browser.start(max_requests=self.max_requests)
            await self.browser.bring_to_front()
            await self.browser.navigate("https://weibo.com/")
            if self.on_progress:
                await self.on_progress(request_id, platform, "waiting_for_login")
            # DOM-only polling; the user performs any login/challenge themselves.
            async with asyncio.timeout(self.timeout_seconds):
                while True:
                    url, raw, status = await self.browser.snapshot()
                    root = document(raw)
                    blocked = barrier(root, url, status)
                    signed_in = bool(root is not None and root.xpath(_SIGNED_IN_XPATH))
                    # Weibo can leave an invisible login form in the rendered DOM
                    # after a successful session restore. A signed-in marker may
                    # therefore coexist with a DOM-only ``login_required`` signal.
                    # Transport/auth failures and explicit challenges still win.
                    if (
                        signed_in
                        and blocked in (None, "login_required")
                        and status not in (401, 403, 429)
                    ):
                        return AuthWorkerResult("connected", "none")
                    await asyncio.sleep(1)
        except TimeoutError:
            return AuthWorkerResult("disconnected", "login_required")
        except (BrowserUnavailable, BrowserBudgetExceeded):
            return AuthWorkerResult("failed", "browser_unavailable")
        finally:
            await self.browser.freeze()

    async def open_result(self, *, request_id, term, content_id):
        if not content_id.isascii() or not content_id.isdigit():
            return OpenResultWorkerResult("content_not_found")
        try:
            await self.browser.start(max_requests=self.max_requests)
            await self.browser.navigate(f"https://m.weibo.cn/detail/{content_id}")
            await self.browser.show()
            return OpenResultWorkerResult("opened")
        except (BrowserUnavailable, BrowserBudgetExceeded, TimeoutError):
            await self.browser.freeze()
            return OpenResultWorkerResult("browser_unavailable")

    async def enrich(self, **kwargs):
        return await self.enricher.enrich(**kwargs)

    def discard_enrichment_checkpoint(self):
        self.enricher.reset()

    async def shutdown(self):
        self.enricher.reset()
        await self.browser.shutdown()
