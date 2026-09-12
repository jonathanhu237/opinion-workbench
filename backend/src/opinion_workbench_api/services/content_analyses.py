"""Lifespan-owned stage-one queue; independent evidence precedes report handoff."""

import asyncio
import hashlib
import logging
import time
import traceback
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from opinion_workbench_api.repositories.content_analyses import (
    ContentAnalysisRepository,
)
from opinion_workbench_api.repositories.search_runs import SearchResultSourceRecord
from opinion_workbench_api.schemas.ai_summaries import FailureCode, ModelRetryNotice
from opinion_workbench_api.schemas.analysis_evidence import SavedInput
from opinion_workbench_api.schemas.analysis_settings import PromptSnapshot
from opinion_workbench_api.schemas.content_analyses import (
    AnalysisCreate,
    WorkflowAnalysisCreate,
)
from opinion_workbench_api.schemas.platform_access import (
    default_platform_access_snapshot,
)
from opinion_workbench_api.services.ai_analysis import (
    ANALYSIS_MAX_TOKENS,
    MODEL_DEADLINE_SECONDS,
    AIAnalysisError,
)
from opinion_workbench_api.services.ai_client import AICompletion, AIUsage
from opinion_workbench_api.services.ai_errors import (
    MANUAL_SYSTEMIC_AI_FAILURES,
    AIError,
)
from opinion_workbench_api.services.analysis_errors import AnalysisError
from opinion_workbench_api.services.content_enrichment import ContentEnrichmentError
from opinion_workbench_api.services.content_understanding import (
    build_understanding_messages,
    parse_understanding,
)
from opinion_workbench_api.services.manual_content import (
    ManualAcquisitionPause,
    ManualContentSession,
)
from opinion_workbench_api.services.model_retry import (
    RETRYABLE_OUTPUT_ERRORS,
    ModelRateLimitEvent,
    ModelRateLimitGate,
)
from opinion_workbench_api.services.settled_tasks import database_call, settle
from opinion_workbench_api.services.summary_errors import (
    FAILURE_MESSAGES,
    failure,
    provider_diagnostic,
)


class BrowserAcquisitionStopped(Exception):
    """A shared browser failure must not fan out to every selected item."""


