"""Project-owned, bounded rendered-browser discovery. No legacy fallback."""

import asyncio
import hashlib
import re
from collections import deque
from time import monotonic, time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from longtian_api.search_platforms import is_valid_search_content_url
from longtian_api.services.collector_contracts import (
    AuthWorkerResult,
    EnrichmentWorkerResult,
    ManualPageWorkerResult,
    OpenResultWorkerResult,
    SearchTermDiagnostic,
    SearchTermIncompleteReason,
    SearchWorkerItem,
    SearchWorkerResult,
)
from longtian_api.services.native_browser_contracts import (
    BrowserBudgetExceeded,
    BrowserUnavailable,
    RenderedBrowser,
)
from longtian_api.services.weibo_dom import barrier, document, read_search_page, text_of

_SIGNED_IN_XPATH = (
    "//*[@node-type='gn_name']|//header//a[starts-with(@href,'/u/')]"
    "|//nav//a[starts-with(@href,'/u/')]"
    "|//*[contains(concat(' ', normalize-space(@class), ' '), ' woo-avatar-hover ')]"
)

_PLATFORM_SIGNED_IN_MARKERS = {
    "dy": ("创作中心", "发布作品", "发布视频", "我的作品"),
    "ks": ("创作者服务", "发布作品", "我的作品", "个人主页"),
    "xhs": ("创作中心", "发布笔记", "我的笔记", "个人主页"),
    "toutiao": ("创作中心", "发布文章", "发文", "个人中心"),
}


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


_PLATFORM_HOME = {
    "wb": "https://weibo.com/",
    "toutiao": "https://www.toutiao.com/",
    "ks": "https://www.kuaishou.com/",
    "dy": "https://www.douyin.com/",
    "xhs": "https://www.xiaohongshu.com/",
}
_PLATFORM_SEARCH = {
    "toutiao": lambda term: (
        "https://so.toutiao.com/search?keyword=" + urlencode({"": term})[1:]
    ),
    "ks": lambda term: (
        "https://www.kuaishou.com/search/video?searchKey=" + urlencode({"": term})[1:]
    ),
    "dy": lambda term: (
        "https://www.douyin.com/search/" + urlencode({"": term})[1:] + "?type=general"
    ),
    "xhs": lambda term: (
        "https://www.xiaohongshu.com/search_result?keyword=" + urlencode({"": term})[1:]
    ),
}
_PLATFORM_HOSTS = {
    "toutiao": ("toutiao.com",),
    "ks": ("kuaishou.com", "kwai.com"),
    "dy": ("douyin.com",),
    "xhs": ("xiaohongshu.com",),
}


def _generic_content_identity(platform, href, base):
    """Extract only canonical public links owned by the selected platform."""
    target = urljoin(base, href)
    try:
        parts = urlsplit(target)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or port not in (None, 443)
    ):
        return None
    if parts.fragment or not any(
        host == root or host.endswith("." + root)
        for root in _PLATFORM_HOSTS.get(platform, ())
    ):
        return None
    patterns = {
        "toutiao": r"/(article|w|video)/([0-9]{8,24})/?$",
        "ks": r"/short-video/([A-Za-z0-9_-]+)/?$",
        "dy": r"/video/([0-9]+)/?$",
        "xhs": r"/explore/([0-9a-f]{24})/?$",
    }
    match = re.fullmatch(patterns[platform], parts.path)
    if not match:
        return None
    content_id = match.group(match.lastindex)
    if platform == "toutiao":
        kind = "video" if match.group(1) == "video" else "post"
        canonical = f"https://www.toutiao.com/{match.group(1)}/{content_id}/"
    elif platform == "ks":
        kind, canonical = "video", f"https://www.kuaishou.com/short-video/{content_id}"
    elif platform == "dy":
        kind, canonical = "video", f"https://www.douyin.com/video/{content_id}"
    else:
        kind, canonical = "post", f"https://www.xiaohongshu.com/explore/{content_id}"
    if not is_valid_search_content_url(platform, content_id, canonical):
        return None
    return content_id, kind, canonical


