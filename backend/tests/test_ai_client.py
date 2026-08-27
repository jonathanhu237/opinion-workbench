import asyncio
import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from longtian_api.services import ai_client
from longtian_api.services.ai_client import (
    MAX_RESPONSE_TEXT_BYTES,
    MAX_STREAM_BYTES,
    TEST_DEADLINE_SECONDS,
    TEST_MAX_TOKENS,
    AIClient,
    AIConfiguration,
    normalize_base_url,
)
from longtian_api.services.ai_errors import AIError

KEY = "fake-transport-credential-sentinel"
CONFIGURATION = AIConfiguration(
    "https://api.example.com/v1", "test-model", 3, SecretStr(KEY)
)


def event(delta=None, finish=None) -> bytes:
    return (
        b"data: "
        + json.dumps(
            {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]},
            ensure_ascii=False,
        ).encode()
        + b"\n\n"
    )


COMPLETE = event({"content": "OK"}) + event(finish="stop") + b"data: [DONE]\n\n"


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.closed = False
        self.iterated = False

    async def __aiter__(self):
        self.iterated = True
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


async def public_resolver(_host, _port):
    return ("8.8.8.8",)


def test_synthetic_payload_pins_destination_tls_host_and_has_explicit_bounds(caplog):
    requests = []
    stream = Chunks([COMPLETE])

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=stream
        )

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(respond), resolver=public_resolver
        )
        try:
            await client.test_connection(CONFIGURATION)
        finally:
            await client.aclose()

    with caplog.at_level(logging.DEBUG):
        asyncio.run(exercise())
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://8.8.8.8/v1/chat/completions"
    assert request.headers["host"] == "api.example.com"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.extensions["sni_hostname"] == "api.example.com"
    assert request.extensions["timeout"] == {
        "connect": 10.0,
        "read": 30.0,
        "write": 30.0,
        "pool": 5.0,
    }
    body = json.loads(request.content)
    assert body == {
        "model": "test-model",
        "stream": True,
        "modalities": ["text"],
        "max_tokens": 32,
        "messages": [
            {
                "role": "system",
                "content": "Check connectivity. Reply with a short text confirmation.",
            },
            {"role": "user", "content": "Reply OK."},
        ],
    }
    assert TEST_MAX_TOKENS == 32
    assert TEST_DEADLINE_SECONDS == 30
    assert MAX_RESPONSE_TEXT_BYTES == 65536
    assert stream.closed
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "ai_authentication_failed"),
        (403, "ai_authentication_failed"),
        (404, "ai_model_not_found"),
        (429, "ai_rate_limited"),
        (500, "ai_provider_unavailable"),
        (503, "ai_provider_unavailable"),
        (302, "ai_invalid_response"),
        (307, "ai_invalid_response"),
        (400, "ai_unsupported_input"),
        (415, "ai_unsupported_input"),
        (413, "ai_request_too_large"),
    ],
)
def test_failures_are_single_attempt_no_redirect_and_never_read_provider_error_body(
    status, code
):
    requests = []
    stream = Chunks([KEY.encode()])

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status,
            headers={
                "Location": "https://other.example/v1",
                "Content-Type": "text/event-stream",
            },
            stream=stream,
        )

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(respond), resolver=public_resolver
        )
        try:
            with pytest.raises(AIError, match=code) as caught:
                await client.test_connection(CONFIGURATION)
            assert KEY not in str(caught.value)
        finally:
            await client.aclose()

    asyncio.run(exercise())
    assert len(requests) == 1
    assert stream.closed and not stream.iterated


def test_fragmented_utf8_multiline_sse_comments_and_usage_only_keep_final_text():
    body = (
        b": heartbeat\r\n\r\n" + b'data: {"choices": [\r\ndata: {"index":0,'
        b'"delta":{"role":"assistant"},"finish_reason":null}]}\r\n\r\n'
        + event({"content": "可以", "reasoning_content": "ignored-private-reasoning"})
        + event({"content": "。"})
        + event(finish="stop")
        + b'data: {"choices":[],"usage":{"total_tokens":4}}\n\n'
        + b"data: [DONE]\n\n"
    )
    stream = Chunks([body[index : index + 1] for index in range(len(body))])

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream; charset=utf-8"},
                    stream=stream,
                )
            ),
            resolver=public_resolver,
        )
        try:
            assert (
                await client.complete_text(
                    CONFIGURATION, messages=[], max_tokens=32, deadline=30
                )
                == "可以。"
            )
        finally:
            await client.aclose()

    asyncio.run(exercise())
    assert stream.closed


