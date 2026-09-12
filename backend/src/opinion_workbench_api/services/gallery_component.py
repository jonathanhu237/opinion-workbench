"""A bounded adapter around the pinned gallery-dl Weibo extractor.

The upstream extractor owns request construction and media download.  The
parent process owns the network boundary, credentials, budgets and result
handoff.  Every product request uses the same brokered acquisition protocol;
there is no parser-only fallback that can silently drop upstream request
options.
"""

import asyncio
import base64
import inspect
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from opinion_workbench_api.services.enrichment_models import MAX_MEDIA_BYTES
from opinion_workbench_api.services.settled_tasks import settle

FRAME_LIMIT = 12 * 1024 * 1024
_MAX_REQUESTS = 64
_MAX_RESPONSE_HEADERS = 32
_HEADER_NAMES = frozenset(
    {
        "content-disposition",
        "content-length",
        "content-range",
        "content-type",
        "last-modified",
        "location",
        "server",
        "set-cookie",
        "cf-mitigated",
        "x-opinion-workbench-error",
    }
)
_MEDIA_HOSTS = ("sinaimg.cn", "weibocdn.com")
_WORKER_ENVIRONMENT_KEYS = ("SystemRoot", "WINDIR", "TEMP", "TMP")


@dataclass(frozen=True, slots=True)
class UpstreamRequest:
    stage: Literal["detail", "media"]
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = field(default=None, repr=False)
    allow_redirects: bool = True
    media_index: int | None = None
    stream: bool = True
    timeout: object = field(default=None, repr=False)
    verify: bool = True
    proxies: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class UpstreamResponse:
    status_code: int
    url: str
    headers: Mapping[str, str]
    body: object = field(repr=False)
    history: tuple[tuple[int, str], ...] = ()
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)


class ComponentError(Exception):
    def __init__(
        self,
        code,
        *,
        status_code: int | None = None,
        stage=None,
        basis=None,
        asset_position=None,
    ):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.stage = stage
        self.basis = basis
        self.asset_position = asset_position


def _json_body(value):
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return {"encoding": "json", "value": value}
    if isinstance(value, bytes):
        return {
            "encoding": "base64",
            "value": base64.b64encode(value).decode("ascii"),
        }
    raise ComponentError("invalid_response")


def _response_payload(value: UpstreamResponse):
    if type(value.status_code) is not int or not 100 <= value.status_code <= 599:
        raise ComponentError("invalid_response")
    if not isinstance(value.url, str) or len(value.url) > 4096:
        raise ComponentError("invalid_response")
    headers = {}
    for key, item in value.headers.items():
        if (
            len(headers) >= _MAX_RESPONSE_HEADERS
            or not isinstance(key, str)
            or not isinstance(item, str)
            or len(key) > 80
            or len(item) > 16_384
        ):
            continue
        if key.lower() in _HEADER_NAMES:
            headers[key] = item
    body = _json_body(value.body)
    if body["encoding"] == "base64" and len(value.body) > FRAME_LIMIT:
        raise ComponentError("response_too_large")
    cookies = {
        str(key): str(item)
        for key, item in value.cookies.items()
        if isinstance(key, str) and isinstance(item, str) and len(key) <= 80
    }
    return {
        "kind": "response",
        "status_code": value.status_code,
        "url": value.url,
        "headers": headers,
        "body": body,
        "history": [
            {"status_code": status, "url": url} for status, url in value.history[:5]
        ],
        "cookies": cookies,
    }


def _decode_download(message):
    if not isinstance(message, dict):
        raise ComponentError("invalid_output")
    position = message.get("position")
    status = message.get("status")
    issue_code = message.get("issue_code")
    if type(position) is not int or position < 0 or position > 128:
        raise ComponentError("invalid_output")
    if status == "ready":
        encoded = message.get("data")
        mime_type = message.get("mime_type")
        if not isinstance(encoded, str) or not isinstance(mime_type, str):
            raise ComponentError("invalid_output")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            raise ComponentError("invalid_output") from None
        if not 0 < len(data) <= MAX_MEDIA_BYTES:
            raise ComponentError("invalid_output")
        return position, {
            "status": "ready",
            "data": data,
            "mime_type": mime_type,
        }
    if status != "unavailable" or not isinstance(issue_code, str):
        raise ComponentError("invalid_output")
    value = {"status": "unavailable", "issue_code": issue_code}
    diagnostic = _decode_diagnostic(message.get("diagnostic"))
    if diagnostic is not None:
        value["diagnostic"] = diagnostic
    return position, value