def _read_generic_page(platform, url, raw, term, status=200):
    if status in (401,):
        return "login_required", ()
    root = document(raw)
    if root is None:
        if status in (403, 429):
            return "platform_blocked_or_rate_limited", ()
        if status >= 400:
            return "structure_changed", ()
        return "pending", ()
    signal = _generic_signal_text(root)
    # Error pages often render a bare text challenge without a dialog/class
    # marker. Since this branch is reached only for an HTTP error, inspecting
    # the page text cannot confuse a user's post copy with platform chrome.
    if status >= 400:
        signal = " ".join((signal, _clean_generic_text(text_of(root), 20_000)))
    # A few platforms return a bare 200 shell for login/challenge pages. With
    # no result links there is no user post text to confuse with platform
    # chrome, so inspect the rendered document as a final barrier signal.
    if status < 400 and not root.xpath("//a[@href]"):
        signal = " ".join((signal, _clean_generic_text(text_of(root), 20_000)))
    if any(word in signal for word in ("验证码", "安全验证", "人机验证", "滑动验证")):
        return "manual_challenge_required", ()
    if any(word in signal for word in ("访问频繁", "请求过于频繁", "稍后再试")):
        return "platform_blocked_or_rate_limited", ()
    if any(word in signal for word in ("请登录", "登录后查看", "登录后继续")):
        return "login_required", ()
    if status in (403, 429):
        return "platform_blocked_or_rate_limited", ()
    if status >= 400:
        return "structure_changed", ()
    title = " ".join(root.xpath("//title/text()"))[:300]
    values = []
    seen = set()
    for anchor in root.xpath("//a[@href]"):
        identity = _generic_content_identity(platform, anchor.get("href", ""), url)
        if identity is None or identity[0] in seen:
            continue
        seen.add(identity[0])
        text = _generic_card_text(anchor, title)
        publisher_name, creator_hash = _generic_publisher(anchor)
        published_at_text = _generic_published_text(anchor)
        hashtags = _generic_hashtags(anchor)
        interaction_stats = _generic_interaction_stats(anchor)
        values.append(
            SearchWorkerItem(
                content_id=identity[0],
                content_type=identity[1],
                title=(text[:300] or f"{platform} 内容 {identity[0]}"),
                snippet=text[:1000],
                creator_hash=creator_hash,
                publisher_name=publisher_name,
                published_at_text=published_at_text,
                content_url=identity[2],
                discovered_at=int(time() * 1000),
                hashtags=hashtags,
                interaction_stats=interaction_stats,
            )
        )
    if values:
        return "results", tuple(values)
    return "empty", ()


def _generic_signal_text(root):
    """Return platform chrome used for barrier detection, excluding post text.

    A user's post can legitimately mention verification, login, or rate-limit
    words.  Only page title and explicit notice/dialog/form containers are
    evidence that the platform itself is blocking the request.
    """
    lower_class = (
        "translate(concat(' ',@class,' ',@id,' ',@data-testid),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
    )
    class_terms = " or ".join(
        f"contains({lower_class},'{term}')"
        for term in (
            "login",
            "captcha",
            "verify",
            "challenge",
            "notice",
            "toast",
            "modal",
            "error",
        )
    )
    prefix = (
        "//title | //form | //dialog | //*[@role='dialog'] | //*[@aria-live] | //*["
    )
    query = prefix + class_terms + "]"
    nodes = root.xpath(query)
    values = []
    seen = set()
    for node in nodes:
        identity = id(node)
        if identity in seen:
            continue
        seen.add(identity)
        value = _clean_generic_text(text_of(node), 2_000)
        if value:
            values.append(value)
    return " ".join(values)[:20_000]


def _clean_generic_text(value, limit):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _generic_card_text(anchor, page_title):
    """Prefer the nearest rendered result card over the search-page title."""
    cards = anchor.xpath(
        "ancestor::*[self::article or self::li or @role='article' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' card ')][1]"
    )
    card_text = _clean_generic_text(text_of(cards[0]), 1000) if cards else ""
    anchor_text = _clean_generic_text(
        anchor.text_content() or anchor.get("title", ""), 1000
    )
    return card_text or anchor_text or _clean_generic_text(page_title, 1000)


def _generic_publisher(anchor):
    """Read optional author metadata and apply the existing masked contract."""
    cards = anchor.xpath(
        "ancestor::*[self::article or self::li or @role='article' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' card ')][1]"
    )
    card = cards[0] if cards else anchor
    values = []
    for query in (
        ".//*[@data-author]/@data-author",
        ".//*[@data-user]/@data-user",
        ".//*[@itemprop='author']",
        ".//*[contains(@class,'author') or contains(@class,'user-name')]",
    ):
        values.extend(card.xpath(query))
    name = next(
        (
            _clean_generic_text(
                value if isinstance(value, str) else text_of(value), 100
            )
            for value in values
            if _clean_generic_text(
                value if isinstance(value, str) else text_of(value), 100
            )
        ),
        "",
    )
    if not name:
        return "", ""
    masked = (
        "*"
        if len(name) == 1
        else name[0] + "*"
        if len(name) == 2
        else name[0] + "***" + name[-1]
    )
    return masked, hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def _generic_published_text(anchor):
    cards = anchor.xpath(
        "ancestor::*[self::article or self::li or @role='article' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' card ')][1]"
    )
    card = cards[0] if cards else anchor
    values = card.xpath(".//time/@datetime | .//time/text()")
    for value in values:
        text = _clean_generic_text(value, 100)
        if text:
            return text
    # Keep a short relative/date label when a platform renders no <time> node.
    card_text = _clean_generic_text(text_of(card), 1000)
    match = re.search(
        r"(?:刚刚|刚才|今天|昨天|前天|\d+分钟前|\d+小时前|\d+天前|"
        r"\d{4}[-年/]\d{1,2}[-月/]\d{1,2}(?:日|)?)",
        card_text,
    )
    return match.group(0)[:100] if match else ""


