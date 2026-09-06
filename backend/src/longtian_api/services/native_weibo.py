"""Project-owned, bounded rendered-browser discovery. No legacy fallback."""

import asyncio
from collections import deque
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit

from longtian_api.services.collector_contracts import (
    AuthWorkerResult,
    ManualPageWorkerResult,
    OpenResultWorkerResult,
    SearchTermDiagnostic,
    SearchTermIncompleteReason,
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


def _search_url_identity(url: str) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
    """Compare rendered search destinations semantically, not by query ordering."""
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        # The view-all entry may omit page=1 while its first numbered page may
        # spell it explicitly.  They are the same destination for loop checks.
        if key == "page" and value == "1":
            continue
        query.append((key, value))
    return (
        parts.scheme,
        parts.netloc,
        parts.path,
        tuple(sorted(query)),
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
        max_total_results=None,
        previous_content_ids=(),
    ):
        if platform != "wb":
            return SearchWorkerResult("browser_unavailable")
        if max_total_results is not None:
            return await self._search_latest(
                terms=terms,
                limit=max_total_results,
                previous_content_ids=previous_content_ids,
                on_progress=on_progress,
                on_item=on_item,
                on_term_completed=on_term_completed,
            )
        found = False
        pages = 0
        deadline = monotonic() + self.timeout_seconds
        incomplete_terms: list[SearchTermDiagnostic] = []

        def result(outcome, execution_limit=None):
            return SearchWorkerResult(
                outcome,
                execution_limit=execution_limit,
                incomplete_terms=tuple(incomplete_terms),
            )

        try:
            await self.browser.start(max_requests=self.max_requests)
            for position, term in enumerate(terms):
                await on_progress(position, len(terms))
                url = "https://s.weibo.com/weibo?" + urlencode({"q": term})
                seen, visited = set(), set()
                recovery_attempted = False
                incomplete_reason: SearchTermIncompleteReason | None = None
                while url:
                    if monotonic() >= deadline:
                        raise BrowserBudgetExceeded("time")
                    if pages >= self.max_pages:
                        raise BrowserBudgetExceeded("pages")
                    identity = _search_url_identity(url)
                    if identity in visited:
                        if recovery_attempted:
                            incomplete_reason = "view_all_unresolved"
                            break
                        return result("search_pagination_incompatible")
                    visited.add(identity)
                    pages += 1
                    async with asyncio.timeout(max(0, deadline - monotonic())):
                        await self.browser.navigate(url)
                    parsed = None
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
                    if parsed is None:
                        parsed = read_search_page(
                            *(await self.browser.snapshot()), term
                        )
                    for item in parsed.items:
                        if (
                            item.content_id not in seen
                            and len(seen) < max_results_per_term
                        ):
                            await on_item(position, item)
                            seen.add(item.content_id)
                            found = True
                    if parsed.state == "omitted":
                        if recovery_attempted or parsed.view_all_url is None:
                            incomplete_reason = "view_all_unresolved"
                            break
                        recovery_attempted = True
                        url = parsed.view_all_url
                        continue
                    if parsed.state not in ("results", "empty"):
                        if recovery_attempted and parsed.state == "pending":
                            incomplete_reason = "view_all_unresolved"
                            break
                        state = (
                            "page_state_unrecognized"
                            if parsed.state == "pending"
                            else parsed.state
                        )
                        return result(state)
                    if len(seen) >= max_results_per_term or parsed.state == "empty":
                        break
                    url = parsed.next_url
                    if url:
                        await asyncio.sleep(self.delay_seconds)
                if incomplete_reason is not None:
                    incomplete_terms.append(
                        SearchTermDiagnostic(
                            position=position,
                            reason=incomplete_reason,
                            result_count=len(seen),
                        )
                    )
                await on_term_completed(position, len(seen), incomplete_reason)
                if position + 1 < len(terms):
                    await asyncio.sleep(self.delay_seconds)
            return result(
                "completed_with_incomplete"
                if incomplete_terms
                else "completed_with_results"
                if found
                else "completed_empty"
            )
        except BrowserBudgetExceeded as error:
            return result("timed_out", execution_limit=error.limit)
        except TimeoutError:
            return result("timed_out", execution_limit="time")
        except BrowserUnavailable:
            return result("browser_unavailable")
        finally:
            await self.browser.freeze()

    async def _search_latest(
        self,
        *,
        terms,
        limit,
        previous_content_ids,
        on_progress,
        on_item,
        on_term_completed,
    ):
        """Take one fresh item per term per round, with one shared unique cap."""
        seen = set(previous_content_ids)
        per_term = [set() for _ in terms]
        queues = [deque() for _ in terms]
        urls = [
            "https://s.weibo.com/realtime?"
            + urlencode({"q": term, "rd": "realtime", "tw": "realtime"})
            for term in terms
        ]
        visited = [set() for _ in terms]
        recovered = set()
        incomplete = set()
        completed = set()
        deadline = monotonic() + self.timeout_seconds
        pages = 0
        try:
            await self.browser.start(max_requests=self.max_requests)
            while len(seen) < limit and any(
                urls[i] or queues[i] for i in range(len(terms))
            ):
                for position, term in enumerate(terms):
                    if len(seen) >= limit:
                        break
                    if position in completed:
                        continue
                    await on_progress(position, len(terms))
                    # Duplicate-only pages don't consume this term's turn.
                    fetched = False
                    while len(seen) < limit:
                        if monotonic() >= deadline:
                            raise BrowserBudgetExceeded("time")
                        if queues[position]:
                            item = queues[position].popleft()
                            if item.content_id in per_term[position]:
                                continue
                            # Record all matched terms for admitted content, but
                            # only a distinct item consumes a slot or a turn.
                            await on_item(position, item)
                            per_term[position].add(item.content_id)
                            if item.content_id not in seen:
                                seen.add(item.content_id)
                                break
                            continue
                        url = urls[position]
                        if not url or fetched:
                            break
                        if pages >= self.max_pages:
                            raise BrowserBudgetExceeded("pages")
                        identity = _search_url_identity(url)
                        if identity in visited[position]:
                            return SearchWorkerResult("search_pagination_incompatible")
                        visited[position].add(identity)
                        if pages:
                            await asyncio.sleep(self.delay_seconds)
                        pages += 1
                        fetched = True
                        async with asyncio.timeout(max(0, deadline - monotonic())):
                            await self.browser.navigate(url)
                            parsed = None
                            for poll in range(self.ready_polls):
                                parsed = read_search_page(
                                    *(await self.browser.snapshot()), term, latest=True
                                )
                                if parsed.state != "pending":
                                    break
                                if poll + 1 < self.ready_polls:
                                    await asyncio.sleep(0.25)
                        queues[position].extend(parsed.items)
                        if parsed.state == "omitted":
                            if position in recovered or parsed.view_all_url is None:
                                incomplete.add(position)
                                urls[position] = None
                            else:
                                recovered.add(position)
                                urls[position] = parsed.view_all_url
                        elif parsed.state in ("results", "empty"):
                            urls[position] = parsed.next_url
                        else:
                            return SearchWorkerResult(
                                "page_state_unrecognized"
                                if parsed.state == "pending"
                                else parsed.state
                            )
                    if not urls[position] and not queues[position]:
                        await on_term_completed(
                            position,
                            len(per_term[position]),
                            "view_all_unresolved" if position in incomplete else None,
                        )
                        completed.add(position)
            for position in range(len(terms)):
                if position in completed:
                    continue
                await on_progress(position, len(terms))
                await on_term_completed(
                    position,
                    len(per_term[position]),
                    "view_all_unresolved" if position in incomplete else None,
                )
            return SearchWorkerResult(
                "completed_with_incomplete"
                if incomplete
                else "completed_with_results"
                if seen
                else "completed_empty"
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
            existing = getattr(self.browser, "page_present", self.browser.available)
            await self.browser.show()
            target = getattr(self.enricher, "manual_target_url", None)
            if target and hasattr(self.browser, "page_present"):
                # The target originates from the validated selected result, not
                # from an untrusted redirect or response body.
                await self.browser.navigate(target)
                await self.browser.bring_to_front()
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