def _decode_diagnostic(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ComponentError("invalid_output")
    allowed = {
        "stage",
        "outcome",
        "status_code",
        "basis",
        "asset_position",
        "target",
    }
    if set(value) - allowed:
        raise ComponentError("invalid_output")
    if value.get("stage") not in ("detail", "media", "browser"):
        raise ComponentError("invalid_output")
    if value.get("outcome") not in {
        "access_denied",
        "asset_blocked",
        "asset_unavailable",
        "content_unavailable",
        "login_required",
        "manual_challenge_required",
        "media_limit",
        "media_redirect",
        "parser_failed",
        "platform_blocked_or_rate_limited",
        "structure_changed",
    }:
        raise ComponentError("invalid_output")
    if value.get("basis") not in {
        "http_status",
        "explicit_platform_evidence",
        "login_redirect",
        "platform_payload",
        "browser_dom_evidence",
        "upstream_exception",
        "transport",
    }:
        raise ComponentError("invalid_output")
    if value.get("target") not in {
        "selected_post",
        "media_asset",
        "search_page",
    }:
        raise ComponentError("invalid_output")
    for key in ("stage", "outcome", "basis", "target"):
        if not isinstance(value.get(key), str) or len(value[key]) > 64:
            raise ComponentError("invalid_output")
    status_code = value.get("status_code")
    if status_code is not None and (
        type(status_code) is not int or not 100 <= status_code <= 599
    ):
        raise ComponentError("invalid_output")
    position = value.get("asset_position")
    if position is not None and (type(position) is not int or not 0 <= position <= 24):
        raise ComponentError("invalid_output")
    return {
        "stage": value["stage"],
        "outcome": value["outcome"],
        "status_code": status_code,
        "basis": value["basis"],
        "asset_position": position,
        "target": value["target"],
    }


def _safe_media_url(url):
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
                host == suffix or host.endswith("." + suffix) for suffix in _MEDIA_HOSTS
            )
        )
    except ValueError:
        return False