def _generic_card(anchor):
    cards = anchor.xpath(
        "ancestor::*[self::article or self::li or @role='article' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' card ')][1]"
    )
    return cards[0] if cards else anchor


def _generic_hashtags(anchor):
    """Collect visible topic labels while keeping the source bounded."""
    card = _generic_card(anchor)
    values = card.xpath(
        ".//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        "'abcdefghijklmnopqrstuvwxyz'),'hashtag') or "
        "contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'topic')]/text()"
    )
    values.extend(
        card.xpath(".//a[contains(@href,'tag') or contains(@href,'topic')]/text()")
    )
    values.append(_clean_generic_text(text_of(card), 2_000))
    result = []
    seen = set()
    for value in values:
        for match in re.finditer(r"#([^#\s]{1,50})#?", str(value)):
            tag = _clean_generic_text(match.group(1), 50)
            if tag and tag not in seen:
                seen.add(tag)
                result.append(tag)
            if len(result) >= 32:
                return tuple(result)
    return tuple(result)


def _parse_generic_count(value):
    value = _clean_generic_text(str(value), 40).replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([万亿]?)", value)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {"": 1, "万": 10_000, "亿": 100_000_000}[match.group(2)]
    result = int(number * multiplier)
    return result if result <= 2**53 - 1 else None


def _generic_interaction_stats(anchor):
    """Read explicitly rendered counters; absent counters remain unknown."""
    card = _generic_card(anchor)
    key_names = {
        "like": "likes",
        "likes": "likes",
        "like-count": "likes",
        "点赞": "likes",
        "赞": "likes",
        "comment": "comments",
        "comments": "comments",
        "comment-count": "comments",
        "评论": "comments",
        "share": "shares",
        "shares": "shares",
        "share-count": "shares",
        "分享": "shares",
        "favorite": "favorites",
        "favorites": "favorites",
        "收藏": "favorites",
    }
    result = {}
    for node in [card, *card.xpath(".//*")]:
        for key, raw in node.attrib.items():
            normalized = key.lower().replace("data-", "").replace("_", "-")
            name = key_names.get(normalized)
            if name:
                parsed = _parse_generic_count(raw)
                if parsed is not None:
                    result[name] = parsed
    labels = _clean_generic_text(" ".join(card.xpath(".//@aria-label")), 2_000)
    stat_labels = (
        r"(?:(\d+(?:\.\d+)?[万亿]?)\s*(点赞|赞|评论|分享|收藏)|"
        r"(点赞|赞|评论|分享|收藏)\s*(\d+(?:\.\d+)?[万亿]?))"
    )
    for match in re.finditer(stat_labels, labels):
        label = match.group(2) or match.group(3)
        raw_value = match.group(1) or match.group(4)
        name = {
            "点赞": "likes",
            "赞": "likes",
            "评论": "comments",
            "分享": "shares",
            "收藏": "favorites",
        }[label]
        parsed = _parse_generic_count(raw_value)
        if parsed is not None:
            result.setdefault(name, parsed)
    return result


def _generic_next_url(platform, base, raw):
    """Return one same-platform pagination link from a rendered search page."""
    root = document(raw)
    if root is None:
        return None
    for anchor in root.xpath("//a[@href] | //link[@href]"):
        href = anchor.get("href", "")
        rel = {value.lower() for value in anchor.get("rel", "").split()}
        label = " ".join(text_of(anchor).split()).lower()
        if "next" not in rel and not any(
            marker in label for marker in ("下一页", "下页", "next")
        ):
            continue
        candidate = urljoin(base, href)
        try:
            parts = urlsplit(candidate)
        except ValueError:
            continue
        host = (parts.hostname or "").lower().rstrip(".")
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or not any(
                host == root_domain or host.endswith("." + root_domain)
                for root_domain in _PLATFORM_HOSTS.get(platform, ())
            )
            or _generic_content_identity(platform, candidate, base) is not None
        ):
            continue
        return candidate
    return None


