"""Disposable A→C browser acceptance app with synthetic, counted operations.

Run from backend: PYTHONPATH=src:tests uv run --frozen uvicorn
topic_report_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
"""

import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from enrichment_fixtures import content_payload
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr
from summary_fixtures import BASE, KEY, MODEL, USAGE, seed_run
from topic_report_fixtures import api_environment

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.ai_summaries import (
    SummaryRepository,
    SummaryVersions,
    fingerprint,
)
from opinion_workbench_api.schemas.ai_settings import AISettingsUpdate
from opinion_workbench_api.schemas.ai_summaries import (
    SummaryCreate,
    SummaryDocument,
    SummaryParagraph,
)
from opinion_workbench_api.schemas.analysis_evidence import SavedInput
from opinion_workbench_api.services.ai_analysis import (
    ANALYSIS_PROMPT_VERSION,
    MODEL_INPUT_VERSION,
    SUMMARY_PROMPT_VERSION,
)
from opinion_workbench_api.services.ai_client import AIConfiguration
from opinion_workbench_api.services.enrichment_models import EnrichedContent
from opinion_workbench_api.services.search_runs import SearchRunService

UI_ORIGIN = "http://127.0.0.1:46081"
COUNTERS_PATH = "/api/v1/topic-report-smoke/counters"
LEGACY_RUN_ID = 4
LEGACY_RESULT_ID = 104
LEGACY_SUMMARY_ID = 1


class ForbiddenCollectionWorker:
    """An accidental collection/open request is counted and cannot reach a browser."""

    browser_session_available = False

    def __init__(self):
        self.collection_calls = 0
        self.browser_calls = 0

    async def search(self, **kwargs):
        self.collection_calls += 1
        raise AssertionError("smoke fixture forbids collection")

    async def open_result(self, **kwargs):
        self.browser_calls += 1
        raise AssertionError("smoke fixture forbids browser opening")

    async def manual_page(self, **kwargs):
        self.browser_calls += 1
        raise AssertionError("smoke fixture forbids browser control")

    async def discard_session(self):
        pass


def seed_legacy_report(database: Database) -> None:
    """Persist genuine legacy shapes/claim triggers without executing legacy work."""
    source_run = seed_run(database, 1, start=9000, rule_name="旧流程历史采集（仅阅读）")
    assert source_run == LEGACY_RUN_ID
    repository = SummaryRepository(database)
    report = repository.create(
        source_run,
        SummaryCreate(
            request_id=str(uuid4()), force_refresh=False, configuration_revision=1
        ),
        AIConfiguration(BASE, MODEL, 1, SecretStr(KEY)),
        SummaryVersions(
            ANALYSIS_PROMPT_VERSION, SUMMARY_PROMPT_VERSION, MODEL_INPUT_VERSION
        ),
    )
    assert report.id == LEGACY_SUMMARY_ID
    item = repository.records(report.id)[0].item
    assert item.source.result_id == LEGACY_RESULT_ID
    content = content_payload("wb", "9000")
    content["text"]["body"] = "旧流程保存的完整正文；仅用于验证历史报告和引用可读。"
    saved_input = SavedInput.from_content(EnrichedContent.model_validate(content))
    repository.start(report.id)
    repository.begin_item(report.id, item.id)
    repository.save_input(
        report.id, item.id, saved_input, fingerprint(saved_input.model_dump())
    )
    repository.mark_attempt(report.id, item.id)
    repository.finish_item(
        report.id,
        item.id,
        "completed",
        decision="relevant",
        reason="旧流程历史判断，非本次独立初步分析。",
        evidence_summary="历史来源称道路积水，真实性尚未核实。",
        usage=USAGE,
    )
    repository.summarising(report.id)
    repository.mark_attempt(report.id, None, input_hash="synthetic-legacy-composition")
    repository.finish(
        report.id,
        "completed",
        document=SummaryDocument(
            overview="旧流程历史报告，仅保留供阅读与引用核对。",
            items=[
                SummaryParagraph(
                    text="旧来源反映积水情况，具体地点与时间仍需核实。",
                    source_ids=[LEGACY_RESULT_ID],
                )
            ],
        ),
        usage=USAGE,
    )


def create_smoke_app() -> FastAPI:
    temporary = TemporaryDirectory(prefix="opinion-workbench-topic-report-smoke-")
    worker = ForbiddenCollectionWorker()
    requests = Counter()

    def runs_factory(rules, platform):
        return SearchRunService(
            monitoring_rules=rules,
            worker=worker,
            browser_operations=platform.browser_operations,
            database=rules.database,
        )

    app, database, model, media = api_environment(
        Path(temporary.name).resolve(),
        count=0,
        search_run_service_factory=runs_factory,
    )
    seed_run(database, 101, start=1000, rule_name="自动文本报告验收主采集")
    seed_run(database, 2, start=5000, rule_name="跨采集任务的历史来源")
    seed_legacy_report(database)
    media.partial.update({"1007", "1018"})
    media.body = "合成验收材料：来源称龙田附近道路积水，未说明行政区与确切时间。"
    model.decisions.update(
        {
            2: "irrelevant",
            3: "irrelevant",
            4: "irrelevant",
            5: "uncertain",
            6: "uncertain",
        }
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[UI_ORIGIN],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def count_legacy_generation(request: Request, call_next):
        if (
            request.method == "POST"
            and request.url.path.startswith("/api/v1/search-runs/")
            and request.url.path.endswith("/ai-summaries")
        ):
            requests["legacy_generation"] += 1
        return await call_next(request)

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original_lifespan(application):
                model.coordinator = (
                    application.state.platform_connection_service.browser_operations
                )
                complete = model.complete

                async def slow_synthetic_completion(configuration, **kwargs):
                    # Keep real progress observable; this is not a provider retry.
                    await asyncio.sleep(0.02)
                    return await complete(configuration, **kwargs)

                application.state.ai_settings_service._client.complete = (
                    slow_synthetic_completion
                )
                application.state.ai_settings_service.save(
                    AISettingsUpdate(base_url=BASE, model=MODEL, api_key=SecretStr(KEY))
                )
                yield
        finally:
            temporary.cleanup()

    app.router.lifespan_context = lifespan

    @app.get(COUNTERS_PATH)
    def counters(response: Response) -> dict[str, int]:
        response.headers["Cache-Control"] = "no-store"
        return {
            "synthetic_collection_calls": worker.collection_calls,
            "synthetic_browser_calls": worker.browser_calls,
            "synthetic_media_calls": len(media.calls),
            "synthetic_initial_calls": model.counts["initial"],
            "synthetic_judgment_calls": model.counts["judgment"],
            "synthetic_leaf_calls": model.counts["leaf"],
            "synthetic_overview_calls": model.counts["overview"],
            "synthetic_composition_calls": model.counts["leaf"]
            + model.counts["overview"],
            "synthetic_model_calls": len(model.calls),
            "legacy_generation_requests": requests["legacy_generation"],
        }

    return app
