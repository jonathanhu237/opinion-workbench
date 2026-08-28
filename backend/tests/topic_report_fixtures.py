"""Fail-closed fake transport and actual A/C services over disposable SQLite."""

import asyncio
import json
from collections import Counter
from uuid import uuid4

from initial_analysis_fixtures import (
    UNDERSTANDING,
    request,
)
from initial_analysis_fixtures import (
    environment as initial_environment,
)
from summary_fixtures import KEY, USAGE, seed_run

from longtian_api.schemas.topic_reports import ReportCreate, ReportRetry
from longtian_api.services.ai_client import AICompletion
from longtian_api.services.topic_reports import TopicReportService


class TextPipelineClient:
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
        self.calls = []
        self.counts = Counter()
        self.decisions = {}
        self.answers = {}
        self.usage = USAGE
        self.block_stage = None
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()
        self.closed = False
        self.failed_override = False

    async def test_connection(self, configuration):
        raise AssertionError("report must not run a connection test")

    async def aclose(self):
        self.closed = True

    async def complete(
        self, configuration, *, messages, max_tokens, deadline, include_usage
    ):
        assert configuration.api_key.get_secret_value() == KEY
        assert deadline == 180 and include_usage is True
        user = messages[1]["content"]
        payload = json.loads(user[0]["text"] if isinstance(user, list) else user)
        if "children" in payload:
            stage = "overview"
            answer = {
                "overview": "各章节归纳的来源陈述，尚未核实。",
                "items": [
                    {
                        "text": "来源反映的问题及时间仍需核实。",
                        "child_ids": [child["key"] for child in payload["children"]],
                    }
                ],
            }
        elif "sources" in payload:
            stage = "leaf"
            answer = {
                "overview": "以下内容来自保存的相关材料。",
                "items": [
                    {
                        "text": "来源称有积水情况，地点与发生时间仍需核实。",
                        "source_ids": [
                            source["result_id"] for source in payload["sources"]
                        ],
                    }
                ],
            }
        elif "understanding" in payload["source"]:
            stage = "judgment"
            answer = {
                "decision": self.decisions.get(
                    payload["source"]["result_id"], "relevant"
                ),
                "reason": "根据已保存的地点线索判断，来源陈述尚未核实。",
            }
        else:
            stage, answer = "initial", UNDERSTANDING
        self.counts[stage] += 1
        self.calls.append((stage, messages))
        if stage != "initial":
            assert isinstance(user, str) and max_tokens == (
                2048 if stage == "judgment" else 4096
            )
            if self.coordinator is not None:
                assert self.coordinator._owner is None
        if stage == self.block_stage:
            self.entered.set()
            await self.gate.wait()
        if self.answers.get(stage):
            answer = self.answers[stage].pop(0)
        if (
            stage == "leaf"
            and "验收：失败一次" in messages[0]["content"]
            and not self.failed_override
        ):
            self.failed_override = True
            answer = {
                "overview": "合成失败",
                "items": [{"text": "合成无效引用", "source_ids": [9007199254740991]}],
            }
        if isinstance(answer, Exception):
            raise answer
        return AICompletion(
            answer
            if isinstance(answer, str)
            else json.dumps(answer, ensure_ascii=False),
            self.usage,
        )


def environment(tmp_path, *, count=10, media=False):
    database, _, initial, ai, _, worker, coordinator = initial_environment(
        tmp_path, count=0, media=media
    )
    for offset in range(0, count, 150):
        seed_run(database, min(150, count - offset), start=1000 + offset)
    model = TextPipelineClient(coordinator)
    ai._client = model
    reports = TopicReportService(database=database, ai_settings=ai)
    reports.initialize()
    initial.on_job_finished = reports.initial_analysis_finished
    return database, initial, reports, ai, model, worker, coordinator


async def finish(service):
    task = service._runner
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 60)


async def analyse_all(database, initial, reports):
    admission = await initial.create(request(database))
    await finish(initial)
    await finish(reports)
    return admission.job, reports.repository.list(
        initial_job_id=admission.job.id
    ).reports[0]


def retry_request(report, **overrides):
    return ReportRetry.model_validate(
        {
            "request_id": str(uuid4()),
            "expected_revision": report.revision,
            "configuration_revision": report.configuration_revision,
            "instructions_override": None,
            **overrides,
        }
    )


def interval_request(database, **overrides):
    from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository

    return ReportCreate.model_validate(
        {
            "request_id": str(uuid4()),
            "configuration_revision": 1,
            "report_prompt_version_id": AnalysisSettingsRepository(database)
            .read()
            .report_prompt.id,
            "instructions_override": None,
            "selection": {
                "kind": "first_seen_interval",
                "first_seen_from": "2020-01-01T00:00:00Z",
                "first_seen_to": "2030-01-01T00:00:00Z",
            },
            **overrides,
        }
    )


def api_environment(tmp_path, *, count=10, **options):
    from test_content_analysis_api import api_fixture

    app, database, transport, media = api_fixture(
        tmp_path,
        count=count,
        topic_reports_available=True,
        analysis_automation_available=True,
        collection_automation_available=True,
        **options,
    )
    model = TextPipelineClient()
    # Existing fixture owns the AISettingsService and fail-closed acquisition.
    # Replace only its injected synthetic transport operation, never production IO.
    transport.complete = model.complete
    return app, database, model, media
