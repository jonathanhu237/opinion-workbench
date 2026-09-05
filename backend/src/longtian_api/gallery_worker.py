"""Run the pinned gallery-dl Weibo extractor behind a small IO broker.

The process deliberately has no access to the application's HTTP client or
filesystem. It receives the dedicated-session cookies in memory, asks the
parent process to perform every request, and returns bounded post/media
material. gallery-dl still owns request preparation, extraction and its HTTP
downloader; the parent owns credentials, network policy and persistence.
"""

import base64
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

FRAME_LIMIT = 12 * 1024 * 1024
MAX_MEDIA_BYTES = 6 * 1024 * 1024
MAX_MEDIA_COUNT = 128
MEDIA_HOSTS = ("sinaimg.cn", "weibocdn.com")


def emit(message):
    payload = json.dumps(message, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > FRAME_LIMIT:
        raise ValueError("frame limit")
    print(payload, flush=True)


def receive():
    line = sys.stdin.buffer.readline(FRAME_LIMIT + 1)
    if not line.endswith(b"\n") or len(line) > FRAME_LIMIT:
        raise ValueError("invalid frame")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("invalid message")
    return value


def allowed_media_url(url):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return (
            parts.scheme == "https"
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and not parts.fragment
            and "\\" not in url
            and len(url) <= 4096
            and not any(ord(char) <= 32 for char in url)
            and any(
                host == suffix or host.endswith("." + suffix) for suffix in MEDIA_HOSTS
            )
        )
    except ValueError:
        return False


def _body_from_reply(reply):
    if reply.get("kind") != "response":
        raise ValueError("request rejected")
    body = reply.get("body")
    if not isinstance(body, dict):
        raise ValueError("invalid response body")
    encoding = body.get("encoding")
    value = body.get("value")
    if encoding == "json":
        return value
    if encoding == "base64" and isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, base64.binascii.Error):
            pass
    raise ValueError("invalid response body")


class BridgeHistory:
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url


def _reason(status):
    return {
        200: "OK",
        206: "Partial Content",
        301: "Moved Permanently",
        302: "Found",
        303: "See Other",
        307: "Temporary Redirect",
        308: "Permanent Redirect",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        410: "Gone",
        413: "Payload Too Large",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }.get(status, "HTTP Error")


class BridgeResponse:
    """The small requests.Response surface used by gallery-dl."""

    def __init__(self, reply):
        from requests.cookies import RequestsCookieJar
        from requests.structures import CaseInsensitiveDict

        self.status_code = int(reply.get("status_code", 0))
        self.url = str(reply.get("url", ""))
        self.headers = CaseInsensitiveDict(reply.get("headers") or {})
        self._body = _body_from_reply(reply)
        self.history = [
            BridgeHistory(item.get("status_code", 0), item.get("url", ""))
            for item in (reply.get("history") or [])
            if isinstance(item, dict)
        ]
        self.cookies = RequestsCookieJar()
        for name, value in (reply.get("cookies") or {}).items():
            self.cookies.set(name, value)
        self.encoding = None
        self.raw = SimpleNamespace(chunked=False)
        self.reason = _reason(self.status_code)
        self.request = None
        self._offset = 0

    @property
    def content(self):
        if isinstance(self._body, bytes):
            return self._body
        return json.dumps(self._body, ensure_ascii=False).encode("utf-8")

    @property
    def text(self):
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    @property
    def is_permanent_redirect(self):
        return self.status_code in (301, 308)

    def json(self):
        if isinstance(self._body, bytes):
            return json.loads(self._body)
        return self._body

    def iter_content(self, chunk_size=32768, **_kwargs):
        data = self.content
        size = max(1, int(chunk_size or len(data) or 1))
        while self._offset < len(data):
            offset = self._offset
            self._offset += size
            yield data[offset : offset + size]

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class BridgeSession:
    """A requests-compatible session whose network calls go to the parent."""

    def __init__(self, cookies, headers, max_media_bytes):
        import requests
        from requests.cookies import RequestsCookieJar

        self._session = requests.Session()
        self.headers = requests.structures.CaseInsensitiveDict(headers)
        self.cookies = RequestsCookieJar()
        for name, value in cookies.items():
            if isinstance(name, str) and isinstance(value, str):
                self.cookies.set(name, value, domain=".weibo.com", path="/")
        self.stage = "detail"
        self.media_index = None
        self.last_response = None
        self.media_bytes = 0
        self.max_media_bytes = max_media_bytes

    def prepare_request(self, request):
        self._session.headers = self.headers
        self._session.cookies = self.cookies
        return self._session.prepare_request(request)

    def request(self, method, url, **kwargs):
        import requests

        # Let requests merge session defaults, cookies, params and body before
        # handing the exact prepared request to the owning application.
        request = requests.Request(
            method=method,
            url=url,
            headers=kwargs.pop("headers", None),
            data=kwargs.pop("data", None),
            json=kwargs.pop("json", None),
            params=kwargs.pop("params", None),
            cookies=kwargs.pop("cookies", None),
        )
        prepared = self.prepare_request(request)
        headers = dict(prepared.headers)
        host = (urlsplit(prepared.url).hostname or "").lower()
        if not (host == "weibo.com" or host.endswith(".weibo.com")):
            headers.pop("Cookie", None)
            headers.pop("cookie", None)
        body = prepared.body
        if body is not None and not isinstance(body, bytes):
            body = str(body).encode("utf-8")
        emit(
            {
                "kind": "request",
                "stage": self.stage,
                "media_index": self.media_index,
                "method": prepared.method,
                "url": prepared.url,
                "headers": headers,
                "body": base64.b64encode(body).decode("ascii") if body else None,
                "allow_redirects": bool(kwargs.pop("allow_redirects", True)),
            }
        )
        response = BridgeResponse(receive())
        response.request = prepared
        self.last_response = response
        if self.stage == "media":
            self.media_bytes += len(response.content)
            if response.headers.get("x-longtian-error") == "media_limit":
                self.media_bytes = self.max_media_bytes
        self.cookies.update(response.cookies)
        return response


