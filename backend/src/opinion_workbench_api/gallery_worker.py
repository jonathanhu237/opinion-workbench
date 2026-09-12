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
from urllib.parse import urljoin, urlsplit

FRAME_LIMIT = 12 * 1024 * 1024
MAX_MEDIA_BYTES = 6 * 1024 * 1024
MAX_MEDIA_COUNT = 128
MEDIA_HOSTS = ("sinaimg.cn", "weibocdn.com")


def media_kind(metadata):
    extension = str(metadata.get("extension", "")).lower()
    if extension in ("jpg", "jpeg", "png", "webp", "gif"):
        return "image"
    if extension in ("mp4", "mov", "m3u8", "webm"):
        return "video"
    return None


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


def _normalize_timeout(value):
    if value is None:
        return None
    if type(value) in (int, float):
        value = float(value)
        if 0 < value <= 120:
            return value
        raise ValueError("invalid timeout")
    if isinstance(value, (tuple, list)) and len(value) == 2:
        normalized = []
        for item in value:
            if item is None:
                normalized.append(None)
                continue
            if type(item) not in (int, float) or not 0 < float(item) <= 120:
                raise ValueError("invalid timeout")
            normalized.append(float(item))
        return normalized
    raise ValueError("invalid timeout")


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
        stream = kwargs.pop("stream", False)
        timeout = kwargs.pop("timeout", None)
        verify = kwargs.pop("verify", True)
        proxies = kwargs.pop("proxies", None)
        allow_redirects = kwargs.pop("allow_redirects", True)
        if type(stream) is not bool or type(allow_redirects) is not bool:
            raise ValueError("invalid request options")
        if type(verify) is not bool or not verify:
            raise ValueError("unsupported TLS options")
        if proxies not in (None, {}):
            raise ValueError("unsupported proxy options")
        timeout = _normalize_timeout(timeout)
        request = requests.Request(
            method=method,
            url=url,
            headers=kwargs.pop("headers", None),
            data=kwargs.pop("data", None),
            json=kwargs.pop("json", None),
            params=kwargs.pop("params", None),
            cookies=kwargs.pop("cookies", None),
        )
        if kwargs:
            raise ValueError("unsupported request options")
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
                "allow_redirects": allow_redirects,
                "stream": stream,
                "timeout": timeout,
                "verify": verify,
                "proxies": {},
            }
        )
        response = BridgeResponse(receive())
        response.request = prepared
        self.last_response = response
        if self.stage == "media":
            self.media_bytes += len(response.content)
            if response.headers.get("x-opinion-workbench-error") == "media_limit":
                self.media_bytes = self.max_media_bytes
        # Only account cookies explicitly issued by the Weibo account host.
        # CDN and unrelated response cookies must never become future account
        # credentials, even if the upstream response exposes them.
        if host == "weibo.com" or host.endswith(".weibo.com"):
            for cookie in response.cookies:
                if cookie.name in ("SUB", "SUBP"):
                    self.cookies.set(
                        cookie.name,
                        cookie.value,
                        domain=".weibo.com",
                        path="/",
                    )
        return response


def _challenge_from_response(response):
    if response is None:
        return None
    from gallery_dl import util

    if util.detect_challenge(response):
        return "manual_challenge_required"
    raw = response.content[: 256 * 1024]
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    if content_type.strip().lower() == "application/json":
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            payload = None
        if isinstance(payload, dict):
            body = " ".join(
                str(payload.get(key, ""))
                for key in ("msg", "message", "error", "reason", "code")
            ).lower()
        else:
            body = ""
    else:
        body = raw.decode("utf-8", errors="ignore").lower()
    headers = " ".join(
        f"{key}:{value}"
        for key, value in response.headers.items()
        if key.lower() not in {"location", "set-cookie", "content-location"}
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


def _trusted_redirect_kind(url):
    """Classify only known platform authentication/verification destinations."""

    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
    ):
        return None
    path = parts.path.lower()
    if host in {"passport.weibo.com", "passport.weibo.cn", "login.sina.com.cn"}:
        return "login"
    if host in {"security.weibo.com", "security.weibo.cn"}:
        return "challenge"
    if host in {"weibo.com", "www.weibo.com", "m.weibo.cn"} and (
        path == "/login" or path.startswith("/login/")
    ):
        return "login"
    return None


