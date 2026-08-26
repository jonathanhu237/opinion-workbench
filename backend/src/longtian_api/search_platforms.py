"""Shared platform identity and content-link validation for product search."""

from typing import Literal
from urllib.parse import urlsplit

SearchPlatform = Literal["toutiao", "wb", "ks"]
SEARCH_PLATFORMS: tuple[SearchPlatform, ...] = ("toutiao", "wb", "ks")


def is_valid_search_content_url(
    platform: SearchPlatform,
    platform_content_id: str,
    value: str,
) -> bool:
    """Return whether a normalized content URL matches its correlated platform."""
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return False

    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        return False

    if platform == "toutiao":
        return (
            parsed.scheme in {"http", "https"}
            and (hostname == "toutiao.com" or hostname.endswith(".toutiao.com"))
            and (port is None or port == (80 if parsed.scheme == "http" else 443))
        )

    if platform == "wb":
        return (
            value == f"https://m.weibo.cn/detail/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "m.weibo.cn"
            and port is None
            and parsed.query == ""
        )

    if platform == "ks":
        return (
            value == f"https://www.kuaishou.com/short-video/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "www.kuaishou.com"
            and port is None
            and parsed.query == ""
        )

    return False
