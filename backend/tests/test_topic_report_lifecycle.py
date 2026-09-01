"""Durable notification, independent queue ownership, usage and settled stop."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from initial_analysis_fixtures import request
from summary_fixtures import BASE, MODEL, seed_run
from topic_report_fixtures import (
    analyse_all,
    environment,
    finish,
    interval_request,
    retry_request,
)

from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.schemas.topic_reports import ReportCancel
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIUsage
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS, AIError
from longtian_api.services.topic_report_engine import (
    ENGINE_VERSION,
    check_request,
    prepare_judgment,
)
from longtian_api.services.topic_report_errors import TopicReportError


def test_event_link_rollback_replay_and_concurrent_consumers(tmp_path):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=2)
        initial.on_job_finished = None
        admission = await initial.create(request(db))
        await finish(initial)
        with db.connect() as connection:
            connection.execute("""CREATE TRIGGER fail_report_child BEFORE INSERT
              ON topic_report_sources WHEN NEW.position=1
              BEGIN SELECT RAISE(ABORT,'secret synthetic write failure'); END""")
        with pytest.raises(TopicReportError, match="storage_unavailable"):
            reports.repository.consume(admission.job.id)
        with db.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM topic_report_runs").fetchone()[
                    0
                ]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT state FROM analysis_completion_events"
                ).fetchone()[0]
                == "pending"
            )
            connection.execute("DROP TRIGGER fail_report_child")
        barrier = Barrier(2)

        def consume():
            barrier.wait()
            return reports.repository.consume(admission.job.id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: consume(), range(2)))
        assert values[0].id == values[1].id
        assert len(reports.repository.list().reports) == 1
        assert model.counts["judgment"] == 0
        # A crash after commit but before queue launch becomes non-runnable.
        reports.initialize()
        recovered = reports.repository.read(values[0].id)
        assert recovered.status == "interrupted"
        assert recovered.recovery_reason == "backend_restart"
        assert recovered.coverage.interrupted == 2
        other = await reports.create(interval_request(db))
        await finish(reports)
        assert reports.repository.read(other.id).status == "completed"
        assert reports.repository.read(recovered.id) == recovered
        assert model.counts["judgment"] == 2
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_pending_manual_event_startup_is_storage_only_and_admits_no_report(tmp_path):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)
        initial.on_job_finished = None
        await initial.create(request(db))
        await finish(initial)
        baseline = model.counts.copy()
        reports.initialize()
        assert reports.repository.list().reports == []
        assert reports.repository.next_report() is None
        reports.initialize()
        assert model.counts == baseline
        with db.connect() as connection:
            assert (
                connection.execute(
                    "SELECT state FROM analysis_completion_events"
                ).fetchone()[0]
                == "pending"
            )
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_workflow_report_freezes_goal_replays_and_saves_zero_model_empty(tmp_path):
    async def run():
        from longtian_api.repositories.analysis_settings import (
            AnalysisSettingsRepository,
        )

        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)
        initial.on_job_finished = None
        admission = await initial.create(request(db))
        await finish(initial)
        settings = AnalysisSettingsRepository(db).read()

        def snapshot(goal):
            return SimpleNamespace(
                analysis_goal=goal,
                ai_configuration_revision=1,
                ai_base_url=BASE,
                ai_model=MODEL,
                initial_prompt_version_id=settings.initial_prompt.id,
                report_prompt_version_id=settings.report_prompt.id,
            )

        goal = "只判断与道路积水处置相关的舆情。"
        report = await reports.workflow_admit(
            run_id=41,
            analysis_job_id=admission.job.id,
            operation_key="workflow:41:topic_report:1",
            snapshot=snapshot(goal),
        )
        await finish(reports)
        report = reports.repository.read(report.id)
        assert report.status == "completed"
        assert report.selection.model_dump() == {"kind": "workflow_run", "run_id": 41}
        assert report.prompt.instructions == goal and report.prompt.origin == "legacy"
        replay = await reports.workflow_admit(
            run_id=41,
            analysis_job_id=admission.job.id,
            operation_key="workflow:41:topic_report:1",
            snapshot=snapshot(goal),
        )
        assert replay.id == report.id
        with db.connect() as connection:
            assert (
                connection.execute(
                    "SELECT state FROM analysis_completion_events"
                ).fetchone()[0]
                == "pending"
            )

        baseline = model.counts.copy()
        empty = await reports.workflow_admit(
            run_id=42,
            analysis_job_id=None,
            operation_key="workflow:42:topic_report:1",
            snapshot=snapshot("识别本轮新增材料。"),
        )
        await finish(reports)
        empty = reports.repository.read(empty.id)
        assert empty.status == "empty" and empty.empty_reason == "no_ready_sources"
        assert empty.selection.model_dump() == {"kind": "workflow_run", "run_id": 42}
        assert model.counts == baseline
        reports.initialize()
        assert len(reports.repository.list().reports) == 2
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize(
    "code",
    [
        "ai_configuration_required",
        "ai_configuration_changed",
        "ai_credentials_unavailable",
        "ai_settings_storage_unavailable",
    ],
)
def test_runtime_provider_blocks_keep_exact_actionable_failure(
    tmp_path, monkeypatch, code
):
    async def run():
        db, initial, reports, ai, _, *_ = environment(tmp_path, count=1)
        initial.on_job_finished = None
        admission = await initial.create(request(db))
        await finish(initial)

        @asynccontextmanager
        async def blocked(_revision):
            raise AIError(code)
            yield

        monkeypatch.setattr(ai, "operation", blocked)
        await reports.initial_analysis_finished(admission.job.id)
        await finish(reports)
        report = reports.repository.list().reports[0]
        assert report.status == "configuration_blocked"
        assert report.error.model_dump() == {
            "stage": "execution",
            "code": code,
            "message": AI_ERROR_CONTRACTS[code][1],
        }
        assert report.coverage.interrupted == 1
        assert report.usage.total.attempted_requests == 0
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
def test_owned_text_call_stops_settled_without_stopping_initial_or_media(
    tmp_path, stop
):
    async def run():
        db, initial, reports, ai, model, worker, coordinator = environment(
            tmp_path, count=2
        )
        model.block_stage = "judgment"
        admission = await initial.create(request(db))
        await finish(initial)
        await asyncio.wait_for(model.entered.wait(), 5)
        report = reports.repository.list(initial_job_id=admission.job.id).reports[0]
        assert report.nodes.judgments.running == 1 and ai._active.is_set()
        if stop == "cancel":
            report = await reports.cancel(
                report.id,
                ReportCancel(
                    request_id=str(uuid4()), expected_revision=report.revision
                ),
            )
            assert report.status == "cancelled"
        else:
            await reports.shutdown()
            report = reports.repository.read(report.id)
            assert report.status == "interrupted"
        assert report.coverage.pending == report.coverage.judging == 0
        assert report.usage.total.attempted_requests == 1
        assert (
            not report.usage.total.complete and report.usage.total.total_tokens is None
        )
        assert not ai._active.is_set() and coordinator._owner is None
        assert (
            len(worker.calls) == 2
            and initial.repository.read(admission.job.id).status == "completed"
        )
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_unexpected_per_report_failure_does_not_strand_next_intent(
    tmp_path, monkeypatch
):
    async def run():
        db, initial, reports, ai, _, *_ = environment(tmp_path, count=1)
        _, original = await analyse_all(db, initial, reports)
        first = reports.repository.retry(original.id, retry_request(original))
        second = reports.repository.retry(original.id, retry_request(original))
        execute = reports._execute

        async def fail_first(report, configuration):
            if report.id == first.id:
                raise RuntimeError("synthetic unexpected failure")
            return await execute(report, configuration)

        monkeypatch.setattr(reports, "_execute", fail_first)
        await reports._launch()
        await finish(reports)
        assert reports.repository.read(first.id).status == "interrupted"
        assert reports.repository.read(second.id).status == "completed"
        assert not ai._active.is_set()
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_callback_failure_never_strands_a_queue_and_later_arrivals_stay_out(tmp_path):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)

        async def broken(_job_id):
            raise RuntimeError("synthetic report admission failure")

        initial.on_job_finished = broken
        first = await initial.create(request(db))
        await finish(initial)
        seed_run(db, 1, start=9000)
        second = await initial.create(request(db))
        await finish(initial)
        assert initial.repository.read(first.job.id).status == "completed"
        assert initial.repository.read(second.job.id).status == "completed"
        assert model.counts["initial"] == 2 and reports.repository.list().reports == []
        report = reports.repository.consume(first.job.id)
        assert report.coverage.total == 1
        assert reports.repository.sources(report.id).items[0].source.result_id == 1
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_override_provider_change_unknown_usage_and_report_only_calls(tmp_path):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=2)
        _, original = await analyse_all(db, initial, reports)
        baseline = len(worker.calls), model.counts["initial"]
        model.usage = None
        changed = await reports.retry(
            original.id,
            retry_request(original, instructions_override="  新的主题范围  "),
        )
        await finish(reports)
        changed = reports.repository.read(changed.id)
        assert (
            changed.status == "completed"
            and changed.prompt.instructions == "  新的主题范围  "
        )
        assert changed.nodes.judgments.reused == 0
        assert changed.usage.total.attempted_requests == 3
        assert (
            changed.usage.total.accounted_requests == 0
            and changed.usage.total.total_tokens is None
        )
        current = ai.save(
            AISettingsUpdate(base_url=BASE, model=MODEL + "-new", api_key=None)
        )
        model.usage = AIUsage(
            prompt_tokens=MAX_USAGE_TOKENS - 1,
            completion_tokens=1,
            total_tokens=MAX_USAGE_TOKENS,
        )
        newer = await reports.retry(
            changed.id, retry_request(changed, configuration_revision=current.revision)
        )
        await finish(reports)
        newer = reports.repository.read(newer.id)
        assert newer.status == "completed" and newer.nodes.judgments.reused == 0
        assert (
            newer.usage.total.accounted_requests == 3
            and newer.usage.total.total_tokens is None
        )
        assert (len(worker.calls), model.counts["initial"]) == baseline
        assert reports.repository.read(original.id) == original
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_admission_at_empty_queue_exit_cannot_strand_report(tmp_path):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=0)
        original = reports.repository.next_report
        empty_seen, release = threading.Event(), threading.Event()
        blocked = False

        def pause_empty():
            nonlocal blocked
            result = original()
            if result is None and not blocked:
                blocked = True
                empty_seen.set()
                assert release.wait(5)
            return result

        reports.repository.next_report = pause_empty
        await reports.create(interval_request(db))
        assert await asyncio.to_thread(empty_seen.wait, 5)
        second = await reports.create(interval_request(db))
        release.set()
        await finish(reports)
        assert reports.repository.read(second.id).status == "empty"
        assert not model.calls
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_notification_does_not_wait_for_upstream_ai_lease(tmp_path):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)
        notified = False

        async def notify(job_id):
            nonlocal notified
            assert ai._active.is_set()
            assert initial.repository.read(job_id).status == "completed"
            await asyncio.wait_for(reports.initial_analysis_finished(job_id), 5)
            assert ai._active.is_set()
            assert model.counts["judgment"] == 0
            notified = True

        initial.on_job_finished = notify
        _, report = await analyse_all(db, initial, reports)
        assert notified and report.status == "completed"
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("boundary", ["admission", "attempt", "output"])
def test_crash_metadata_never_reruns_and_retry_reuses_only_finished_nodes(
    tmp_path, boundary
):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=2)
        initial.on_job_finished = None
        admitted = await initial.create(request(db))
        await finish(initial)
        report = reports.repository.consume(admitted.job.id)
        node = reports.repository.nodes(report.id, kind="judgment")[0]
        call = prepare_judgment(
            reports.repository.context(report),
            reports.repository.evidence(node["id"])[0],
        )
        if boundary == "attempt":
            proof = check_request(call, ai._configuration(1))
            reports.repository.prepare(
                node["id"], call, ENGINE_VERSION, proof.request_hash
            )
            reports.repository.mark_attempt(node["id"])
        elif boundary == "output":
            async with ai.operation(1) as configuration:
                await reports._execute_node(report, node["id"], call, configuration)
        calls = model.counts.copy()
        reports.initialize()
        reports.initialize()
        recovered = reports.repository.read(report.id)
        assert (
            recovered.status == "interrupted"
            and recovered.recovery_reason == "backend_restart"
        )
        assert reports.repository.next_report() is None and model.counts == calls
        assert recovered.usage.total.attempted_requests == int(boundary != "admission")
        if boundary == "attempt":
            assert recovered.usage.total.total_tokens is None
        retried = await reports.retry(report.id, retry_request(recovered))
        await finish(reports)
        retried = reports.repository.read(retried.id)
        assert retried.status == "completed"
        assert retried.nodes.judgments.reused == int(boundary == "output")
        assert retried.usage.total.attempted_requests == (
            2 if boundary == "output" else 3
        )
        assert model.counts["initial"] == len(worker.calls) == 2
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("valid_output", [True, False])
@pytest.mark.parametrize("wrong_type", [False, True])
def test_invalid_transport_usage_stays_unknown_and_history_readable(
    tmp_path, valid_output, wrong_type
):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)
        initial.on_job_finished = None
        admitted = await initial.create(request(db))
        await finish(initial)
        usage = AIUsage(
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            prompt_tokens_details={"text_tokens": 20},
        )
        usage.prompt_tokens_details["text_tokens"] = 21
        model.usage = {"prompt_tokens": 20} if wrong_type else usage
        if not valid_output:
            model.answers["judgment"] = ["{}"]
        await reports.initial_analysis_finished(admitted.job.id)
        await finish(reports)
        report = reports.repository.list().reports[0]
        assert report.status == ("completed" if valid_output else "failed")
        assert report.usage.total.attempted_requests == (2 if valid_output else 1)
        assert report.usage.total.accounted_requests == 0
        assert (
            report.usage.total.total_tokens is None and not report.usage.total.complete
        )
        assert model.counts["initial"] == model.counts["judgment"] == 1
        assert model.counts["leaf"] == int(valid_output)
        with db.connect() as connection:
            rows = connection.execute(
                "SELECT attempted,usage_json FROM topic_report_nodes WHERE report_id=?",
                (report.id,),
            ).fetchall()
            assert all(row[0] == 1 and row[1] is None for row in rows)
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())
