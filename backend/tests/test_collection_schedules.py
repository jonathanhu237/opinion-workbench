"""Fake-clock scheduler, crash fences, shared owners and A+B handoff."""

import asyncio
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from collection_schedule_fixtures import FakeClock, drain, enabled, environment, payload
from initial_analysis_fixtures import finish
from test_initial_analysis_handoff import services
from test_search_runs import BlockingSearchWorker

from opinion_workbench_api.repositories.search_batches import SearchBatchRepository
from opinion_workbench_api.schemas.collection_schedules import CollectionScheduleReplace
from opinion_workbench_api.schemas.monitoring_rules import MonitoringRuleReplace
from opinion_workbench_api.schemas.search_batches import SearchBatchCreate
from opinion_workbench_api.services.browser_operations import BrowserOperationOwner
from opinion_workbench_api.services.collection_schedule_errors import (
    CollectionScheduleError,
)
from opinion_workbench_api.services.collection_schedules import (
    CollectionScheduleService,
)
from opinion_workbench_api.services.search_batches import ScheduledAdmissionError


def test_exact_due_duplicate_polls_and_concurrent_token_dispatch(tmp_path):
    async def run():
        _, service, clock, worker, runs, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        await service.tick()
        assert worker.calls == []
        clock.advance(60)
        await asyncio.gather(service.tick(), service.tick())
        await drain(batches)
        occurrence = service.get(schedule.id).latest_occurrence
        assert (
            occurrence.status == "dispatched" and occurrence.batch_status == "completed"
        )
        assert len(worker.calls) == 1
        await service.tick()
        assert len(worker.calls) == 1
        assert (
            service.get(schedule.id).next_due_at
            == (clock.now + timedelta(minutes=1)).isoformat()
        )
        clock.advance(60)
        claim = service.repository.advance_due(clock.now)[0]
        first, second = await asyncio.gather(
            *(
                batches.start_scheduled_batch(
                    claim,
                    timestamp=clock.now.isoformat(),
                    admission_allowed=lambda: True,
                )
                for _ in range(2)
            )
        )
        await drain(batches)
        assert first.id == second.id and len(worker.calls) == 2
        await service.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize(
    "feature",
    ["search_run", "platform_connection", "content_enrichment", "search_result_open"],
)
def test_busy_other_owner_skips_without_stealing(tmp_path, feature):
    async def run():
        _, service, clock, worker, _, _, _, coordinator = environment(tmp_path)
        schedule = enabled(service)
        owner = BrowserOperationOwner(feature, uuid4())
        assert await coordinator.try_claim(owner)
        clock.advance(60)
        await service.tick()
        occurrence = service.get(schedule.id).latest_occurrence
        assert (
            occurrence.status == "skipped"
            and occurrence.reason == "browser_operation_active"
        )
        assert await coordinator.is_owned_by(owner)
        assert worker.calls == []
        await service.shutdown()
        await coordinator.release(owner)

    asyncio.run(run())


def test_manual_pause_never_auto_resumes_or_loses_owner(tmp_path):
    async def run():
        _, service, clock, worker, runs, batches, _, coordinator = environment(
            tmp_path, outcome="manual_challenge_required"
        )
        schedule = enabled(service)
        await batches.start_batch(
            SearchBatchCreate(monitoring_rule_id=1, platforms=["wb"])
        )
        await drain(batches)
        before = await batches.get_batch(batches._active_batch_id)
        owner = coordinator._owner
        clock.advance(60)
        await service.tick()
        after = await batches.get_batch(before.id)
        assert after == before and after.status == "paused_for_manual_action"
        assert coordinator._owner == owner and len(worker.calls) == 1
        assert (
            service.get(schedule.id).latest_occurrence.reason
            == "browser_operation_active"
        )
        await service.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("unavailable", "browser_unavailable"),
        ("disabled", "monitoring_rule_disabled"),
        ("deleted", "monitoring_rule_not_found"),
        ("oversize", "too_many_search_terms"),
        ("invalid", "invalid_monitoring_rule"),
    ],
)
def test_visible_skip_categories_without_browser_work(tmp_path, change, reason):
    async def run():
        database, service, clock, worker, _, _, rules, _ = environment(tmp_path)
        schedule = enabled(service)
        if change == "unavailable":
            worker.browser_session_available = False
        elif change == "deleted":
            rules.delete_rule(1)
        elif change == "invalid":
            with database.connect() as connection:
                connection.execute("DELETE FROM monitoring_rule_terms WHERE rule_id=1")
        else:
            rules.replace_rule(
                1,
                MonitoringRuleReplace(
                    name="测试规则",
                    monitoring_objects=[str(n) for n in range(21)]
                    if change == "oversize"
                    else ["对象"],
                    issue_keywords=[],
                    enabled=change != "disabled",
                ),
            )
        clock.advance(60)
        await service.tick()
        occurrence = service.get(schedule.id).latest_occurrence
        assert occurrence.status == "skipped" and occurrence.reason == reason
        assert occurrence.batch_id is None and worker.calls == []
        assert service.get(schedule.id).next_due_at > clock.now.isoformat()
        await service.shutdown()

    asyncio.run(run())


