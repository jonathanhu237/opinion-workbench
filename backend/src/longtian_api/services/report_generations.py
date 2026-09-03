"""Lifespan-owned manual flow, never a frontend chain or collection callback."""

import asyncio

from longtian_api.repositories.report_generations import (
    ReportGenerationRepository,
)
from longtian_api.schemas.report_generations import GenerationControl
from longtian_api.schemas.topic_reports import ACTIVE_REPORTS
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.content_enrichment import ContentEnrichmentError
from longtian_api.services.settled_tasks import database_call, settle


class ReportGenerationService:
    def __init__(self, database, *, analyses, reports, ai_settings):
        self.repository = ReportGenerationRepository(database, reports.repository)
        self.analyses, self.reports, self.ai = analyses, reports, ai_settings
        self._admission = asyncio.Lock()
        self._runner = None
        self._active_id = None
        self._closed = False
        self.analyses.on_manual_configuration_failure = self.block_configuration
        self.reports.on_manual_configuration_failure = self.block_configuration
        self.analyses.on_manual_acquisition_pause = self.pause
        self._paused_sessions = {}
        self._cancellations = {}
        self.analyses.on_manual_job_cancel = self.cancel_by_analysis

    def initialize(self):
        self.repository.initialize()

    async def block_configuration(self, revision, error):
        await database_call(self.repository.block_configuration, revision, error.code)
        for generation_id, session in tuple(self._paused_sessions.items()):
            value = await database_call(self.repository.read_generation, generation_id)
            if value.status != "paused_for_manual_action":
                await session.release_hold(abandon=True)
                self._paused_sessions.pop(generation_id, None)

    async def pause(self, attempt, session, reason):
        async with self._admission:
            session.hold_for_manual()
            try:
                generation_id = await database_call(
                    self.repository.pause, attempt.job_id, attempt.id, reason
                )
            except BaseException:
                session.discard_manual_hold()
                raise
            self._paused_sessions[generation_id] = session

    async def control(self, generation_id, payload, *, show=False):
        return await settle(self._control(generation_id, payload, show=show))

    async def cancel_by_analysis(self, job_id):
        value = await database_call(self.repository.for_analysis, job_id)
        if value is None or (
            value.analysis.status not in ("queued", "running")
            and value.id not in self._cancellations
        ):
            return None
        result = await self.cancel(
            value.id, GenerationControl(expected_revision=value.control_revision)
        )
        return result.analysis

    async def cancel(self, generation_id, payload):
        return await settle(self._cancel(generation_id, payload))

    async def _cancel(self, generation_id, payload):
        async with self._admission:
            task = self._cancellations.get(generation_id)
            if task is None:
                value = await database_call(
                    self.repository.cancel_generation,
                    generation_id,
                    payload.expected_revision,
                )
                if value.status != "cancelled":
                    return value
                task = asyncio.create_task(
                    self._stop_cancelled(value), name="cancel-manual-generation"
                )
                self._cancellations[generation_id] = task
        # Never hold parent admission while a child unwinds its pause callback.
        try:
            return await settle(task)
        finally:
            if task.done() and self._cancellations.get(generation_id) is task:
                self._cancellations.pop(generation_id, None)

    async def _stop_cancelled(self, value):
        await self.analyses.cancel_owned(value.analysis.id)
        if value.report is not None:
            await self.reports.stop_owned(value.report.id)
        session = self._paused_sessions.pop(value.id, None)
        if session is not None:
            await session.release_hold(abandon=True)
        self._launch()
        return await database_call(self.repository.read_generation, value.id)

    async def _control(self, generation_id, payload, *, show):
        async with self._admission:
            value = await database_call(self.repository.read_generation, generation_id)
            if (
                not show
                and value.pause_reason is None
                and value.control_revision == payload.expected_revision + 1
            ):
                return value
            if (
                self._closed
                or value.status != "paused_for_manual_action"
                or value.control_revision != payload.expected_revision
            ):
                raise AnalysisError("content_analysis_selection_conflict")
            session = self._paused_sessions.get(generation_id)
            if session is None:
                raise AnalysisError("content_analysis_unavailable")
            try:
                if show:
                    await session.show_manual("wb")
                    return value
                await session.prepare_resume()
            except ContentEnrichmentError:
                raise AnalysisError("content_analysis_unavailable") from None
            value = await database_call(
                self.repository.resume, generation_id, payload.expected_revision
            )
            await session.release_hold()
            self._paused_sessions.pop(generation_id, None)
            await self.analyses.start_pending()
            self._launch()
            return value

    def _launch(self):
        if self._closed:
            return
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(
                self._run(), name="manual-report-generation"
            )
            self._runner.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )

    async def create(self, payload):
        return await settle(self._create(payload))

    async def _create(self, payload):
        async with self._admission:
            replay = await database_call(self.repository.replay_generation, payload)
            if replay is not None:
                return replay
            if self._closed or not self.reports.available:
                raise AnalysisError("content_analysis_unavailable")
            await database_call(self.ai.read)
            result = await database_call(self.repository.create_generation, payload)
            await self.analyses.start_pending()
            self._launch()
            return result

    async def _run(self):
        try:
            while not self._closed:
                value = await database_call(self.repository.next_generation)
                if value is None:
                    async with self._admission:
                        value = await database_call(self.repository.next_generation)
                        if value is None:
                            self._runner = None
                            return
                self._active_id = value.id
                if value.status == "summarising":
                    if value.analysis_status in ("queued", "running"):
                        await asyncio.sleep(0.1)
                        continue
                    if value.analysis_status != "completed":
                        await database_call(
                            self.repository.finish_generation,
                            value.id,
                            value.analysis_status,
                        )
                        continue
                    try:
                        await database_call(self.repository.admit_report, value.id)
                    except AnalysisError:
                        current = await database_call(
                            self.repository.read_generation, value.id
                        )
                        if current.status in (
                            "cancelled",
                            "interrupted",
                            "configuration_blocked",
                        ):
                            continue
                        raise
                    await self.reports.start_pending()
                elif value.report_status in ACTIVE_REPORTS:
                    await asyncio.sleep(0.1)
                else:
                    await database_call(
                        self.repository.finish_generation, value.id, value.report_status
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Ambiguous storage/execution failures require an explicit new
            # attempt; never silently reissue model requests.
            if self._active_id is not None:
                await database_call(
                    self.repository.finish_generation, self._active_id, "interrupted"
                )
        finally:
            self._active_id = None

    async def shutdown(self):
        async with self._admission:
            self._closed = True
            if self._runner is not None and not self._runner.done():
                self._runner.cancel()
                await settle(asyncio.gather(self._runner, return_exceptions=True))
            cancellations = tuple(self._cancellations.values())
        if cancellations:
            await settle(asyncio.gather(*cancellations, return_exceptions=True))
        async with self._admission:
            await database_call(self.repository.initialize)
            for session in self._paused_sessions.values():
                await session.release_hold(abandon=True)
            self._paused_sessions.clear()
