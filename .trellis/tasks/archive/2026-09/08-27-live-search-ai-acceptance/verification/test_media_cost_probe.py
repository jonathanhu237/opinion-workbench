"""Offline-only probe gates; every provider call and credential is synthetic."""

import asyncio
import importlib.util
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from longtian_api.database import Database
from longtian_api.repositories.ai_settings import AISettingsRecord
from longtian_api.services.ai_client import AIClient, AIConfiguration
from longtian_api.services.ai_errors import AIError
from longtian_api.services.ai_settings import AISettingsService

SPEC = importlib.util.spec_from_file_location(
    "media_cost_probe", Path(__file__).with_name("media_cost_probe.py")
)
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)

KEY = "fake-only-probe-credential"
ANALYSIS = {
    "decision": "uncertain",
    "reason": "现有地点信息不足。",
    "evidence_summary": "来源声称曾有污染，尚未证实地点和事实。",
    "visual_observations": ["画面中有一条河流。"],
    "audio_observations": ["未观察到可辨识的音频。"],
}
USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 50,
    "total_tokens": 350,
    "prompt_tokens_details": {
        "audio_tokens": 200,
        "video_tokens": 70,
        "text_tokens": 30,
    },
    "completion_tokens_details": {"text_tokens": 50},
}


def event(payload):
    return b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\r\n\r\n"