def _challenge_from_response(response):
    if response is None:
        return None
    from gallery_dl import util

    if util.detect_challenge(response):
        return "manual_challenge_required"
    body = response.content[: 256 * 1024].decode("utf-8", errors="ignore").lower()
    headers = " ".join(
        f"{key}:{value}" for key, value in response.headers.items()
    ).lower()
    evidence = body + " " + headers
    if any(
        word in evidence
        for word in (
            "安全验证",
            "请完成验证",
            "滑动验证",
            "拖动滑块",
            "验证码",
            "captcha",
            "challenge",
            "异常访问",
            "访问异常",
        )
    ):
        return "manual_challenge_required"
    return None


def _classify_response(response, *, stage):
    if response is None:
        return "parser_failed"
    if response.headers.get("x-longtian-error") == "media_limit":
        return "media_limit"
    status = response.status_code
    if status == 429:
        return "platform_blocked_or_rate_limited"
    if status == 401:
        return "login_required"
    if status == 403:
        return _challenge_from_response(response) or "access_denied"
    if stage == "detail" and status == 200:
        try:
            payload = response.json()
        except (ValueError, TypeError, UnicodeError):
            payload = None
        if isinstance(payload, dict):
            if payload.get("ok") == 0:
                message = str(payload.get("msg") or payload.get("message") or "")
                if any(word in message for word in ("不存在", "已删除", "找不到")):
                    return "content_unavailable"
                if any(word in message for word in ("登录", "登陆", "login")):
                    return "login_required"
                if any(word in message for word in ("频繁", "频次", "限流")):
                    return "platform_blocked_or_rate_limited"
                if any(word in message for word in ("验证", "验证码", "异常访问")):
                    return "manual_challenge_required"
            if "ok" not in payload:
                return "structure_changed"
            if payload.get("ok") == 1:
                return "content_unavailable"
    if response.history:
        urls = [item.url for item in response.history] + [response.url]
        if any(
            "login.sina.com" in url
            or "passport.weibo.com" in url
            or "/login" in url.lower()
            for url in urls
        ):
            return "login_required"
    if stage == "detail" and status in (404, 410):
        return "content_unavailable"
    if stage == "media" and status in (404, 410):
        return "asset_unavailable"
    if stage == "media" and 300 <= status < 400:
        return "media_redirect"
    if 300 <= status < 400:
        return "access_denied"
    return "parser_failed"


def _filtered_post(metadata):
    return {
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
            "created_at",
        }
    }