class NativeWeiboCollector:
    def __init__(
        self,
        *,
        browser: RenderedBrowser,
        delay_seconds=2.0,
        ready_polls=20,
        max_pages=40,
        timeout_seconds=180,
        check_timeout_seconds=20,
        on_progress=None,
        enricher=None,
        latest_first=True,
    ):
        self.browser = browser
        self.delay_seconds = delay_seconds
        self.ready_polls = ready_polls
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.check_timeout_seconds = check_timeout_seconds
        self.on_progress = on_progress
        self.latest_first = latest_first
        if enricher is None:
            from longtian_api.services.weibo_enrichment import WeiboEnricher

            enricher = WeiboEnricher(browser=browser)
        self.enricher = enricher

    supports_manual_acquisition = True
    supports_per_term_resume_budget = True
    supported_platforms = frozenset({"wb", "dy", "ks", "xhs", "toutiao"})

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
        previous_content_ids_by_term=(),
    ):
        if platform != "wb":
            return await self._search_generic(
                platform=platform,
                terms=terms,
                max_results_per_term=max_results_per_term,
                on_progress=on_progress,
                on_item=on_item,
                on_term_completed=on_term_completed,
                max_total_results=max_total_results,
                previous_content_ids=previous_content_ids,
                previous_content_ids_by_term=previous_content_ids_by_term,
            )
        if max_total_results is not None:
            return await self._search_latest(
                terms=terms,
                limit=max_total_results,
                previous_content_ids=previous_content_ids,
                on_progress=on_progress,
                on_item=on_item,
                on_term_completed=on_term_completed,
            )
        found = any(previous_content_ids_by_term)
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
            await self.browser.start()
            for position, term in enumerate(terms):
                await on_progress(position, len(terms))
                previous = (
                    set(previous_content_ids_by_term[position])
                    if position < len(previous_content_ids_by_term)
                    else set()
                )
                url = (
                    "https://s.weibo.com/realtime?"
                    + urlencode({"q": term, "rd": "realtime", "tw": "realtime"})
                    if self.latest_first
                    else "https://s.weibo.com/weibo?" + urlencode({"q": term})
                )
                seen, visited = set(), set()
                recovery_attempted = False
                incomplete_reason: SearchTermIncompleteReason | None = None
                while url and len(previous | seen) < max_results_per_term:
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
                            *(await self.browser.snapshot()),
                            term,
                            latest=self.latest_first,
                        )
                        if parsed.state not in ("pending", "empty_page"):
                            break
                        if poll + 1 < self.ready_polls:
                            await asyncio.sleep(0.25)
                    if parsed is None:
                        parsed = read_search_page(
                            *(await self.browser.snapshot()),
                            term,
                            latest=self.latest_first,
                        )
                    for item in parsed.items:
                        if item.content_id not in seen and (
                            item.content_id in previous
                            or len(previous | seen) < max_results_per_term
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
                    if parsed.state not in ("results", "empty", "empty_page"):
                        if recovery_attempted and parsed.state == "pending":
                            incomplete_reason = "view_all_unresolved"
                            break
                        state = (
                            "page_state_unrecognized"
                            if parsed.state == "pending"
                            else parsed.state
                        )
                        return result(state)
                    if (
                        len(previous | seen) >= max_results_per_term
                        or parsed.state == "empty"
                    ):
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
            await self.browser.start()
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
                                if parsed.state not in ("pending", "empty_page"):
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
                        elif parsed.state in ("results", "empty", "empty_page"):
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

    async def discard_session(self):
        await self.browser.close_page()

    async def _search_generic(
        self,
        *,
        platform,
        terms,
        max_results_per_term,
        on_progress,
        on_item,
        on_term_completed,
        max_total_results=None,
        previous_content_ids=(),
        previous_content_ids_by_term=(),
    ):
        """Collect visible public cards from a platform search page.

        The adapter deliberately uses rendered links and text only. It does
        not call private JSON endpoints or download media; unsupported DOM
        changes become a bounded empty/incomplete result for that platform.
        """
        deadline = monotonic() + self.timeout_seconds
        found = False
        pages = 0
        try:
            await self.browser.start()
            global_admitted = set(previous_content_ids)
            for position, term in enumerate(terms):
                if monotonic() >= deadline:
                    return SearchWorkerResult("timed_out", execution_limit="time")
                await on_progress(position, len(terms))
                url = _PLATFORM_SEARCH[platform](term)
                visited = set()
                previous = (
                    set(previous_content_ids_by_term[position])
                    if position < len(previous_content_ids_by_term)
                    else set()
                )
                # Resume IDs count towards the durable cap, but completion
                # proofs belong to this attempt. Keep those two sets separate
                # so a resumed term with no new cards reports zero current
                # observations instead of claiming rows that live in an older
                # attempt.
                term_admitted = set(previous)
                # A max-total run has one unique cap across all terms.  The
                # per-term protocol keeps independent caps and resumes from
                # the IDs already observed for each term.
                found = found or bool(term_admitted) or bool(global_admitted)
                observed = set()
                state = "empty"
                while url and len(
                    global_admitted if max_total_results is not None else term_admitted
                ) < (
                    max_total_results
                    if max_total_results is not None
                    else max_results_per_term
                ):
                    if monotonic() >= deadline:
                        return SearchWorkerResult("timed_out", execution_limit="time")
                    if pages >= self.max_pages:
                        return SearchWorkerResult("timed_out", execution_limit="pages")
                    identity = _search_url_identity(url)
                    if identity in visited:
                        return SearchWorkerResult("search_pagination_incompatible")
                    visited.add(identity)
                    pages += 1
                    await self.browser.navigate(url)
                    current_url, raw, status = await self.browser.snapshot()
                    state, items = _read_generic_page(
                        platform, current_url, raw, term, status
                    )
                    if state in {
                        "login_required",
                        "manual_challenge_required",
                        "platform_blocked_or_rate_limited",
                        "structure_changed",
                        "pending",
                    }:
                        if state == "pending":
                            state = "page_state_unrecognized"
                        return SearchWorkerResult(state)
                    for item in items:
                        if item.content_id in observed:
                            continue
                        if max_total_results is not None:
                            if (
                                item.content_id not in global_admitted
                                and len(global_admitted) >= max_total_results
                            ):
                                break
                        elif (
                            item.content_id not in term_admitted
                            and len(term_admitted) >= max_results_per_term
                        ):
                            break
                        await on_item(position, item)
                        observed.add(item.content_id)
                        term_admitted.add(item.content_id)
                        global_admitted.add(item.content_id)
                        found = True
                        if len(
                            global_admitted
                            if max_total_results is not None
                            else term_admitted
                        ) >= (
                            max_total_results
                            if max_total_results is not None
                            else max_results_per_term
                        ):
                            break
                    if len(
                        global_admitted
                        if max_total_results is not None
                        else term_admitted
                    ) >= (
                        max_total_results
                        if max_total_results is not None
                        else max_results_per_term
                    ):
                        break
                    url = _generic_next_url(platform, current_url, raw)
                await on_term_completed(
                    position,
                    len(observed),
                    None,
                )
            return SearchWorkerResult(
                "completed_with_results" if found else "completed_empty"
            )
        except BrowserBudgetExceeded as error:
            return SearchWorkerResult("timed_out", execution_limit=error.limit)
        except TimeoutError:
            return SearchWorkerResult("timed_out", execution_limit="time")
        except BrowserUnavailable:
            return SearchWorkerResult("browser_unavailable")

    async def manual_page(self, *, request_id, platform, action):
        if platform not in self.supported_platforms:
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
            elif platform != "wb":
                await self.browser.navigate(_PLATFORM_HOME[platform])
                await self.browser.bring_to_front()
            return ManualPageWorkerResult(
                "opened_existing" if existing else "opened_homepage"
            )
        except BrowserUnavailable:
            return ManualPageWorkerResult("browser_unavailable")

    async def open_browser(self, *, request_id, platform=None):
        """Open the owned browser without starting an authentication check."""
        if platform is not None and platform not in self.supported_platforms:
            return ManualPageWorkerResult("browser_unavailable")
        try:
            existing = getattr(self.browser, "page_present", self.browser.available)
            await self.browser.show()
            # A platform row explicitly requests that platform's homepage,
            # including when the browser was already opened on a blank tab.
            # The general browser button only foregrounds the current page.
            if platform is not None:
                await self.browser.navigate(_PLATFORM_HOME[platform])
                await self.browser.bring_to_front()
            return ManualPageWorkerResult(
                "opened_existing" if existing else "opened_homepage"
            )
        except BrowserUnavailable:
            return ManualPageWorkerResult("browser_unavailable")

    async def check(self, *, request_id, platform):
        if platform not in self.supported_platforms:
            return AuthWorkerResult("failed", "browser_unavailable")
        use_check_page = self.browser.available and all(
            hasattr(self.browser, method)
            for method in (
                "start_check_page",
                "navigate_check",
                "snapshot_check",
                "close_check_page",
            )
        )
        try:
            # The budget covers browser setup, navigation, and the one DOM
            # snapshot.  A platform can leave navigation pending indefinitely
            # while a challenge or network failure is being rendered.
            async with asyncio.timeout(self.check_timeout_seconds):
                if not self.browser.available:
                    # The public platform-connection service rejects checks
                    # before this point when no browser is open.  Keeping this
                    # fallback makes the worker safe for direct internal
                    # callers.
                    await self.browser.start()
                if not use_check_page:
                    # Compatibility doubles may not expose an isolated page;
                    # only that fallback needs to foreground the main page.
                    await self.browser.bring_to_front()
                home = _PLATFORM_HOME.get(platform, "https://weibo.com/")
                if use_check_page:
                    await self.browser.start_check_page()
                    await self.browser.navigate_check(home)
                    snapshot = self.browser.snapshot_check
                else:
                    # Compatibility for older test doubles; the native browser
                    # always uses the isolated check page above.
                    await self.browser.start()
                    await self.browser.navigate(home)
                    snapshot = self.browser.snapshot
                hydration_started = monotonic()
                wait_update = (
                    getattr(self.browser, "wait_check_update", None)
                    if use_check_page
                    else None
                )
                while True:
                    url, raw, status = await snapshot()
                    result = _classify_connection_page(platform, url, raw, status)
                    if (
                        not callable(wait_update)
                        or result.outcome == "connected"
                        or result.reason == "manual_challenge"
                        or status >= 400
                    ):
                        return result
                    # An SSR login button can disappear once the existing
                    # session hydrates. Do not publish that provisional state.
                    if (
                        result.outcome == "disconnected"
                        and monotonic() - hydration_started >= 3
                    ):
                        return result
                    await wait_update()
        except (BrowserUnavailable, BrowserBudgetExceeded):
            return AuthWorkerResult("failed", "browser_unavailable")
        except TimeoutError:
            return AuthWorkerResult("failed", "check_failed")
        finally:
            if use_check_page:
                await self.browser.close_check_page()

    async def open_result(
        self, *, request_id, term, content_id, platform=None, content_url=None
    ):
        if (
            not isinstance(content_id, str)
            or not content_id
            or len(content_id) > 128
            or not content_id.isascii()
            or not re.fullmatch(r"[A-Za-z0-9_-]+", content_id)
        ):
            return OpenResultWorkerResult("content_not_found")
        try:
            await self.browser.start()
            # The content URL is reconstructed from the selected platform ID;
            # callers cannot inject an arbitrary navigation target here.
            if content_url is None:
                platform = platform or ("xhs" if len(content_id) == 24 else "wb")
                content_url = {
                    "wb": f"https://m.weibo.cn/detail/{content_id}",
                    "xhs": f"https://www.xiaohongshu.com/explore/{content_id}",
                    "ks": f"https://www.kuaishou.com/short-video/{content_id}",
                    "dy": f"https://www.douyin.com/video/{content_id}",
                    "toutiao": f"https://www.toutiao.com/article/{content_id}/",
                }.get(platform)
            if (
                platform is None
                or content_url is None
                or not is_valid_search_content_url(platform, content_id, content_url)
            ):
                return OpenResultWorkerResult("content_not_found")
            await self.browser.navigate(content_url)
            await self.browser.show()
            return OpenResultWorkerResult("opened")
        except (BrowserUnavailable, BrowserBudgetExceeded, TimeoutError):
            return OpenResultWorkerResult("browser_unavailable")

    async def enrich(self, **kwargs):
        if kwargs.get("platform") == "wb":
            return await self.enricher.enrich(**kwargs)
        return await self._enrich_text(**kwargs)

    async def _enrich_text(
        self, *, request_id, platform, content_id, content_url, term, budget, **_kwargs
    ):
        from longtian_api.services.enrichment_models import (
            EnrichedContent,
            EnrichmentIssue,
            EnrichmentText,
        )

        try:
            if not is_valid_search_content_url(platform, content_id, content_url):
                return EnrichmentWorkerResult("content_unavailable")
            await self.browser.start()
            await self.browser.navigate(content_url)
            url, raw, status = await self.browser.snapshot()
            root = document(raw)
            if root is None:
                return EnrichmentWorkerResult("content_unavailable")
            barrier_outcome = _generic_detail_barrier(url, root, status)
            if barrier_outcome is not None:
                return EnrichmentWorkerResult(barrier_outcome)
            title = _generic_detail_title(root)
            body, body_truncated = _generic_detail_text(root)
            body_limit = max(0, budget.max_text_chars - len(title))
            if len(body) > body_limit:
                body = body[:body_limit]
                body_truncated = True
            # Toutiao article pages are required to expose the article body.
            # Their title and OpenGraph/search descriptions are often rendered
            # even when the article payload is missing, so title-only input
            # would falsely satisfy the full-text acquisition contract.
            toutiao_article_without_body = False
            if platform == "toutiao":
                path = (urlsplit(url).path or "").rstrip("/").lower()
                toutiao_article_without_body = (
                    path.startswith("/article/") and not body.strip()
                )
            if toutiao_article_without_body or (not title and not body):
                # The detail page was reachable, but it exposed no usable
                # prose (for example a media-only post). Preserve that as a
                # completed acquisition with an explicit text gap so the
                # analysis stage can deliver a human-review report.
                value = EnrichedContent(
                    schema_version=1,
                    platform=platform,
                    content_id=content_id,
                    content_url=content_url,
                    acquired_at=int(time() * 1000),
                    extractor_version=f"{platform}-enrichment-v1",
                    status="unavailable",
                    text=EnrichmentText(
                        title=title if not toutiao_article_without_body else "",
                        body="",
                        coverage="unavailable",
                    ),
                    detected_modalities=["text"],
                    media_inventory_complete=True,
                    assets=[],
                    issues=[
                        EnrichmentIssue(code="text_unavailable", asset_position=None)
                    ],
                )
                return EnrichmentWorkerResult("completed", content=value)
            issues = []
            coverage = "complete"
            if body_truncated:
                coverage = "partial"
                issues.append(EnrichmentIssue(code="text_limit", asset_position=None))
            value = EnrichedContent(
                schema_version=1,
                platform=platform,
                content_id=content_id,
                content_url=content_url,
                acquired_at=int(time() * 1000),
                extractor_version=f"{platform}-enrichment-v1",
                status="partial" if issues else "ready",
                text=EnrichmentText(title=title, body=body, coverage=coverage),
                detected_modalities=["text"],
                media_inventory_complete=True,
                assets=[],
                issues=issues,
            )
            return EnrichmentWorkerResult("completed", content=value)
        except BrowserBudgetExceeded:
            return EnrichmentWorkerResult("timed_out")
        except (BrowserUnavailable, TimeoutError):
            return EnrichmentWorkerResult("browser_unavailable")

    def discard_enrichment_checkpoint(self):
        self.enricher.reset()

    async def shutdown(self):
        self.enricher.reset()
        await self.browser.shutdown()


def _classify_connection_page(platform, url, raw, status):
    """Classify one rendered platform home page without waiting for login."""
    root = document(raw)
    if root is None:
        return AuthWorkerResult("failed", "check_failed")

    body = text_of(root)
    title = " ".join(root.xpath("//title/text()"))
    if platform == "wb":
        signed_in = bool(
            root.xpath(_SIGNED_IN_XPATH)
            or any(word in body for word in ("退出", "我的主页", "个人中心"))
        )
        blocked = barrier(root, url, status)
        if blocked == "manual_challenge_required":
            return AuthWorkerResult("failed", "manual_challenge")
        if status >= 400:
            return AuthWorkerResult("failed", "check_failed")
        if signed_in and blocked not in {
            "platform_blocked_or_rate_limited",
        }:
            return AuthWorkerResult("connected", "none")
        if blocked == "login_required" or _weibo_anonymous_shell(root, url):
            return AuthWorkerResult("disconnected", "login_required")
        return AuthWorkerResult("failed", "check_failed")

    challenge_markers = ("验证码", "安全验证", "人机验证", "滑动验证", "请完成验证")
    if any(marker in f"{title} {body}" for marker in challenge_markers):
        return AuthWorkerResult("failed", "manual_challenge")
    if status >= 400:
        return AuthWorkerResult("failed", "check_failed")
    signed_in = bool(
        root.xpath(_SIGNED_IN_XPATH)
        or (
            platform == "ks"
            and root.xpath(
                "//*[contains(concat(' ', normalize-space(@class), ' '), ' down-box ')]"
                "//*[contains(concat(' ', normalize-space(@class), ' '), ' user ')]"
                "//*[contains(concat(' ', normalize-space(@class), ' '), ' text-name ')"
                " and normalize-space()]"
            )
        )
        or any(word in body for word in ("退出", "我的主页", "个人中心"))
        or any(
            marker in f"{title} {body}"
            for marker in _PLATFORM_SIGNED_IN_MARKERS.get(platform, ())
        )
    )
    if signed_in:
        return AuthWorkerResult("connected", "none")
    anonymous_markers = (
        "登录",
        "请登录",
        "手机号登录",
        "扫码登录",
        "登录后查看",
    )
    try:
        path = (urlsplit(url).path or "").lower()
    except ValueError:
        path = ""
    if (
        path == "/login"
        or path.startswith("/login/")
        or any(marker in body for marker in anonymous_markers)
    ):
        return AuthWorkerResult("disconnected", "login_required")
    return AuthWorkerResult("failed", "check_failed")


def _weibo_anonymous_shell(root, url):
    """Recognize compact login shells without scanning arbitrary post text."""
    try:
        path = (urlsplit(url).path or "").lower()
    except ValueError:
        path = ""
    if path == "/login" or path.startswith("/login/"):
        return True
    markers = ("登录", "请登录", "手机号登录", "扫码登录", "登录后查看")
    for node in root.xpath("//header | //main"):
        value = re.sub(r"\s+", "", text_of(node))
        if len(value) <= 80 and any(marker in value for marker in markers):
            return True
    return False


def _generic_detail_title(root):
    """Extract a rendered post title without using a search-page snippet."""
    values = root.xpath(
        "//meta[translate(@property,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        "'abcdefghijklmnopqrstuvwxyz')='og:title']/@content"
        " | //meta[@itemprop='name']/@content"
        " | //*[@id='detail-title' or @data-testid='post-title']/text()"
        " | //h1[normalize-space()]/text()"
    )
    for value in values:
        cleaned = _clean_generic_text(value, 1000)
        if cleaned and not _generic_shell_title(cleaned):
            return cleaned
    # A document title is useful only when it describes the post.  Platform
    # shells commonly expose titles such as “登录” or “抖音”, which would turn
    # a media-only page into apparently usable model input.
    for value in root.xpath("//title/text()"):
        cleaned = _clean_generic_text(value, 1000)
        if cleaned and not _generic_shell_title(cleaned):
            return cleaned
    return ""


