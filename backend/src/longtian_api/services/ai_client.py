"""Bounded, text-output Chat Completions transport with pinned public DNS.

The application owns the protocol. Model output is data and cannot request tools,
redirects, configuration changes, or additional network operations.
"""

import asyncio
import codecs
import ipaddress
import json
import logging
import math
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)

from longtian_api.services.ai_errors import AIError

TEST_DEADLINE_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 30.0
TEST_MAX_TOKENS = 32
MAX_RESPONSE_TEXT_BYTES = 64 * 1024
MAX_STREAM_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 9_000_000
MAX_USAGE_TOKENS = 2**53 - 1
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_BASE_PATH = re.compile(r"(?:/[A-Za-z0-9._~-]+)*\Z")


@dataclass(frozen=True)
class AIConfiguration:
    base_url: str
    model: str
    revision: int
    api_key: SecretStr = field(repr=False)


TokenDetail = Literal[
    "text_tokens", "image_tokens", "video_tokens", "audio_tokens", "cached_tokens"
]
TokenCount = Annotated[int, Field(ge=0, le=MAX_USAGE_TOKENS)]
_TOKEN_DETAILS = (
    "text_tokens",
    "image_tokens",
    "video_tokens",
    "audio_tokens",
    "cached_tokens",
)


class AIUsage(BaseModel):
    """Only validated provider accounting, never estimated or arbitrary metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    prompt_tokens: TokenCount
    completion_tokens: TokenCount
    total_tokens: TokenCount
    prompt_tokens_details: dict[TokenDetail, TokenCount] | None = None
    completion_tokens_details: dict[TokenDetail, TokenCount] | None = None

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        if self.prompt_tokens + self.completion_tokens != self.total_tokens:
            raise ValueError("invalid token total")
        for total, details in (
            (self.prompt_tokens, self.prompt_tokens_details),
            (self.completion_tokens, self.completion_tokens_details),
        ):
            if details is not None and (
                any(value > total for value in details.values())
                or sum(
                    value for key, value in details.items() if key != "cached_tokens"
                )
                > total
            ):
                # Cached tokens overlap modalities; missing modalities remain unknown.
                raise ValueError("invalid token detail total")
        return self


@dataclass(frozen=True, slots=True)
class AICompletion:
    text: str = field(repr=False)
    usage: AIUsage | None = None


def decode_model_json(text: str) -> object:
    """Shared strict JSON syntax for SSE and final answers, no repair/coercion."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("invalid JSON constant")

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


def encode_completion_request(
    configuration: AIConfiguration,
    *,
    messages: list[dict[str, object]],
    max_tokens: int,
    include_usage: bool = True,
) -> bytes:
    """The bytes checked here are exactly the bytes sent, before DNS/provider work."""
    if (
        type(max_tokens) is not int
        or not 1 <= max_tokens <= 4096
        or type(include_usage) is not bool
        or type(messages) is not list
    ):
        raise AIError("ai_unsupported_input")
    payload = {
        "model": configuration.model,
        "messages": messages,
        "stream": True,
        "modalities": ["text"],
        "max_tokens": max_tokens,
    }
    if include_usage:
        payload["stream_options"] = {"include_usage": True}
    # Only the verified provider/model combination; arbitrary compatible
    # endpoints and the plain-text connectivity probe retain their protocol.
    if configuration.base_url.rstrip(
        "/"
    ) == "https://dashscope.aliyuncs.com/compatible-mode/v1" and any(
        isinstance(message, dict)
        and message.get("role") == "system"
        and isinstance(message.get("content"), str)
        and "json" in message["content"].lower()
        for message in messages
    ):
        if configuration.model == "qwen3.5-omni-plus":
            payload["response_format"] = {"type": "json_object"}
        elif configuration.model in {"qwen3.8-max", "qwen3.8-max-0902"}:
            # Qwen3.8 defaults to xhigh thinking; max_tokens bounds only the
            # answer, so an otherwise bounded report can time out before it.
            # The verified DashScope extension caps reasoning independently.
            # https://help.aliyun.com/zh/model-studio/deep-thinking
            payload["enable_thinking"] = True
            payload["thinking_budget"] = 1024
            payload["response_format"] = {"type": "json_object"}
    if configuration.base_url.rstrip("/") in {
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
    } and configuration.model in {"deepseek-v4-pro", "deepseek-v4-flash"}:
        # Official DeepSeek text completions use this thinking switch, not
        # DashScope's enable_thinking/thinking_budget extension.
        payload.pop("modalities", None)
        payload["thinking"] = {"type": "disabled"}
        if any(
            message.get("role") == "system"
            and isinstance(message.get("content"), str)
            and "json" in message["content"].lower()
            for message in messages
            if isinstance(message, dict)
        ):
            payload["response_format"] = {"type": "json_object"}
    try:
        data = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AIError("ai_unsupported_input") from None
    if len(data) >= MAX_REQUEST_BYTES:
        raise AIError("ai_request_too_large")
    return data


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
    for attempt in range(3):
        answers = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
        addresses = tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))
        # Local DNS interceptors can briefly return synthetic benchmarking IPs
        # during a network transition. Retry DNS only; never connect to these
        # addresses or relax the public-address check at the call boundary.
        if not _synthetic_dns_addresses(addresses):
            return addresses
        if attempt == 2:
            # The local-first app may run behind a fake-IP DNS proxy. Resolve
            # only known public provider names through a fixed TLS-verified
            # public resolver; private/mixed answers never enter this fallback.
            if host in {"api.deepseek.com", "dashscope.aliyuncs.com"}:
                resolved = await _resolve_provider_dns_https(host)
                if resolved:
                    return resolved
            return addresses
        await asyncio.sleep(0.25 * (attempt + 1))
    return ()