def test_backward_jump_cannot_repeat_and_forward_jump_is_one_range(tmp_path):
    async def run():
        _, service, clock, worker, runs, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        await service.tick()
        clock.advance(60)
        await service.tick()
        await drain(batches)
        clock.advance(-60, wall_only=True)
        await service.tick()
        clock.advance(60)
        await service.tick()
        assert len(worker.calls) == 1
        clock.advance(600, wall_only=True)
        await service.tick()
        occurrence = service.get(schedule.id).latest_occurrence
        assert occurrence.status == "missed" and occurrence.reason == "clock_jump"
        assert occurrence.missed_count == 10
        assert occurrence.due_at == "2026-08-29T00:02:00+00:00"
        assert occurrence.missed_until == "2026-08-29T00:11:00+00:00"
        assert service.get(schedule.id).next_due_at == "2026-08-29T00:12:00+00:00"
        assert len(service.repository.occurrences(schedule.id).occurrences) == 2
        await service.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_startup_long_offline_gap_is_bounded_and_future_facing(tmp_path):
    async def run():
        database, service, clock, worker, _, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        clock.advance(60 * 100_000)
        restarted = CollectionScheduleService(
            database, batches, clock=clock, monotonic=clock.monotonic, available=True
        )
        await restarted.start()
        await restarted.tick()
        occurrence = restarted.get(schedule.id).latest_occurrence
        assert occurrence.status == "missed" and occurrence.reason == "offline"
        assert occurrence.missed_count == 100_000 and worker.calls == []
        assert (
            restarted.get(schedule.id).next_due_at
            == (clock.now + timedelta(minutes=1)).isoformat()
        )
        await restarted.shutdown()
        again = CollectionScheduleService(
            database, batches, clock=clock, monotonic=clock.monotonic, available=True
        )
        await again.start()
        assert len(again.repository.occurrences(schedule.id).occurrences) == 1
        assert worker.calls == []
        await again.shutdown()

    asyncio.run(run())


def test_forward_jump_marks_every_schedule_across_storage_pages(tmp_path):
    async def run():
        _, service, clock, worker, *_ = environment(tmp_path)
        schedules = [enabled(service) for _ in range(101)]
        await service.tick()
        clock.advance(65, wall_only=True)
        await service.tick()
        await service.tick()
        assert worker.calls == []
        for schedule in schedules:
            occurrence = service.get(schedule.id).latest_occurrence
            assert occurrence.status == "missed" and occurrence.reason == "clock_jump"
            assert occurrence.missed_count == 1
        await service.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("boundary", ["before_link", "after_link", "after_start"])
