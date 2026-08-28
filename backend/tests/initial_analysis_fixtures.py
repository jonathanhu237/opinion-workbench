"""Synthetic initial understanding only; no browser account or provider traffic."""

import asyncio
from uuid import uuid4

from pydantic import SecretStr
from summary_fixtures import BASE, KEY, MODEL, MediaWorker, ModelClient, seed_run

from longtian_api.database import Database
from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.schemas.content_analyses import AnalysisCreate
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.browser_operations import BrowserOperationCoordinator
from longtian_api.services.content_analyses import ContentAnalysisService
from longtian_api.services.content_enrichment import ContentEnrichmentService
from longtian_api.services.enrichment_staging import MediaSpool

UNDERSTANDING = {
    "summary": "来源反映一处路段积水，陈述尚未核实。",
    "location_clues": [
        {"excerpt": "来源写明龙田，具体行政区未说明。", "modality": "text"}
    ],
    "time_context": "来源未注明确切发生时间。",
    "media_observations": ["图片显示路面有水，不能证明具体地点或原因。"],
    "uncertainties": "同名地点无法区分，时间与事实真实性仍不确定。",
}


class UnderstandingClient(ModelClient):
    async def complete(self, configuration, **kwargs):
        assert kwargs["max_tokens"] == 2048, "stage one must never compose reports"
        if not self.item_answers:
            self.item_answers.append(UNDERSTANDING)
        return await super().complete(configuration, **kwargs)


def request(database, *, kind="all_never_started", result_ids=None, **overrides):
    settings = AnalysisSettingsRepository(database).read()
    selection = {"kind": kind}
    if result_ids is not None:
        selection["result_ids"] = result_ids
    return AnalysisCreate.model_validate(
        {
            "request_id": str(uuid4()),
            "configuration_revision": 1,
            "initial_prompt_version_id": settings.initial_prompt.id,
            "report_prompt_version_id": settings.report_prompt.id,
            "force_refresh": False,
            "selection": selection,
            **overrides,
        }
    )


def environment(tmp_path, *, count=2, media=True, available=False):
    database = Database(tmp_path / "initial.sqlite3")
    database.initialize()
    source = seed_run(database, count) if count else None
    model = UnderstandingClient()
    ai = AISettingsService(database, client=model)
    ai.save(AISettingsUpdate(base_url=BASE, model=MODEL, api_key=SecretStr(KEY)))
    worker, coordinator = MediaWorker(media=media), BrowserOperationCoordinator()
    model.coordinator = coordinator
    enrichment = ContentEnrichmentService(
        repository=SearchRunRepository(database),
        worker=worker,
        browser_operations=coordinator,
        spool=MediaSpool(tmp_path / "media"),
    )
    service = ContentAnalysisService(
        database=database, ai_settings=ai, enrichment=enrichment, available=available
    )
    service.initialize()
    return database, source, service, ai, model, worker, coordinator


async def finish(service):
    task = service._runner
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 20)