def _generic_shell_title(value):
    lowered = " ".join(value.split()).lower()
    if any(
        marker in lowered
        for marker in ("登录", "login", "验证码", "安全验证", "人机验证")
    ):
        return True
    # Platform home shells use a bare product name; a real post title may
    # legitimately mention the platform name and must not be discarded.
    return lowered in {
        "douyin",
        "kuaishou",
        "toutiao",
        "xiaohongshu",
        "抖音",
        "快手",
        "今日头条",
        "小红书",
        # These labels are common headings for a media/detail shell.  They do
        # not describe the selected post and must not make a media-only page
        # look like usable text evidence.
        "作品",
        "视频",
        "文章",
        "笔记",
        "内容",
        "首页",
        "搜索",
        "搜索结果",
        "用户主页",
        "video",
        "post",
        "note",
        "article",
        "content",
        "home",
        "search",
    }


def _generic_detail_barrier(url, root, status):
    """Classify access barriers before page chrome becomes source text."""
    if status == 401:
        return "login_required"
    try:
        path = (urlsplit(url).path or "").lower()
    except ValueError:
        path = ""
    if path == "/login" or path.startswith("/login/") or path.endswith("/login"):
        return "login_required"
    signal = _generic_signal_text(root)
    if status >= 400:
        signal = " ".join((signal, _clean_generic_text(text_of(root), 20_000)))
    # Bare 200 login/challenge shells may contain only a heading and text.
    # When no recognizable content container exists, the full document is a
    # safe fallback because there is no post body to misclassify.
    if status < 400 and not root.xpath(_generic_detail_container_query()):
        signal = " ".join((signal, _clean_generic_text(text_of(root), 20_000)))
    if any(word in signal for word in ("验证码", "安全验证", "人机验证", "滑动验证")):
        return "manual_challenge_required"
    if status in (403, 429) or any(
        word in signal for word in ("访问频繁", "请求过于频繁", "稍后再试")
    ):
        return "platform_blocked_or_rate_limited"
    if any(word in signal for word in ("请登录", "登录后查看", "登录后继续")):
        return "login_required"
    if status >= 400:
        return "content_unavailable"
    return None