async def _resolve_provider_dns_https(host: str) -> tuple[str, ...]:
    # Fixed IP avoids recursively using the intercepted system resolver.
    # This request contains only a public provider hostname, no model data/key.
    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=4.0
        ) as client:
            async with client.stream(
                "GET",
                "https://1.1.1.1/dns-query",
                params={"name": host, "type": "A"},
                headers={"Accept": "application/dns-json"},
            ) as response:
                if response.status_code != 200:
                    return ()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 16384:
                        return ()
        value = decode_model_json(body.decode())
        if (
            value.get("Status") != 0
            or value.get("TC") is not False
            or value.get("Question")
            not in (
                [{"name": host, "type": 1}],
                [{"name": host + ".", "type": 1}],
            )
        ):
            return ()
        addresses = tuple(
            dict.fromkeys(
                item["data"]
                for item in value.get("Answer", [])
                if item.get("type") == 1
            )
        )
        if addresses and all(is_public_address(item) for item in addresses):
            return addresses
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return ()


def _synthetic_dns_addresses(addresses: tuple[str, ...]) -> bool:
    try:
        return bool(addresses) and all(
            ipaddress.ip_address(value) in ipaddress.ip_network("198.18.0.0/15")
            for value in addresses
        )
    except ValueError:
        return False


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
        self._usage: AIUsage | None = None
        self._usage_invalid = False

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
        payload = decode_model_json(data)
        if not isinstance(payload, dict) or "error" in payload:
            raise AIError("ai_invalid_response")
        self._observe_usage(payload.get("usage"))
        choices = payload.get("choices")
        if choices == []:
            return  # Optional usage-only event.
        if not isinstance(choices, list) or len(choices) != 1:
            raise AIError("ai_invalid_response")
        choice = choices[0]
        if (
            not isinstance(choice, dict)
            or type(choice.get("index")) is not int
            or choice["index"] != 0
        ):
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

    def _observe_usage(self, value: object) -> None:
        if value is None or self._usage_invalid:
            return
        try:
            if type(value) is not dict:
                raise ValueError
            data = {
                name: value[name]
                for name in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            for name in ("prompt_tokens_details", "completion_tokens_details"):
                details = value.get(name)
                if details is not None:
                    if type(details) is not dict:
                        raise ValueError
                    data[name] = {
                        key: details[key] for key in _TOKEN_DETAILS if key in details
                    }
            usage = AIUsage.model_validate(data)
            if self._usage is not None and self._usage != usage:
                raise ValueError
            self._usage = usage
        except (KeyError, TypeError, ValueError, ValidationError):
            # Malformed/conflicting accounting does not make successful text a
            # transport failure, but never becomes zero or an invented merge.
            self._usage = None
            self._usage_invalid = True

    @property
    def usage(self) -> AIUsage | None:
        return self._usage if not self._usage_invalid else None

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
        self._public_destination: tuple[str, int, tuple[str, ...], float] | None = None
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
        self._public_destination = None
        await self._http.aclose()

    async def _resolve_destination(self, host: str, port: int) -> tuple[str, ...]:
        addresses = await self._resolver(host, port)
        now = asyncio.get_running_loop().time()
        if addresses and all(is_public_address(value) for value in addresses):
            self._public_destination = (host, port, addresses, now + 60)
        elif _synthetic_dns_addresses(addresses):
            cached = self._public_destination
            if cached is not None and cached[:2] == (host, port) and cached[3] > now:
                # A short DNS cache can bridge a local fake-IP transition. It
                # contains only previously validated public IPs for this exact
                # authority. The cache expiry is never extended by a fallback;
                # the connection still pins the IP and verifies the host's TLS.
                return cached[2]
        else:
            # Ordinary private/mixed answers must fail closed, including after
            # a previous public resolution. Do not treat them as proxy fake IPs.
            self._public_destination = None
        return addresses

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
        result = await self.complete(
            configuration,
            messages=messages,
            max_tokens=max_tokens,
            deadline=deadline,
            include_usage=False,
        )
        return result.text

    async def complete(
        self,
        configuration: AIConfiguration,
        *,
        messages: list[dict[str, object]],
        max_tokens: int,
        deadline: float,
        include_usage: bool = True,
    ) -> AICompletion:
        if (
            type(deadline) not in (int, float)
            or not math.isfinite(deadline)
            or not 0 < deadline <= 180
        ):
            raise AIError("ai_unsupported_input")
        body = encode_completion_request(
            configuration,
            messages=messages,
            max_tokens=max_tokens,
            include_usage=include_usage,
        )
        try:
            async with asyncio.timeout(deadline):
                endpoint = httpx.URL(
                    normalize_base_url(configuration.base_url) + "/chat/completions"
                )
                addresses = await self._resolve_destination(
                    endpoint.host, endpoint.port or 443
                )
                if not addresses or not all(
                    is_public_address(item) for item in addresses
                ):
                    logging.getLogger(__name__).warning(
                        "Model DNS address validation rejected %s: %s",
                        endpoint.host,
                        addresses,
                    )
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
                        "Content-Type": "application/json",
                    },
                    extensions={"sni_hostname": endpoint.host},
                    content=body,
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
                    return AICompletion(stream.result(), stream.usage)
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