def test_crash_reconciliation_never_replays_dispatch(tmp_path, boundary):
    async def run():
        database, service, clock, worker, runs, batches, rules, _ = environment(
            tmp_path
        )
        schedule = enabled(service)
        clock.advance(60)
        claim = service.repository.advance_due(clock.now)[0]
        repository = SearchBatchRepository(database)
        batch = None
        if boundary != "before_link":
            batch, _ = repository.create_scheduled_batch(
                claim.dispatch_token,
                rules.list_enabled()[0],
                timestamp=clock.now.isoformat(),
            )
            if boundary == "after_start":
                repository.mark_running(batch.id)
        runs.initialize()
        batches.initialize()
        await batches.resume_after_startup()
        await service.start()
        await service.tick()
        occurrence = service.get(schedule.id).latest_occurrence
        assert occurrence.status == (
            "dispatched" if boundary == "after_start" else "interrupted"
        )
        assert worker.calls == []
        if batch:
            assert (
                occurrence.batch_id == batch.id
                and occurrence.batch_status == "paused_for_manual_action"
            )
            assert repository.get(batch.id).items[0].latest_attempt is None
            await batches.start_scheduled_batch(
                claim, timestamp=clock.now.isoformat(), admission_allowed=lambda: True
            )
            assert worker.calls == []
        else:
            with pytest.raises(ScheduledAdmissionError):
                await batches.start_scheduled_batch(
                    claim,
                    timestamp=clock.now.isoformat(),
                    admission_allowed=lambda: True,
                )
        await service.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_disable_does_not_cancel_linked_running_collection(tmp_path):
    async def run():
        worker = BlockingSearchWorker()
        worker.browser_session_available = True
        _, service, clock, _, runs, batches, *_ = environment(tmp_path, worker=worker)
        schedule = enabled(service)
        clock.advance(60)
        await service.tick()
        await asyncio.wait_for(worker.started.wait(), 2)
        clock.advance(60)
        await service.tick()
        assert (
            service.get(schedule.id).latest_occurrence.reason
            == "browser_operation_active"
        )
        disabled = service.replace(
            schedule.id,
            CollectionScheduleReplace(**payload(), expected_revision=2, enabled=False),
        )
        assert not disabled.enabled and disabled.next_due_at is None
        clock.advance(600)
        await service.tick()
        assert worker.cancelled == 0
        await service.shutdown()
        assert worker.cancelled == 0
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_current_rule_is_frozen_at_dispatch_not_schedule_creation(tmp_path):
    async def run():
        _, service, clock, worker, runs, batches, rules, _ = environment(tmp_path)
        schedule = enabled(service)
        rules.replace_rule(
            1,
            MonitoringRuleReplace(
                name="改后的规则",
                monitoring_objects=["新对象"],
                issue_keywords=["新问题"],
                enabled=True,
            ),
        )
        clock.advance(60)
        await service.tick()
        await drain(batches)
        batch = await batches.get_batch(
            service.get(schedule.id).latest_occurrence.batch_id
        )
        assert batch.rule_name == "改后的规则" and batch.terms == ("新对象 新问题",)
        assert worker.calls[0][2] == batch.terms
        rules.delete_rule(1)
        assert (await batches.get_batch(batch.id)).terms == batch.terms
        await service.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_schedule_edit_between_claim_and_link_skips_old_revision(tmp_path, monkeypatch):
    async def run():
        _, service, clock, worker, _, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        original = batches._load_rule

        async def edit(rule_id):
            service.replace(
                schedule.id,
                CollectionScheduleReplace(
                    **payload(), expected_revision=2, enabled=False
                ),
            )
            return await original(rule_id)

        monkeypatch.setattr(batches, "_load_rule", edit)
        clock.advance(60)
        await service.tick()
        current = service.get(schedule.id)
        assert current.revision == 3 and not current.enabled
        assert current.latest_occurrence.reason == "schedule_changed"
        assert current.latest_occurrence.batch_id is None and worker.calls == []
        await service.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("corruption", ["empty"])
@pytest.mark.parametrize("boundary", ["before_claim", "before_link"])
def test_damaged_platforms_never_admit_a_batch(
    tmp_path, monkeypatch, corruption, boundary
):
    async def run():
        database, service, clock, worker, _, batches, _, coordinator = environment(
            tmp_path
        )
        schedule = enabled(service)

        def corrupt():
            with database.connect() as connection:
                if corruption == "empty":
                    connection.execute("DELETE FROM collection_schedule_platforms")
                else:
                    connection.execute(
                        "UPDATE collection_schedule_platforms SET position=4-position"
                    )

        if boundary == "before_claim":
            corrupt()
        else:
            original = batches._load_rule

            async def changed(rule_id):
                rule = await original(rule_id)
                corrupt()
                return rule

            monkeypatch.setattr(batches, "_load_rule", changed)
        clock.advance(60)
        if boundary == "before_claim":
            with pytest.raises(
                CollectionScheduleError, match="collection_schedule_storage_unavailable"
            ):
                await service.tick()
        else:
            await service.tick()
        await drain(batches)
        occurrences = service.repository.occurrences(schedule.id).occurrences
        if boundary == "before_claim":
            assert occurrences == []
        else:
            assert len(occurrences) == 1
            assert occurrences[0].status == "skipped"
            assert occurrences[0].reason == "storage_unavailable"
            assert occurrences[0].batch_id is None
        with database.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM search_batches").fetchone()[0]
                == 0
            )
        assert worker.calls == [] and coordinator._owner is None
        await service.shutdown()

    asyncio.run(run())


