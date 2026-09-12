import asyncio
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from opinion_workbench_api.services import ai_client
from opinion_workbench_api.services.ai_client import (
    MAX_RESPONSE_TEXT_BYTES,
    MAX_STREAM_BYTES,
    TEST_DEADLINE_SECONDS,
    TEST_MAX_TOKENS,
    AIClient,
    AICompletion,
    AIConfiguration,
    AIUsage,
    encode_completion_request,
    normalize_base_url,
)
from opinion_workbench_api.services.ai_errors import AIError

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


@pytest.mark.parametrize(
    "base_url,model,system,expected",
    [
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen3.8-max",
            "仅输出严格JSON",
            True,
        ),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen3.8-max-0902",
            "仅输出严格JSON",
            True,
        ),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen3.8-max",
            "只回答OK",
            False,
        ),
        ("https://api.example.com/v1", "qwen3.8-max", "严格JSON", False),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "other-model",
            "严格JSON",
            False,
        ),
    ],
)
def test_verified_qwen_structured_requests_bound_thinking(
    base_url, model, system, expected
):
    configuration = AIConfiguration(base_url, model, 3, SecretStr(KEY))
    payload = json.loads(
        encode_completion_request(
            configuration,
            messages=[{"role": "system", "content": system}],
            max_tokens=4096,
        )
    )
    assert payload["max_tokens"] == 4096
    if expected:
        assert payload["enable_thinking"] is True
        assert payload["thinking_budget"] == 1024
        assert payload["response_format"] == {"type": "json_object"}
    else:
        assert "enable_thinking" not in payload
        assert "thinking_budget" not in payload


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
    "answers,expected_calls,allowed",
    [
        (["198.18.1.229", "8.8.8.8"], 2, True),
        (["198.18.1.229"] * 3, 3, False),
        (["127.0.0.1"], 1, False),
    ],
)
def test_synthetic_dns_retry_never_sends_to_nonpublic_address(
    monkeypatch, answers, expected_calls, allowed
):
    sent = []

    def respond(request):
        assert request.url.host == "8.8.8.8"
        sent.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Chunks([COMPLETE]),
        )

    async def run():
        lookup = AsyncMock(
            side_effect=[[(2, 1, 6, "", (address, 443))] for address in answers]
        )
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
        client = AIClient(transport=httpx.MockTransport(respond))
        try:
            if allowed:
                await client.test_connection(CONFIGURATION)
            else:
                with pytest.raises(AIError, match="ai_destination_forbidden"):
                    await client.test_connection(CONFIGURATION)
            assert lookup.await_count == expected_calls
            assert len(sent) == int(allowed)
        finally:
            await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "addresses,expired,other_host,allowed",
    [
        (("198.18.1.229",), False, False, True),
        (("198.18.1.229",), True, False, False),
        (("198.18.1.229",), False, True, False),
        (("127.0.0.1",), False, False, False),
        (("8.8.8.8", "198.18.1.229"), False, False, False),
    ],
)
def test_public_dns_cache_is_bounded_and_only_bridges_synthetic_answers(
    addresses, expired, other_host, allowed
):
    sent = []

    def respond(request):
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "api.example.com"
        assert request.extensions["sni_hostname"] == "api.example.com"
        sent.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Chunks([COMPLETE]),
        )

    async def run():
        client = AIClient(
            transport=httpx.MockTransport(respond),
            resolver=AsyncMock(side_effect=[("8.8.8.8",), addresses]),
        )
        try:
            await client.test_connection(CONFIGURATION)
            cached = client._public_destination
            if expired:
                client._public_destination = (*cached[:3], 0)
            configuration = (
                AIConfiguration(
                    "https://other.example.com/v1", "test-model", 3, SecretStr(KEY)
                )
                if other_host
                else CONFIGURATION
            )
            if allowed:
                await client.test_connection(configuration)
                assert client._public_destination == cached
            else:
                with pytest.raises(AIError, match="ai_destination_forbidden"):
                    await client.test_connection(configuration)
            assert len(sent) == 1 + int(allowed)
        finally:
            await client.aclose()

    asyncio.run(run())


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


def usage_event(usage):
    return b"data: " + json.dumps({"choices": [], "usage": usage}).encode() + b"\n\n"


USAGE = {
    "prompt_tokens": 30,
    "completion_tokens": 4,
    "total_tokens": 34,
    "prompt_tokens_details": {"text_tokens": 2, "audio_tokens": 3, "video_tokens": 25},
    "completion_tokens_details": {"text_tokens": 4},
}


def typed_completion(chunks):
    calls, stream = [], Chunks(chunks)

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=stream
        )

    async def run():
        client = AIClient(
            transport=httpx.MockTransport(respond), resolver=public_resolver
        )
        try:
            return await client.complete(
                CONFIGURATION,
                messages=[{"role": "user", "content": "测试"}],
                max_tokens=2048,
                deadline=180,
            )
        finally:
            await client.aclose()

    return asyncio.run(run()), calls, stream


