"""Lifespan-owned stage-one queue; independent evidence precedes report handoff."""

import asyncio
import hashlib
import time
from typing import cast
from uuid import UUID

from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.search_runs import SearchResultSourceRecord
from longtian_api.schemas.ai_summaries import FailureCode
from longtian_api.schemas.analysis_evidence import SavedInput
from longtian_api.schemas.analysis_settings import PromptSnapshot
from longtian_api.schemas.content_analyses import (
    AnalysisCreate,
    WorkflowAnalysisCreate,
)
from longtian_api.services.ai_analysis import (
    ANALYSIS_MAX_TOKENS,
    MODEL_DEADLINE_SECONDS,
    AIAnalysisError,
)
from longtian_api.services.ai_errors import MANUAL_SYSTEMIC_AI_FAILURES, AIError
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.content_enrichment import ContentEnrichmentError
from longtian_api.services.content_understanding import (
    build_understanding_messages,
    parse_understanding,
)
from longtian_api.services.manual_content import (
    ManualAcquisitionPause,
    ManualContentSession,
)
from longtian_api.services.model_retry import RETRYABLE_OUTPUT_ERRORS
from longtian_api.services.settled_tasks import database_call, settle
from longtian_api.services.summary_errors import FAILURE_MESSAGES, failure


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
                    async with self._ai.operation(
                        job.configuration_revision
                    ) as configuration:
                        await self._execute(job, configuration)
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
                    await database_call(self.repository.finish, job.id, "interrupted")
                except AnalysisError:
                    # A storage write may have failed: settle history if possible,
                    # never retry an ambiguous model request automatically.
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
        except Exception:
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
                await database_call(self.repository.start, job.id)
                await database_call(self.repository.begin, attempt.id)
                await self._analyse(
                    attempt,
                    ManualContentSession(
                        attempt,
                        enrichment=self._enrichment,
                        database=self.repository.database,
                        on_pause=self.on_manual_acquisition_pause,
                    ),
                    configuration,
                    job.initial_prompt,
                    allow_preview=False,
                    stop_on_systemic_error=True,
                )
                continue
            if not job.force_refresh and await database_call(
                self.repository.reuse, attempt.id
            ):
                await database_call(self.repository.start, job.id)
                continue
            # Acquire the browser before marking an item started. Busy ownership
            # leaves the member queued, without a failed/paid attempt.
            async with self._enrichment.operation() as session:
                await database_call(self.repository.start, job.id)
                await database_call(self.repository.begin, attempt.id)
                await self._analyse(attempt, session, configuration, job.initial_prompt)
            # Browser is released between individual records, before any future report.
            await asyncio.sleep(0)

    async def _analyse(
        self,
        attempt,
        session,
        configuration,
        prompt,
        *,
        # Search-card title/snippet is discovery evidence only.  It cannot
        # stand in for the original post's complete text in the automatic
        # text-understanding pipeline.  Keep the flag as an explicit escape
        # hatch for callers that intentionally exercise preview analysis.
        allow_preview=False,
        stop_on_systemic_error=False,
    ):
        source = attempt.source
        expected = SearchResultSourceRecord(
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
        usage = None
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
                    # The stored search title/snippet is a safe, immutable
                    # fallback when detail acquisition cannot produce a
                    # document. It is explicitly labelled preview evidence
                    # in the persisted input and model envelope.
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
                    return
                messages = await settle(
                    asyncio.to_thread(
                        build_understanding_messages, configuration, candidate, prompt
                    )
                )
                await database_call(self.repository.mark_attempt, attempt.id)
                for attempt_number in range(2):
                    usage = None
                    completion = await self._ai.complete(
                        configuration,
                        messages=messages,
                        max_tokens=ANALYSIS_MAX_TOKENS,
                        deadline=MODEL_DEADLINE_SECONDS,
                    )
                    usage = completion.usage
                    try:
                        output = parse_understanding(
                            completion, api_key=configuration.api_key
                        )
                        break
                    except AIAnalysisError as error:
                        if attempt_number or error.code not in RETRYABLE_OUTPUT_ERRORS:
                            raise
                        await database_call(
                            self.repository.mark_retry, attempt.id, usage
                        )
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
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                "failed",
                error=failure("analysis", code),
                usage=usage,
            )
            if stop_on_systemic_error and error.code in MANUAL_SYSTEMIC_AI_FAILURES:
                # Block peers before the provider lease is released, so a
                # queued manual task cannot slip in another paid request.
                if self.on_manual_configuration_failure is not None:
                    await self.on_manual_configuration_failure(
                        configuration.revision, error
                    )
                raise
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