class ContentAnalysisService:
    def __init__(
        self, *, database, ai_settings, enrichment, available=False, repository=None
    ):
        self.repository = repository or ContentAnalysisRepository(database)
        self._ai, self._enrichment = ai_settings, enrichment
        self.available = available
        self._admission = asyncio.Lock()
        self._runner: asyncio.Task | None = None
        self._active_id: int | None = None
        self._closed = False
        self.on_job_finished = None
        self.on_manual_configuration_failure = None
        self.on_manual_acquisition_pause = None
        self.on_manual_job_cancel = None
        # Set before the queue runner is cancelled so consumers that have not
        # entered a model call yet cannot cross the cancellation boundary.
        self._active_stop_event: asyncio.Event | None = None

    def initialize(self):
        self.repository.initialize()  # Storage reconciliation only, never launch.

    async def create(self, payload: AnalysisCreate):
        return await settle(self._create(payload))

    async def start_pending(self):
        """Run already committed jobs without admitting another intent."""
        async with self._admission:
            if self._closed:
                raise AnalysisError("content_analysis_unavailable")
            await self._launch()

    async def workflow_admit(self, *, result_ids, operation_key, snapshot):
        """Admit topic-neutral understanding for one workflow membership.

        The workflow owns the selected IDs and operation key.  Workflow
        admission has its own mixed-selection repository contract: the public
        explicit/retry/reanalysis semantics stay strict while a single
        workflow job can contain never-started, recoverable and reusable
        completed members.  The task-specific objective is consumed only by
        the report stage.
        """
        if not result_ids:
            return None
        configuration_revision = getattr(snapshot, "ai_configuration_revision", None)
        if configuration_revision is None:
            raise AIError("ai_configuration_required")
        initial_prompt = getattr(snapshot, "initial_prompt", None)
        report_prompt = getattr(snapshot, "report_prompt", None)
        initial_version_id = getattr(snapshot, "initial_prompt_version_id", None) or (
            initial_prompt.version_id if initial_prompt is not None else None
        )
        report_version_id = getattr(snapshot, "report_prompt_version_id", None) or (
            report_prompt.version_id if report_prompt is not None else None
        )
        if initial_version_id is None or report_version_id is None:
            raise AIError("ai_configuration_required")
        # Version IDs preserve the exact immutable row.  For task-local custom
        # text that happens to equal the built-in template, also carry the
        # explicit choice so admission cannot infer the source as ``default``.
        initial_choice = _workflow_prompt_choice(initial_prompt)
        report_choice = _workflow_prompt_choice(report_prompt)
        platform_access_snapshot = getattr(snapshot, "platform_access_snapshot", None)
        if platform_access_snapshot is None:
            platform_access_snapshot = default_platform_access_snapshot(
                basis="upgrade_safe_default"
            )
        payload = WorkflowAnalysisCreate(
            request_id=_operation_request_id(operation_key),
            configuration_revision=configuration_revision,
            initial_prompt_version_id=initial_version_id,
            report_prompt_version_id=report_version_id,
            initial_prompt_mode=(
                initial_prompt.mode if initial_prompt is not None else None
            ),
            report_prompt_mode=(
                report_prompt.mode if report_prompt is not None else None
            ),
            initial_prompt=initial_choice,
            report_prompt=report_choice,
            platform_access_snapshot=platform_access_snapshot,
            force_refresh=False,
            result_ids=list(result_ids),
        )
        return await settle(self._workflow_admit(payload, operation_key))

    async def _workflow_admit(
        self, payload: WorkflowAnalysisCreate, operation_key: str
    ):
        async with self._admission:
            replay = await database_call(
                self.repository.workflow_replay,
                payload,
                operation_key=operation_key,
            )
            if replay is not None:
                return replay
            if self._closed:
                raise AnalysisError("content_analysis_unavailable")
            await database_call(self._ai.read)
            workflow_create = getattr(self.repository, "workflow_create", None)
            if workflow_create is None:
                raise AnalysisError("content_analysis_unavailable")
            result = await database_call(
                workflow_create,
                payload,
                operation_key=operation_key,
            )
            if result.job is not None:
                await self._launch()
            return result

    async def _create(self, payload):
        async with self._admission:
            replay = await database_call(self.repository.replay, payload)
            if replay is not None:
                return replay
            # ``available`` controls the legacy collection-completion handoff,
            # not the independently callable analysis API.  Manual analysis
            # must remain usable when the old automatic path is disabled; the
            # fixed workflow performs its own availability checks at admission.
            if self._closed:
                raise AnalysisError("content_analysis_unavailable")
            await database_call(
                self._ai.read
            )  # Credentials checked, not retained by admission.
            result = await database_call(self.repository.create, payload)
            if result.job is not None:
                await self._launch()
            return result

    async def collection_finished(self, kind, identity):
        # Collection remains successful even if downstream storage is unavailable.
        # Discovery claims already committed with the sources are retained.
        async with self._admission:
            if self._closed:
                return
            result = await database_call(
                self.repository.collection_finished,
                kind,
                identity,
                available=self.available,
            )
            if result is not None and result.job is not None:
                await self._launch()

    async def _launch(self):
        if self._runner is None or self._runner.done():
            started = asyncio.Event()
            self._runner = asyncio.create_task(
                self._run(started), name="content-analysis-queue"
            )
            self._runner.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            await started.wait()

    async def cancel(self, job_id):
        if self.on_manual_job_cancel is not None:
            manual = await self.on_manual_job_cancel(job_id)
            if manual is not None:
                return manual
        return await self.cancel_owned(job_id)

    async def cancel_owned(self, job_id):
        return await settle(self._cancel(job_id))

    async def _cancel(self, job_id):
        async with self._admission:
            job = await database_call(self.repository.read, job_id)
            if job.status not in ("queued", "running") and self._active_id != job_id:
                return job
            if self._active_id == job_id and self._runner is not None:
                if self._active_stop_event is not None:
                    self._active_stop_event.set()
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))
            else:
                await database_call(self.repository.finish, job_id, "cancelled")
            if not self._closed:
                await self._launch()
            return await database_call(self.repository.read, job_id)

    async def shutdown(self):
        async with self._admission:
            self._closed = True
            if self._runner is not None and not self._runner.done():
                if self._active_stop_event is not None:
                    self._active_stop_event.set()
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))
            # Settle never-executed queued jobs too; do not leave stale active claims.
            await database_call(self.repository.initialize)

    async def _run(self, started):
        started.set()
        try:
            while not self._closed:
                job = await database_call(self.repository.next_job)
                if job is None:
                    # An enqueue must be observed here or see a free runner slot.
                    async with self._admission:
                        job = await database_call(self.repository.next_job)
                        if job is None:
                            self._runner = None
                            return
                self._active_id = job.id
                try:
                    if (
                        job.platform_access_snapshot is not None
                        and job.platform_access_snapshot.basis == "legacy_unavailable"
                    ):
                        materialized = default_platform_access_snapshot(
                            basis="upgrade_safe_default"
                        )
                        ensure_snapshot = getattr(
                            self.repository, "ensure_platform_access_snapshot", None
                        )
                        if callable(ensure_snapshot):
                            await database_call(ensure_snapshot, job.id, materialized)
                            job = await database_call(self.repository.read, job.id)
                    # Validate the frozen provider revision before touching a
                    # source, but do not hold the global AI lease around the
                    # serial browser producer. A queued job must not hold the
                    # lease while waiting for a platform interval or browser
                    # ownership; ready model work from another task can then
                    # make progress.
                    async with self._ai.operation(job.configuration_revision):
                        pass
                    await self._execute(job, None)
                except ManualAcquisitionPause:
                    # The parent excludes this job until an explicit Continue.
                    # Release the AI lease so stored-only work can proceed.
                    pass
                except BrowserAcquisitionStopped:
                    await database_call(self.repository.finish, job.id, "interrupted")
                except AIError as error:
                    if error.code == "ai_operation_active":
                        await database_call(
                            self.repository.queue, job.id, "ai_operation_active"
                        )
                        await asyncio.sleep(0.25)
                        continue
                    if (
                        error.code in MANUAL_SYSTEMIC_AI_FAILURES
                        and self.on_manual_configuration_failure is not None
                        and await database_call(
                            self.repository.is_report_generation, job.id
                        )
                    ):
                        await self.on_manual_configuration_failure(
                            job.configuration_revision, error
                        )
                    await database_call(
                        self.repository.finish, job.id, "configuration_blocked"
                    )
                except ContentEnrichmentError as error:
                    if error.code == "browser_operation_active":
                        await database_call(
                            self.repository.queue, job.id, "browser_operation_active"
                        )
                        await asyncio.sleep(0.25)
                        continue
                    # Unsettled ownership cannot safely proceed to another item.
                    logging.getLogger(__name__).error(
                        "Analysis job %s acquisition stopped: %s", job.id, error.code
                    )
                    await database_call(self.repository.finish, job.id, "interrupted")
                except AnalysisError as error:
                    # A storage write may have failed: settle history if possible,
                    # never retry an ambiguous model request automatically.
                    logging.getLogger(__name__).error(
                        "Analysis job %s storage stopped: %s", job.id, error.code
                    )
                    await database_call(self.repository.finish, job.id, "interrupted")
                self._active_id = None
        except asyncio.CancelledError:
            if self._active_id is not None:
                await database_call(
                    self.repository.finish,
                    self._active_id,
                    "interrupted" if self._closed else "cancelled",
                )
            raise
        except Exception as error:
            # Exception messages may contain source text or provider secrets.
            # Keep only the type and code locations for operational diagnosis.
            logging.getLogger(__name__).error(
                "Analysis job %s stopped (%s): %s",
                self._active_id,
                type(error).__name__,
                "; ".join(
                    f"{frame.name}:{frame.lineno}"
                    for frame in traceback.extract_tb(error.__traceback__)
                ),
            )
            if self._active_id is not None:
                await database_call(
                    self.repository.finish, self._active_id, "interrupted"
                )
        finally:
            self._active_id = None

    async def _execute(self, job, configuration):
        manual_generation = await database_call(
            self.repository.is_report_generation, job.id
        )
        while not self._closed:
            attempt = await database_call(self.repository.next_attempt, job.id)
            if attempt is None:
                await database_call(self.repository.finish, job.id, "completed")
                if self.on_job_finished is not None:
                    try:
                        await self.on_job_finished(job.id)
                    except Exception:
                        # The durable event remains pending. A report admission
                        # failure cannot undo A settlement or strand A's queue.
                        pass
                return
            if manual_generation:
                return await self._execute_concurrent(job, configuration, manual=True)
            if not job.force_refresh and await database_call(
                self.repository.reuse, attempt.id
            ):
                await database_call(self.repository.start, job.id)
                continue
            return await self._execute_concurrent(job, configuration)

    async def _execute_concurrent(self, job, configuration, *, manual=False):
        """Enrich serially and fan out only the bounded model stage.

        Browser admission is deliberately completed before consumers are
        created.  A failed ``operation()`` entry therefore reaches the queue
        supervisor directly instead of leaving consumers waiting on an empty
        queue.  The producer and consumers remain one failure domain so a
        later producer or worker failure also tears down every peer.
        """
        concurrency = int(getattr(job, "summary_concurrency", 1) or 1)
        # The public setting belongs only to manual report generation.  Keep
        # the shared executor's legacy/automatic entry points serial even if a
        # historical or injected job happens to carry a larger value.
        if not manual or concurrency not in (1, 2, 4, 8, 16):
            concurrency = 1
        ready: asyncio.Queue = asyncio.Queue(maxsize=concurrency)
        stop_event = asyncio.Event()
        self._active_stop_event = stop_event
        rate_limited_attempts: set[int] = set()

        async def on_access_waiting(platform, seconds, stage):
            setter = getattr(self.repository, "set_access_waiting", None)
            if callable(setter):
                await database_call(
                    setter,
                    job.id,
                    None
                    if not seconds
                    else {
                        "platform": platform,
                        "stage": stage,
                        "seconds": round(float(seconds), 3),
                    },
                )

        async def on_access_notice(platform, diagnostic):
            setter = getattr(self.repository, "set_access_notice", None)
            if callable(setter):
                await database_call(setter, job.id, diagnostic)

        async def on_model_retry(event: ModelRateLimitEvent):
            details = event.context
            if not isinstance(details, dict):
                return
            attempt_id = details.get("attempt_id")
            if not isinstance(attempt_id, int):
                return
            setter = getattr(self.repository, "record_model_rate_limit", None)
            if not callable(setter):
                # Older injected repositories cannot persist per-network
                # history. Do not suppress a validated usage value from the
                # terminal attempt just because that optional projection is
                # unavailable.
                return
            rate_limited_attempts.add(attempt_id)
            notice = ModelRetryNotice(
                stage="analysis",
                retry_number=min(event.retry_number, 100),
                wait_seconds=min(max(event.delay_seconds, 0.0), 60.0),
                action="retrying" if event.will_retry else "exhausted",
                provider_diagnostic=provider_diagnostic(event.error),
                observed_at=datetime.now(UTC),
            )
            await database_call(setter, attempt_id, event.usage, notice)

        model_rate_limit = ModelRateLimitGate(on_retry=on_model_retry)
        model_lease = AsyncExitStack()
        model_lease_lock = asyncio.Lock()
        model_configuration = None
        model_lease_closed = False

        async def configuration_for_model():
            nonlocal model_configuration
            async with model_lease_lock:
                if model_configuration is None:
                    model_configuration = await model_lease.enter_async_context(
                        self._ai.operation(job.configuration_revision)
                    )
                return model_configuration

        async def close_model_lease():
            nonlocal model_lease_closed
            if not model_lease_closed:
                model_lease_closed = True
                await model_lease.aclose()

        async def produce_loop(session=None) -> ManualAcquisitionPause | None:
            pause: ManualAcquisitionPause | None = None
            try:
                while not self._closed and not stop_event.is_set():
                    attempt = await database_call(
                        self.repository.next_attempt,
                        job.id,
                        prefer_reusable=not job.force_refresh,
                        allow_preview=False,
                    )
                    if attempt is None:
                        break
                    # Cache/reuse is decided before browser acquisition. The
                    # repository prioritizes reusable summaries and saved
                    # detail inputs so an earlier URL-only item cannot block a
                    # later source that is already usable offline.
                    if not job.force_refresh and await database_call(
                        self.repository.reuse,
                        attempt.id,
                        allow_preview=False,
                    ):
                        await database_call(self.repository.start, job.id)
                        continue
                    await database_call(self.repository.start, job.id)
                    await database_call(self.repository.begin, attempt.id)
                    if manual:
                        item_session = ManualContentSession(
                            attempt,
                            enrichment=self._enrichment,
                            database=self.repository.database,
                            on_pause=self.on_manual_acquisition_pause,
                            access_snapshot=job.platform_access_snapshot,
                            on_access_waiting=on_access_waiting,
                            on_access_notice=on_access_notice,
                        )
                    else:
                        item_session = session
                    candidate = await self._prepare_attempt(
                        attempt, item_session, allow_preview=False
                    )
                    if candidate is not None and not stop_event.is_set():
                        await ready.put((attempt, candidate))
                    await asyncio.sleep(0)
            except ManualAcquisitionPause as error:
                # The parent pause is already durable. Drain acquired peers
                # before returning so their model work is not discarded.
                pause = error
            except asyncio.CancelledError:
                raise
            # Sentinels are emitted only for the normal/pause path. If the
            # producer itself fails, the supervisor cancels consumers directly;
            # this avoids a second blocking await while a queue is full.
            for _ in range(concurrency):
                await ready.put(None)
            return pause

        async def systemic_model_failure(revision, error):
            # Fence producer admission before awaiting the durable cross-task
            # configuration block. Peers already inside the provider call are
            # settled by the supervisor; no later queued candidate may start.
            stop_event.set()
            if self.on_manual_configuration_failure is not None:
                await self.on_manual_configuration_failure(
                    revision,
                    error,
                )

        async def consume():
            while True:
                value = await ready.get()
                if value is None:
                    return
                attempt, candidate = value
                if stop_event.is_set() or self._closed:
                    continue
                try:
                    configuration = await configuration_for_model()
                    # Configuration acquisition is awaitable. Re-check after
                    # it so cancellation cannot turn a queued candidate into a
                    # new paid request while another consumer is unwinding.
                    if stop_event.is_set() or self._closed:
                        continue
                    await self._analyse_model(
                        attempt,
                        candidate,
                        configuration,
                        job.initial_prompt,
                        stop_on_systemic_error=manual,
                        model_rate_limit=model_rate_limit,
                        retry_context={
                            "attempt_id": attempt.id,
                            "stage": "analysis",
                        },
                        rate_limited_attempts=rate_limited_attempts,
                        on_systemic_error=systemic_model_failure,
                    )
                except asyncio.CancelledError:
                    raise
                except BaseException:
                    # Let the supervisor observe the original exception and
                    # tear down every peer, but stop new producer work first.
                    stop_event.set()
                    raise

        async def run_pipeline(session=None):
            producer = asyncio.create_task(
                produce_loop(session), name=f"analysis-producer-{job.id}"
            )
            workers = [
                asyncio.create_task(consume(), name=f"analysis-consumer-{job.id}-{i}")
                for i in range(concurrency)
            ]

            async def join_workers():
                return await asyncio.gather(*workers)

            worker_join = asyncio.create_task(
                join_workers(), name=f"analysis-consumers-{job.id}"
            )
            try:
                # FIRST_EXCEPTION is the important ownership boundary: neither
                # a failed producer nor a failed worker may leave the other side
                # waiting forever for a sentinel.
                done, _ = await asyncio.wait(
                    (producer, worker_join), return_when=asyncio.FIRST_EXCEPTION
                )
                for task in done:
                    if task.cancelled():
                        raise asyncio.CancelledError
                    error = task.exception()
                    if error is not None:
                        raise error
                # FIRST_EXCEPTION also returns when the producer finishes
                # normally.  Do not publish the parent completion or release
                # the shared model lease until every consumer has drained its
                # sentinel and all per-item writes have settled.
                await asyncio.gather(producer, worker_join)
                producer_result = producer.result()
                if isinstance(producer_result, ManualAcquisitionPause):
                    await close_model_lease()
                    return
                # Publish completion while the task's stable model lease is
                # still held.  The callback is admission-only and may launch a
                # report runner; that runner queues behind this lease and
                # retries after the lease is released below.  Keeping this
                # order preserves the existing callback contract without
                # allowing any extra model request in this task.
                await database_call(self.repository.finish, job.id, "completed")
                if self.on_job_finished is not None:
                    try:
                        await self.on_job_finished(job.id)
                    except Exception:
                        # Completion is durable; downstream handoff can be
                        # reconciled without replaying any model request.
                        pass
                # No consumer remains after worker_join has settled. Release
                # before returning to the queue supervisor/report poller.
                await close_model_lease()
            except BaseException:
                stop_event.set()
                if not producer.done():
                    producer.cancel()
                if not worker_join.done():
                    worker_join.cancel()
                for worker in workers:
                    if not worker.done():
                        worker.cancel()
                await settle(
                    asyncio.gather(
                        producer, worker_join, *workers, return_exceptions=True
                    )
                )
                await settle(close_model_lease())
                raise

        # Enter the browser operation before launching the pipeline.  Manual
        # report work enters per-item operations only when it has to acquire a
        # missing source, so stored evidence can still drain without Chrome.
        try:
            async with AsyncExitStack() as stack:
                session = None
                if not manual:
                    session = await stack.enter_async_context(
                        self._enrichment.operation(
                            access_snapshot=job.platform_access_snapshot,
                            on_access_waiting=on_access_waiting,
                            on_access_notice=on_access_notice,
                        )
                    )
                await run_pipeline(session)
        finally:
            if self._active_stop_event is stop_event:
                self._active_stop_event = None

    async def _prepare_attempt(self, attempt, session, *, allow_preview):
        """Acquire and durably save one immutable input while owning the browser."""
        source = attempt.source
        expected = _expected_source(source)
        try:
            async with session.item(
                run_id=source.source_run_id,
                result_id=source.result_id,
                expected_source=expected,
            ) as acquired:
                if acquired.outcome == "browser_unavailable":
                    await database_call(
                        self.repository.finish_attempt,
                        attempt.id,
                        "failed",
                        error=failure("acquisition", "browser_unavailable"),
                    )
                    raise BrowserAcquisitionStopped()
                if acquired.detail_analysis_eligible:
                    candidate = acquired
                    saved_input = SavedInput.from_content(acquired.content)
                    input_fingerprint = acquired.input_fingerprint
                elif (
                    allow_preview
                    and acquired.outcome != "access_denied"
                    and acquired.preview_analysis_eligible
                ):
                    candidate = acquired.as_preview()
                    saved_input = SavedInput.from_preview(
                        platform=source.platform,
                        title=source.title,
                        snippet=source.snippet,
                        acquired_at=time.time_ns() // 1_000_000,
                    )
                    input_fingerprint = candidate.input_fingerprint
                else:
                    candidate = acquired
                    saved_input = None
                    input_fingerprint = None
                if saved_input is not None:
                    await database_call(
                        self.repository.save_input,
                        attempt.id,
                        saved_input,
                        input_fingerprint,
                    )
                if saved_input is None or not candidate.analysis_eligible:
                    status = (
                        "unsupported"
                        if acquired.content and acquired.content.status == "unsupported"
                        else "input_incomplete"
                    )
                    await database_call(
                        self.repository.finish_attempt,
                        attempt.id,
                        status,
                        error=failure(
                            "acquisition",
                            "input_incomplete"
                            if acquired.content
                            else cast(
                                FailureCode,
                                {
                                    "content_unavailable": "source_content_unavailable",
                                    "lookup_miss": "source_content_unavailable",
                                    "access_denied": "source_access_denied",
                                    "structure_changed": "source_structure_changed",
                                    "timed_out": "acquisition_timed_out",
                                }.get(acquired.outcome, "acquisition_failed"),
                            ),
                            diagnostic=acquired.diagnostic,
                        ),
                    )
                    return None
                return candidate
        except ContentEnrichmentError as error:
            if error.code in (
                "worker_unsettled",
                "service_unavailable",
                "staging_unavailable",
                "browser_operation_active",
            ):
                raise
            code = cast(
                FailureCode,
                error.code
                if error.code
                in (
                    "source_active",
                    "source_changed",
                    "invalid_enrichment",
                    "stored_content_unavailable",
                    "platform_not_supported",
                )
                else "acquisition_failed",
            )
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                "unsupported"
                if code == "platform_not_supported"
                else "input_incomplete",
                error=failure("acquisition", code),
            )
            return None

    async def _analyse(
        self,
        attempt,
        session,
        configuration,
        prompt,
        *,
        allow_preview=False,
        stop_on_systemic_error=False,
    ):
        candidate = await self._prepare_attempt(
            attempt, session, allow_preview=allow_preview
        )
        if candidate is not None:
            await self._analyse_model(
                attempt,
                candidate,
                configuration,
                prompt,
                stop_on_systemic_error=stop_on_systemic_error,
            )

    async def _analyse_model(
        self,
        attempt,
        candidate,
        configuration,
        prompt,
        *,
        stop_on_systemic_error=False,
        model_rate_limit=None,
        retry_context=None,
        rate_limited_attempts=None,
        on_systemic_error=None,
    ):
        usage = None
        try:
            messages = await settle(
                asyncio.to_thread(
                    build_understanding_messages, configuration, candidate, prompt
                )
            )
            await database_call(self.repository.mark_attempt, attempt.id)
            for attempt_number in range(2):
                usage = None
                complete = self._ai.complete
                if model_rate_limit is not None:
                    completion = await model_rate_limit.complete(
                        complete,
                        configuration,
                        messages=messages,
                        max_tokens=ANALYSIS_MAX_TOKENS,
                        deadline=MODEL_DEADLINE_SECONDS,
                        retry_context=retry_context,
                    )
                else:
                    completion = await complete(
                        configuration,
                        messages=messages,
                        max_tokens=ANALYSIS_MAX_TOKENS,
                        deadline=MODEL_DEADLINE_SECONDS,
                    )
                usage = _observed_usage(getattr(completion, "usage", None))
                # Parser and repository boundaries must see the same validated
                # transport accounting. A malformed usage object is an unknown
                # request, not an exception that can interrupt the whole job.
                completion = AICompletion(completion.text, usage)
                try:
                    output = parse_understanding(
                        completion, api_key=configuration.api_key
                    )
                    break
                except AIAnalysisError as error:
                    if attempt_number or error.code not in RETRYABLE_OUTPUT_ERRORS:
                        raise
                    await database_call(self.repository.mark_retry, attempt.id, usage)
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                "completed",
                output=output,
                usage=usage,
            )
        except AIAnalysisError as error:
            status = (
                "unsupported"
                if error.code == "unsupported_model"
                else ("input_incomplete" if error.stage == "input" else "failed")
            )
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                status,
                error=failure(
                    "input" if error.stage == "input" else "analysis",
                    error.code,
                    validation_issues=error.validation_issues,
                ),
                usage=error.usage or usage,
            )
        except AIError as error:
            code = cast(
                FailureCode,
                error.code if error.code in FAILURE_MESSAGES else "internal_error",
            )
            rate_limit_seen = (
                rate_limited_attempts is not None
                and attempt.id in rate_limited_attempts
            )
            final_usage = (
                None
                if error.transient_rate_limit and rate_limit_seen
                else getattr(error, "usage", None) or usage
            )
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                "failed",
                error=failure(
                    "analysis",
                    code,
                    provider_diagnostic=provider_diagnostic(error),
                ),
                usage=final_usage,
            )
            if (
                stop_on_systemic_error
                and error.code in MANUAL_SYSTEMIC_AI_FAILURES
                and not error.transient_rate_limit
            ):
                callback = on_systemic_error or self.on_manual_configuration_failure
                if callback is not None:
                    await callback(configuration.revision, error)
                raise