def test_typed_completion_retains_valid_usage_and_requests_it_without_metadata(caplog):
    extra = {**USAGE, "provider_debug": KEY}
    extra["prompt_tokens_details"] = {**USAGE["prompt_tokens_details"], "private": KEY}
    body = event({"content": "已完成", "reasoning_content": KEY}) + event(finish="stop")
    body += usage_event(extra) + usage_event(USAGE) + b"data: [DONE]\n\n"
    with caplog.at_level(logging.DEBUG):
        result, calls, stream = typed_completion(
            [body[i : i + 1] for i in range(len(body))]
        )
    assert result.text == "已完成" and result.usage == AIUsage.model_validate(USAGE)
    assert "已完成" not in repr(result) and KEY not in repr(result)
    assert KEY not in result.usage.model_dump_json() and KEY not in caplog.text
    assert len(calls) == 1 and stream.closed
    assert json.loads(calls[0].content)["stream_options"] == {"include_usage": True}
    assert calls[0].content == encode_completion_request(
        CONFIGURATION,
        messages=[{"role": "user", "content": "测试"}],
        max_tokens=2048,
    )


@pytest.mark.parametrize(
    "events",
    [
        [],
        [None],
        [{"total_tokens": 34}],
        [{**USAGE, "prompt_tokens": True}],
        [{**USAGE, "prompt_tokens": "30"}],
        [{**USAGE, "total_tokens": 35}],
        [{**USAGE, "completion_tokens": -1}],
        [{**USAGE, "total_tokens": 2**53}],
        [{**USAGE, "prompt_tokens_details": {"video_tokens": True}}],
        [{**USAGE, "prompt_tokens_details": {"video_tokens": 31}}],
        [{**USAGE, "prompt_tokens_details": {"video_tokens": 25, "audio_tokens": 10}}],
        [{**USAGE, "completion_tokens_details": []}],
        [USAGE, {"prompt_tokens": 40, "completion_tokens": 4, "total_tokens": 44}],
        [USAGE, {"prompt_tokens": 30, "completion_tokens": 4, "total_tokens": 34}],
        [USAGE, {}, USAGE],
        [{}, USAGE],
    ],
)
def test_missing_malformed_or_conflicting_usage_is_unknown_not_zero_or_failed_text(
    events,
):
    body = event({"content": "OK"}) + event(finish="stop")
    body += b"".join(usage_event(value) for value in events) + b"data: [DONE]\n\n"
    result, calls, stream = typed_completion([body])
    assert result == AICompletion("OK", None) and len(calls) == 1 and stream.closed


def test_partial_modality_counts_remain_sparse_and_cache_tokens_can_overlap():
    raw = {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
        "prompt_tokens_details": {"video_tokens": 6, "cached_tokens": 9},
    }
    result, _, _ = typed_completion(
        [
            event({"content": "OK"})
            + event(finish="stop")
            + usage_event(raw)
            + b"data: [DONE]\n\n"
        ]
    )
    assert result.usage.prompt_tokens_details == {"video_tokens": 6, "cached_tokens": 9}
    assert result.usage.completion_tokens_details is None


@pytest.mark.parametrize(
    "body",
    [
        event({"content": "partial"}) + usage_event(USAGE),
        event({"content": "partial"}) + usage_event(USAGE) + b"data: [DONE]\n\n",
        event({"content": "partial"})
        + event(finish="length")
        + usage_event(USAGE)
        + b"data: [DONE]\n\n",
        b'data: {"choices":[],"choices":[]}\n\n' + COMPLETE,
        b'data: {"choices":[{"index":false,"delta":{"content":"x"}}]}\n\n' + COMPLETE,
    ],
)
def test_valid_usage_never_turns_partial_or_duplicate_key_stream_into_success(body):
    with pytest.raises(AIError, match="ai_invalid_response"):
        typed_completion([body])


@pytest.mark.parametrize("difference", [-1, 0, 1])
def test_exact_encoded_request_byte_limit_is_checked_before_dns(difference):
    messages = [{"role": "user", "content": ""}]
    base = encode_completion_request(CONFIGURATION, messages=messages, max_tokens=2048)
    messages[0]["content"] = "x" * (
        ai_client.MAX_REQUEST_BYTES - len(base) + difference
    )
    requests = []
    resolver = AsyncMock(return_value=("8.8.8.8",))

    def respond(request):
        requests.append(request)
        assert len(request.content) == ai_client.MAX_REQUEST_BYTES + difference
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks([COMPLETE]),
        )

    async def run():
        client = AIClient(transport=httpx.MockTransport(respond), resolver=resolver)
        try:
            if difference < 0:
                assert (
                    await client.complete(
                        CONFIGURATION, messages=messages, max_tokens=2048, deadline=180
                    )
                ).text == "OK"
            else:
                with pytest.raises(AIError, match="ai_request_too_large"):
                    await client.complete(
                        CONFIGURATION, messages=messages, max_tokens=2048, deadline=180
                    )
        finally:
            await client.aclose()

    asyncio.run(run())
    assert len(requests) == (1 if difference < 0 else 0)
    if difference >= 0:
        resolver.assert_not_awaited()


