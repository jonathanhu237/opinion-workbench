import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from enrichment_fixtures import content_payload
from test_search_worker_client import SearchProcess, build_client

import longtian_api.services.media_crawler_auth_worker as worker_module
from longtian_api.services.enrichment_models import (
    ENRICHMENT_COMMAND_PREFIX,
    ENRICHMENT_EVENT_PREFIX,
    MAX_ENRICHMENT_EVENT_BYTES,
    MEDIA_ROOT_ENV,
    EnrichmentBudget,
)
from longtian_api.services.media_crawler_auth_worker import (
    AUTH_EVENT_PREFIX,
    AuthWorkerError,
    EnrichmentWorkerUnsettledError,
    _parse_event,
)


def enrichment_event(command, event="result", **changes):
    payload = {
        "version": 1,
        "type": "event",
        "event": event,
        "request_id": command["request_id"],
        "platform": command["platform"],
        "content_id": command["content_id"],
    }
    if event == "result":
        payload.update(
            outcome="completed",
            manifest=None,
            content=content_payload(
                command["platform"], command["content_id"], command["content_url"]
            ),
        )
    payload.update(changes)
    return (
        ENRICHMENT_EVENT_PREFIX
        + json.dumps(payload, separators=(",", ":")).encode()
        + b"\n"
    )


def session_event():
    return (
        AUTH_EVENT_PREFIX + b'{"version":2,"type":"event","event":"session",'
        b'"state":"disconnected","reason":"browser_disconnected"}\n'
    )


class EnrichmentProcess(SearchProcess):
    def __init__(self, mode="normal"):
        super().__init__()
        self.mode = mode
        self.received = asyncio.Event()
        self.last = None

    def receive(self, data):
        if not data.startswith(ENRICHMENT_COMMAND_PREFIX):
            return super().receive(data)
        command = json.loads(data[len(ENRICHMENT_COMMAND_PREFIX) :])
        self.commands.append((ENRICHMENT_COMMAND_PREFIX, command))
        if command["command"] == "cancel":
            if self.mode == "no_ack":
                return
            if self.mode == "cancel_completed":
                self.stdout.feed(enrichment_event(self.last))
            else:
                self.stdout.feed(
                    enrichment_event(self.last, outcome="cancelled", content=None)
                )
            return
        self.last = command
        self.received.set()
        if self.mode == "preaccepted_idle":
            self.stdout.feed(session_event())
        if self.mode != "no_accepted":
            self.stdout.feed(enrichment_event(command, event="accepted"))
        if self.mode in {"hanging", "no_ack", "cancel_completed"}:
            return
        if self.mode == "duplicate_accepted":
            self.stdout.feed(enrichment_event(command, event="accepted"))
        if self.mode == "busy_idle":
            self.stdout.feed(session_event())
        changes = {}
        if self.mode == "wrong_id":
            changes["content_id"] = "99999"
        elif self.mode == "wrong_platform":
            changes["platform"] = "dy"
        elif self.mode == "wrong_uuid":
            changes["request_id"] = str(uuid4())
        elif self.mode == "unsolicited_cancel":
            changes.update(outcome="cancelled", content=None)
        elif self.mode == "extra":
            changes["secret"] = "DO_NOT_RETAIN"
        elif self.mode == "wrong_body_identity":
            changes["content"] = content_payload("wb", "99999")
        self.stdout.feed(enrichment_event(command, **changes))


async def enrich(client):
    return await client.enrich(
        request_id=uuid4(),
        platform="wb",
        content_id="12345",
        content_url="https://m.weibo.cn/detail/12345",
        term="对象",
        budget=EnrichmentBudget(),
    )


def test_new_protocol_reuses_one_worker_and_accepts_old_idle_notification():
    async def scenario():
        process = EnrichmentProcess("preaccepted_idle")
        client, launcher, terminator, disconnects = build_client(process)
        client.configure_media_spool(Path("/trusted/runtime/media"))
        for _ in range(2):
            result = await enrich(client)
            assert result.outcome == "completed"
            assert result.content.text.body == "完整的正文。"
        assert launcher.calls == 1 and terminator.calls == 0
        assert len(disconnects) == 2
        command = process.commands[0][1]
        assert set(command) == {
            "version",
            "type",
            "command",
            "request_id",
            "platform",
            "content_id",
            "content_url",
            "term",
            "budget",
        }
        assert command["version"] == 1
        assert command["budget"] == EnrichmentBudget().model_dump()
        await client.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "no_accepted",
        "duplicate_accepted",
        "busy_idle",
        "wrong_id",
        "wrong_platform",
        "wrong_uuid",
        "unsolicited_cancel",
        "extra",
        "wrong_body_identity",
    ],
)
def test_enrichment_mismatch_fails_closed_and_recycles_only_owned_worker(mode, caplog):
    async def scenario():
        process = EnrichmentProcess(mode)
        client, _, terminator, _ = build_client(process)
        client.configure_media_spool(Path("/trusted/runtime/media"))
        with pytest.raises(AuthWorkerError) as caught:
            await enrich(client)
        assert str(caught.value) == ""
        assert terminator.calls == 1 and process.returncode is not None
        await client.shutdown()

    asyncio.run(scenario())
    assert "DO_NOT_RETAIN" not in caplog.text


