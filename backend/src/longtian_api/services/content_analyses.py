"""Lifespan-owned stage-one queue; independent evidence precedes report handoff."""

import asyncio
from typing import cast

from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.repositories.search_runs import SearchResultSourceRecord
from longtian_api.schemas.ai_summaries import FailureCode
from longtian_api.schemas.analysis_evidence import SavedInput
from longtian_api.schemas.content_analyses import AnalysisCreate
from longtian_api.services.ai_analysis import (
    ANALYSIS_MAX_TOKENS,
    MODEL_DEADLINE_SECONDS,
    AIAnalysisError,
)
from longtian_api.services.ai_errors import AIError
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.content_enrichment import ContentEnrichmentError
from longtian_api.services.content_understanding import (
    build_understanding_messages,
    parse_understanding,
)
from longtian_api.services.settled_tasks import database_call, settle
from longtian_api.services.summary_errors import FAILURE_MESSAGES, failure


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

    def initialize(self):
        self.repository.initialize()  # Storage reconciliation only, never launch.

    async def create(self, payload: AnalysisCreate):
        return await settle(self._create(payload))

    async def _create(self, payload):
        async with self._admission:
            replay = await database_call(self.repository.replay, payload)
            if replay is not None:
                return replay
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
        return await settle(self._cancel(job_id))

    async def _cancel(self, job_id):
        async with self._admission:
            job = await database_call(self.repository.read, job_id)
            if job.status not in ("queued", "running"):
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
                except AIError as error:
                    if error.code == "ai_operation_active":
                        await database_call(
                            self.repository.queue, job.id, "ai_operation_active"
                        )
                        await asyncio.sleep(0.25)
                        continue
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

    async def _analyse(self, attempt, session, configuration, prompt):
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
        )
        usage = None
        try:
            async with session.item(
                run_id=source.source_run_id,
                result_id=source.result_id,
                expected_source=expected,
            ) as acquired:
                if acquired.content is not None:
                    await database_call(
                        self.repository.save_input,
                        attempt.id,
                        SavedInput.from_content(acquired.content),
                        acquired.input_fingerprint,
                    )
                if not acquired.ready:
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
                            else "acquisition_failed",
                        ),
                    )
                    return
                messages = await settle(
                    asyncio.to_thread(
                        build_understanding_messages, configuration, acquired, prompt
                    )
                )
                await database_call(self.repository.mark_attempt, attempt.id)
                completion = await self._ai.complete(
                    configuration,
                    messages=messages,
                    max_tokens=ANALYSIS_MAX_TOKENS,
                    deadline=MODEL_DEADLINE_SECONDS,
                )
                usage = completion.usage
                output = parse_understanding(completion, api_key=configuration.api_key)
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
                    "input" if error.stage == "input" else "analysis", error.code
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
        except ContentEnrichmentError as error:
            if error.code in (
                "worker_unsettled",
                "service_unavailable",
                "staging_unavailable",
            ):
                raise
            code = cast(
                FailureCode,
                error.code
                if error.code
                in ("source_active", "source_changed", "invalid_enrichment")
                else "acquisition_failed",
            )
            await database_call(
                self.repository.finish_attempt,
                attempt.id,
                "input_incomplete",
                error=failure("acquisition", code),
            )
