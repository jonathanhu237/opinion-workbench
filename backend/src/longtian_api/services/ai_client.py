"""Bounded, text-output Chat Completions transport with pinned public DNS.

The application owns the protocol. Model output is data and cannot request tools,
redirects, configuration changes, or additional network operations.
"""

import asyncio
import codecs
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import SecretStr

from longtian_api.services.ai_errors import AIError

TEST_DEADLINE_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 30.0
TEST_MAX_TOKENS = 32
MAX_RESPONSE_TEXT_BYTES = 64 * 1024
MAX_STREAM_BYTES = 1024 * 1024
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_BASE_PATH = re.compile(r"(?:/[A-Za-z0-9._~-]+)*\Z")


@dataclass(frozen=True)
class AIConfiguration:
    base_url: str
    model: str
    revision: int
    api_key: SecretStr = field(repr=False)


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and (
        address.ipv4_mapped is not None
        or address.sixtofour is not None
        or address.teredo is not None
    ):
        return False
    return address.is_global and not address.is_multicast


def normalize_base_url(value: str) -> str:
    """No DNS or provider call during save; resolved addresses are checked on use."""
    if (
        not value
        or len(value) > 2048
        or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
    ):
        raise AIError("invalid_ai_base_url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        path = parsed.path.rstrip("/")
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or "\\" in value
            or "%" in parsed.netloc
            or (port is not None and not 1 <= port <= 65535)
            or not _BASE_PATH.fullmatch(path)
            or any(part in (".", "..") for part in path.split("/"))
            or path.endswith("/chat/completions")
        ):
            raise ValueError()
        host = host.lower().rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if (
                len(host) > 253
                or len(labels) < 2
                or not all(_HOST_LABEL.fullmatch(label) for label in labels)
                or not re.fullmatch(r"[a-z]{2,63}", labels[-1])
                or labels[-1] in {"localhost", "local", "internal", "test", "invalid"}
            ):
                raise ValueError() from None
        else:
            if not is_public_address(host):
                raise ValueError()
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != 443:
            authority += f":{port}"
        return urlunsplit(("https", authority, path, "", ""))
    except ValueError:
        raise AIError("invalid_ai_base_url") from None


async def resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    answers = await asyncio.get_running_loop().getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
    )
    return tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))