class CaptureJob:
    """DownloadJob adapter that captures upstream files in memory."""

    def __init__(self, extractor, tempdir, emit_media, session):
        from gallery_dl.job import DownloadJob

        class _Job(DownloadJob):
            pass

        self._job = _Job(extractor)
        self._job.handle_directory = self.handle_directory
        self._job.handle_url = self.handle_url
        self._tempdir = tempdir
        self._emit_media = emit_media
        self._session = session
        self.post = None
        self.files = []
        self.pause_reason = None

    @property
    def extractor(self):
        return self._job.extractor

    def _configure(self):
        extractor = self.extractor
        options = {
            "base-directory": self._tempdir,
            "directory": (),
            "filename": "{status[id]}_{num:>02}.{extension}",
            "part": False,
            "postprocess": False,
            "progress": None,
            "retries": 0,
            "download": True,
            "skip": False,
        }
        previous = extractor.config
        extractor.config = lambda key, default=None: options.get(
            key, previous(key, default)
        )

    def run(self):
        self._configure()
        self._job._init()
        self._job.dispatch(self._job.extractor)

    def handle_directory(self, metadata):
        if self.post is not None:
            raise ValueError("unexpected second post")
        self.post = _filtered_post(metadata)
        from gallery_dl import path

        if self._job.pathfmt is None:
            self._job.pathfmt = path.PathFormat(self.extractor)
        self._job.pathfmt.set_directory(metadata)

    def handle_url(self, url, metadata):
        position = int(metadata.get("num", len(self.files) + 1)) - 1
        if position < 0 or position >= MAX_MEDIA_COUNT:
            raise ValueError("inventory limit")
        self.files.append(
            {
                "url": url,
                "metadata": {
                    key: value
                    for key, value in metadata.items()
                    if key in ("extension", "filename", "num", "width", "height")
                    and isinstance(value, (str, int, float, bool, type(None)))
                },
            }
        )
        if self.pause_reason is not None:
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="asset_blocked",
            )
            return
        if url.startswith("ytdl:"):
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="unsupported_transport",
            )
            return
        if self._session.media_bytes >= self._session.max_media_bytes:
            self._emit_media(
                position=position, status="unavailable", issue_code="media_limit"
            )
            return
        if not allowed_media_url(url):
            self._emit_media(
                position=position, status="unavailable", issue_code="unsafe_media_url"
            )
            return

        self._session.stage = "media"
        self._session.media_index = position
        self._job.pathfmt.set_filename(metadata)
        self._job.pathfmt.build_path()
        try:
            ok = self._job.download(url)
            path = Path(self._job.pathfmt.temppath)
            if ok and path.is_file():
                data = path.read_bytes()
                if not 0 < len(data) <= MAX_MEDIA_BYTES:
                    self._emit_media(
                        position=position,
                        status="unavailable",
                        issue_code="media_limit",
                    )
                else:
                    self._emit_media(
                        position=position,
                        status="ready",
                        data=data,
                        mime_type=_mime_for(metadata, self._session.last_response),
                    )
                path.unlink(missing_ok=True)
                return
            response = self._session.last_response
            reason = _classify_response(response, stage="media")
            if response is not None and response.status_code == 200:
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                extension = str(metadata.get("extension", "")).lower()
                accepted = (
                    {"image/png", "image/jpeg", "image/webp"}
                    if extension in {"png", "jpg", "jpeg", "webp", "gif"}
                    else {"video/mp4"}
                )
                if content_type not in accepted:
                    reason = "unsupported_media_type"
                elif reason == "parser_failed":
                    reason = "invalid_media"
            if reason in (
                "login_required",
                "manual_challenge_required",
                "platform_blocked_or_rate_limited",
            ):
                self.pause_reason = reason
            self._emit_media(
                position=position, status="unavailable", issue_code=_media_issue(reason)
            )
            path.unlink(missing_ok=True)
        finally:
            self._session.stage = "detail"
            self._session.media_index = None


def _mime_for(metadata, response):
    if response is not None:
        value = (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if value:
            return value
    extension = str(metadata.get("extension", "")).lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "mp4": "video/mp4",
    }.get(extension, "application/octet-stream")


def _media_issue(reason):
    return {
        "login_required": "asset_blocked",
        "manual_challenge_required": "asset_blocked",
        "platform_blocked_or_rate_limited": "asset_blocked",
        "asset_unavailable": "asset_unavailable",
        "media_redirect": "media_redirect",
        "invalid_media": "invalid_media",
        "unsupported_media_type": "unsupported_media_type",
        "media_limit": "media_limit",
        "access_denied": "asset_blocked",
    }.get(reason, "download_failed")


