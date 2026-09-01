"""Independent saved evidence, actual-media boundaries and owned queue lifecycle."""

import asyncio
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from initial_analysis_fixtures import UNDERSTANDING, environment, finish, request
from summary_fixtures import seed_run

from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.results import ResultsRepository
from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.schemas.ai_summaries import SummaryCreate
from longtian_api.schemas.content_analyses import WorkflowAnalysisCreate
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIUsage
from longtian_api.services.ai_errors import AIError
from longtian_api.services.ai_summaries import SummaryService
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.browser_operations import BrowserOperationOwner
from longtian_api.services.media_crawler_auth_worker import EnrichmentWorkerResult
from longtian_api.services.summary_errors import failure


def test_independent_neutral_media_understanding_and_unique_settlement(tmp_path):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(
            tmp_path, count=10
        )
        worker.partial.add("1008")
        model.item_answers = [UNDERSTANDING] * 8 + ["invalid model JSON"]
        admission = await service.create(request(database))
        await finish(service)
        job = service.repository.read(admission.job.id)
        assert job.status == "completed"
        assert (
            job.counts.completed == 9
            and job.counts.input_incomplete == 0
            and job.counts.failed == 1
        )
        assert job.usage.attempted_requests == job.usage.accounted_requests == 10
        assert len(worker.calls) == 10 and len(model.calls) == 10
        assert all(stage == "analysis" for stage, _ in model.calls)
        assert coordinator._owner is None
        items = service.repository.items(job.id).items
        assert items[0].output.summary == UNDERSTANDING["summary"]
        assert items[0].input.text.body == worker.body
        assert items[8].input.evidence_coverage.level == "detail_text"
        assert items[8].input.evidence_coverage.image.unknown == 1
        assert items[8].usage is not None and items[8].error.code == "invalid_json"
        assert items[-1].output is not None
        text = model.calls[0][1][0]["content"]
        assert job.initial_prompt.instructions in text
        assert "monitoring_scope" not in str(model.calls)
        assert "image_url" in str(model.calls)
        assert "blob_ref" not in items[0].model_dump_json()
        events = service.repository.completion_events()
        assert len(events) == 1 and len(events[0]["successful_attempt_ids"]) == 9
        assert events[0]["job"].report_prompt == job.report_prompt
        service.repository.finish(job.id, "completed")
        assert len(service.repository.completion_events()) == 1
        with database.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM ai_summary_runs").fetchone()[0]
                == 0
            )
        await service.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["input_incomplete", "failed"])
def test_zero_successes_still_publish_one_normally_settled_handoff(tmp_path, outcome):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(tmp_path)
        if outcome == "input_incomplete":
            worker.partial.update({"1000", "1001"})
        else:
            model.item_answers = ["invalid JSON", "invalid JSON"]
        admission = await service.create(request(database))
        await finish(service)
        job = service.repository.read(admission.job.id)
        expected_completed = 2 if outcome == "input_incomplete" else 0
        assert job.status == "completed" and job.counts.completed == expected_completed
        assert getattr(job.counts, outcome) == 2 - expected_completed
        assert all(
            attempt.status == ("completed" if expected_completed else outcome)
            and (attempt.output is not None) == bool(expected_completed)
            for attempt in service.repository.items(job.id).items
        )
        events = service.repository.completion_events()
        assert len(events) == 1
        assert len(events[0]["successful_attempt_ids"]) == expected_completed
        assert events[0]["job"] == job and events[0]["state"] == "pending"
        assert job.completion_event_id == events[0]["id"]
        assert service.repository.completion_events(after_id=events[0]["id"]) == []
        assert (await service.cancel(job.id)) == job
        service.repository.finish(job.id, "completed")
        assert service.repository.completion_events() == events
        assert ResultsRepository(database).list().active_count == 0
        assert ResultsRepository(database).list().eligible_count == 0
        assert len(worker.calls) == 2
        assert len(model.calls) == 2
        assert all(stage == "analysis" for stage, _ in model.calls)
        assert coordinator._owner is None
        await service.shutdown()

    asyncio.run(run())