def test_multibyte_request_size_is_utf8_bytes_not_python_characters(monkeypatch):
    messages = [{"role": "user", "content": "测试"}]
    encoded = encode_completion_request(
        CONFIGURATION, messages=messages, max_tokens=2048
    )
    monkeypatch.setattr(ai_client, "MAX_REQUEST_BYTES", len(encoded))
    with pytest.raises(AIError, match="ai_request_too_large"):
        encode_completion_request(CONFIGURATION, messages=messages, max_tokens=2048)


def test_cancelled_typed_completion_closes_stream_and_does_not_retry():
    calls = []

    async def run():
        ready = asyncio.Event()

        class WaitingStream(Chunks):
            async def __aiter__(self):
                yield event({"content": "partial"})
                ready.set()
                await asyncio.Event().wait()

        stream = WaitingStream([])

        def respond(request):
            calls.append(request)
            return httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=stream
            )

        client = AIClient(
            transport=httpx.MockTransport(respond), resolver=public_resolver
        )
        try:
            task = asyncio.create_task(
                client.complete(
                    CONFIGURATION, messages=[], max_tokens=2048, deadline=180
                )
            )
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stream.closed
        finally:
            await client.aclose()

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize(
    "base", ["https://api.deepseek.com", "https://api.deepseek.com/v1"]
)
@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-v4-flash"])
def test_deepseek_uses_its_verified_text_json_protocol(base, model):
    configuration = AIConfiguration(base, model, 1, SecretStr(KEY))
    payload = json.loads(
        encode_completion_request(
            configuration,
            messages=[{"role": "system", "content": "输出 JSON"}],
            max_tokens=4096,
        )
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert "modalities" not in payload
    assert "enable_thinking" not in payload
    assert "thinking_budget" not in payload
    probe = json.loads(
        encode_completion_request(
            configuration,
            messages=[{"role": "user", "content": "Reply OK"}],
            max_tokens=16,
        )
    )
    assert "response_format" not in probe


@pytest.mark.parametrize(
    "base,model",
    [
        ("https://api.example.com/v1", "deepseek-v4-pro"),
        ("https://api.deepseek.com", "unknown-model"),
    ],
)
def test_deepseek_extensions_do_not_change_other_compatible_configurations(base, model):
    payload = json.loads(
        encode_completion_request(
            AIConfiguration(base, model, 1, SecretStr(KEY)),
            messages=[{"role": "system", "content": "输出 JSON"}],
            max_tokens=4096,
        )
    )
    assert "thinking" not in payload
    assert "response_format" not in payload
    assert payload["modalities"] == ["text"]


@pytest.mark.parametrize(
    "addresses,expected",
    [
        (["8.8.8.8"], ("8.8.8.8",)),
        (["127.0.0.1"], ()),
        (["8.8.8.8", "198.18.4.118"], ()),
    ],
)
def test_provider_https_dns_validates_public_answers_without_credentials(
    monkeypatch, addresses, expected
):
    original = httpx.AsyncClient

    def respond(request):
        assert request.url.host == "1.1.1.1"
        assert request.url.params["name"] == "api.deepseek.com"
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "Status": 0,
                "TC": False,
                "Question": [{"name": "api.deepseek.com", "type": 1}],
                "Answer": [{"type": 1, "data": address} for address in addresses],
            },
        )

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    assert (
        asyncio.run(ai_client._resolve_provider_dns_https("api.deepseek.com"))
        == expected
    )


@pytest.mark.parametrize(
    "host,addresses,called",
    [
        ("api.deepseek.com", ["198.18.4.118"], True),
        ("api.deepseek.com", ["127.0.0.1"], False),
        ("api.deepseek.com", ["8.8.8.8", "198.18.4.118"], False),
        ("custom.example.com", ["198.18.4.118"], False),
    ],
)
def test_https_dns_fallback_only_for_known_provider_with_all_fake_ip(
    monkeypatch, host, addresses, called
):
    async def run():
        lookup = AsyncMock(
            return_value=[(2, 1, 6, "", (address, 443)) for address in addresses]
        )
        fallback = AsyncMock(return_value=("8.8.8.8",))
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
        monkeypatch.setattr(ai_client, "_resolve_provider_dns_https", fallback)
        actual = await ai_client.resolve_public_addresses(host, 443)
        assert bool(fallback.await_count) == called
        assert actual == (("8.8.8.8",) if called else tuple(addresses))

    asyncio.run(run())
