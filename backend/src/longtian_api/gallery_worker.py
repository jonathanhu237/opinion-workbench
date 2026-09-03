"""Isolated gallery-dl parser process: no credentials, config, cache or HTTP.

Only the parent can satisfy a requested lookup. The pinned upstream extractor
is used unchanged; these per-instance public boundaries replace its transport
and configuration. Never invoke the downloader/job/user-feed CLI here.
"""

import json
import logging
import sys
from types import SimpleNamespace

FRAME_LIMIT = 2 * 1024 * 1024


def emit(message):
    payload = json.dumps(message, ensure_ascii=True, separators=(",", ":"))
    if len(payload) > FRAME_LIMIT:
        raise ValueError("frame limit")
    print(payload, flush=True)


def receive():
    line = sys.stdin.buffer.readline(FRAME_LIMIT + 1)
    if not line.endswith(b"\n") or len(line) > FRAME_LIMIT:
        raise ValueError("invalid frame")
    return json.loads(line)


def main():
    from importlib.metadata import version

    from gallery_dl import exception
    from gallery_dl.extractor.message import Message
    from gallery_dl.extractor.weibo import WeiboStatusExtractor
    from requests.cookies import RequestsCookieJar

    try:
        if version("gallery-dl") != "1.32.10":
            raise ValueError("unreviewed parser version")
        identity = receive()["content_id"]
        if (
            not isinstance(identity, str)
            or not identity.isascii()
            or not identity.isdigit()
        ):
            raise ValueError("invalid identity")
        extractor = WeiboStatusExtractor.from_url(
            f"https://m.weibo.cn/detail/{identity}"
        )
        options = {
            "text": True,
            "retweets": True,
            "videos": True,
            "movies": True,
            "livephoto": False,
            "retries": 0,
            "proxy-env": False,
            "write-pages": False,
            "input": False,
            "netrc": False,
        }
        extractor.config = lambda key, default=None: options.get(key, default)
        extractor.cache = lambda *args, **kwargs: None
        extractor.session = SimpleNamespace(cookies=RequestsCookieJar())
        extractor.log = logging.Logger("isolated-weibo-parser", level=logging.CRITICAL)

        def request(url, **kwargs):
            if kwargs.get("method", "GET") != "GET":
                # Optional live-video location probing is outside this component.
                raise exception.HttpError("unsupported lookup")
            emit({"kind": "request", "url": url})
            reply = receive()
            if reply.get("kind") != "response":
                raise ValueError("lookup rejected")
            return SimpleNamespace(text=json.dumps(reply["body"]))

        extractor.request = request
        post, files = None, []
        for kind, url, metadata in extractor:
            if kind == Message.Directory:
                if post is not None:
                    raise ValueError("unexpected second post")
                # Source dictionaries contain details the product does not need.
                post = {
                    key: value
                    for key, value in metadata.items()
                    if key
                    in {
                        "id",
                        "idstr",
                        "text",
                        "text_raw",
                        "isLongText",
                        "longText",
                        "pic_ids",
                        "pic_infos",
                        "page_info",
                        "mix_media_info",
                        "retweeted_status",
                        "count",
                    }
                }
            elif kind == Message.Url:
                files.append(
                    {
                        "url": url,
                        "metadata": {
                            key: value
                            for key, value in metadata.items()
                            if key not in ("status", "user", "date")
                        },
                    }
                )
            else:
                raise ValueError("recursive extraction is not supported")
            if len(files) > 128:
                raise ValueError("inventory limit")
        if post is None:
            raise exception.NotFoundError("status")
        emit({"kind": "result", "post": post, "files": files})
    except exception.NotFoundError:
        emit({"kind": "error", "code": "content_unavailable"})
    except Exception:
        # Never forward exception text, platform payloads or parser logs.
        emit({"kind": "error", "code": "parser_failed"})


if __name__ == "__main__":
    main()