def response_bytes(
    *, analysis=ANALYSIS, usage=USAGE, done=True, finish="stop", answer=None
):
    data = event(
        {
            "model": probe.EXPECTED_MODEL,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": json.dumps(analysis, ensure_ascii=False)
                        if answer is None
                        else answer,
                        "reasoning_content": KEY,
                    },
                    "finish_reason": None,
                }
            ],
        }
    )
    data += event({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    if usage is not None:
        data += event({"choices": [], "usage": usage})
    return data + (b"data: [DONE]\r\n\r\n" if done else b"")


class Chunks(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data, self.closed, self.iterated = data, False, False

    async def __aiter__(self):
        self.iterated = True
        for offset in range(0, len(self.data), 7):
            yield self.data[offset : offset + 7]

    async def aclose(self):
        self.closed = True


async def public_resolver(host, port):
    assert (host, port) == ("dashscope.aliyuncs.com", 443)
    return ("8.8.8.8",)


def sample_data(path, content_id=1):
    return {
        "content_id": content_id,
        "source_url": f"https://www.douyin.com/video/{content_id}",
        "title": "合成视频标题",
        "published_at_text": "2024-01-01",
        "full_text": "合成来源文字",
        "media_path": str(path),
        "duration_seconds": 15.0,
        "width": 720,
        "height": 1280,
    }


def private_write(path, data):
    path.write_bytes(data)
    path.chmod(0o600)


def make_manifest(tmp_path, count=3):
    samples = []
    for index in range(count):
        path = tmp_path / f"synthetic-{index}.mp4"
        private_write(path, b"\x00\x00\x00\x18ftypisom" + b"synthetic" * 10)
        samples.append(sample_data(path, index + 1))
    manifest = tmp_path / "manifest.json"
    private_write(manifest, json.dumps({"samples": samples}).encode())
    return manifest


class FakeRepository:
    def __init__(self, model=probe.EXPECTED_MODEL, revision=1):
        self.record = AISettingsRecord(
            probe.EXPECTED_URL, model, "fake-reference", revision
        )
        self.read_count = 0

    def read(self):
        self.read_count += 1
        return self.record


class FakeCredentials:
    def read(self, reference):
        assert reference == "fake-reference"
        return SecretStr(KEY)


def exercise(tmp_path, respond, *, model=probe.EXPECTED_MODEL, revision=1, count=3):
    samples = probe.load_samples(make_manifest(tmp_path, count))
    output = tmp_path / "output.json"
    repository = FakeRepository(model, revision)
    transport = probe.RecordingTransport(httpx.MockTransport(respond))
    client = AIClient(transport=transport, resolver=public_resolver)
    service = AISettingsService(
        Database(tmp_path / "never-created.sqlite3"),
        repository=repository,
        credentials=FakeCredentials(),
        client=client,
    )

    async def run():
        descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            try:
                return await probe.run_probe(
                    service, client, transport, samples, descriptor
                )
            finally:
                # The real settings owner can admit another operation after all exits.
                async with service.operation(revision):
                    pass
        finally:
            os.close(descriptor)
            await service.shutdown()

    try:
        report = asyncio.run(run())
    finally:
        assert not (tmp_path / "never-created.sqlite3").exists()
    return report, json.loads(output.read_text()), transport, repository


def test_three_calls_reuse_secure_client_and_capture_only_bounded_usage(tmp_path):
    requests, streams = [], []

    def respond(request):
        # A crash during the provider call still leaves a private in-progress journal.
        journal = json.loads((tmp_path / "output.json").read_text())
        assert journal["samples"][-1]["status"] == "started"
        assert len(journal["samples"]) == len(requests) + 1
        requests.append(request)
        usage = {
            **USAGE,
            "arbitrary_private_field": KEY,
            "prompt_tokens_details": {**USAGE["prompt_tokens_details"], "unknown": KEY},
        }
        stream = Chunks(response_bytes(usage=usage))
        streams.append(stream)
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=stream
        )

    report, stored, transport, repository = exercise(tmp_path, respond)
    assert report == stored
    assert report["status"] == "completed" and report["request_count"] == 3
    assert transport.request_count == 3 and repository.read_count == 2
    assert stat.S_IMODE((tmp_path / "output.json").stat().st_mode) == 0o600
    assert KEY not in json.dumps(stored) and "base64" not in json.dumps(stored)
    for record in report["samples"]:
        assert record["analysis"] == ANALYSIS and record["usage"] == USAGE
        assert record["request_count"] == 1 and record["provider_model_matches"] is True
        assert 0 <= record["elapsed_seconds"] <= 180
    for request in requests:
        assert str(request.url) == "https://8.8.8.8/compatible-mode/v1/chat/completions"
        assert request.headers["host"] == "dashscope.aliyuncs.com"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert request.extensions["sni_hostname"] == "dashscope.aliyuncs.com"
        assert request.extensions["timeout"]["read"] == 30.0
        body = json.loads(request.content)
        assert len(request.content) < 9_000_000
        assert body["stream_options"] == {"include_usage": True}
        assert body["max_tokens"] == 1200 and body["modalities"] == ["text"]
        assert set(body) == {
            "model",
            "messages",
            "stream",
            "modalities",
            "max_tokens",
            "stream_options",
        }
        assert body["messages"][0]["content"] == probe.SYSTEM_PROMPT
        content = body["messages"][1]["content"]
        assert len(content) == 2 and content[1]["video_url"]["url"].startswith(
            "data:;base64,"
        )
        assert "media_path" not in content[0]["text"]
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "ai_authentication_failed"),
        (404, "ai_model_not_found"),
        (429, "ai_rate_limited"),
        (415, "ai_unsupported_input"),
        (302, "ai_invalid_response"),
    ],
)
def test_provider_failure_stops_without_retry_or_reading_error_body(
    tmp_path, status, code
):
    stream = Chunks(KEY.encode())
    report, stored, transport, _ = exercise(
        tmp_path,
        lambda request: httpx.Response(
            status,
            headers={
                "Content-Type": "text/event-stream",
                "Location": "https://other.invalid",
            },
            stream=stream,
        ),
    )
    assert report["status"] == "stopped_on_failure" and transport.request_count == 1
    assert len(stored["samples"]) == 1 and stored["samples"][0]["error_code"] == code
    assert KEY not in json.dumps(stored)
    assert stream.closed and not stream.iterated


@pytest.mark.parametrize(
    "changes",
    [
        {"done": False},
        {"finish": "length"},
        {"analysis": {**ANALYSIS, "unexpected": KEY}},
        {"analysis": {**ANALYSIS, "reason": KEY}},
        {"usage": {**USAGE, "prompt_tokens": True}},
        {"usage": {**USAGE, "total_tokens": 351}},
        {"usage": {**USAGE, "prompt_tokens_details": {"video_tokens": -1}}},
    ],
)
def test_incomplete_or_invalid_output_is_not_accepted_or_retried(tmp_path, changes):
    report, stored, transport, _ = exercise(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(response_bytes(**changes)),
        ),
    )
    assert report["status"] == "stopped_on_failure" and transport.request_count == 1
    assert "analysis" not in stored["samples"][0]
    assert KEY not in json.dumps(stored)


def test_exact_json_fence_is_accepted_without_semantic_repair(tmp_path):
    answer = "```json\n" + json.dumps(ANALYSIS, ensure_ascii=False) + "\n```"
    report, _, transport, _ = exercise(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(response_bytes(answer=answer)),
        ),
        count=2,
    )
    assert report["status"] == "completed" and transport.request_count == 2
    assert all(item["json_fence_removed"] for item in report["samples"])
    assert all(item["analysis"] == ANALYSIS for item in report["samples"])