class GalleryComponent:
    def __init__(self, *, launcher=asyncio.create_subprocess_exec):
        self._launcher = launcher

    async def extract(
        self,
        content_id,
        *,
        request_fetch,
        cookies=None,
        max_media_bytes=MAX_MEDIA_BYTES,
        max_images=24,
        max_videos=1,
        text_only=False,
    ):
        if not re.fullmatch(r"[1-9][0-9]{5,23}", content_id):
            raise ComponentError("invalid_identity")
        if not isinstance(cookies, Mapping):
            raise ComponentError("invalid_credentials")
        cookies = {
            name: value
            for name, value in cookies.items()
            if name in ("SUB", "SUBP") and isinstance(value, str) and len(value) <= 4096
        }
        if (
            type(max_media_bytes) is not int
            or not 1 <= max_media_bytes <= MAX_MEDIA_BYTES
        ):
            raise ComponentError("invalid_budget")
        if type(max_images) is not int or not 1 <= max_images <= 24:
            raise ComponentError("invalid_budget")
        if type(max_videos) is not int or max_videos != 1:
            raise ComponentError("invalid_budget")
        return await self._extract_upstream(
            content_id,
            request_fetch=request_fetch,
            cookies=cookies,
            max_media_bytes=max_media_bytes,
            mode="text_only" if text_only else "upstream",
            max_images=max_images,
            max_videos=max_videos,
        )

    async def acquire_media(
        self,
        content_id,
        *,
        post,
        files,
        request_fetch,
        cookies=None,
        max_media_bytes=MAX_MEDIA_BYTES,
        max_images=24,
        max_videos=1,
    ):
        """Resume upstream media downloads without repeating the detail lookup."""
        if not re.fullmatch(r"[1-9][0-9]{5,23}", content_id):
            raise ComponentError("invalid_identity")
        if request_fetch is None or not isinstance(cookies, Mapping):
            raise ComponentError("invalid_credentials")
        if (
            not isinstance(post, Mapping)
            or str(post.get("idstr", post.get("id"))) != content_id
            or not isinstance(files, list)
            or len(files) > 128
        ):
            raise ComponentError("invalid_resume_input")
        checked_files = []
        for item in files:
            if not isinstance(item, Mapping):
                raise ComponentError("invalid_resume_input")
            url = item.get("url")
            metadata = item.get("metadata")
            if not isinstance(url, str) or len(url) > 4096:
                raise ComponentError("invalid_resume_input")
            if not isinstance(metadata, Mapping):
                raise ComponentError("invalid_resume_input")
            checked = {}
            for key in ("extension", "filename", "num", "width", "height"):
                value = metadata.get(key)
                if not (isinstance(value, (str, int, float, bool)) or value is None):
                    raise ComponentError("invalid_resume_input")
                checked[key] = value
            number = checked.get("num")
            if type(number) is not int or not 1 <= number <= 128:
                raise ComponentError("invalid_resume_input")
            checked_files.append({"url": url, "metadata": checked})
        cookies = {
            name: value
            for name, value in cookies.items()
            if name in ("SUB", "SUBP") and isinstance(value, str) and len(value) <= 4096
        }
        if (
            type(max_media_bytes) is not int
            or not 1 <= max_media_bytes <= MAX_MEDIA_BYTES
        ):
            raise ComponentError("invalid_budget")
        if type(max_images) is not int or not 1 <= max_images <= 24:
            raise ComponentError("invalid_budget")
        if type(max_videos) is not int or max_videos != 1:
            raise ComponentError("invalid_budget")
        return await self._extract_upstream(
            content_id,
            request_fetch=request_fetch,
            cookies=cookies,
            max_media_bytes=max_media_bytes,
            mode="upstream_media",
            post=dict(post),
            files=checked_files,
            max_images=max_images,
            max_videos=max_videos,
        )

    async def _start(self):
        command = _gallery_worker_command()
        # The worker is a brokered parser.  Give it only the operating-system
        # variables required by a frozen Windows process and its locale; do
        # not forward API keys, proxy settings or other unrelated parent
        # process state into the child.
        environment = {
            key: os.environ[key]
            for key in _WORKER_ENVIRONMENT_KEYS
            if key in os.environ
        }
        environment["LANG"] = os.environ.get("LANG", "C.UTF-8")
        options = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.DEVNULL,
            "limit": FRAME_LIMIT,
            # A Windows console-subsystem worker keeps real stdin/stdout
            # handles for the JSON protocol while CREATE_NO_WINDOW prevents a
            # transient console from flashing for the user.
            "env": environment,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0x08000000
            )
        launch = asyncio.create_task(self._launcher(*command, **options))
        try:
            return await asyncio.shield(launch)
        except asyncio.CancelledError:

            async def finish_starting():
                process = await launch
                await self._stop(process)

            await settle(finish_starting())
            raise

    async def _extract_upstream(
        self,
        content_id,
        *,
        request_fetch,
        cookies,
        max_media_bytes,
        mode="upstream",
        post=None,
        files=None,
        max_images=24,
        max_videos=1,
    ):
        if mode not in ("upstream", "upstream_media", "text_only"):
            raise ComponentError("invalid_mode")
        process = await self._start()
        downloads = {}
        media_bytes = 0
        request_count = 0
        try:
            async with asyncio.timeout(120):
                startup = {
                    "content_id": content_id,
                    "mode": mode,
                    "cookies": dict(cookies),
                    "max_media_bytes": max_media_bytes,
                    "max_images": max_images,
                    "max_videos": max_videos,
                }
                if mode == "upstream_media":
                    startup.update({"post": post, "files": files})
                await self._send(process, startup)
                while True:
                    message = await self._read(process)
                    kind = message.get("kind")
                    if kind == "request":
                        request_count += 1
                        if request_count > _MAX_REQUESTS:
                            raise ComponentError("request_limit")
                        request = self._request(message, content_id)
                        response = request_fetch(request)
                        if inspect.isawaitable(response):
                            response = await response
                        if not isinstance(response, UpstreamResponse):
                            raise ComponentError("invalid_response")
                        if request.stage == "media" and isinstance(
                            response.body, bytes
                        ):
                            media_bytes += len(response.body)
                            if (
                                response.headers.get("x-opinion-workbench-error")
                                == "media_limit"
                            ):
                                media_bytes = max_media_bytes
                            if media_bytes > max_media_bytes:
                                response = UpstreamResponse(
                                    status_code=413,
                                    url=response.url,
                                    headers={
                                        "x-opinion-workbench-error": "media_limit"
                                    },
                                    body=b"",
                                )
                        await self._send(process, _response_payload(response))
                    elif kind == "media":
                        position, value = _decode_download(message)
                        if position in downloads:
                            raise ComponentError("invalid_output")
                        downloads[position] = value
                    elif kind == "result":
                        result = self._result(message, content_id)
                        result["downloads"] = downloads
                        result["pause_reason"] = message.get("pause_reason")
                        result["diagnostic"] = _decode_diagnostic(
                            message.get("diagnostic")
                        )
                        return result
                    elif kind == "error":
                        raise ComponentError(
                            message.get("code", "parser_failed"),
                            status_code=message.get("status_code"),
                            stage=message.get("stage"),
                            basis=message.get("basis"),
                            asset_position=message.get("asset_position"),
                        )
                    else:
                        raise ComponentError("invalid_output")
        except (ValueError, OSError, asyncio.IncompleteReadError):
            raise ComponentError("invalid_output") from None
        finally:
            await settle(self._stop(process))

    def _request(self, message, content_id):
        stage = message.get("stage")
        method = message.get("method")
        url = message.get("url")
        headers = message.get("headers")
        if stage not in ("detail", "media") or not isinstance(method, str):
            raise ComponentError("invalid_request")
        if not isinstance(url, str) or len(url) > 4096:
            raise ComponentError("invalid_request")
        expected = (
            "https://weibo.com/ajax/statuses/show?id="
            + content_id
            + "&isGetLongText=true"
        )
        if stage == "detail" and url != expected:
            raise ComponentError("lookup_out_of_scope")
        if stage == "media" and not _safe_media_url(url):
            raise ComponentError("unsafe_media_url")
        if not isinstance(headers, dict) or len(headers) > 64:
            raise ComponentError("invalid_request")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(key) > 120
            or len(value) > 32_768
            for key, value in headers.items()
        ):
            raise ComponentError("invalid_request")
        body = message.get("body")
        if body is not None:
            if not isinstance(body, str):
                raise ComponentError("invalid_request")
            try:
                body = base64.b64decode(body, validate=True)
            except (ValueError, base64.binascii.Error):
                raise ComponentError("invalid_request") from None
            if len(body) > 1_048_576:
                raise ComponentError("request_too_large")
        media_index = message.get("media_index")
        if media_index is not None and (
            type(media_index) is not int or not 0 <= media_index <= 128
        ):
            raise ComponentError("invalid_request")
        stream = message.get("stream", True)
        allow_redirects = message.get("allow_redirects", True)
        verify = message.get("verify", True)
        proxies = message.get("proxies", {})
        if type(stream) is not bool or type(allow_redirects) is not bool:
            raise ComponentError("invalid_request")
        if verify is not True or proxies not in (None, {}):
            raise ComponentError("unsupported_request_options")
        timeout = message.get("timeout")
        if timeout is not None:
            if type(timeout) in (int, float):
                if not 0 < float(timeout) <= 120:
                    raise ComponentError("invalid_request")
            elif isinstance(timeout, list) and len(timeout) == 2:
                if any(
                    item is not None
                    and (type(item) not in (int, float) or not 0 < float(item) <= 120)
                    for item in timeout
                ):
                    raise ComponentError("invalid_request")
            else:
                raise ComponentError("invalid_request")
        return UpstreamRequest(
            stage=stage,
            method=method,
            url=url,
            headers=headers,
            body=body,
            allow_redirects=allow_redirects,
            media_index=media_index,
            stream=stream,
            timeout=timeout,
            verify=verify,
            proxies=proxies or {},
        )

    @staticmethod
    def _result(message, content_id):
        post = message.get("post")
        files = message.get("files")
        if (
            not isinstance(post, dict)
            or str(post.get("idstr", post.get("id"))) != content_id
            or not isinstance(files, list)
            or len(files) > 128
        ):
            raise ComponentError("identity_mismatch")
        return {"post": post, "files": files}

    async def _read(self, process):
        raw = await process.stdout.readline()
        if not raw.endswith(b"\n") or len(raw) > FRAME_LIMIT:
            raise ComponentError("invalid_output")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ComponentError("invalid_output") from None
        if not isinstance(value, dict):
            raise ComponentError("invalid_output")
        return value

    async def _send(self, process, message):
        raw = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode()
        if len(raw) > FRAME_LIMIT:
            raise ComponentError("frame_limit")
        process.stdin.write(raw + b"\n")
        await process.stdin.drain()

    async def _stop(self, process):
        if process is None:
            return
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if process.stdin is not None:
            process.stdin.close()


def _gallery_worker_command() -> tuple[str, ...]:
    """Return a worker command that remains valid after freezing.

    A frozen PyInstaller executable is an application, not a Python
    interpreter, so ``sys.executable -m ...`` cannot be assumed to work.  The
    Windows entry point accepts a private worker switch and dispatches to the
    same module in the child process.
    """

    if getattr(sys, "frozen", False):
        worker_name = (
            "OpinionWorkbenchGalleryWorker.exe"
            if os.name == "nt"
            else "OpinionWorkbenchGalleryWorker"
        )
        worker = Path(sys.executable).with_name(worker_name)
        if worker.is_file():
            return (str(worker), "--opinion-workbench-gallery-worker")
        if os.name == "nt":
            raise FileNotFoundError("OpinionWorkbenchGalleryWorker.exe is missing")
        return (sys.executable, "--opinion-workbench-gallery-worker")
    return (sys.executable, "-I", "-u", "-m", "opinion_workbench_api.gallery_worker")
