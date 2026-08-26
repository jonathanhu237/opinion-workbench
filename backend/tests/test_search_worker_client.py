import asyncio
import json
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

import pytest

from longtian_api.services.media_crawler_auth_worker import (
    AUTH_COMMAND_PREFIX,
    AUTH_EVENT_PREFIX,
    SEARCH_COMMAND_PREFIX,
    SEARCH_EVENT_PREFIX,
    AuthWorkerError,
    PersistentAuthWorkerClient,
    _parse_event,
)


class LineReader:
    def __init__(self, lines: Iterable[bytes] = ()) -> None:
        self.lines = deque(lines)
        self.available = asyncio.Event()
        self.closed = False
        if self.lines:
            self.available.set()

    async def readline(self) -> bytes:
        while not self.lines and not self.closed:
            self.available.clear()
            await self.available.wait()
        return self.lines.popleft() if self.lines else b""

    async def read(self, size: int = -1) -> bytes:
        return await self.readline()

    def feed(self, line: bytes) -> None:
        self.lines.append(line)
        self.available.set()

    def close(self) -> None:
        self.closed = True
        self.available.set()


def auth_event(event: str) -> bytes:
    return (
        AUTH_EVENT_PREFIX
        + json.dumps(
            {"version": 2, "type": "event", "event": event},
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def search_event(event: str, request_id: str, **fields: object) -> bytes:
    return (
        SEARCH_EVENT_PREFIX
        + json.dumps(
            {
                "version": 1,
                "type": "event",
                "event": event,
                "request_id": request_id,
                "platform": "toutiao",
                **fields,
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


class Writer:
    def __init__(self, process: "SearchProcess") -> None:
        self.process = process

    def write(self, data: bytes) -> None:
        self.process.receive(data)

    async def drain(self) -> None:
        pass


class SearchProcess:
    def __init__(
        self,
        *,
        hanging: bool = False,
        malformed: bool = False,
        scenario: str = "normal",
    ) -> None:
        self.pid = 99001
        self.returncode: int | None = None
        self.stdout = LineReader((auth_event("ready"),))
        self.stderr = LineReader()
        self.stdin = Writer(self)
        self.commands: list[tuple[bytes, dict[str, object]]] = []
        self.hanging = hanging
        self.malformed = malformed
        self.scenario = scenario
        self.finished = asyncio.Event()

    @staticmethod
    def item(*, content_type: str = "article", unsafe_url: bool = False):
        return {
            "content_id": "100",
            "content_type": content_type,
            "title": "龙田街道公开信息",
            "snippet": "公开摘要",
            "creator_hash": "0123456789abcdef",
            "publisher_name": "公***号",
            "published_at_text": "刚刚",
            "content_url": (
                "https://evil.example/article/100/"
                if unsafe_url
                else "https://www.toutiao.com/article/100/"
            ),
            "discovered_at": 1_777_000_000_000,
        }

    def receive(self, data: bytes) -> None:
        if data.startswith(SEARCH_COMMAND_PREFIX):
            prefix = SEARCH_COMMAND_PREFIX
        else:
            assert data.startswith(AUTH_COMMAND_PREFIX)
            prefix = AUTH_COMMAND_PREFIX
        payload = json.loads(data[len(prefix) :])
        self.commands.append((prefix, payload))
        if payload["command"] == "search":
            request_id = str(payload["request_id"])
            term_count = len(payload["terms"])
            if self.scenario == "item_before_progress":
                self.stdout.feed(
                    search_event(
                        "item",
                        request_id,
                        term_position=0,
                        item=self.item(),
                    )
                )
                return
            self.stdout.feed(
                search_event(
                    "progress",
                    request_id,
                    phase="term_started",
                    term_position=0,
                    term_count=term_count,
                )
            )
            if self.hanging:
                return
            if self.scenario == "repeated_progress":
                self.stdout.feed(
                    search_event(
                        "progress",
                        request_id,
                        phase="term_started",
                        term_position=0,
                        term_count=term_count,
                    )
                )
                return
            if self.scenario == "results_without_item":
                self.stdout.feed(
                    search_event("result", request_id, outcome="completed_with_results")
                )
                return
            if self.scenario == "unsolicited_cancel":
                self.stdout.feed(
                    search_event("result", request_id, outcome="cancelled")
                )
                return
            self.stdout.feed(
                search_event(
                    "item",
                    request_id,
                    term_position=0,
                    item=self.item(
                        content_type=(
                            "" if self.scenario == "empty_content_type" else "article"
                        ),
                        unsafe_url=self.malformed,
                    )
                    | (
                        {"publisher_name": "公开账号"}
                        if self.scenario == "unsafe_publisher"
                        else {}
                    ),
                )
            )
            if self.scenario == "over_limit":
                self.stdout.feed(
                    search_event(
                        "item",
                        request_id,
                        term_position=0,
                        item={**self.item(), "content_id": "101"},
                    )
                )
            if self.scenario == "empty_after_item":
                self.stdout.feed(
                    search_event("result", request_id, outcome="completed_empty")
                )
                return
            if not self.malformed and self.scenario not in {
                "empty_content_type",
                "unsafe_publisher",
            }:
                for position in range(1, term_count):
                    self.stdout.feed(
                        search_event(
                            "progress",
                            request_id,
                            phase="term_started",
                            term_position=position,
                            term_count=term_count,
                        )
                    )
                self.stdout.feed(
                    search_event("result", request_id, outcome="completed_with_results")
                )
        elif payload["command"] == "cancel":
            self.stdout.feed(
                search_event("result", str(payload["request_id"]), outcome="cancelled")
            )
        elif payload["command"] == "shutdown":
            self.stdout.feed(auth_event("stopped"))
            self.finish(0)

    async def wait(self) -> int:
        await self.finished.wait()
        assert self.returncode is not None
        return self.returncode

    def finish(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout.close()
        self.stderr.close()
        self.finished.set()

    def terminate(self) -> None:
        self.finish(-15)

    def kill(self) -> None:
        self.finish(-9)


class Launcher:
    def __init__(self, process: SearchProcess) -> None:
        self.process = process
        self.calls = 0

    async def __call__(self, _command: tuple[str, ...], _cwd: Path) -> SearchProcess:
        self.calls += 1
        return self.process


class Terminator:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, process: SearchProcess, _grace: float) -> None:
        self.calls += 1
        process.finish(-15)


def build_client(process: SearchProcess):
    launcher = Launcher(process)
    terminator = Terminator()
    disconnects: list[object] = []

    async def on_auth_progress(*_args: object) -> None:
        pass

    async def on_session_disconnected(request_id: object) -> None:
        disconnects.append(request_id)

    client = PersistentAuthWorkerClient(
        media_crawler_dir=Path("/repo/third_party/MediaCrawler"),
        on_progress=on_auth_progress,  # type: ignore[arg-type]
        on_session_disconnected=on_session_disconnected,  # type: ignore[arg-type]
        process_launcher=launcher,
        process_group_terminator=terminator,  # type: ignore[arg-type]
        ready_timeout_seconds=1,
        cancel_timeout_seconds=1,
        shutdown_timeout_seconds=1,
        termination_grace_seconds=0.01,
    )
    return client, launcher, terminator, disconnects


def test_client_decodes_progress_items_and_result_from_search_protocol() -> None:
    async def scenario() -> None:
        process = SearchProcess()
        client, launcher, _terminator, disconnects = build_client(process)
        progress: list[tuple[int, int]] = []
        items: list[tuple[int, str]] = []

        async def on_progress(position: int, count: int) -> None:
            progress.append((position, count))

        async def on_item(position: int, item) -> None:
            items.append((position, item.content_url))

        result = await client.search(
            request_id=uuid4(),
            terms=("龙田街道", "坪山大道"),
            max_results_per_term=10,
            on_progress=on_progress,
            on_item=on_item,
        )

        assert result.outcome == "completed_with_results"
        assert progress == [(0, 2), (1, 2)]
        assert items == [(0, "https://www.toutiao.com/article/100/")]
        assert launcher.calls == 1
        prefix, command = process.commands[0]
        assert prefix == SEARCH_COMMAND_PREFIX
        assert command["terms"] == ["龙田街道", "坪山大道"]
        assert disconnects == []
        await client.shutdown()

    asyncio.run(scenario())


def test_client_search_cancellation_uses_the_search_cancel_frame() -> None:
    async def scenario() -> None:
        process = SearchProcess(hanging=True)
        client, _launcher, _terminator, _disconnects = build_client(process)
        task = asyncio.create_task(
            client.search(
                request_id=uuid4(),
                terms=("龙田街道",),
                max_results_per_term=10,
                on_progress=lambda _position, _count: asyncio.sleep(0),
                on_item=lambda _position, _item: asyncio.sleep(0),
            )
        )
        while len(process.commands) < 1:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert [prefix for prefix, _command in process.commands[:2]] == [
            SEARCH_COMMAND_PREFIX,
            SEARCH_COMMAND_PREFIX,
        ]
        assert process.commands[1][1]["command"] == "cancel"
        await client.shutdown()

    asyncio.run(scenario())


def test_client_rejects_non_toutiao_item_urls_and_recycles_worker() -> None:
    async def scenario() -> None:
        process = SearchProcess(malformed=True)
        client, _launcher, terminator, disconnects = build_client(process)

        with pytest.raises(AuthWorkerError):
            await client.search(
                request_id=uuid4(),
                terms=("龙田街道",),
                max_results_per_term=10,
                on_progress=lambda _position, _count: asyncio.sleep(0),
                on_item=lambda _position, _item: asyncio.sleep(0),
            )

        assert terminator.calls == 1
        assert len(disconnects) == 1

    asyncio.run(scenario())


def test_search_event_parser_rejects_non_millisecond_discovery_time() -> None:
    request_id = str(uuid4())
    frame = search_event(
        "item",
        request_id,
        term_position=0,
        item={
            "content_id": "100",
            "content_type": "article",
            "title": "龙田街道公开信息",
            "snippet": "公开摘要",
            "creator_hash": "0123456789abcdef",
            "publisher_name": "公***号",
            "published_at_text": "刚刚",
            "content_url": "https://www.toutiao.com/article/100/",
            "discovered_at": 1234,
        },
    )

    with pytest.raises(AuthWorkerError):
        _parse_event(frame)


@pytest.mark.parametrize(
    ("scenario", "limit"),
    [
        ("item_before_progress", 10),
        ("repeated_progress", 10),
        ("over_limit", 1),
        ("empty_after_item", 10),
        ("results_without_item", 10),
        ("unsolicited_cancel", 10),
        ("empty_content_type", 10),
        ("unsafe_publisher", 10),
    ],
)
def test_client_rejects_inconsistent_search_event_sequences_and_recycles_worker(
    scenario: str,
    limit: int,
) -> None:
    async def run_scenario() -> None:
        process = SearchProcess(scenario=scenario)
        client, _launcher, terminator, disconnects = build_client(process)

        with pytest.raises(AuthWorkerError):
            await client.search(
                request_id=uuid4(),
                terms=("龙田街道",),
                max_results_per_term=limit,
                on_progress=lambda _position, _count: asyncio.sleep(0),
                on_item=lambda _position, _item: asyncio.sleep(0),
            )

        assert terminator.calls == 1
        assert len(disconnects) == 1

    asyncio.run(run_scenario())
