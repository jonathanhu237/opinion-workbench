"""Shared platform identity and content-link validation for product search."""

from typing import Literal
from urllib.parse import urlsplit

SearchPlatform = Literal["wb"]
SEARCH_PLATFORMS: tuple[SearchPlatform, ...] = ("wb",)


def is_supported_search_platform(platform: SearchPlatform | str) -> bool:
    """Return whether a platform can be admitted by the current product."""
    return platform == "wb"


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

    if platform == "wb":
        return (
            value == f"https://m.weibo.cn/detail/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "m.weibo.cn"
            and port is None
            and parsed.query == ""
        )

    return False