def _normalize_generic_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _generic_detail_text(root, *, max_chars=20_000):
    """Return bounded post prose and whether the rendered text was truncated.

    Only dedicated post/article/caption containers are trusted.  Page-level
    ``main``/``article`` nodes and OpenGraph descriptions can include shell
    copy, recommendations, or search excerpts, so they are intentionally
    treated as unavailable instead of being presented as original text.
    """
    nodes = root.xpath(_generic_detail_container_query(include_main=False))
    candidates = []
    seen = set()
    for node in nodes:
        identity = id(node)
        if identity in seen:
            continue
        seen.add(identity)
        value = _normalize_generic_text(text_of(node))
        if value:
            candidates.append((node, value))
    if not candidates:
        return "", False

    node, body = max(candidates, key=lambda item: len(item[1]))
    # Preserve the source boundary when a rendered post contains an explicitly
    # nested quote/repost block.  Do not silently merge quoted text into the
    # publisher's own copy.
    quoted = []
    quote_query = (
        ".//blockquote | .//*[contains(translate(concat(' ',@class,' ',@id),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' retweet ') "
        "or contains(translate(concat(' ',@class,' ',@id),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' repost ') "
        "or contains(translate(concat(' ',@class,' ',@id),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' quoted ') "
        "or contains(translate(concat(' ',@class,' ',@id),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),' forward ')]"
    )
    for quote_node in node.xpath(quote_query):
        quote_text = _normalize_generic_text(text_of(quote_node))
        if quote_text and quote_text != body and quote_text not in quoted:
            quoted.append(quote_text)
    for quote_text in quoted:
        body = body.replace(quote_text, "", 1).strip()
        body = (
            f"{body}\n\n【转发附带原帖】\n{quote_text}"
            if body
            else (f"【转发附带原帖】\n{quote_text}")
        )
    truncated = len(body) > max_chars
    return body[:max_chars], truncated