class _TextStream:
    """Incremental SSE/UTF-8 decoder retaining only bounded final text."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._data: list[str] = []
        self._event_bytes = 0
        self._wire_bytes = 0
        self._text_bytes = 0
        self._content: list[str] = []
        self._finished = False
        self._done = False

    def feed(self, chunk: bytes, *, final: bool = False) -> None:
        self._wire_bytes += len(chunk)
        if self._wire_bytes > MAX_STREAM_BYTES:
            raise AIError("ai_invalid_response")
        self._buffer += self._decoder.decode(chunk, final=final)
        while match := re.search(r"\r\n|\r|\n", self._buffer):
            if match.group() == "\r" and match.end() == len(self._buffer) and not final:
                break
            line = self._buffer[: match.start()]
            self._buffer = self._buffer[match.end() :]
            self._line(line)
        if len(self._buffer.encode("utf-8")) > MAX_RESPONSE_TEXT_BYTES:
            raise AIError("ai_invalid_response")
        if final and (self._buffer or self._data):
            # An unframed terminal event is a partial stream, not success.
            raise AIError("ai_invalid_response")

    def _line(self, line: str) -> None:
        self._event_bytes += len(line.encode("utf-8"))
        if self._event_bytes > MAX_RESPONSE_TEXT_BYTES:
            raise AIError("ai_invalid_response")
        if not line:
            if self._data:
                self._event("\n".join(self._data))
            self._data = []
            self._event_bytes = 0
        elif line.startswith("data:"):
            self._data.append(line[5:].removeprefix(" "))

    def _event(self, data: str) -> None:
        if self._done:
            raise AIError("ai_invalid_response")
        if data == "[DONE]":
            if not self._finished:
                raise AIError("ai_invalid_response")
            self._done = True
            return
        payload = json.loads(data)
        if not isinstance(payload, dict) or "error" in payload:
            raise AIError("ai_invalid_response")
        choices = payload.get("choices")
        if choices == []:
            return  # Optional usage-only event.
        if not isinstance(choices, list) or len(choices) != 1:
            raise AIError("ai_invalid_response")
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index") != 0:
            raise AIError("ai_invalid_response")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise AIError("ai_invalid_response")
        if any(
            delta.get(key)
            for key in ("refusal", "tool_calls", "function_call", "audio")
        ):
            raise AIError("ai_invalid_response")
        content = delta.get("content")
        if content is not None and not isinstance(content, str):
            raise AIError("ai_invalid_response")
        if content:
            if self._finished:
                raise AIError("ai_invalid_response")
            self._text_bytes += len(content.encode("utf-8"))
            if self._text_bytes > MAX_RESPONSE_TEXT_BYTES:
                raise AIError("ai_invalid_response")
            self._content.append(content)
        finish = choice.get("finish_reason")
        if finish is not None:
            if finish != "stop" or self._finished:
                raise AIError("ai_invalid_response")
            self._finished = True

    def result(self) -> str:
        text = "".join(self._content)
        if not self._done or not self._finished or not text.strip():
            raise AIError("ai_invalid_response")
        return text


class AIClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable[
            [str, int], Awaitable[tuple[str, ...]]
        ] = resolve_public_addresses,
    ) -> None:
        self._resolver = resolver
        # Do not reuse TLS connections across different configured hosts that share
        # a pinned IP. No environment proxy, insecure TLS, or automatic retry path.
        self._http = httpx.AsyncClient(
            transport=transport
            or httpx.AsyncHTTPTransport(
                verify=True,
                trust_env=False,
                retries=0,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ),
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(
                READ_TIMEOUT_SECONDS,
                connect=CONNECT_TIMEOUT_SECONDS,
                pool=5.0,
            ),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def test_connection(self, configuration: AIConfiguration) -> None:
        await self.complete_text(
            configuration,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Check connectivity. Reply with a short text confirmation."
                    ),
                },
                {"role": "user", "content": "Reply OK."},
            ],
            max_tokens=TEST_MAX_TOKENS,
            deadline=TEST_DEADLINE_SECONDS,
        )

    async def complete_text(
        self,
        configuration: AIConfiguration,
        *,
        messages: list[dict[str, object]],
        max_tokens: int,
        deadline: float,
    ) -> str:
        try:
            async with asyncio.timeout(deadline):
                endpoint = httpx.URL(
                    normalize_base_url(configuration.base_url) + "/chat/completions"
                )
                addresses = await self._resolver(endpoint.host, endpoint.port or 443)
                if not addresses or not all(
                    is_public_address(item) for item in addresses
                ):
                    raise AIError("ai_destination_forbidden")
                # Pin the checked address. TLS still verifies the original host,
                # and Host retains the configured authority (including its port).
                target = endpoint.copy_with(host=addresses[0])
                async with self._http.stream(
                    "POST",
                    target,
                    headers={
                        "Authorization": (
                            f"Bearer {configuration.api_key.get_secret_value()}"
                        ),
                        "Host": endpoint.netloc.decode("ascii"),
                        "Accept": "text/event-stream",
                        "Accept-Encoding": "identity",
                    },
                    extensions={"sni_hostname": endpoint.host},
                    json={
                        "model": configuration.model,
                        "messages": messages,
                        "stream": True,
                        "modalities": ["text"],
                        "max_tokens": max_tokens,
                    },
                ) as response:
                    self._check_status(response.status_code)
                    if (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                        != "text/event-stream"
                        or response.headers.get("content-encoding", "identity")
                        != "identity"
                    ):
                        raise AIError("ai_invalid_response")
                    stream = _TextStream()
                    async for chunk in response.aiter_raw():
                        stream.feed(chunk)
                    stream.feed(b"", final=True)
                    return stream.result()
        except AIError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise AIError("ai_timeout") from None
        except (httpx.HTTPError, OSError):
            raise AIError("ai_provider_unavailable") from None
        except (ValueError, UnicodeError, RecursionError):
            raise AIError("ai_invalid_response") from None

    @staticmethod
    def _check_status(status: int) -> None:
        if status == 200:
            return
        if status in (401, 403):
            raise AIError("ai_authentication_failed")
        if status == 404:
            raise AIError("ai_model_not_found")
        if status == 429:
            raise AIError("ai_rate_limited")
        if status == 413:
            raise AIError("ai_request_too_large")
        if status in (400, 415, 422):
            raise AIError("ai_unsupported_input")
        if status >= 500:
            raise AIError("ai_provider_unavailable")
        raise AIError("ai_invalid_response")