def _redirect_kind(response):
    if response is None:
        return None
    targets = []
    for item in response.history:
        if item.url:
            targets.append(item.url)
    location = response.headers.get("location")
    if location:
        targets.append(urljoin(response.url, location))
    for target in targets:
        kind = _trusted_redirect_kind(target)
        if kind is not None:
            return kind
    return None


def _classify_response(response, *, stage):
    if response is None:
        return "parser_failed"
    if response.headers.get("x-opinion-workbench-error") == "media_limit":
        return "media_limit"
    status = response.status_code
    if status == 429:
        return "platform_blocked_or_rate_limited"
    if status == 401:
        return "login_required"
    if status == 403:
        return _challenge_from_response(response) or (
            "manual_challenge_required"
            if _redirect_kind(response) == "challenge"
            else "access_denied"
        )
    redirect_kind = _redirect_kind(response)
    if redirect_kind == "login":
        return "login_required"
    if redirect_kind == "challenge":
        return "manual_challenge_required"
    if 300 <= status < 400:
        return "media_redirect" if stage == "media" else "access_denied"
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
    if response.history and any(
        _trusted_redirect_kind(item.url) == "login" for item in response.history
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


def _classification_basis(response, *, code):
    if response is None:
        return "upstream_exception"
    if code == "manual_challenge_required":
        return "explicit_platform_evidence"
    if code == "login_required" and _redirect_kind(response) == "login":
        return "login_redirect"
    if code in ("content_unavailable", "asset_unavailable", "structure_changed"):
        return "platform_payload" if response.status_code == 200 else "http_status"
    if response.status_code >= 300:
        return "http_status"
    return "upstream_exception"


def _diagnostic_payload(
    *, stage, outcome, response=None, basis=None, asset_position=None
):
    return {
        "stage": stage,
        "outcome": outcome,
        "status_code": response.status_code if response is not None else None,
        "basis": basis or _classification_basis(response, code=outcome),
        "asset_position": asset_position,
        "target": "media_asset" if stage == "media" else "selected_post",
    }


def _diagnostic_outcome(code):
    return {
        "access_denied": "access_denied",
        "asset_blocked": "access_denied",
        "asset_unavailable": "asset_unavailable",
        "media_limit": "media_limit",
        "media_redirect": "media_redirect",
        "login_required": "login_required",
        "manual_challenge_required": "manual_challenge_required",
        "platform_blocked_or_rate_limited": "platform_blocked_or_rate_limited",
        "content_unavailable": "content_unavailable",
        "structure_changed": "structure_changed",
    }.get(code, "parser_failed")


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

    def __init__(
        self,
        extractor,
        tempdir,
        emit_media,
        session,
        *,
        max_images=24,
        max_videos=1,
        text_only=False,
    ):
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
        self.pause_diagnostic = None
        self.max_images = max_images
        self.max_videos = max_videos
        self.text_only = text_only
        self._media_counts = {"image": 0, "video": 0}

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

    def _init_job(self):
        self._configure()
        self._job._init()

    def run(self):
        self._init_job()
        self._job.dispatch(self._job.extractor)

    def run_files(self, post, files):
        """Run the upstream downloader for files already extracted earlier.

        A paused report must not perform a second detail lookup.  Feeding the
        original post metadata and only the unfinished files through the same
        gallery-dl ``DownloadJob`` preserves the upstream downloader/session
        semantics while keeping resume work scoped to the pending assets.
        """
        from gallery_dl.extractor.message import Message

        self._init_job()
        directory = _filtered_post(post)

        def messages():
            yield Message.Directory, "", directory
            for index, item in enumerate(files, 1):
                metadata = dict(item.get("metadata") or {})
                metadata.setdefault("num", index)
                metadata["status"] = directory
                yield Message.Url, item["url"], metadata

        self._job.dispatch(messages())

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
        if self.text_only:
            # Text-only analysis still needs the extractor's post metadata, but
            # must never invoke DownloadJob.download or request a media URL.
            return
        kind = media_kind(metadata)
        if kind is not None:
            self._media_counts[kind] += 1
            limit = self.max_images if kind == "image" else self.max_videos
            if self._media_counts[kind] > limit:
                self._emit_media(
                    position=position,
                    status="unavailable",
                    issue_code="media_limit",
                    diagnostic=_diagnostic_payload(
                        stage="media",
                        outcome="media_limit",
                        asset_position=position,
                    ),
                )
                return
        if self.pause_reason is not None:
            diagnostic = self.pause_diagnostic
            if isinstance(diagnostic, dict):
                diagnostic = {
                    **diagnostic,
                    "asset_position": position,
                    "target": "media_asset",
                }
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="asset_blocked",
                diagnostic=diagnostic,
            )
            return
        if url.startswith("ytdl:"):
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="unsupported_transport",
                diagnostic=_diagnostic_payload(
                    stage="media",
                    outcome="parser_failed",
                    basis="upstream_exception",
                    asset_position=position,
                ),
            )
            return
        if self._session.media_bytes >= self._session.max_media_bytes:
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="media_limit",
                diagnostic=_diagnostic_payload(
                    stage="media",
                    outcome="media_limit",
                    asset_position=position,
                ),
            )
            return
        if not allowed_media_url(url):
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code="unsafe_media_url",
                diagnostic=_diagnostic_payload(
                    stage="media",
                    outcome="parser_failed",
                    basis="upstream_exception",
                    asset_position=position,
                ),
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
                        diagnostic=_diagnostic_payload(
                            stage="media",
                            outcome="media_limit",
                            response=self._session.last_response,
                            asset_position=position,
                        ),
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
            diagnostic = _diagnostic_payload(
                stage="media",
                outcome=_diagnostic_outcome(reason),
                response=response,
                asset_position=position,
            )
            if reason in (
                "login_required",
                "manual_challenge_required",
                "platform_blocked_or_rate_limited",
            ):
                self.pause_reason = reason
                self.pause_diagnostic = _diagnostic_payload(
                    stage="media",
                    outcome=reason,
                    response=response,
                    asset_position=position,
                )
            self._emit_media(
                position=position,
                status="unavailable",
                issue_code=_media_issue(reason),
                diagnostic=diagnostic,
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


def _upstream_context(identity, startup):
    from importlib.metadata import version

    from gallery_dl.extractor.weibo import WeiboStatusExtractor

    if version("gallery-dl") != "1.32.10":
        raise ValueError("unreviewed parser version")
    cookies = startup.get("cookies")
    if not isinstance(cookies, dict):
        raise ValueError("invalid credentials")
    max_media_bytes = startup.get("max_media_bytes", MAX_MEDIA_BYTES)
    if type(max_media_bytes) is not int or not 1 <= max_media_bytes <= MAX_MEDIA_BYTES:
        raise ValueError("invalid media budget")
    max_images = startup.get("max_images", 24)
    max_videos = startup.get("max_videos", 1)
    if type(max_images) is not int or not 1 <= max_images <= 24:
        raise ValueError("invalid image budget")
    if type(max_videos) is not int or max_videos != 1:
        raise ValueError("invalid video budget")

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
    return extractor, bridge, max_media_bytes, max_images, max_videos


def _media_resume_input(identity, startup):
    post = startup.get("post")
    files = startup.get("files")
    if (
        not isinstance(post, dict)
        or str(post.get("idstr", post.get("id"))) != identity
        or not isinstance(files, list)
        or len(files) > MAX_MEDIA_COUNT
    ):
        raise ValueError("invalid resume input")
    checked = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("invalid resume input")
        url = item.get("url")
        metadata = item.get("metadata")
        if not isinstance(url, str) or len(url) > 4096:
            raise ValueError("invalid resume input")
        if not isinstance(metadata, dict):
            metadata = {}
        safe = {}
        for key in ("extension", "filename", "num", "width", "height"):
            value = metadata.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
        number = safe.get("num")
        if type(number) is not int or not 1 <= number <= MAX_MEDIA_COUNT:
            raise ValueError("invalid resume input")
        checked.append({"url": url, "metadata": safe})
    return post, checked


def _run_upstream(identity, startup):
    from gallery_dl import exception

    mode = startup.get("mode", "upstream")
    resume_post = resume_files = None
    if mode == "upstream_media":
        resume_post, resume_files = _media_resume_input(identity, startup)
    elif mode not in ("upstream", "text_only"):
        raise ValueError("invalid mode")
    (
        extractor,
        bridge,
        max_media_bytes,
        max_images,
        max_videos,
    ) = _upstream_context(identity, startup)

    tempdir = tempfile.mkdtemp(prefix="opinion-workbench-gallery-")
    try:

        def emit_media(
            *,
            position,
            status,
            issue_code=None,
            data=None,
            mime_type=None,
            diagnostic=None,
        ):
            message = {
                "kind": "media",
                "position": position,
                "status": status,
                "issue_code": issue_code,
            }
            if diagnostic is not None:
                message["diagnostic"] = diagnostic
            if status == "ready":
                message["data"] = base64.b64encode(data).decode("ascii")
                message["mime_type"] = mime_type
            emit(message)

        capture = CaptureJob(
            extractor,
            tempdir,
            emit_media,
            bridge,
            max_images=max_images,
            max_videos=max_videos,
            text_only=mode == "text_only",
        )
        try:
            if mode == "upstream_media":
                capture.run_files(resume_post, resume_files)
            else:
                capture.run()
        except exception.NotFoundError:
            response = bridge.last_response
            stage = "media" if mode == "upstream_media" else "detail"
            code = (
                _classify_response(response, stage=stage)
                if response is not None
                else (
                    "asset_unavailable" if stage == "media" else "content_unavailable"
                )
            )
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "status_code": response.status_code if response else None,
                    "stage": stage,
                    "basis": _classification_basis(response, code=code),
                    "asset_position": bridge.media_index if stage == "media" else None,
                }
            )
            return
        except exception.GalleryDLException as error:
            response = getattr(error, "response", None) or bridge.last_response
            stage = "media" if mode == "upstream_media" else "detail"
            code = _classify_response(response, stage=stage)
            if isinstance(error, exception.ChallengeError):
                code = "manual_challenge_required"
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "status_code": response.status_code if response else None,
                    "stage": stage,
                    "basis": _classification_basis(response, code=code),
                    "asset_position": bridge.media_index if stage == "media" else None,
                }
            )
            return
        except Exception:
            response = bridge.last_response
            stage = "media" if mode == "upstream_media" else "detail"
            code = (
                _classify_response(response, stage=stage)
                if response
                else "parser_failed"
            )
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "status_code": response.status_code if response else None,
                    "stage": stage,
                    "basis": _classification_basis(response, code=code),
                    "asset_position": bridge.media_index if stage == "media" else None,
                }
            )
            return
        if capture.post is None:
            code = (
                "asset_unavailable"
                if mode == "upstream_media"
                else "content_unavailable"
            )
            emit(
                {
                    "kind": "error",
                    "code": code,
                    "stage": "media" if mode == "upstream_media" else "detail",
                    "basis": "upstream_exception",
                }
            )
            return
        emit(
            {
                "kind": "result",
                "post": capture.post,
                "files": capture.files,
                "pause_reason": capture.pause_reason,
                "diagnostic": capture.pause_diagnostic,
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
        if startup.get("mode", "upstream") not in (
            "upstream",
            "upstream_media",
            "text_only",
        ):
            raise ValueError("invalid mode")
        _run_upstream(identity, startup)
    except Exception:
        # Never forward exception text, platform payloads or parser logs.
        try:
            emit({"kind": "error", "code": "parser_failed"})
        except Exception:
            pass


if __name__ == "__main__":
    main()
