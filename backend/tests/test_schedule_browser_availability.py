"""Only validated existing-worker evidence enables scheduling; never a probe."""

import asyncio
from uuid import uuid4

import pytest
from test_platform_connections import (
    FakeProcess,
    build_service,
    connected_plan,
    disconnected_plan,
    wait_for_terminal,
    worker_event,
)
from test_search_worker_client import SearchProcess, build_client


@pytest.mark.parametrize("plan", [connected_plan, disconnected_plan])
def test_manual_account_check_establishes_browser_not_login_requirement(plan):
    async def run():
        process = FakeProcess(plan)
        service, launcher, _ = build_service(process)
        assert not service.worker.browser_session_available
        assert launcher.calls == []
        await service.start_attempt("wb")
        await wait_for_terminal(service, "wb")
        assert service.worker.browser_session_available
        before = len(launcher.calls)
        assert service.worker.browser_session_available
        assert len(launcher.calls) == before
        process.feed(
            worker_event("session", state="disconnected", reason="browser_disconnected")
        )
        for _ in range(30):
            if not service.worker.browser_session_available:
                break
            await asyncio.sleep(0)
        assert not service.worker.browser_session_available
        await service.shutdown()

    asyncio.run(run())


def test_search_proves_session_and_death_reset_never_launches_again():
    async def run():
        process = SearchProcess()
        client, launcher, _, _ = build_client(process)
        assert not client.browser_session_available and launcher.calls == 0
        await client.search(
            request_id=uuid4(),
            platform="wb",
            terms=("对象",),
            max_results_per_term=1,
            on_progress=lambda *_: asyncio.sleep(0),
            on_item=lambda *_: asyncio.sleep(0),
            on_term_completed=lambda *_: asyncio.sleep(0),
        )
        assert client.browser_session_available and launcher.calls == 1
        process.finish(1)
        assert not client.browser_session_available
        await client.shutdown()
        assert not client.browser_session_available and launcher.calls == 1

    asyncio.run(run())


def test_worker_ready_alone_does_not_prove_browser():
    async def run():
        client, launcher, _, _ = build_client(SearchProcess())
        await client._ensure_worker()
        assert not client.browser_session_available and launcher.calls == 1
        await client.shutdown()

    asyncio.run(run())
