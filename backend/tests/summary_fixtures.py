"""Isolated product-summary fixtures; real repositories, no real external services."""

import asyncio
import json
from pathlib import Path

from enrichment_fixtures import PNG, content_payload, image_asset, write_file
from fixture_support import initialize_database
from pydantic import SecretStr

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
)
from opinion_workbench_api.schemas.ai_settings import AISettingsUpdate
from opinion_workbench_api.schemas.monitoring_rules import MonitoringRuleCreate
from opinion_workbench_api.services.ai_client import AICompletion, AIUsage
from opinion_workbench_api.services.ai_settings import AISettingsService
from opinion_workbench_api.services.ai_summaries import SummaryService
from opinion_workbench_api.services.browser_operations import (
    BrowserOperationCoordinator,
)
from opinion_workbench_api.services.collector_contracts import EnrichmentWorkerResult
from opinion_workbench_api.services.content_enrichment import ContentEnrichmentService
from opinion_workbench_api.services.enrichment_models import EnrichedContent
from opinion_workbench_api.services.enrichment_staging import MediaSpool
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService

KEY = "synthetic-summary-secret-never-public"
BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-omni-plus"
USAGE = AIUsage(
    prompt_tokens=10,
    completion_tokens=5,
    total_tokens=15,
    prompt_tokens_details={"text_tokens": 8, "image_tokens": 2},
)


def seed_run(
    database: Database,
    count=1,
    *,
    terminal="completed_with_results",
    rule_name="历史规则",
    terms=("对象", "另一个对象", "第三个对象"),
    start=1000,
):
    rule_service = MonitoringRuleService(database_path=database.path)
    if not rule_service.list_rules().rules:
        rule_service.create_rule(
            MonitoringRuleCreate(
                name=rule_name,
                monitoring_objects=list(terms),
                issue_keywords=[],
                enabled=True,
            )
        )
    repository = SearchRunRepository(database)
    run = repository.create_run(
        monitoring_rule_id=1,
        platform="wb",
        rule_name=rule_name,
        terms=terms,
        max_results_per_term=50,
    )
    repository.mark_running(run.id)
    for position in range(len(terms)):
        repository.set_progress(run.id, position)
        for index in range(position * 50, min((position + 1) * 50, count)):
            identity = str(start + index)
            repository.observe_item(
                run_id=run.id,
                term_position=position,
                item=SearchContentInput(
                    identity,
                    "post",
                    f"搜索标题 {index}",
                    "不是完整正文",
                    "",
                    "",
                    "刚刚",
                    f"https://m.weibo.cn/detail/{identity}",
                    "2026-08-28T00:00:00+00:00",
                ),
            )
        repository.complete_term(
            run.id, position, min(50, max(0, count - position * 50))
        )
    if terminal is not None:
        repository.finish(run.id, terminal)
    return run.id


class MediaWorker:
    def __init__(self, *, media=False):
        self.root = None
        self.calls = []
        self.media = media
        self.partial = set()
        self.body = "完整的原文内容，来源反映当地问题。"
        self.gate = None
        self.entered = asyncio.Event()

    def configure_media_spool(self, root):
        self.root = root

    async def discard_session(self):
        pass

    async def enrich(
        self, *, request_id, platform, content_id, content_url, term, budget
    ):
        self.calls.append((content_id, term))
        payload = content_payload(platform, content_id, content_url)
        payload["text"]["body"] = self.body
        if self.media:
            asset = image_asset()
            write_file(self.root / request_id.hex, asset["asset_id"], PNG)
            payload.update(assets=[asset], detected_modalities=["text", "image"])
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if content_id in self.partial:
            payload.update(
                status="partial",
                media_inventory_complete=False,
                issues=[{"code": "inventory_unknown", "asset_position": None}],
            )
        return EnrichmentWorkerResult(
            "completed", EnrichedContent.model_validate(payload)
        )


class ModelClient:
    def __init__(self):
        self.calls = []
        self.item_answers = []
        self.summary_answer = None
        self.usage = USAGE
        self.gate = None
        self.block_stage = "analysis"
        self.entered = asyncio.Event()
        self.closed = False
        self.coordinator = None

    async def test_connection(self, configuration):
        raise AssertionError("summary must not run a connection test")

    async def aclose(self):
        self.closed = True

    async def complete(
        self, configuration, *, messages, max_tokens, deadline, include_usage
    ):
        assert configuration.api_key.get_secret_value() == KEY
        assert deadline == 180 and include_usage is True
        stage = "analysis" if max_tokens == 2048 else "composition"
        self.calls.append((stage, messages))
        if self.coordinator is not None:
            owner = self.coordinator._owner
            assert (owner is None) == (stage == "composition")
        if self.gate is not None and self.block_stage == stage:
            self.entered.set()
            await self.gate.wait()
        if stage == "analysis":
            answer = (
                self.item_answers.pop(0)
                if self.item_answers
                else {
                    "decision": "relevant",
                    "reason": "属于监控范围。",
                    "evidence_summary": "来源反映当地问题，尚未核实。",
                }
            )
        else:
            data = json.loads(messages[1]["content"])
            answer = (
                self.summary_answer
                if self.summary_answer is not None
                else {
                    "overview": "以下是来源反映的情况。",
                    "items": [
                        {
                            "text": "来源反映了相关问题，尚未核实。",
                            "source_ids": [row["source_id"] for row in data["sources"]],
                        }
                    ],
                }
            )
        if isinstance(answer, Exception):
            raise answer
        return AICompletion(
            answer
            if isinstance(answer, str)
            else json.dumps(answer, ensure_ascii=False),
            self.usage,
        )


def environment(tmp_path: Path, *, count=1, media=True):
    database = Database(tmp_path / "summary.sqlite3")
    initialize_database(database)
    source_run_id = seed_run(database, count)
    client = ModelClient()
    settings = AISettingsService(database, client=client)
    settings.save(AISettingsUpdate(base_url=BASE, model=MODEL, api_key=SecretStr(KEY)))
    worker = MediaWorker(media=media)
    coordinator = BrowserOperationCoordinator()
    client.coordinator = coordinator
    enrichment = ContentEnrichmentService(
        repository=SearchRunRepository(database),
        worker=worker,
        browser_operations=coordinator,
        spool=MediaSpool(tmp_path / "media"),
    )
    service = SummaryService(
        database=database, ai_settings=settings, enrichment=enrichment
    )
    service.initialize()
    return database, source_run_id, service, settings, client, worker, coordinator


async def finished(service):
    assert service._runner is not None
    await asyncio.wait_for(asyncio.shield(service._runner), 10)
    return service.read(service._active_id)
