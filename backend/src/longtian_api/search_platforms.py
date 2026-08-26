"""Shared platform identity and content-link validation for product search."""

from typing import Literal
from urllib.parse import urlsplit

SearchPlatform = Literal["toutiao", "wb", "ks", "dy", "xhs"]
SEARCH_PLATFORMS: tuple[SearchPlatform, ...] = (
    "toutiao",
    "wb",
    "ks",
    "dy",
    "xhs",
)


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

    if platform == "dy":
        return (
            platform_content_id.isascii()
            and platform_content_id.isdigit()
            and value == f"https://www.douyin.com/video/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "www.douyin.com"
            and port is None
            and parsed.query == ""
        )

    if platform == "xhs":
        return (
            len(platform_content_id) == 24
            and platform_content_id.isascii()
            and all(
                character in "0123456789abcdef" for character in platform_content_id
            )
            and value == f"https://www.xiaohongshu.com/explore/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "www.xiaohongshu.com"
            and port is None
            and parsed.query == ""
        )

    return False
