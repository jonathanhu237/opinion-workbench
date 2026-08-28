"""Isolated UI acceptance app. Synthetic inputs only; no network model or browser.

Run from backend with PYTHONPATH=src:tests:<this directory>. This harness owns a
new /tmp directory, never reads product runtime files, and has no live worker.
"""

import asyncio
import json
import tempfile
from pathlib import Path

from longtian_api.database import Database
from longtian_api.main import create_app
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.content_enrichment import ContentEnrichmentService
from longtian_api.services.enrichment_staging import MediaSpool
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from pydantic import SecretStr
from summary_fixtures import BASE, KEY, MODEL, MediaWorker, ModelClient, seed_run


class PreviewWorker(MediaWorker):
    async def enrich(self, **kwargs):
        self.body = f"模拟内容 {kwargs['content_id']}，用于验证汇总界面。"
        await asyncio.sleep(0.3)
        return await super().enrich(**kwargs)


class PreviewModel(ModelClient):
    async def complete(self, configuration, **kwargs):
        await asyncio.sleep(2)
        if kwargs["max_tokens"] == 2048:
            content = kwargs["messages"][1]["content"]
            data = json.loads(
                content[0]["text"] if isinstance(content, list) else content
            )
            body = data["source"]["body"]
            decision = (
                "uncertain"
                if "1001" in body
                else "irrelevant"
                if "1002" in body
                else "relevant"
            )
            self.item_answers = [
                {
                    "decision": decision,
                    "reason": {
                        "relevant": "模拟来源提到监控对象及施工噪声。",
                        "uncertain": "模拟来源没有提供足够地点信息，无法确认属于监控范围。",
                        "irrelevant": "模拟来源讨论旅游攻略，与本次监控无关。",
                    }[decision],
                    "evidence_summary": "本条为界面验收用模拟分析，不代表实际事件。",
                }
            ]
        return await super().complete(configuration, **kwargs)


async def no_live_process(*_args, **_kwargs):
    raise RuntimeError("This isolated preview forbids real browser processes")


runtime_directory = Path(tempfile.mkdtemp(prefix="longtian-summary-ui-qa-"))
database = Database(runtime_directory / "preview.sqlite3")
database.initialize()
source_run_id = seed_run(
    database, 4, rule_name="汇总功能验收（模拟数据）", terms=("模拟对象 投诉",)
)
model_client = PreviewModel()
media_worker = PreviewWorker()
media_worker.partial = {"1003"}


def settings_factory(shared_database):
    settings = AISettingsService(shared_database, client=model_client)
    settings.save(AISettingsUpdate(base_url=BASE, model=MODEL, api_key=SecretStr(KEY)))
    return settings


def enrichment_factory(shared_database, platforms):
    model_client.coordinator = platforms.browser_operations
    return ContentEnrichmentService(
        repository=SearchRunRepository(shared_database),
        worker=media_worker,
        browser_operations=platforms.browser_operations,
        spool=MediaSpool(runtime_directory / "media"),
    )


app = create_app(
    platform_connection_service_factory=lambda: PlatformConnectionService(
        process_launcher=no_live_process
    ),
    monitoring_rule_service_factory=lambda: MonitoringRuleService(
        database_path=database.path
    ),
    ai_settings_service_factory=settings_factory,
    content_enrichment_service_factory=enrichment_factory,
    ai_frontend_origins=("http://127.0.0.1:15184",),
)


@app.get("/__qa__/metrics")
async def qa_metrics():
    """Counters only; no credentials, model bodies, or product information."""
    return {
        "synthetic": True,
        "source_run_id": source_run_id,
        "model_attempts": len(model_client.calls),
        "media_acquisitions": len(media_worker.calls),
        "pending_media_directories": len(list((runtime_directory / "media").glob("*"))),
    }