def test_prompt_choices_freeze_both_stages_and_isolate_cache_keys(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=1)
        model.gate = asyncio.Event()
        custom_initial = "先完整理解来源，再交由第二阶段判断相关性。"
        custom_report = "只讨论深圳坪山龙田，证据不足时保留不确定。"
        admission = await service.create(
            request(
                database,
                initial_prompt={"mode": "custom", "instructions": custom_initial},
                report_prompt={"mode": "custom", "instructions": custom_report},
            )
        )
        await model.entered.wait()
        model.gate.set()
        await finish(service)
        frozen = service.repository.read(admission.job.id)
        assert frozen.initial_prompt.instructions == custom_initial
        assert frozen.initial_prompt.mode == "custom"
        assert frozen.report_prompt.instructions == custom_report
        assert frozen.report_prompt.mode == "custom"
        assert ResultsRepository(database).list().eligible_count == 0
        same_custom = await service.create(
            request(
                database,
                kind="reanalysis",
                result_ids=[1],
                initial_prompt={
                    "mode": "custom",
                    "instructions": custom_initial,
                },
                report_prompt={
                    "mode": "custom",
                    "instructions": custom_report,
                },
            )
        )
        await finish(service)
        reused_custom = service.repository.read(same_custom.job.id)
        assert reused_custom.counts.reused == 1
        assert len(model.calls) == len(worker.calls) == 1

        different_prompt = await service.create(
            request(
                database,
                kind="reanalysis",
                result_ids=[1],
                initial_prompt={"mode": "default"},
                report_prompt={"mode": "default"},
            )
        )
        await finish(service)
        isolated = service.repository.read(different_prompt.job.id)
        assert isolated.counts.reused == 0
        assert len(model.calls) == len(worker.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_search_preview_reuse_is_invalidated_by_richer_detail_evidence(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=1)
        detail_enrich = worker.enrich

        async def preview_only(**kwargs):
            worker.calls.append((kwargs["content_id"], kwargs["term"]))
            return EnrichmentWorkerResult("lookup_miss")

        worker.enrich = preview_only
        first = await service.create(request(database))
        await finish(service)
        original = service.repository.items(first.job.id).items[0]
        assert (
            original.status == "completed"
            and original.input.extractor_version == "wb-search-preview-v1"
            and original.input.evidence_coverage.level == "search_preview"
        )
        assert len(worker.calls) == len(model.calls) == 1

        reused = await service.create(
            request(database, kind="reanalysis", result_ids=[1])
        )
        await finish(service)
        reused_item = service.repository.items(reused.job.id).items[0]
        assert reused_item.reused_from_attempt_id == original.id
        assert reused_item.input_fingerprint == original.input_fingerprint
        assert len(worker.calls) == len(model.calls) == 1

        worker.enrich = detail_enrich
        worker.body = "后来保存的详情正文，与搜索摘要不同。"
        richer = await service.create(
            request(
                database,
                kind="reanalysis",
                result_ids=[1],
                force_refresh=True,
            )
        )
        await finish(service)
        richer_item = service.repository.items(richer.job.id).items[0]
        assert richer_item.reused_from_attempt_id is None
        assert richer_item.input_fingerprint != original.input_fingerprint
        assert len(worker.calls) == len(model.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_failed_known_new_input_cannot_resurrect_old_compatible_text(tmp_path):
    async def run():
        database, _, service, _, model, worker, _ = environment(tmp_path, count=1)
        first = await service.create(request(database))
        await finish(service)
        old = service.repository.items(first.job.id).items[0]
        worker.body = "已知新正文：同名地点发生变化。"
        model.item_answers = ["invalid"]
        refresh = await service.create(
            request(database, kind="reanalysis", result_ids=[1], force_refresh=True)
        )
        await finish(service)
        failed = service.repository.items(refresh.job.id).items[0]
        assert (
            failed.status == "failed"
            and failed.input_fingerprint != old.input_fingerprint
        )
        retry = await service.create(request(database, kind="retry", result_ids=[1]))
        await finish(service)
        assert service.repository.read(retry.job.id).counts.reused == 0
        assert len(worker.calls) == len(model.calls) == 3
        assert service.repository.attempt(old.id) == old
        await service.shutdown()

    asyncio.run(run())


def test_workflow_admission_accepts_mixed_new_retryable_and_reusable_members(
    tmp_path,
):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=4)
        settings = AnalysisSettingsRepository(database).read()
        snapshot = SimpleNamespace(
            ai_configuration_revision=1,
            initial_prompt_version_id=settings.initial_prompt.id,
            report_prompt_version_id=settings.report_prompt.id,
        )

        completed = await service.create(
            request(database, kind="explicit", result_ids=[1])
        )
        await finish(service)
        assert service.repository.read(completed.job.id).counts.completed == 1

        retryable = service.repository.create(
            request(database, kind="explicit", result_ids=[2])
        ).job
        retryable_item = service.repository.items(retryable.id).items[0]
        service.repository.start(retryable.id)
        service.repository.begin(retryable_item.id)
        service.repository.finish_attempt(
            retryable_item.id,
            "input_incomplete",
            error=failure("acquisition", "input_incomplete"),
        )
        service.repository.finish(retryable.id, "completed")
        with database.connect() as connection:
            connection.execute(
                "UPDATE content_analysis_claims SET legacy_state='legacy_completed' "
                "WHERE content_id=4"
            )

        # The public contract remains deliberately strict and atomic.
        with pytest.raises(AnalysisError, match="content_analysis_selection_conflict"):
            service.repository.create(
                request(database, kind="explicit", result_ids=[2, 3, 1, 4])
            )

        operation_key = "automation:run:2:initial_analysis:1"
        admitted = await service.workflow_admit(
            result_ids=(2, 3, 1, 4),
            operation_key=operation_key,
            snapshot=snapshot,
        )
        assert admitted.admitted_count == 4
        assert admitted.already_active_count == 0
        assert admitted.job.trigger == "automatic"
        assert [
            item.source.result_id
            for item in service.repository.items(admitted.job.id).items
        ] == [2, 3, 1, 4]

        await finish(service)
        settled = service.repository.read(admitted.job.id)
        assert settled.status == "completed"
        assert settled.counts.completed == 4
        assert settled.counts.reused == 1
        assert len(model.calls) == len(worker.calls) == 4

        replay = await service.workflow_admit(
            result_ids=(2, 3, 1, 4),
            operation_key=operation_key,
            snapshot=snapshot,
        )
        workflow_payload = WorkflowAnalysisCreate(
            request_id=replay.job.request_id,
            configuration_revision=replay.job.configuration_revision,
            initial_prompt_version_id=replay.job.initial_prompt.id,
            report_prompt_version_id=replay.job.report_prompt.id,
            force_refresh=False,
            result_ids=[2, 3, 1, 4],
        )
        assert replay == service.repository.workflow_replay(
            workflow_payload, operation_key=operation_key
        )
        assert replay.job.id == admitted.job.id
        with pytest.raises(AnalysisError, match="content_analysis_request_conflict"):
            service.repository.create(
                request(
                    database,
                    kind="explicit",
                    result_ids=[2, 3, 1],
                    request_id=replay.job.request_id,
                )
            )
        with pytest.raises(AnalysisError, match="content_analysis_request_conflict"):
            service.repository.workflow_create(
                workflow_payload,
                operation_key="automation:run:999:initial_analysis:1",
            )
        with pytest.raises(AnalysisError, match="content_analysis_request_conflict"):
            service.repository.workflow_create(
                workflow_payload.model_copy(update={"request_id": str(uuid4())}),
                operation_key=operation_key,
            )
        assert len(model.calls) == len(worker.calls) == 4
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_workflow_admission_freezes_active_member_without_duplicate_work(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=2)
        settings = AnalysisSettingsRepository(database).read()
        snapshot = SimpleNamespace(
            ai_configuration_revision=1,
            initial_prompt_version_id=settings.initial_prompt.id,
            report_prompt_version_id=settings.report_prompt.id,
        )
        model.gate = asyncio.Event()
        active = await service.create(
            request(database, kind="explicit", result_ids=[1])
        )
        await model.entered.wait()

        admitted = await service.workflow_admit(
            result_ids=(1, 2),
            operation_key="automation:run:3:initial_analysis:1",
            snapshot=snapshot,
        )
        assert admitted.admitted_count == 1
        assert admitted.already_active_count == 1
        assert admitted.job.counts.total == 2
        assert admitted.job.counts.input_incomplete == 1
        items = service.repository.items(admitted.job.id).items
        assert [item.source.result_id for item in items] == [1, 2]
        assert items[0].status == "input_incomplete"
        assert items[0].error.code == "source_active"
        assert items[1].status == "queued"

        with database.connect() as connection:
            claims = {
                row["content_id"]: row["active_job_id"]
                for row in connection.execute(
                    """SELECT content_id,active_job_id FROM content_analysis_claims
                       WHERE content_id IN (1,2) ORDER BY content_id"""
                )
            }
        assert claims == {1: active.job.id, 2: admitted.job.id}

        model.gate.set()
        await finish(service)
        settled = service.repository.read(admitted.job.id)
        assert settled.status == "completed"
        assert settled.counts.completed == 1
        assert settled.counts.input_incomplete == 1
        assert sorted(content_id for content_id, _ in worker.calls) == ["1000", "1001"]
        assert len(model.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_workflow_admission_supports_uncapped_exact_membership(tmp_path):
    async def run():
        database, _, service, ai, _, _, _ = environment(tmp_path, count=0)
        seed_run(
            database,
            1001,
            terms=tuple(f"批量词-{index}" for index in range(21)),
        )
        settings = AnalysisSettingsRepository(database).read()
        payload = WorkflowAnalysisCreate(
            request_id=str(uuid4()),
            configuration_revision=1,
            initial_prompt_version_id=settings.initial_prompt.id,
            report_prompt_version_id=settings.report_prompt.id,
            force_refresh=False,
            result_ids=list(range(1, 1002)),
        )
        admitted = service.repository.workflow_create(
            payload, operation_key="automation:large-membership:initial-analysis"
        )
        assert admitted.admitted_count == 1001
        assert admitted.already_active_count == 0
        assert admitted.job.counts.total == 1001
        assert admitted.job.counts.queued == 1001
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT content_id,position,status FROM content_analysis_attempts "
                "WHERE job_id=? ORDER BY position",
                (admitted.job.id,),
            ).fetchall()
        assert len(rows) == 1001
        assert rows[0][0:2] == (1, 0)
        assert rows[-1][0:2] == (1001, 1000)
        assert {row[2] for row in rows} == {"queued"}
        # This is an admission-boundary test; cancel the frozen job without
        # starting enrichment or model work.
        service.repository.finish(admitted.job.id, "cancelled")
        assert service.repository.read(admitted.job.id).counts.cancelled == 1001
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_workflow_admission_rolls_back_job_claims_and_replay_on_member_failure(
    tmp_path,
):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path, count=2)
        settings = AnalysisSettingsRepository(database).read()
        snapshot = SimpleNamespace(
            ai_configuration_revision=1,
            initial_prompt_version_id=settings.initial_prompt.id,
            report_prompt_version_id=settings.report_prompt.id,
        )
        operation_key = "automation:run:4:initial_analysis:1"
        with database.connect() as connection:
            connection.execute(
                """CREATE TRIGGER fail_workflow_member
                   BEFORE INSERT ON content_analysis_attempts WHEN NEW.position=1
                   BEGIN SELECT RAISE(ABORT,'private workflow sentinel'); END"""
            )

        with pytest.raises(AnalysisError, match="analysis_storage_unavailable"):
            await service.workflow_admit(
                result_ids=(1, 2),
                operation_key=operation_key,
                snapshot=snapshot,
            )

        with database.connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM content_analysis_jobs"
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM content_analysis_attempts"
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM content_analysis_requests"
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    """SELECT COUNT(*) FROM content_analysis_claims
                   WHERE active_job_id IS NOT NULL OR first_attempt_id IS NOT NULL
                     OR latest_attempt_id IS NOT NULL"""
                ).fetchone()[0]
                == 0
            )
            connection.execute("DROP TRIGGER fail_workflow_member")

        admitted = await service.workflow_admit(
            result_ids=(1, 2),
            operation_key=operation_key,
            snapshot=snapshot,
        )
        await finish(service)
        assert service.repository.read(admitted.job.id).counts.completed == 2
        assert len(model.calls) == len(worker.calls) == 2
        await service.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_cancel_preserves_success_suppresses_event_and_requires_explicit_retry(
    tmp_path,
):
    async def run():
        database, _, service, _, model, worker, _ = environment(tmp_path)
        original = model.complete
        gate, entered = asyncio.Event(), asyncio.Event()

        async def block_second(configuration, **kwargs):
            if len(model.calls) == 1:
                entered.set()
                await gate.wait()
            return await original(configuration, **kwargs)

        model.complete = block_second
        first = await service.create(request(database))
        await entered.wait()
        cancelled = await service.cancel(first.job.id)
        assert cancelled.status == "cancelled" and cancelled.counts.completed == 1
        assert cancelled.counts.cancelled == 1 and cancelled.completion_event_id is None
        assert service.repository.completion_events() == []
        assert ResultsRepository(database).list().eligible_count == 0
        assert (await service.create(request(database))).job is None
        assert len(worker.calls) == 2
        gate.set()
        retry = await service.create(request(database, kind="retry", result_ids=[2]))
        await finish(service)
        assert service.repository.read(retry.job.id).counts.completed == 1
        assert service.repository.read(first.job.id).counts.completed == 1
        await service.shutdown()

    asyncio.run(run())


