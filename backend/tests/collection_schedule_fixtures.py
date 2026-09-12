"""Deterministic schedule clocks and collectors with no live browser/network."""

from datetime import UTC, datetime, timedelta

from fixture_support import initialize_database
from test_initial_analysis_handoff import IdentityConsistentWorker

from opinion_workbench_api.database import Database
from opinion_workbench_api.schemas.collection_schedules import (
    CollectionScheduleCreate,
    CollectionScheduleReplace,
)
from opinion_workbench_api.services.browser_operations import (
    BrowserOperationCoordinator,
)
from opinion_workbench_api.services.collection_schedules import (
    CollectionScheduleService,
)
from opinion_workbench_api.services.collector_contracts import ManualPageWorkerResult
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService
from opinion_workbench_api.services.search_batches import SearchBatchService
from opinion_workbench_api.services.search_runs import SearchRunService


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 8, 29, tzinfo=UTC)
        self.elapsed = 0.0

    def __call__(self):
        return self.now

    def monotonic(self):
        return self.elapsed

    def advance(self, seconds, *, wall_only=False):
        self.now += timedelta(seconds=seconds)
        if not wall_only:
            self.elapsed += seconds


class ScheduledWorker(IdentityConsistentWorker):
    browser_session_available = True

    async def manual_page(self, *, action, **kwargs):
        return ManualPageWorkerResult(
            "opened_homepage" if action == "show" else "not_present"
        )

    async def discard_session(self):
        pass


def payload(**changes):
    return {
        "monitoring_rule_id": 1,
        "platforms": ["wb"],
        "max_results_per_term": 1,
        "interval": {"value": 1, "unit": "minutes"},
        **changes,
    }


def enabled(service, **changes):
    config = payload(**changes)
    schedule = service.create(CollectionScheduleCreate(**config))
    return service.replace(
        schedule.id,
        CollectionScheduleReplace(
            **config, expected_revision=schedule.revision, enabled=True
        ),
    )


def environment(tmp_path, *, outcome="completed_empty", worker=None, available=True):
    database = Database(tmp_path / "schedules.sqlite3")
    initialize_database(database)
    rules = MonitoringRuleService(database_path=database.path)
    clock = FakeClock()
    coordinator = BrowserOperationCoordinator()
    worker = worker or ScheduledWorker(
        outcome=outcome, emit_item=outcome != "completed_empty"
    )
    runs = SearchRunService(
        monitoring_rules=rules,
        worker=worker,
        browser_operations=coordinator,
        database=database,
    )
    batches = SearchBatchService(
        search_runs=runs, browser_operations=coordinator, database=database
    )
    service = CollectionScheduleService(
        database, batches, clock=clock, monotonic=clock.monotonic, available=available
    )
    return database, service, clock, worker, runs, batches, rules, coordinator


async def drain(batches):
    task = batches._current_task
    if task is not None:
        await task