@pytest.mark.parametrize(
    "body",
    [
        b"",
        event({"content": "partial"}),
        event({"content": "partial"}) + b"data: [DONE]\n\n",
        event({"content": "partial"}) + event(finish="length") + b"data: [DONE]\n\n",
        event({"refusal": "not allowed"}) + COMPLETE,
        event({"tool_calls": [{"function": "send_key"}]}) + COMPLETE,
        event({"function_call": {"name": "send_key"}}) + COMPLETE,
        event({"audio": {"data": "unsupported"}}) + COMPLETE,
        event({"content": ["bad"]}) + COMPLETE,
        b"data: not-json\n\n",
        pytest.param(
            b"data: " + b"[" * 2000 + b"0" + b"]" * 2000 + b"\n\n",
            id="excessive-json-nesting",
        ),
        b"data: \xff\n\n",
        b"data: {}\n\n",
        b"data: []\n\n",
        event(finish="stop") + b"data: [DONE]\n\n",
        COMPLETE.rstrip(b"\n"),
        COMPLETE + event({"content": "after done"}),
        event({"content": "a" * MAX_RESPONSE_TEXT_BYTES}) + COMPLETE,
        event({"content": "a" * 40000})
        + event({"content": "a" * 30000})
        + event(finish="stop")
        + b"data: [DONE]\n\n",
        b":" + b"a" * (MAX_STREAM_BYTES + 1),
    ],
)
def test_invalid_partial_refusal_tool_empty_or_oversized_output_fails(body):
    stream = Chunks([body])

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, headers={"Content-Type": "text/event-stream"}, stream=stream
                )
            ),
            resolver=public_resolver,
        )
        try:
            with pytest.raises(AIError, match="ai_invalid_response"):
                await client.test_connection(CONFIGURATION)
        finally:
            await client.aclose()

    asyncio.run(exercise())
    assert stream.closed


def test_midstream_disconnect_is_failure_even_after_content():
    stream = Chunks([event({"content": "partial"})], httpx.ReadError(KEY))

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, headers={"Content-Type": "text/event-stream"}, stream=stream
                )
            ),
            resolver=public_resolver,
        )
        try:
            with pytest.raises(AIError, match="ai_provider_unavailable"):
                await client.test_connection(CONFIGURATION)
        finally:
            await client.aclose()

    asyncio.run(exercise())
    assert stream.closed


@pytest.mark.parametrize("phase", ["dns", "stream"])
def test_overall_deadline_covers_dns_and_streaming_without_retry(monkeypatch, phase):
    monkeypatch.setattr(ai_client, "TEST_DEADLINE_SECONDS", 0.01)
    calls = []

    async def stalled_resolver(_host, _port):
        if phase == "dns":
            await asyncio.Event().wait()
        return ("8.8.8.8",)

    class StalledStream(Chunks):
        async def __aiter__(self):
            yield event({"content": "partial"})
            await asyncio.Event().wait()

    stream = StalledStream([])

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=stream
        )

    async def exercise():
        client = AIClient(
            transport=httpx.MockTransport(respond), resolver=stalled_resolver
        )
        try:
            with pytest.raises(AIError, match="ai_timeout"):
                await client.test_connection(CONFIGURATION)
        finally:
            await client.aclose()

    asyncio.run(exercise())
    assert len(calls) == (0 if phase == "dns" else 1)
    if phase == "stream":
        assert stream.closed


@pytest.mark.parametrize(
    "addresses",
    [
        (),
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.169.254",),
        ("::1",),
        ("8.8.8.8", "192.168.0.1"),
        ("224.0.0.1",),
        ("::ffff:8.8.8.8",),
    ],
)
def test_nonpublic_or_mixed_dns_answers_never_receive_a_credential(addresses):
    async def resolver(_host, _port):
        return addresses

    def forbidden(_request):
        pytest.fail("unsafe destination received a request")

    async def exercise():
        client = AIClient(transport=httpx.MockTransport(forbidden), resolver=resolver)
        try:
            with pytest.raises(AIError, match="ai_destination_forbidden"):
                await client.test_connection(CONFIGURATION)
        finally:
            await client.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com",
        "https://localhost",
        "https://api.local",
        "https://127.0.0.1",
        "https://[::1]",
        "https://10.0.0.1",
        "https://169.254.169.254",
        "https://2130706433",
        "https://api.example.com?secret=value",
        "https://api.example.com?",
        "https://api.example.com#fragment",
        "https://user:secret@api.example.com",
        " https://api.example.com",
        "https://api.example.com\n",
        "https://api.example.com\\evil",
        "https://api.example.com/%2fsecret",
        "https://api.example.com/../v1",
        "https://api.example.com:0",
        "https://api.example.com/v1/chat/completions",
    ],
)
def test_base_url_validation_rejects_unsafe_or_full_completion_urls(url):
    with pytest.raises(AIError, match="invalid_ai_base_url"):
        normalize_base_url(url)


def test_base_url_canonicalization():
    assert (
        normalize_base_url("https://API.EXAMPLE.COM:443/v1/")
        == "https://api.example.com/v1"
    )
    assert (
        normalize_base_url("https://api.example.com:8443/api/v1")
        == "https://api.example.com:8443/api/v1"
    )


def test_default_transport_disables_proxies_redirects_retries_and_pool_reuse(
    monkeypatch,
):
    options = []
    original = httpx.AsyncHTTPTransport

    def transport(**kwargs):
        options.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    client = AIClient()
    assert options[0]["verify"] is True
    assert options[0]["trust_env"] is False
    assert options[0]["retries"] == 0
    assert options[0]["limits"].max_keepalive_connections == 0
    assert client._http.follow_redirects is False
    assert client._http.trust_env is False
    asyncio.run(client.aclose())