def test_restart_reconciles_without_calls_and_late_callbacks_fail_closed(tmp_path):
    database, _, service, _, model, worker, _ = environment(tmp_path)
    job = service.repository.create(request(database)).job
    attempt = service.repository.items(job.id).items[0]
    service.repository.start(job.id)
    service.repository.begin(attempt.id)
    restarted = ContentAnalysisRepository(database)
    restarted.initialize()
    assert restarted.read(job.id).status == "interrupted"
    assert restarted.read(job.id).counts.interrupted == 2
    assert ResultsRepository(database).list().active_count == 0
    assert ResultsRepository(database).list().eligible_count == 0
    assert model.calls == worker.calls == []
    with pytest.raises(AnalysisError, match="content_analysis_selection_conflict"):
        service.repository.mark_attempt(attempt.id)
    assert restarted.completion_events() == []


def test_busy_browser_stays_queued_without_attempt_and_release_allows_progress(
    tmp_path,
):
    async def run():
        database, _, service, _, model, worker, coordinator = environment(
            tmp_path, count=1
        )
        owner = BrowserOperationOwner("search_batch", uuid4())
        assert await coordinator.try_claim(owner)
        job = (await service.create(request(database))).job
        for _ in range(100):
            current = service.repository.read(job.id)
            if current.queue_reason:
                break
            await asyncio.sleep(0.01)
        assert current.queue_reason == "browser_operation_active"
        assert current.counts.queued == 1 and current.usage.attempted_requests == 0
        assert worker.calls == model.calls == []
        await coordinator.release(owner)
        await finish(service)
        assert service.repository.read(job.id).counts.completed == 1
        await service.shutdown()

    asyncio.run(run())