@pytest.mark.parametrize(
    "answer,stage,code",
    [
        (
            "<script>not executable</script>\n普通文本",
            "json_decode",
            "probe_invalid_json",
        ),
        ("前缀```json\n{}\n```", "json_decode", "probe_invalid_json"),
        ("```json\n{}\n```后缀", "json_decode", "probe_invalid_json"),
        (
            "不" * (probe.MAX_DIAGNOSTIC_CHARS + 100),
            "json_decode",
            "probe_invalid_json",
        ),
        (
            json.dumps({**ANALYSIS, "unexpected": "untrusted value"}),
            "schema_validation",
            "probe_invalid_schema",
        ),
        (
            json.dumps(
                {key: value for key, value in ANALYSIS.items() if key != "decision"}
            ),
            "schema_validation",
            "probe_invalid_schema",
        ),
    ],
)
def test_local_output_failure_keeps_bounded_plain_diagnostic_and_advances_unique_item(
    tmp_path, answer, stage, code
):
    requested_ids = []

    def respond(request):
        source = json.loads(
            json.loads(request.content)["messages"][1]["content"][0]["text"]
        )
        requested_ids.append(source["content_id"])
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(
                response_bytes(answer=answer if len(requested_ids) == 1 else None)
            ),
        )

    report, stored, transport, _ = exercise(tmp_path, respond, count=2)
    assert report["status"] == "completed_with_output_errors"
    assert requested_ids == [1, 2] and transport.request_count == 2
    failed, completed = stored["samples"]
    assert failed["status"] == "failed" and "analysis" not in failed
    assert failed["failure_stage"] == stage and failed["error_code"] == code
    assert failed["answer_text"] == answer[: probe.MAX_DIAGNOSTIC_CHARS]
    assert failed["answer_text_truncated"] is (len(answer) > probe.MAX_DIAGNOSTIC_CHARS)
    assert completed["status"] == "completed" and completed["analysis"] == ANALYSIS
    assert KEY not in json.dumps(stored)
    output = tmp_path / "output.json"
    assert output.stat().st_size < 64 * 1024
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "answer",
    [
        "x" * (probe.MAX_DIAGNOSTIC_CHARS + 1) + KEY,
        json.dumps({**ANALYSIS, "reason": KEY}).replace(
            KEY, "".join(f"\\u{ord(char):04x}" for char in KEY)
        ),
    ],
)
def test_key_check_precedes_bounded_diagnostic_and_stops_remaining_samples(
    tmp_path, answer
):
    report, stored, transport, _ = exercise(
        tmp_path,
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(response_bytes(answer=answer)),
        ),
        count=2,
    )
    assert report["status"] == "stopped_on_failure" and transport.request_count == 1
    failed = stored["samples"][0]
    assert failed["failure_stage"] == "answer_safety" and "answer_text" not in failed
    assert KEY not in json.dumps(stored)


def test_provider_failure_after_local_format_failure_still_stops(tmp_path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200 if len(requests) == 1 else 429,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(
                response_bytes(answer="普通文本")
                if len(requests) == 1
                else KEY.encode()
            ),
        )

    report, stored, transport, _ = exercise(tmp_path, respond)
    assert report["status"] == "stopped_on_failure" and transport.request_count == 2
    assert stored["samples"][0]["failure_stage"] == "json_decode"
    assert stored["samples"][1]["failure_stage"] == "provider_request"
    assert stored["samples"][1]["error_code"] == "ai_rate_limited"
    assert "answer_text" not in stored["samples"][1]


def test_cancellation_releases_lease_and_flushes_partial_report(tmp_path):
    async def cancel(_request):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        exercise(tmp_path, cancel)
    stored = json.loads((tmp_path / "output.json").read_text())
    assert stored["status"] == "interrupted" and stored["request_count"] == 1
    assert stored["samples"][0]["status"] == "interrupted"


@pytest.mark.parametrize("kwargs", [{"model": "different-model"}, {"revision": 2}])
def test_saved_configuration_mismatch_never_calls_provider(tmp_path, kwargs):
    def forbidden(_request):
        pytest.fail("configuration mismatch must not call provider")

    with pytest.raises((probe.ProbeError, AIError)):
        exercise(tmp_path, forbidden, **kwargs)
    assert json.loads((tmp_path / "output.json").read_text())["request_count"] == 0