@pytest.mark.parametrize("mode", ["hanging", "cancel_completed"])
def test_cancel_uses_exact_enrichment_frame_and_waits_for_terminal_fence(mode):
    async def scenario():
        process = EnrichmentProcess(mode)
        client, _, _, _ = build_client(process)
        client.configure_media_spool(Path("/trusted/runtime/media"))
        task = asyncio.create_task(enrich(client))
        await process.received.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.commands[1] == (
            ENRICHMENT_COMMAND_PREFIX,
            {
                "version": 1,
                "type": "command",
                "command": "cancel",
                "request_id": process.last["request_id"],
            },
        )
        await client.shutdown()

    asyncio.run(scenario())


def test_failed_kill_wait_does_not_claim_process_exit_proof():
    async def scenario():
        process = EnrichmentProcess("no_ack")
        client, _, _, _ = build_client(process)
        client.configure_media_spool(Path("/trusted/runtime/media"))
        client._cancel_timeout_seconds = 0.01

        async def unconfirmed_termination(*_args):
            pass

        client._process_group_terminator = unconfirmed_termination
        task = asyncio.create_task(enrich(client))
        await process.received.wait()
        task.cancel()
        with pytest.raises(EnrichmentWorkerUnsettledError) as caught:
            await task
        assert not caught.value.quiescent()
        process.finish(-9)
        assert caught.value.quiescent()
        await client.shutdown()

    asyncio.run(scenario())


def test_unconfigured_or_arbitrary_source_starts_no_process():
    async def scenario():
        client, launcher, _, _ = build_client(EnrichmentProcess())
        with pytest.raises(AuthWorkerError):
            await enrich(client)
        client.configure_media_spool(Path("/trusted/runtime/media"))
        with pytest.raises(AuthWorkerError):
            await client.enrich(
                request_id=uuid4(),
                platform="wb",
                content_id="12345",
                content_url="https://example.com/arbitrary",
                term="对象",
                budget=EnrichmentBudget(),
            )
        assert launcher.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate",
        "oversize",
        "wrong_version",
        "boolean_version",
        "accepted_extra",
        "both_content_manifest",
    ],
)
def test_new_frame_decoder_rejects_invalid_envelopes(damage):
    command = {
        "request_id": str(uuid4()),
        "platform": "wb",
        "content_id": "12345",
        "content_url": "https://m.weibo.cn/detail/12345",
    }
    line = enrichment_event(command)
    if damage == "duplicate":
        line = line.replace(b'"version":1', b'"version":1,"version":1')
    elif damage == "oversize":
        line = line[:-1] + b" " * MAX_ENRICHMENT_EVENT_BYTES + b"\n"
    elif damage == "wrong_version":
        line = line.replace(b'"version":1', b'"version":2')
    elif damage == "boolean_version":
        line = line.replace(b'"version":1', b'"version":true')
    elif damage == "accepted_extra":
        line = enrichment_event(command, event="accepted", content=None)
    elif damage == "both_content_manifest":
        line = enrichment_event(
            command,
            manifest={
                "handle": uuid4().hex,
                "byte_size": 1,
                "sha256": "0" * 64,
                "mime_type": "application/json",
            },
        )
    with pytest.raises(AuthWorkerError):
        _parse_event(line)


def test_worker_root_is_startup_environment_not_command_and_creates_no_directory(
    tmp_path, monkeypatch
):
    async def scenario():
        captured = {}

        async def fake_launch(*args, **kwargs):
            captured.update(kwargs)
            captured["args"] = args
            return EnrichmentProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_launch)
        root = tmp_path / "media"
        await worker_module.launch_process(
            ("fixed-worker",), tmp_path, media_spool_root=root
        )
        assert captured["env"][MEDIA_ROOT_ENV] == str(root)
        assert captured["args"] == ("fixed-worker",)
        assert not root.exists()
        assert captured["start_new_session"] == (os.name == "posix")

    asyncio.run(scenario())