def test_provider_changed_while_queued_settles_claims_without_calls(tmp_path):
    async def run():
        database, _, service, ai, model, worker, _ = environment(tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()
        original = ai.operation
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def delayed(revision):
            entered.set()
            await release.wait()
            async with original(revision) as configuration:
                yield configuration

        ai.operation = delayed
        job = (await service.create(request(database))).job
        await entered.wait()
        settings = ai.read()
        ai.save(AISettingsUpdate(base_url=settings.base_url, model="changed-model"))
        release.set()
        await finish(service)
        current = service.repository.read(job.id)
        assert current.status == "configuration_blocked"
        assert current.counts.interrupted == 2 and current.completion_event_id is None
        assert ResultsRepository(database).list().active_count == 0
        assert worker.calls == model.calls == []
        await service.shutdown()

    asyncio.run(run())


def test_admission_at_empty_queue_exit_cannot_strand_work(tmp_path):
    async def run():
        database, _, service, _, model, _, _ = environment(tmp_path, count=1)
        original = service.repository.next_job
        empty_seen, release = threading.Event(), threading.Event()
        blocked = False

        def pause_empty():
            nonlocal blocked
            job = original()
            if job is None and not blocked:
                blocked = True
                empty_seen.set()
                assert release.wait(5)
            return job

        service.repository.next_job = pause_empty
        await service.create(request(database))
        assert await asyncio.to_thread(empty_seen.wait, 5)
        seed_run(database, 1, start=9000)
        second = await service.create(request(database))
        assert second.admitted_count == 1
        release.set()
        await finish(service)
        assert service.repository.read(second.job.id).counts.completed == 1
        assert len(model.calls) == 2
        await service.shutdown()

    asyncio.run(run())


def test_legacy_active_claim_and_new_active_claim_exclude_both_paths(tmp_path):
    async def run():
        database, source, service, ai, model, worker, _ = environment(tmp_path, count=1)
        legacy = SummaryService(
            database=database, ai_settings=ai, enrichment=service._enrichment
        )
        legacy.initialize()
        model.gate = asyncio.Event()
        old = await legacy.create(
            source,
            SummaryCreate(
                request_id=str(uuid4()), force_refresh=False, configuration_revision=1
            ),
        )
        await model.entered.wait()
        excluded = service.repository.create(request(database))
        assert excluded.job is None and excluded.already_active_count == 1
        await legacy.cancel(old.id)
        assert ResultsRepository(database).read(1).analysis_state == "legacy_attempted"
        assert service.repository.create(request(database)).job is None
        new = service.repository.create(
            request(database, kind="retry", result_ids=[1])
        ).job
        with pytest.raises(AIError, match="ai_operation_active"):
            await legacy.create(
                source,
                SummaryCreate(
                    request_id=str(uuid4()),
                    force_refresh=False,
                    configuration_revision=1,
                ),
            )
        assert service.repository.read(new.id).counts.total == 1
        await service.shutdown()
        await legacy.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize(
    "usage,known",
    [
        (None, False),
        (
            AIUsage(
                prompt_tokens=MAX_USAGE_TOKENS,
                completion_tokens=0,
                total_tokens=MAX_USAGE_TOKENS,
            ),
            True,
        ),
    ],
)
def test_unknown_and_overflow_usage_are_not_zero(tmp_path, usage, known):
    async def run():
        database, _, service, _, model, _, _ = environment(tmp_path)
        model.usage = usage
        job = (await service.create(request(database))).job
        await finish(service)
        result = service.repository.read(job.id)
        assert result.counts.completed == 2
        assert result.usage.accounted_requests == (2 if known else 0)
        assert result.usage.total_tokens is None and result.usage.complete is False
        await service.shutdown()

    asyncio.run(run())


def test_cancel_drains_inflight_success_write_before_releasing_browser(tmp_path):
    database, _, service, _, model, _, coordinator = environment(tmp_path, count=2)
    entered, release = threading.Event(), threading.Event()
    original = service.repository.finish_attempt

    def delayed(*args, **kwargs):
        if args[1] == "completed":
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    service.repository.finish_attempt = delayed

    async def run():
        job = (await service.create(request(database))).job
        assert await asyncio.to_thread(entered.wait, 5)
        cancelling = asyncio.create_task(service.cancel(job.id))
        await asyncio.sleep(0)
        assert not cancelling.done() and coordinator._owner is not None
        release.set()
        result = await asyncio.wait_for(cancelling, 5)
        assert result.status == "cancelled" and result.counts.completed == 1
        assert result.counts.cancelled == 1 and result.completion_event_id is None
        assert result.usage.total_tokens == 15 and len(model.calls) == 1
        assert coordinator._owner is None
        await service.shutdown()

    asyncio.run(run())


def test_ambiguous_cancelled_post_still_admits_once_under_its_uuid(tmp_path):
    database, _, service, _, model, _, _ = environment(tmp_path, count=1)
    entered, release = threading.Event(), threading.Event()
    original = service.repository.create
    payload = request(database)

    def delayed(value):
        admitted = original(value)
        entered.set()
        assert release.wait(5)
        return admitted

    service.repository.create = delayed

    async def run():
        posting = asyncio.create_task(service.create(payload))
        assert await asyncio.to_thread(entered.wait, 5)
        posting.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await posting
        await finish(service)
        replay = await service.create(payload)
        assert replay.admitted_count == 1 and replay.job.counts.completed == 1
        assert len(model.calls) == 1
        assert len(service.repository.list().jobs) == 1
        await service.shutdown()

    asyncio.run(run())
