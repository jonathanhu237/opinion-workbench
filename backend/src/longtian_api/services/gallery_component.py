"""A bounded adapter around the pinned gallery-dl Weibo extractor.

The upstream extractor owns request construction and media download.  The
parent process owns the network boundary, credentials, budgets and result
handoff.  The legacy ``fetch`` mode remains for parser-only fixtures; the
product uses ``request_fetch`` so request options are preserved.
"""

import asyncio
import base64
import inspect
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from longtian_api.services.enrichment_models import MAX_MEDIA_BYTES
from longtian_api.services.settled_tasks import settle

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
        "x-longtian-error",
    }
)
_MEDIA_HOSTS = ("sinaimg.cn", "weibocdn.com")


@dataclass(frozen=True, slots=True)
class UpstreamRequest:
    stage: Literal["detail", "media"]
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = field(default=None, repr=False)
    allow_redirects: bool = True
    media_index: int | None = None


@dataclass(frozen=True, slots=True)
class UpstreamResponse:
    status_code: int
    url: str
    headers: Mapping[str, str]
    body: object = field(repr=False)
    history: tuple[tuple[int, str], ...] = ()
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)


class ComponentError(Exception):
    def __init__(self, code, *, status_code: int | None = None, stage=None):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.stage = stage


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
    return position, {"status": "unavailable", "issue_code": issue_code}


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
        fetch=None,
        request_fetch=None,
        cookies=None,
        max_media_bytes=MAX_MEDIA_BYTES,
    ):
        if not re.fullmatch(r"[1-9][0-9]{5,23}", content_id):
            raise ComponentError("invalid_identity")
        if request_fetch is None:
            return await self._extract_legacy(content_id, fetch=fetch)
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
        return await self._extract_upstream(
            content_id,
            request_fetch=request_fetch,
            cookies=cookies,
            max_media_bytes=max_media_bytes,
        )

    async def _start(self):
        launch = asyncio.create_task(
            self._launcher(
                sys.executable,
                "-I",
                "-u",
                "-m",
                "longtian_api.gallery_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=FRAME_LIMIT,
                env={"LANG": "C.UTF-8"},
            )
        )
        try:
            return await asyncio.shield(launch)
        except asyncio.CancelledError:

            async def finish_starting():
                process = await launch
                await self._stop(process)

            await settle(finish_starting())
            raise

    async def _extract_legacy(self, content_id, *, fetch):
        if fetch is None:
            raise ComponentError("invalid_fetcher")
        process = await self._start()
        try:
            async with asyncio.timeout(30):
                await self._send(process, {"content_id": content_id, "mode": "legacy"})
                requests = 0
                expected = (
                    "https://weibo.com/ajax/statuses/show?id="
                    + content_id
                    + "&isGetLongText=true"
                )
                while True:
                    message = await self._read(process)
                    if message.get("kind") == "request":
                        if requests >= 2 or message.get("url") != expected:
                            raise ComponentError("lookup_out_of_scope")
                        requests += 1
                        body = fetch(message["url"])
                        if inspect.isawaitable(body):
                            body = await body
                        await self._send(
                            process,
                            {"kind": "response", "body": _json_body(body)},
                        )
                    elif message.get("kind") == "result":
                        return self._result(message, content_id)
                    elif message.get("kind") == "error":
                        raise ComponentError(
                            message.get("code", "parser_failed"),
                            status_code=message.get("status_code"),
                            stage=message.get("stage"),
                        )
                    else:
                        raise ComponentError("invalid_output")
        except (ValueError, OSError, asyncio.IncompleteReadError):
            raise ComponentError("invalid_output") from None
        finally:
            await settle(self._stop(process))

    async def _extract_upstream(
        self, content_id, *, request_fetch, cookies, max_media_bytes
    ):
        process = await self._start()
        downloads = {}
        media_bytes = 0
        request_count = 0
        try:
            async with asyncio.timeout(120):
                await self._send(
                    process,
                    {
                        "content_id": content_id,
                        "mode": "upstream",
                        "cookies": dict(cookies),
                        "max_media_bytes": max_media_bytes,
                    },
                )
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
                                response.headers.get("x-longtian-error")
                                == "media_limit"
                            ):
                                media_bytes = max_media_bytes
                            if media_bytes > max_media_bytes:
                                response = UpstreamResponse(
                                    status_code=413,
                                    url=response.url,
                                    headers={"x-longtian-error": "media_limit"},
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
                        return result
                    elif kind == "error":
                        raise ComponentError(
                            message.get("code", "parser_failed"),
                            status_code=message.get("status_code"),
                            stage=message.get("stage"),
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
        return UpstreamRequest(
            stage=stage,
            method=method,
            url=url,
            headers=headers,
            body=body,
            allow_redirects=bool(message.get("allow_redirects", True)),
            media_index=media_index,
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