def test_fourth_request_rejected_and_transport_closed():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=Chunks(response_bytes()),
        )

    async def run():
        transport = probe.RecordingTransport(httpx.MockTransport(respond))
        client = AIClient(transport=transport, resolver=public_resolver)
        configuration = AIConfiguration(
            probe.EXPECTED_URL, probe.EXPECTED_MODEL, 1, SecretStr(KEY)
        )
        try:
            for _ in range(3):
                await client.complete_text(
                    configuration, messages=[], max_tokens=1200, deadline=180
                )
            with pytest.raises(probe.ProbeError, match="call_limit"):
                await client.complete_text(
                    configuration, messages=[], max_tokens=1200, deadline=180
                )
        finally:
            await client.aclose()

    asyncio.run(run())
    assert len(requests) == 3


@pytest.mark.parametrize("length", [probe.MAX_BODY_BYTES, probe.MAX_BODY_BYTES + 1])
def test_request_size_rejected_before_transport(length):
    async def run():
        transport = probe.RecordingTransport(
            httpx.MockTransport(lambda request: pytest.fail("oversized request"))
        )
        try:
            with pytest.raises(AIError, match="ai_request_too_large"):
                await transport.handle_async_request(
                    httpx.Request(
                        "POST", "https://example.invalid", content=b"x" * length
                    )
                )
            assert transport.request_count == 0
        finally:
            await transport.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation", ["symlink", "parent_symlink", "hardlink", "mode", "empty", "oversize"]
)
def test_private_input_rejects_unsafe_files(tmp_path, mutation):
    source = tmp_path / "source"
    private_write(source, b"private")
    path = source
    if mutation == "symlink":
        path = tmp_path / "link"
        path.symlink_to(source)
    elif mutation == "parent_symlink":
        parent = tmp_path / "linked-parent"
        parent.symlink_to(tmp_path, target_is_directory=True)
        path = parent / "source"
    elif mutation == "hardlink":
        os.link(source, tmp_path / "hardlink")
    elif mutation == "mode":
        source.chmod(0o644)
    elif mutation == "empty":
        source.write_bytes(b"")
    elif mutation == "oversize":
        source.write_bytes(b"x" * 11)
    with pytest.raises((probe.ProbeError, OSError)):
        probe.read_private(path, 10)


def test_manifest_bounds_duplicates_and_mp4(tmp_path):
    manifest = make_manifest(tmp_path)
    raw = json.loads(manifest.read_text())
    for changed in [
        raw["samples"] * 2,
        [raw["samples"][0]] * 2,
        [{**raw["samples"][0], "duration_seconds": 90.1}],
        [
            {
                **raw["samples"][0],
                "source_url": "https://www.douyin.com/video/1?token=secret",
            }
        ],
    ]:
        with pytest.raises(ValidationError):
            probe.Manifest.model_validate({"samples": changed})
    private_write(Path(raw["samples"][0]["media_path"]), b"not an mp4 file")
    with pytest.raises(probe.ProbeError, match="invalid_mp4"):
        probe.load_samples(manifest)


def test_existing_output_rejected_before_client_construction(tmp_path, monkeypatch):
    manifest = make_manifest(tmp_path, 1)
    output = tmp_path / "existing.json"
    private_write(output, b"preserve-existing")
    monkeypatch.setattr(
        probe, "RecordingTransport", lambda: pytest.fail("existing report")
    )
    with pytest.raises(FileExistsError):
        asyncio.run(probe.execute(manifest, tmp_path / "missing.sqlite3", output))
    assert output.read_bytes() == b"preserve-existing"


def test_readonly_database_cannot_create_initialize_or_mutate(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    database = probe.ReadOnlyDatabase(path)
    with pytest.raises(sqlite3.OperationalError):
        database.connect()
    assert not path.exists()
    with pytest.raises(probe.ProbeError):
        database.initialize()
    with sqlite3.connect(path) as fixture:
        fixture.execute("CREATE TABLE sentinel (value TEXT)")
        fixture.execute("INSERT INTO sentinel VALUES ('unchanged')")
    before = path.read_bytes()
    connection = database.connect()
    try:
        assert (
            connection.execute("SELECT value FROM sentinel").fetchone()[0]
            == "unchanged"
        )
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM sentinel")
    finally:
        connection.close()
    assert path.read_bytes() == before
