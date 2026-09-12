"""One lifespan-owned, explicit analysis/composition runner; never auto-resumed."""

import asyncio
from contextlib import AsyncExitStack
from typing import cast

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.ai_summaries import (
    SavedInput,
    SummaryItemRecord,
    SummaryRepository,
    SummaryVersions,
    fingerprint,
)
from opinion_workbench_api.schemas.ai_summaries import (
    FailureCode,
    SummaryCreate,
    SummaryDocument,
    SummaryRun,
    TokenUsage,
)
from opinion_workbench_api.services.ai_analysis import (
    ANALYSIS_MAX_TOKENS,
    ANALYSIS_PROMPT_VERSION,
    MODEL_DEADLINE_SECONDS,
    MODEL_INPUT_VERSION,
    SUMMARY_MAX_TOKENS,
    SUMMARY_PROMPT_VERSION,
    AIAnalysisError,
    AnalysisContext,
    SummaryEvidence,
    build_analysis_messages,
    build_summary_messages,
    parse_analysis,
    parse_summary,
)
from opinion_workbench_api.services.ai_client import AIConfiguration
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.ai_settings import AISettingsService
from opinion_workbench_api.services.content_enrichment import (
    ContentEnrichmentError,
    ContentEnrichmentService,
)
from opinion_workbench_api.services.settled_tasks import database_call, settle
from opinion_workbench_api.services.summary_errors import (
    FAILURE_MESSAGES,
    SummaryError,
    failure,
)