def test_timer_uses_bounded_monotonic_wait_and_stop_signal(tmp_path, monkeypatch):
    async def run():
        _, service, _, *_ = environment(tmp_path)
        waits, ticks = [], []

        async def fake_wait(awaitable, *, timeout):
            awaitable.close()
            waits.append(timeout)
            if len(waits) == 1:
                raise TimeoutError
            return True

        async def tick():
            ticks.append(True)

        monkeypatch.setattr(asyncio, "wait_for", fake_wait)
        monkeypatch.setattr(service, "tick", tick)
        await service._run()
        assert waits == [1.0, 1.0] and ticks == [True]
        await service.shutdown()

    asyncio.run(run())


def test_shutdown_drains_slow_dispatch_before_releasing_admission(
    tmp_path, monkeypatch
):
    async def run():
        _, service, clock, worker, runs, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        entered, release = Event(), Event()
        original = batches._repository.create_scheduled_batch

        def slow(*args, **kwargs):
            entered.set()
            assert release.wait(3)
            return original(*args, **kwargs)

        monkeypatch.setattr(batches._repository, "create_scheduled_batch", slow)
        clock.advance(60)
        tick = asyncio.create_task(service.tick())
        assert await asyncio.to_thread(entered.wait, 2)
        shutdown = asyncio.create_task(service.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()
        release.set()
        await tick
        await shutdown
        await drain(batches)
        assert service.get(schedule.id).latest_occurrence.batch_id is not None
        calls = len(worker.calls)
        clock.advance(60)
        await service.tick()
        assert len(worker.calls) == calls
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_shutdown_during_rule_load_prevents_new_batch(tmp_path, monkeypatch):
    async def run():
        _, service, clock, worker, _, batches, *_ = environment(tmp_path)
        schedule = enabled(service)
        entered, release = asyncio.Event(), asyncio.Event()
        original = batches._load_rule

        async def slow(rule_id):
            entered.set()
            await release.wait()
            return await original(rule_id)

        monkeypatch.setattr(batches, "_load_rule", slow)
        clock.advance(60)
        task = asyncio.create_task(service.tick())
        await entered.wait()
        shutdown = asyncio.create_task(service.shutdown())
        await asyncio.sleep(0)
        release.set()
        await task
        await shutdown
        assert service.get(schedule.id).latest_occurrence.status == "interrupted"
        assert worker.calls == []

    asyncio.run(run())


def test_scheduled_batch_uses_a_single_post_release_handoff(tmp_path):
    async def run():
        analyses, model, runs, batches, callbacks = services(tmp_path)
        runs._worker.browser_session_available = True
        clock = FakeClock()
        service = CollectionScheduleService(
            runs.database,
            batches,
            clock=clock,
            monotonic=clock.monotonic,
            available=True,
        )
        schedule = enabled(service)
        clock.advance(60)
        await service.tick()
        await drain(batches)
        await finish(analyses)
        batch_id = service.get(schedule.id).latest_occurrence.batch_id
        assert callbacks == [("batch", batch_id)]
        jobs = analyses.repository.list().jobs
        assert len(jobs) == 1 and jobs[0].counts.completed == 1
        assert len(model.calls) == 1
        clock.advance(60)
        await service.tick()
        await drain(batches)
        await finish(analyses)
        assert len(analyses.repository.list().jobs) == 1
        assert len(model.calls) == 1
        await service.shutdown()
        await analyses.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())
