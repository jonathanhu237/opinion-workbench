"""Existing collection owners publish once after release, never per batch child."""

import asyncio

from initial_analysis_fixtures import environment, finish
from test_search_runs import FakeSearchWorker

from opinion_workbench_api.repositories.analysis_settings import (
    AnalysisSettingsRepository,
)
from opinion_workbench_api.schemas.analysis_settings import AutomationUpdate
from opinion_workbench_api.schemas.search_batches import SearchBatchCreate
from opinion_workbench_api.schemas.search_runs import SearchRunCreate
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService
from opinion_workbench_api.services.search_batches import SearchBatchService
from opinion_workbench_api.services.search_runs import SearchRunService


class IdentityConsistentWorker(FakeSearchWorker):
    async def search(self, **kwargs):
        on_item = kwargs["on_item"]

        async def publish(position, item):
            await on_item(position, item)

        return await super().search(**{**kwargs, "on_item": publish})


def services(tmp_path, *, outcome="completed_with_results"):
    database, _, analyses, _, model, _, coordinator = environment(
        tmp_path, count=0, available=True
    )
    AnalysisSettingsRepository(database).save_automation(
        AutomationUpdate(
            expected_revision=1,
            enabled=True,
            configuration_revision=1,
        )
    )
    rules = MonitoringRuleService(database_path=database.path)
    worker = IdentityConsistentWorker(outcome=outcome)
    runs = SearchRunService(
        monitoring_rules=rules,
        worker=worker,
        browser_operations=coordinator,
        database=database,
    )
    batches = SearchBatchService(
        search_runs=runs, browser_operations=coordinator, database=database
    )
    callbacks = []

    async def handoff(kind, identity):
        assert coordinator._owner is None
        callbacks.append((kind, identity))
        await analyses.collection_finished(kind, identity)

    runs.on_collection_finished = batches.on_collection_finished = handoff
    return analyses, model, runs, batches, callbacks


def test_independent_run_hands_off_after_release_with_saved_sources(tmp_path):
    async def run():
        analyses, model, runs, batches, callbacks = services(tmp_path)
        source = await runs.start_run(
            SearchRunCreate(monitoring_rule_id=1, platform="wb")
        )
        task = runs._current_task
        await asyncio.wait_for(task, 5)
        await finish(analyses)
        assert callbacks == [("run", source.id)]
        jobs = analyses.repository.list().jobs
        assert len(jobs) == 1 and jobs[0].trigger == "automatic"
        assert jobs[0].counts.completed == 1 and len(model.calls) == 1
        await analyses.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_batch_has_one_handoff_not_one_per_child(tmp_path):
    async def run():
        analyses, model, runs, batches, callbacks = services(tmp_path)
        batch = await batches.start_batch(
            SearchBatchCreate(
                monitoring_rule_id=1,
                platforms=["wb"],
                max_results_per_term=1,
            )
        )
        task = batches._current_task
        await asyncio.wait_for(task, 5)
        await finish(analyses)
        assert callbacks == [("batch", batch.id)]
        jobs = analyses.repository.list().jobs
        assert len(jobs) == 1 and jobs[0].counts.total == 1
        assert jobs[0].counts.completed == 1 and len(model.calls) == 1
        await analyses.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())


def test_manual_pause_keeps_browser_and_suppresses_handoff(tmp_path):
    async def run():
        analyses, model, runs, batches, callbacks = services(
            tmp_path, outcome="manual_challenge_required"
        )
        await batches.start_batch(
            SearchBatchCreate(
                monitoring_rule_id=1,
                platforms=["wb"],
                max_results_per_term=1,
            )
        )
        await asyncio.wait_for(batches._current_task, 5)
        assert callbacks == [] and model.calls == []
        assert analyses.repository.list().jobs == []
        await analyses.shutdown()
        await batches.shutdown()
        await runs.shutdown()

    asyncio.run(run())