class SummaryService:
    def __init__(
        self,
        *,
        database: Database,
        ai_settings: AISettingsService,
        enrichment: ContentEnrichmentService,
        repository: SummaryRepository | None = None,
    ):
        self.repository = repository or SummaryRepository(database)
        self._ai = ai_settings
        self._enrichment = enrichment
        self._admission = asyncio.Lock()
        self._runner: asyncio.Task[None] | None = None
        self._active_id: int | None = None
        self._closed = False

    def initialize(self) -> None:
        self.repository.initialize()

    def read(self, summary_id: int) -> SummaryRun:
        return self.repository.read(summary_id)

    async def create(self, source_run_id: int, payload: SummaryCreate) -> SummaryRun:
        # A disconnected POST cannot abandon an admission SQLite thread or its
        # credential lease. UUID replay recovers an accepted request's identity.
        return await settle(self._create(source_run_id, payload))

    async def _create(self, source_run_id: int, payload: SummaryCreate) -> SummaryRun:
        async with self._admission:
            replay = await database_call(self.repository.replay, source_run_id, payload)
            if replay is not None:
                return replay
            if self._closed:
                raise SummaryError("ai_summary_unavailable")
            if self._runner is not None and not self._runner.done():
                raise AIError("ai_operation_active")
            stack = AsyncExitStack()
            try:
                configuration = await stack.enter_async_context(
                    self._ai.operation(payload.configuration_revision)
                )
                run = await database_call(
                    self.repository.create,
                    source_run_id,
                    payload,
                    configuration,
                    SummaryVersions(
                        ANALYSIS_PROMPT_VERSION,
                        SUMMARY_PROMPT_VERSION,
                        MODEL_INPUT_VERSION,
                    ),
                )
            except BaseException:
                await settle(stack.aclose())
                raise
            started = asyncio.Event()
            self._active_id = run.id
            self._runner = asyncio.create_task(
                self._run(run, configuration, stack, started),
                name=f"ai-summary-{run.id}",
            )
            self._runner.add_done_callback(self._consume_failure)
            # Ensure cancellation never targets an unstarted coroutine holding a
            # lease whose finally block has not yet been installed.
            await started.wait()
            return run

    @staticmethod
    def _consume_failure(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def cancel(self, summary_id: int) -> SummaryRun:
        return await settle(self._cancel(summary_id))

    async def _cancel(self, summary_id: int) -> SummaryRun:
        async with self._admission:
            run = await database_call(self.repository.read, summary_id)
            if run.status not in ("queued", "running"):
                return run
            if self._active_id != summary_id or self._runner is None:
                # No foreign task is cancelled; restart reconciliation normally
                # makes this path terminal before serving requests.
                await database_call(
                    self.repository.finish,
                    summary_id,
                    "interrupted",
                    error=failure("execution", "interrupted"),
                )
            else:
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))
            return await database_call(self.repository.read, summary_id)

    async def shutdown(self) -> None:
        async with self._admission:
            self._closed = True
            if self._runner is not None and not self._runner.done():
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))

    async def _run(
        self,
        run: SummaryRun,
        configuration: AIConfiguration,
        stack: AsyncExitStack,
        started: asyncio.Event,
    ) -> None:
        composition_usage: TokenUsage | None = None
        phase = "analysis"
        try:
            started.set()
            await database_call(self.repository.start, run.id)
            context = AnalysisContext(rule_name=run.rule_name, terms=tuple(run.terms))
            records = await database_call(self.repository.records, run.id)
            pending: list[SummaryItemRecord] = []
            for record in records:
                cached = (
                    None
                    if run.force_refresh
                    else await database_call(self.repository.find_cached, record)
                )
                if cached is None:
                    pending.append(record)
                else:
                    await database_call(
                        self.repository.reuse, run.id, record.item.id, cached.item.id
                    )
            if pending:
                # One browser reservation spans only uncached serial input work.
                # It is released before the final text-only request below.
                async with self._enrichment.operation() as session:
                    for record in pending:
                        await database_call(
                            self.repository.begin_item, run.id, record.item.id
                        )
                        await self._analyse(
                            run.id, record, session, configuration, context
                        )
            await database_call(self.repository.summarising, run.id)
            phase = "composition"
            current = await database_call(self.repository.read, run.id)
            records = await database_call(self.repository.records, run.id)
            relevant = [
                record for record in records if record.item.decision == "relevant"
            ]
            if not relevant:
                document = SummaryDocument(
                    overview="本次没有可纳入汇总的相关内容；未完成或无法判断的内容请查看分析结果。",
                    items=[],
                )
            else:
                evidence = []
                for record in relevant:
                    if (
                        record.input is None
                        or record.item.reason is None
                        or record.item.evidence_summary is None
                    ):
                        raise SummaryError("ai_summary_storage_unavailable")
                    evidence.append(
                        SummaryEvidence(
                            source_id=record.item.source.result_id,
                            title=record.input.text.title,
                            body=record.input.text.body,
                            evidence_coverage=record.input.evidence_coverage,
                            reason=record.item.reason,
                            evidence_summary=record.item.evidence_summary,
                        )
                    )
                coverage = current.counts.model_dump(
                    exclude={"pending", "analysing", "reused"}
                )
                messages = await settle(
                    asyncio.to_thread(
                        build_summary_messages, context, evidence, coverage
                    )
                )
                await database_call(
                    self.repository.mark_attempt,
                    run.id,
                    None,
                    input_hash=fingerprint(messages),
                )
                completion = await self._ai.complete(
                    configuration,
                    messages=messages,
                    max_tokens=SUMMARY_MAX_TOKENS,
                    deadline=MODEL_DEADLINE_SECONDS,
                )
                composition_usage = completion.usage
                parsed = parse_summary(
                    completion,
                    allowed_source_ids={entry.source_id for entry in evidence},
                    api_key=configuration.api_key,
                )
                document = SummaryDocument.model_validate(parsed.model_dump())
            await database_call(
                self.repository.finish,
                run.id,
                "completed",
                document=document,
                usage=composition_usage,
            )
        except asyncio.CancelledError:
            cancelled_status = "interrupted" if self._closed else "cancelled"
            await database_call(
                self.repository.finish,
                run.id,
                cancelled_status,
                error=failure("execution", cancelled_status),
                usage=composition_usage,
            )
        except AIAnalysisError as error:
            await database_call(
                self.repository.finish,
                run.id,
                "failed",
                error=failure(
                    "composition" if phase == "composition" else "input", error.code
                ),
                usage=error.usage or composition_usage,
            )
        except AIError as error:
            code = cast(
                FailureCode,
                error.code if error.code in FAILURE_MESSAGES else "internal_error",
            )
            await database_call(
                self.repository.finish,
                run.id,
                "failed",
                error=failure(
                    "composition" if phase == "composition" else "analysis", code
                ),
                usage=composition_usage,
            )
        except ContentEnrichmentError as error:
            code = (
                "browser_operation_active"
                if error.code == "browser_operation_active"
                else "acquisition_failed"
            )
            await database_call(
                self.repository.finish,
                run.id,
                "failed",
                error=failure("acquisition", code),
                usage=composition_usage,
            )
        except Exception:
            await database_call(
                self.repository.finish,
                run.id,
                "failed",
                error=failure("execution", "internal_error"),
                usage=composition_usage,
            )
        finally:
            await settle(stack.aclose())

    async def _analyse(self, summary_id, record, session, configuration, context):
        usage = None
        try:
            async with session.item(
                run_id=record.item.source.source_run_id,
                result_id=record.item.source.result_id,
                expected_source=record.expected_source,
            ) as acquired:
                if acquired.content is not None:
                    await database_call(
                        self.repository.save_input,
                        summary_id,
                        record.item.id,
                        SavedInput.from_content(acquired.content),
                        acquired.input_fingerprint,
                    )
                if not acquired.ready:
                    await database_call(
                        self.repository.finish_item,
                        summary_id,
                        record.item.id,
                        "input_incomplete",
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
                        build_analysis_messages, configuration, acquired, context
                    )
                )
                await database_call(
                    self.repository.mark_attempt, summary_id, record.item.id
                )
                completion = await self._ai.complete(
                    configuration,
                    messages=messages,
                    max_tokens=ANALYSIS_MAX_TOKENS,
                    deadline=MODEL_DEADLINE_SECONDS,
                )
                usage = completion.usage
                analysis = parse_analysis(completion, api_key=configuration.api_key)
                await database_call(
                    self.repository.finish_item,
                    summary_id,
                    record.item.id,
                    "completed",
                    decision=analysis.decision,
                    reason=analysis.reason,
                    evidence_summary=analysis.evidence_summary,
                    usage=usage,
                )
        except AIAnalysisError as error:
            await database_call(
                self.repository.finish_item,
                summary_id,
                record.item.id,
                "input_incomplete" if error.stage == "input" else "failed",
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
                self.repository.finish_item,
                summary_id,
                record.item.id,
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
                self.repository.finish_item,
                summary_id,
                record.item.id,
                "input_incomplete",
                error=failure("acquisition", code),
            )