def _observed_usage(value):
    if value is None:
        return None
    try:
        if isinstance(value, AIUsage):
            value = value.model_dump(mode="json")
        return AIUsage.model_validate(value)
    except (TypeError, ValueError):
        return None


def _expected_source(source: SearchResultSourceRecord) -> SearchResultSourceRecord:
    return SearchResultSourceRecord(
        run_id=source.source_run_id,
        result_id=source.result_id,
        platform=source.platform,
        platform_content_id=source.platform_content_id,
        content_type=source.content_type,
        content_url=source.content_url,
        title=source.title,
        snippet=source.snippet,
        matched_terms=tuple(source.matched_terms),
        collection_active=False,
        publisher_name=source.publisher_name,
        published_at_text=source.published_at_text,
        hashtags=tuple(source.hashtags),
        interaction_stats=dict(source.interaction_stats),
    )


def _workflow_prompt_choice(prompt: PromptSnapshot | None):
    """Return only explicit custom intent for workflow replay fingerprints."""
    if prompt is not None and prompt.mode == "custom":
        return {"mode": "custom", "instructions": prompt.instructions}
    return None


def _operation_request_id(operation_key: str) -> str:
    """Derive a stable canonical UUIDv4-shaped replay key.

    ``uuid5`` is deterministic but its version is 5, while the public
    AnalysisCreate contract intentionally accepts only canonical UUIDv4
    request IDs. Hashing the operation key and setting the RFC 4122 version
    and variant bits preserves deterministic replay without weakening that
    boundary.
    """
    raw = bytearray(hashlib.sha256(operation_key.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(raw)))
