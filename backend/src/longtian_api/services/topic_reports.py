"""Independent report queue: saved text only, existing provider lease/transport."""

import asyncio
from datetime import datetime

from longtian_api.repositories.topic_reports import (
    TopicReportRepository,
    observed_usage,
)
from longtian_api.schemas.topic_report_engine import CompletedOutput
from longtian_api.schemas.topic_reports import ACTIVE_REPORTS
from longtian_api.services.ai_analysis import AIAnalysisError
from longtian_api.services.ai_client import AICompletion, decode_model_json
from longtian_api.services.ai_errors import AIError
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.settled_tasks import database_call, settle
from longtian_api.services.summary_errors import FAILURE_MESSAGES, failure
from longtian_api.services.topic_report_engine import (
    ENGINE_VERSION,
    check_request,
    parse_completion,
    prepare_judgment,
    take_leaf,
    take_overview,
    validate_reuse,
)
from longtian_api.services.topic_report_errors import (
    CONFIGURATION_FAILURES,
    TopicReportError,
    configuration_failure,
)


class TopicReportService:
    def __init__(self, *, database, ai_settings, repository=None, available=True):
        self.repository = repository or TopicReportRepository(database)
        self._ai = ai_settings
        self._admission = asyncio.Lock()
        self._runner: asyncio.Task | None = None
        self._active_id = None
        self._closed = False
        self.available = available

    def initialize(self):
        self.repository.initialize()

    @staticmethod
    def _validate_override(value):
        if value is None:
            return
        try:
            if not 1 <= len(value) <= 8000 or not value.strip() or "\x00" in value:
                raise ValueError
            value.encode("utf-8", errors="strict")
        except (ValueError, UnicodeError):
            raise AnalysisError("invalid_analysis_prompt") from None

    async def create(self, payload):
        return await settle(self._admit("create", None, payload))

    async def retry(self, report_id, payload):
        return await settle(self._admit("retry", report_id, payload))

    async def _admit(self, action, target, payload):
        async with self._admission:
            replay = await database_call(
                self.repository.replay, action, target, payload
            )
            if replay is not None:
                return replay
            if self._closed or not self.available:
                raise TopicReportError("topic_report_unavailable")
            self._validate_override(payload.instructions_override)
            if action == "create" and datetime.fromisoformat(
                payload.selection.first_seen_from
            ) >= datetime.fromisoformat(payload.selection.first_seen_to):
                raise TopicReportError("invalid_report_interval")
            await database_call(self._ai.read)
            result = (
                await database_call(self.repository.create, payload)
                if action == "create"
                else await database_call(self.repository.retry, target, payload)
            )
            await self._launch()
            return result

    async def initial_analysis_finished(self, job_id):
        # This is admission-only. It never waits for the A lease or report work.
        async with self._admission:
            if self._closed or not self.available:
                return
            report = await database_call(self.repository.consume, job_id)
            if report is not None and report.status == "queued":
                await self._launch()

    async def _launch(self):
        if self._runner is None or self._runner.done():
            started = asyncio.Event()
            self._runner = asyncio.create_task(
                self._run(started), name="topic-report-queue"
            )
            self._runner.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            await started.wait()

    async def cancel(self, report_id, payload):
        return await settle(self._cancel(report_id, payload))

    async def _cancel(self, report_id, payload):
        async with self._admission:
            replay = await database_call(
                self.repository.replay, "cancel", report_id, payload
            )
            if replay is not None and replay.status not in ACTIVE_REPORTS:
                return replay
            result = await database_call(
                self.repository.request_cancel, report_id, payload
            )
            if result.status in ACTIVE_REPORTS:
                if self._active_id == report_id and self._runner is not None:
                    self._runner.cancel()
                    await settle(asyncio.gather(self._runner, return_exceptions=True))
                else:
                    await database_call(self.repository.finish, report_id, "cancelled")
            if not self._closed:
                await self._launch()
            return await database_call(self.repository.read, report_id)

    async def shutdown(self):
        async with self._admission:
            self._closed = True
            if self._runner is not None and not self._runner.done():
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))
            await database_call(self.repository.initialize)

    async def _run(self, started):
        started.set()
        try:
            while not self._closed:
                report = await database_call(self.repository.next_report)
                if report is None:
                    async with self._admission:
                        report = await database_call(self.repository.next_report)
                        if report is None:
                            self._runner = None
                            return
                self._active_id = report.id
                try:
                    if report.coverage.ready == 0:
                        await database_call(
                            self.repository.finish,
                            report.id,
                            "empty",
                            empty_reason="no_ready_sources",
                        )
                    else:
                        async with self._ai.operation(
                            report.configuration_revision
                        ) as configuration:
                            if (configuration.base_url, configuration.model) != (
                                report.base_url,
                                report.model,
                            ):
                                raise AIError("ai_configuration_changed")
                            await self._execute(report, configuration)
                except AIError as error:
                    if error.code == "ai_operation_active":
                        await database_call(self.repository.queue, report.id)
                        await asyncio.sleep(0.25)
                        continue
                    await database_call(
                        self.repository.finish,
                        report.id,
                        "configuration_blocked",
                        error=configuration_failure(error.code)
                        if error.code in CONFIGURATION_FAILURES
                        else failure("execution", "internal_error"),
                    )
                except TopicReportError:
                    await database_call(
                        self.repository.finish,
                        report.id,
                        "interrupted",
                        error=failure("execution", "storage_unavailable"),
                    )
                except AIAnalysisError as error:
                    await database_call(
                        self.repository.finish,
                        report.id,
                        "failed",
                        error=failure(
                            "input" if error.stage == "input" else "composition",
                            error.code,
                        ),
                    )
                except Exception:
                    # A bounded per-report failure must not abandon a later
                    # independently admitted intent in this same owned queue.
                    await database_call(
                        self.repository.finish,
                        report.id,
                        "interrupted",
                        error=failure("execution", "internal_error"),
                    )
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
                    self.repository.finish,
                    self._active_id,
                    "interrupted",
                    error=failure("execution", "internal_error"),
                )
        finally:
            self._active_id = None

    async def _execute(self, report, configuration):
        context = self.repository.context(report)
        await database_call(self.repository.stage, report.id, "judging")
        offset = 0
        while not self._closed:
            nodes = await database_call(
                self.repository.nodes, report.id, kind="judgment", offset=offset
            )
            if not nodes:
                break
            for node in nodes:
                try:
                    evidence = await database_call(self.repository.evidence, node["id"])
                    call = prepare_judgment(context, evidence[0])
                    await self._execute_node(report, node["id"], call, configuration)
                except AIAnalysisError as error:
                    await database_call(
                        self.repository.finish_node,
                        node["id"],
                        error=failure("input", error.code),
                    )
            offset += len(nodes)
        progress = await database_call(self.repository.read, report.id)
        if progress.coverage.failed:
            await database_call(
                self.repository.finish,
                report.id,
                "failed",
                error=failure("analysis", "internal_error"),
            )
            return
        if progress.coverage.relevant == 0:
            await database_call(
                self.repository.finish,
                report.id,
                "empty",
                empty_reason="no_relevant_sources",
            )
            return
        await database_call(self.repository.stage, report.id, "composing")
        # Plan all bounded leaves before the first composition request. A failed
        # request never causes dynamic repartitioning or an implicit repair.
        offset = position = 0
        while offset < progress.coverage.relevant:
            candidates = await database_call(
                self.repository.relevant, report.id, offset=offset, limit=8
            )
            plan = take_leaf(context, candidates, position=position)
            await database_call(
                self.repository.add_composition,
                report.id,
                plan.call,
                level=0,
                position=position,
            )
            offset += plan.consumed_count
            position += 1
        await self._execute_level(report, context, configuration, kind="leaf", level=0)
        progress = await database_call(self.repository.read, report.id)
        if progress.nodes.composition.failed:
            await database_call(
                self.repository.finish,
                report.id,
                "failed",
                error=failure("composition", "internal_error"),
            )
            return
        current = []
        offset = 0
        while True:
            nodes = await database_call(
                self.repository.nodes, report.id, kind="leaf", level=0, offset=offset
            )
            current.extend(node["id"] for node in nodes)
            if len(nodes) < 100:
                break
            offset += len(nodes)
        level = 1
        while len(current) > 1:
            next_level = []
            offset = position = 0
            while offset < len(current):
                children = await database_call(
                    self.repository.children, current[offset : offset + 8]
                )
                plan = take_overview(context, children, level=level, position=position)
                if plan.kind == "carry":
                    next_level.append(current[offset])
                else:
                    node_id = await database_call(
                        self.repository.add_composition,
                        report.id,
                        plan.call,
                        level=level,
                        position=position,
                    )
                    next_level.append(node_id)
                offset += plan.consumed_count
                position += 1
            if len(next_level) >= len(current):
                raise AIAnalysisError("input", "request_too_large")
            await self._execute_level(
                report, context, configuration, kind="overview", level=level
            )
            progress = await database_call(self.repository.read, report.id)
            if progress.nodes.composition.failed:
                await database_call(
                    self.repository.finish,
                    report.id,
                    "failed",
                    error=failure("composition", "internal_error"),
                )
                return
            current = next_level
            level += 1
        await database_call(
            self.repository.finish, report.id, "completed", root_id=current[0]
        )

    async def _execute_level(self, report, context, configuration, *, kind, level):
        offset = 0
        while True:
            nodes = await database_call(
                self.repository.nodes, report.id, kind=kind, level=level, offset=offset
            )
            if not nodes:
                return
            for node in nodes:
                call = await self._fresh_call(context, node)
                await self._execute_node(report, node["id"], call, configuration)
            offset += len(nodes)

    async def _fresh_call(self, context, node):
        # Regenerate from frozen evidence/child rows. Stored prepared_json is
        # audit-only, both for this version and a canonical reuse candidate.
        if node["kind"] == "judgment":
            evidence = await database_call(self.repository.evidence, node["id"])
            if len(evidence) != 1:
                raise AIAnalysisError("input", "input_incomplete")
            return prepare_judgment(context, evidence[0])
        if node["kind"] == "leaf":
            evidence = await database_call(self.repository.evidence, node["id"])
            candidates = await database_call(
                self.repository.leaf_candidates, node["id"]
            )
            call = take_leaf(context, candidates, position=node["position"]).call
            if tuple(call.source_ids) != tuple(
                item.source.result_id for item in evidence
            ):
                raise AIAnalysisError("input", "input_incomplete")
            return call
        ids = await database_call(self.repository.dependency_ids, node["id"])
        children = await database_call(self.repository.children, ids)
        plan = take_overview(
            context, children, level=node["level"], position=node["position"]
        )
        if plan.kind != "call" or plan.consumed_count != len(ids):
            raise AIAnalysisError("input", "input_incomplete")
        return plan.call

    async def _execute_node(self, report, node_id, call, configuration):
        usage = None
        try:
            proof = check_request(call, configuration)
            await database_call(
                self.repository.prepare,
                node_id,
                call,
                ENGINE_VERSION,
                proof.request_hash,
            )
            candidate = await database_call(
                self.repository.reuse_candidate, report.id, call.key
            )
            if candidate is not None:
                original_context = await database_call(
                    self.repository.frozen_context, candidate["report_id"]
                )
                original_call = await self._fresh_call(original_context, candidate)
                if original_call.input_hash != candidate["input_hash"]:
                    raise TopicReportError("topic_report_storage_unavailable")
                saved = CompletedOutput.model_validate(
                    {
                        "engine_version": candidate["engine_version"],
                        "input_hash": candidate["input_hash"],
                        "output_hash": candidate["output_hash"],
                        "output": decode_model_json(candidate["output_json"]),
                    }
                )
                output = validate_reuse(call, saved, api_key=configuration.api_key)
                if output is not None:
                    await database_call(
                        self.repository.finish_node,
                        node_id,
                        output=output,
                        reused_from=candidate["id"],
                    )
                    return
            await database_call(self.repository.mark_attempt, node_id)
            completion = await self._ai.complete(
                configuration,
                messages=[
                    {"role": "system", "content": call.system_text},
                    {"role": "user", "content": call.user_text},
                ],
                max_tokens=call.max_tokens,
                deadline=call.deadline_seconds,
            )
            usage = observed_usage(completion.usage)
            output = parse_completion(
                call,
                AICompletion(completion.text, usage),
                api_key=configuration.api_key,
            )
            await database_call(
                self.repository.finish_node, node_id, output=output, usage=usage
            )
        except AIAnalysisError as error:
            await database_call(
                self.repository.finish_node,
                node_id,
                error=failure(
                    "analysis" if call.kind == "judgment" else "composition", error.code
                ),
                usage=observed_usage(error.usage) or usage,
            )
        except AIError as error:
            code = error.code if error.code in FAILURE_MESSAGES else "internal_error"
            await database_call(
                self.repository.finish_node,
                node_id,
                error=failure(
                    "analysis" if call.kind == "judgment" else "composition", code
                ),
                usage=usage,
            )
