"""Small versioned adapter for rendered Weibo DOM, not private platform APIs.

Selectors fail closed. Page fixtures prove adapter semantics, not compatibility
with a live site; real-account acceptance is a separate release prerequisite.
"""

import hashlib
import re
from dataclasses import dataclass
from time import time
from urllib.parse import parse_qs, urljoin, urlsplit

from lxml import etree, html

from longtian_api.services.collector_contracts import SearchWorkerItem


def css_class(name):
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def text_of(node):
    return " ".join(node.text_content().split())


def safe_weibo_link(value, base):
    value = urljoin(base, value)
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.hostname not in ("weibo.com", "www.weibo.com", "m.weibo.cn")
        ):
            return None
    except ValueError:
        return None
    return value


def permalink_matches(value, base, mid):
    link = safe_weibo_link(value, base)
    if link is None:
        return False
    parts = urlsplit(link)
    pattern = (
        r"/(?:detail|status)/([a-zA-Z0-9]+)"
        if parts.hostname == "m.weibo.cn"
        else r"/[0-9]+/([a-zA-Z0-9]+)"
    )
    matched = re.fullmatch(pattern, parts.path)
    if not matched:
        return False
    identity = matched[1]
    if identity.isdigit() and len(identity) >= 13:
        return identity == mid
    if not 5 <= len(identity) <= 16:
        return False
    # Weibo encodes each seven decimal digits as four base-62 digits.
    # Known independent fixture: A09LvzUOy <-> 3600375418559878.
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    padded = identity.zfill(((len(identity) + 3) // 4) * 4)
    numeric = 0
    for offset in range(0, len(padded), 4):
        group = sum(
            alphabet.index(char) * 62 ** (3 - index)
            for index, char in enumerate(padded[offset : offset + 4])
        )
        if group >= 10_000_000:
            return False
        numeric = numeric * 10_000_000 + group
    return str(numeric) == mid


@dataclass(frozen=True)
class SearchPage:
    state: str
    items: tuple[SearchWorkerItem, ...] = ()
    next_url: str | None = None


def document(raw):
    if not raw or len(raw) > 4 * 1024 * 1024:
        return None
    try:
        root = html.fromstring(raw, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError):
        return None
    for node in root.xpath("//script|//style|//*[@hidden]|//*[@aria-hidden='true']"):
        node.drop_tree()
    return root


def barrier(root, url, status):
    host = urlsplit(url).hostname or ""
    if status == 429:
        return "platform_blocked_or_rate_limited"
    if status == 401 or host in ("passport.weibo.com", "passport.weibo.cn"):
        return "login_required"
    if root is None:
        return None
    titles = " ".join(root.xpath("//title/text()"))
    if host in ("security.weibo.com", "security.weibo.cn") or any(
        word in titles for word in ("安全验证", "访问异常")
    ):
        return "manual_challenge_required"
    # Inspect platform notice/login containers, never keywords in a user's post.
    notices = root.xpath(
        "//*[self::form or @role='dialog' or "
        + css_class("card-no-result")
        + " or "
        + css_class("woo-modal-main")
        + " or "
        + css_class("WB_error")
        + "]"
    )
    values = " ".join(text_of(node) for node in notices)
    if any(word in values for word in ("访问频次过高", "操作频繁", "请求过于频繁")):
        return "platform_blocked_or_rate_limited"
    if any(
        word in values for word in ("安全验证", "请完成验证", "拖动滑块", "访问异常")
    ):
        return "manual_challenge_required"
    if root.xpath("//input[@type='password']") or any(
        word in values for word in ("登录后查看", "请先登录", "扫码登录")
    ):
        return "login_required"
    if status == 403:
        return "manual_challenge_required"
    return None


def read_search_page(url, raw, status, term):
    root = document(raw)
    blocked = barrier(root, url, status)
    if blocked:
        return SearchPage(blocked)
    parts = urlsplit(url)
    if (
        parts.hostname != "s.weibo.com"
        or parts.path != "/weibo"
        or parse_qs(parts.query).get("q") != [term]
    ):
        return SearchPage("search_context_unavailable")
    if root is None:
        return SearchPage("pending")
    cards = root.xpath("//*[@action-type='feed_list_item']")
    items = []
    for card in cards:
        mid = card.get("mid", "")
        links = card.xpath(".//*[" + css_class("from") + "]//a[@href]")
        bodies = card.xpath(
            ".//*[@node-type='feed_list_content_full' or "
            "@node-type='feed_list_content']"
        )
        if (
            not re.fullmatch(r"[1-9][0-9]{5,23}", mid)
            or not links
            or not bodies
            or not permalink_matches(links[0].get("href"), url, mid)
        ):
            return SearchPage("search_results_incompatible", tuple(items))
        names = card.xpath(".//a[" + css_class("name") + "]")
        name = text_of(names[0]) if names else ""
        creator = hashlib.sha256(name.encode()).hexdigest()[:16] if name else ""
        masked = (
            ""
            if not name
            else (
                "*"
                if len(name) == 1
                else name[0] + "*"
                if len(name) == 2
                else name[0] + "***" + name[-1]
            )
        )
        body = max((text_of(node) for node in bodies), key=len)
        items.append(
            SearchWorkerItem(
                content_id=mid,
                content_type="post",
                title=body[:300] or f"微博内容 {mid}",
                snippet=body[:1000],
                creator_hash=creator,
                publisher_name=masked,
                published_at_text=text_of(links[0])[:100],
                content_url=f"https://m.weibo.cn/detail/{mid}",
                discovered_at=int(time() * 1000),
            )
        )
    if not cards:
        empty = root.xpath("//*[" + css_class("card-no-result") + "]")
        if empty and any(word in text_of(empty[0]) for word in ("未找到", "没有找到")):
            return SearchPage("empty")
        return SearchPage("pending")
    next_links = root.xpath("//a[" + css_class("next") + "][@href]")
    next_url = None
    if next_links:
        next_url = urljoin(url, next_links[0].get("href"))
        parsed = urlsplit(next_url)
        query = parse_qs(parsed.query)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "s.weibo.com"
            or parsed.path != "/weibo"
            or query.get("q") != [term]
            or not re.fullmatch(r"[1-9][0-9]{0,3}", query.get("page", [""])[0])
        ):
            return SearchPage("search_pagination_incompatible", tuple(items))
    return SearchPage("results", tuple(items), next_url)