def _run_legacy(identity):
    from gallery_dl import exception
    from gallery_dl.extractor.message import Message
    from gallery_dl.extractor.weibo import WeiboStatusExtractor
    from requests.cookies import RequestsCookieJar

    extractor = WeiboStatusExtractor.from_url(f"https://m.weibo.cn/detail/{identity}")
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
            raise exception.HttpError("unsupported lookup")
        emit({"kind": "request", "url": url})
        reply = receive()
        if reply.get("kind") != "response":
            raise ValueError("lookup rejected")
        return SimpleNamespace(text=json.dumps(_body_from_reply(reply)))

    extractor.request = request
    post, files = None, []
    for kind, url, metadata in extractor:
        if kind == Message.Directory:
            if post is not None:
                raise ValueError("unexpected second post")
            post = _filtered_post(metadata)
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
        if len(files) > MAX_MEDIA_COUNT:
            raise ValueError("inventory limit")
    if post is None:
        raise exception.NotFoundError("status")
    emit({"kind": "result", "post": post, "files": files})


def _run_upstream(identity, startup):
    from importlib.metadata import version

    from gallery_dl import exception
    from gallery_dl.extractor.weibo import WeiboStatusExtractor

    if version("gallery-dl") != "1.32.10":
        raise ValueError("unreviewed parser version")
    cookies = startup.get("cookies")
    if not isinstance(cookies, dict):
        raise ValueError("invalid credentials")
    max_media_bytes = startup.get("max_media_bytes", MAX_MEDIA_BYTES)
    if type(max_media_bytes) is not int or not 1 <= max_media_bytes <= MAX_MEDIA_BYTES:
        raise ValueError("invalid media budget")

    extractor = WeiboStatusExtractor.from_url(f"https://m.weibo.cn/detail/{identity}")
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
        "browser": "firefox",
    }
    extractor.config = lambda key, default=None: options.get(key, default)
    extractor.cache = lambda *args, **kwargs: None
    extractor._init_options()
    extractor._init_session()
    defaults = dict(extractor.session.headers)
    bridge = BridgeSession(cookies, defaults, max_media_bytes)
    extractor.session = bridge
    extractor.cookies = bridge.cookies
    extractor.log = logging.Logger("isolated-weibo-acquisition", level=logging.CRITICAL)

    tempdir = tempfile.mkdtemp(prefix="longtian-gallery-")
    try:

        def emit_media(*, position, status, issue_code=None, data=None, mime_type=None):
            message = {
                "kind": "media",
                "position": position,
                "status": status,
                "issue_code": issue_code,
            }
            if status == "ready":
                message["data"] = base64.b64encode(data).decode("ascii")
                message["mime_type"] = mime_type
            emit(message)

        capture = CaptureJob(extractor, tempdir, emit_media, bridge)
        try:
            capture.run()
        except exception.NotFoundError:
            response = bridge.last_response
            emit(
                {
                    "kind": "error",
                    "code": _classify_response(response, stage="detail")
                    if response is not None
                    else "content_unavailable",
                    "status_code": response.status_code if response else None,
                    "stage": "detail",
                }
            )
            return
        except exception.GalleryDLException as error:
            response = getattr(error, "response", None) or bridge.last_response
            code = _classify_response(response, stage="detail")
            if isinstance(error, exception.ChallengeError):
                code = "manual_challenge_required"
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "status_code": response.status_code if response else None,
                    "stage": "detail",
                }
            )
            return
        except Exception:
            response = bridge.last_response
            code = (
                _classify_response(response, stage="detail")
                if response
                else "parser_failed"
            )
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "status_code": response.status_code if response else None,
                    "stage": "detail",
                }
            )
            return
        if capture.post is None:
            emit({"kind": "error", "code": "content_unavailable", "stage": "detail"})
            return
        emit(
            {
                "kind": "result",
                "post": capture.post,
                "files": capture.files,
                "pause_reason": capture.pause_reason,
            }
        )
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def main():
    try:
        startup = receive()
        identity = startup.get("content_id")
        if (
            not isinstance(identity, str)
            or not identity.isascii()
            or not identity.isdigit()
        ):
            raise ValueError("invalid identity")
        if startup.get("mode", "legacy") == "upstream":
            _run_upstream(identity, startup)
        else:
            _run_legacy(identity)
    except Exception:
        # Never forward exception text, platform payloads or parser logs.
        try:
            emit({"kind": "error", "code": "parser_failed"})
        except Exception:
            pass


if __name__ == "__main__":
    main()