def _generic_detail_body(root, platform=None):
    """Choose one rendered post container and avoid page-chrome text.

    Falling back to ``<body>`` makes navigation labels, login prompts, and
    media-only shells look like post text.  The selector set is intentionally
    conservative; an unknown layout yields text insufficiency for review.
    """
    return _generic_detail_text(root)[0]


def _generic_detail_container_query(*, include_main=False):
    """Return the bounded set of selectors used for rendered post prose.

    Platform layouts are dynamic, so the selector set includes stable
    semantic attributes and the common article/caption class names observed in
    rendered pages. It intentionally excludes a generic ``body`` fallback;
    navigation and login chrome must never become model input.
    """
    lower_class = (
        "translate(concat(' ',@class,' ',@id,' ',@data-testid),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
    )
    class_terms = " or ".join(
        f"contains({lower_class},'{term}')"
        for term in (
            "article-body",
            "article-content",
            "article_body",
            "tt-article",
            "pgc-article",
            "post-content",
            "note-content",
            "note-scroller",
            "detail-content",
            "feed-detail-content",
            "video-desc",
            "video-description",
            "caption",
            "content-body",
        )
    )
    selectors = (
        "//*[@itemprop='articleBody'] | //*[@data-testid='article-content'] | "
        "//*[@data-testid='post-content'] | //*[@data-testid='note-content'] | "
        "//*[@data-testid='video-desc'] | //*[@data-e2e='video-desc' or "
        "@data-e2e='feed-video-desc' or @data-e2e='note-content'] | "
        "//*[@id='detail-desc' or @id='noteContainer' or @id='article-content'] | "
        "//*[" + class_terms + "]"
    )
    if include_main:
        selectors = selectors + " | //*[@role='main'] | //main | //article"
    return selectors
