"""Shared platform identity and content-link validation for product search."""

import re
from typing import Literal
from urllib.parse import urlsplit

SearchPlatform = Literal["wb", "dy", "ks", "xhs", "toutiao"]
# Keep the existing Weibo entry first so stored/UI catalog projections remain
# backward-compatible while newly admitted requests still default to all five.
SEARCH_PLATFORMS: tuple[SearchPlatform, ...] = ("wb", "dy", "ks", "xhs", "toutiao")

_TOUTIAO_CONTENT_PATH = re.compile(r"/(article|w|video)/([0-9]{8,24})/$")
_KS_CONTENT_PATH = re.compile(r"/short-video/([A-Za-z0-9_-]{1,128})$")
_DY_CONTENT_PATH = re.compile(r"/video/([0-9]{1,128})$")
_XHS_CONTENT_PATH = re.compile(r"/explore/([0-9a-f]{24})$")
_WB_CONTENT_PATH = re.compile(r"/detail/([0-9]{1,24})$")


def is_supported_search_platform(platform: SearchPlatform | str) -> bool:
    """Return whether a platform can be admitted by the current product."""
    return platform in SEARCH_PLATFORMS


def is_valid_search_content_url(
    platform: SearchPlatform,
    platform_content_id: str,
    value: str,
) -> bool:
    """Return whether a normalized content URL matches its correlated platform."""
    if type(platform_content_id) is not str or type(value) is not str:
        return False
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return False

    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        return False

    if platform == "toutiao":
        match = _TOUTIAO_CONTENT_PATH.fullmatch(parsed.path)
        return (
            match is not None
            and match.group(2) == platform_content_id
            and value
            == f"https://www.toutiao.com/{match.group(1)}/{platform_content_id}/"
            and parsed.scheme == "https"
            and hostname == "www.toutiao.com"
            and port is None
            and parsed.query == ""
        )
    if platform == "wb":
        return (
            platform_content_id.isascii()
            and platform_content_id.isdigit()
            and _WB_CONTENT_PATH.fullmatch(parsed.path) is not None
            and value == f"https://m.weibo.cn/detail/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "m.weibo.cn"
            and port is None
            and parsed.query == ""
        )

    if platform == "ks":
        match = _KS_CONTENT_PATH.fullmatch(parsed.path)
        return (
            match is not None
            and match.group(1) == platform_content_id
            and value == f"https://www.kuaishou.com/short-video/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "www.kuaishou.com"
            and port is None
            and parsed.query == ""
        )
    if platform == "dy":
        return (
            platform_content_id.isascii()
            and platform_content_id.isdigit()
            and _DY_CONTENT_PATH.fullmatch(parsed.path) is not None
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
            and all(c in "0123456789abcdef" for c in platform_content_id)
            and _XHS_CONTENT_PATH.fullmatch(parsed.path) is not None
            and value == f"https://www.xiaohongshu.com/explore/{platform_content_id}"
            and parsed.scheme == "https"
            and hostname == "www.xiaohongshu.com"
            and port is None
            and parsed.query == ""
        )
    return False
