"""Loopback B acceptance app; all collection/model/media operations are fake.

PYTHONPATH=src:tests uv run --frozen uvicorn
collection_schedule_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from collection_schedule_fixtures import (
    FakeClock,
    ScheduledWorker,
    drain,
    enabled,
    payload,
)
from fastapi.middleware.cors import CORSMiddleware
from test_content_analysis_api import api_fixture

from longtian_api.schemas.collection_schedules import CollectionScheduleReplace
from longtian_api.services.collection_schedules import CollectionScheduleService
from longtian_api.services.search_runs import SearchRunService


def create_smoke_app():
    temporary = TemporaryDirectory(prefix="longtian-schedule-smoke-")
    clock, worker = FakeClock(), ScheduledWorker()
    clock.now = datetime.now(UTC) - timedelta(hours=2)

    def runs_factory(rules, platform):
        return SearchRunService(
            monitoring_rules=rules,
            worker=worker,
            browser_operations=platform.browser_operations,
            database=rules.database,
        )

    app, _, model, media = api_fixture(
        Path(temporary.name),
        count=3,
        search_run_service_factory=runs_factory,
        collection_schedule_service_factory=lambda db, batches: (
            CollectionScheduleService(
                db, batches, clock=clock, monotonic=clock.monotonic, available=True
            )
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:46081"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original_lifespan(application):
                owner = application.state.collection_schedule_service
                owner.available = False
                batches = application.state.search_batch_service
                schedule = enabled(owner, platforms=["toutiao", "wb"])
                for index in range(55):
                    clock.advance(60)
                    claim = owner.repository.advance_due(clock.now)[0]
                    if index == 50:
                        await batches.start_scheduled_batch(
                            claim,
                            timestamp=clock.now.isoformat(),
                            admission_allowed=lambda: True,
                        )
                        await drain(batches)
                    else:
                        reason = [
                            "browser_operation_active",
                            "browser_unavailable",
                            "dispatch_interrupted",
                        ][index % 3]
                        owner.repository.skip(claim.dispatch_token, reason)
                clock.advance(600)
                owner.repository.advance_due(clock.now, missed_reason="offline")
                clock.advance(60)
                claim = owner.repository.advance_due(clock.now)[0]
                rule = application.state.monitoring_rule_service.list_enabled()[0]
                batches._repository.create_scheduled_batch(
                    claim.dispatch_token, rule, timestamp=clock.now.isoformat()
                )
                # A linked prelaunch interruption retains the existing recovery UI.
                batches.initialize()
                await batches.resume_after_startup()
                owner.repository.reconcile_startup(clock.now)
                owner.replace(
                    schedule.id,
                    CollectionScheduleReplace(
                        **payload(platforms=["toutiao", "wb"]),
                        expected_revision=schedule.revision,
                        enabled=False,
                    ),
                )
                clock.now = datetime.now(UTC)
                # Keep a fixed synthetic clock: no ambient tick can start collection.
                owner._last_wall, owner._last_monotonic = clock.now, clock.monotonic()
                owner.available = True
                yield
        finally:
            temporary.cleanup()

    app.router.lifespan_context = lifespan

    @app.get("/api/v1/collection-schedule-smoke/counters")
    def counters() -> dict[str, int]:
        return {
            "synthetic_collection_calls": len(worker.calls),
            "synthetic_model_calls": len(model.calls),
            "synthetic_media_calls": len(media.calls),
        }

    return app
