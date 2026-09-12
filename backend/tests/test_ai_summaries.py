"""Full manual pipeline, immutable reuse, truthful accounting and ownership tests."""

import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import SecretStr
from summary_fixtures import BASE, KEY, MODEL, environment, finished, seed_run

from opinion_workbench_api.schemas.ai_settings import AISettingsUpdate
from opinion_workbench_api.schemas.ai_summaries import SummaryCreate
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.browser_operations import BrowserOperationOwner
from opinion_workbench_api.services.summary_errors import SummaryError


def payload(*, force=False, revision=1, request_id=None):
    return SummaryCreate(
        request_id=request_id or str(uuid4()),
        force_refresh=force,
        configuration_revision=revision,
    )


def test_full_pipeline_text_only_composition_and_canonical_reuse(tmp_path):
    database, source, service, _, client, worker, coordinator = environment(
        tmp_path, count=3
    )
    client.item_answers = [
        {"decision": decision, "reason": "解释。", "evidence_summary": "来源陈述。"}
        for decision in ("relevant", "irrelevant", "uncertain")
    ]

    async def scenario():
        requested = payload()
        created = await service.create(source, requested)
        result = await finished(service)
        assert result.status == "completed"
        assert result.counts.model_dump() == dict(
            total=3,
            pending=0,
            analysing=0,
            relevant=1,
            irrelevant=1,
            uncertain=1,
            input_incomplete=0,
            failed=0,
            cancelled=0,
            interrupted=0,
            reused=0,
        )
        assert len(worker.calls) == 3 and len(client.calls) == 4
        assert result.usage.attempted_requests == 4 and result.usage.total_tokens == 60
        assert result.usage.complete
        for stage, messages in client.calls[:3]:
            assert stage == "analysis"
            assert isinstance(messages[1]["content"], str)
            assert "image_url" not in messages[1]["content"]
        composition = client.calls[-1][1]
        assert isinstance(composition[1]["content"], str)
        body = json.loads(composition[1]["content"])
        assert len(body["sources"]) == 1
        assert body["sources"][0]["body"] == worker.body
        assert "不是完整正文" not in composition[1]["content"]
        assert "data:image" not in composition[1]["content"]
        assert coordinator._owner is None and not list((tmp_path / "media").iterdir())
        assert (await service.create(source, requested)).id == created.id
        assert len(client.calls) == 4
        canonical = service.repository.items(result.id).items
        for _ in range(2):
            await service.create(source, payload())
            reused = await finished(service)
            assert reused.counts.reused == 3
            assert (
                reused.usage.attempted_requests == 1 and reused.usage.total_tokens == 15
            )
            items = service.repository.items(reused.id).items
            assert [item.reused_from_item_id for item in items] == [
                item.id for item in canonical
            ]
            assert all(not item.attempted and item.usage is None for item in items)
        assert len(worker.calls) == 3
        with database.connect() as connection:
            serialized = " ".join(
                row[0] or ""
                for row in connection.execute("SELECT input_json FROM ai_summary_items")
            )
        assert "blob_ref" not in serialized and "asset_id" not in serialized
        assert KEY not in serialized and "data:image" not in serialized
        await service.shutdown()

    asyncio.run(scenario())


def test_incomplete_uncertain_and_invalid_output_are_distinct_with_usage(tmp_path):
    _, source, service, _, client, worker, _ = environment(tmp_path, count=3)
    worker.partial.add("1000")
    client.item_answers = [
        {
            "decision": "uncertain",
            "reason": "地点不明确。",
            "evidence_summary": "无法确认地点。",
        },
        "not-json",
    ]

    async def scenario():
        await service.create(source, payload())
        result = await finished(service)
        assert result.status == "completed" and result.document.items == []
        assert (
            result.counts.input_incomplete
            == result.counts.uncertain
            == result.counts.failed
            == 1
        )
        assert len(client.calls) == 2 and all(
            stage == "analysis" for stage, _ in client.calls
        )
        items = service.repository.items(result.id).items
        assert items[0].attempted is False and items[0].input_issues == [
            "inventory_unknown"
        ]
        assert items[1].status == "completed" and items[1].decision == "uncertain"
        assert (
            items[2].error.code == "invalid_json" and items[2].usage.total_tokens == 15
        )
        assert result.usage.total_tokens == 30

    asyncio.run(scenario())


def test_failed_composition_preserves_analysis_and_retries_only_composition(tmp_path):
    _, source, service, _, client, worker, _ = environment(tmp_path)
    client.summary_answer = {
        "overview": "错误引用。",
        "items": [{"text": "内容。", "source_ids": [999999]}],
    }

    async def scenario():
        await service.create(source, payload())
        failed = await finished(service)
        assert failed.status == "failed" and failed.error.code == "invalid_citations"
        assert failed.counts.relevant == 1 and failed.usage.total_tokens == 30
        original = service.repository.items(failed.id).items[0]
        client.summary_answer = None
        await service.create(source, payload())
        retry = await finished(service)
        assert retry.status == "completed" and retry.counts.reused == 1
        assert len(worker.calls) == 1 and [stage for stage, _ in client.calls] == [
            "analysis",
            "composition",
            "composition",
        ]
        assert (
            service.repository.items(retry.id).items[0].reused_from_item_id
            == original.id
        )
        assert service.read(failed.id) == failed

    asyncio.run(scenario())


def test_known_input_change_after_failed_force_does_not_resurrect_stale_analysis(
    tmp_path,
):
    _, source, service, _, client, worker, _ = environment(tmp_path)

    async def scenario():
        await service.create(source, payload())
        first = await finished(service)
        worker.body = "原文已经修改，内容与之前不同。"
        client.item_answers = ["malformed"]
        await service.create(source, payload(force=True))
        refreshed = await finished(service)
        assert refreshed.counts.failed == 1
        await service.create(source, payload())
        latest = await finished(service)
        assert latest.counts.reused == 0 and len(worker.calls) == 3
        assert service.read(first.id) == first

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change", ["relative_time", "observation", "rule", "configuration"]
)
def test_reuse_tracks_known_versions_not_relative_display_time(tmp_path, change):
    database, source, service, settings, client, worker, _ = environment(tmp_path)

    async def scenario():
        await service.create(source, payload())
        first = await finished(service)
        before = service.repository.items(first.id).items[0].source
        revision = 1
        with database.connect() as connection:
            if change == "relative_time":
                connection.execute(
                    "UPDATE search_contents SET published_at_text='昨天'"
                )
            elif change == "observation":
                connection.execute("UPDATE search_contents SET snippet='新的搜索摘要'")
            elif change == "rule":
                connection.execute(
                    "UPDATE search_runs SET rule_name='不同历史范围' WHERE id=?",
                    (source,),
                )
        if change == "configuration":
            settings.save(
                AISettingsUpdate(base_url=BASE, model=MODEL, api_key=SecretStr(KEY))
            )
            revision = 2
        await service.create(source, payload(revision=revision))
        result = await finished(service)
        assert result.counts.reused == (1 if change == "relative_time" else 0)
        assert len(worker.calls) == (1 if change == "relative_time" else 2)
        assert service.repository.items(first.id).items[0].source == before

    asyncio.run(scenario())


def test_all_pages_and_new_repeat_results_are_frozen(tmp_path):
    database, source, service, _, client, worker, _ = environment(
        tmp_path, count=60, media=False
    )
    # A second run observes the same 60 rows: summary must include repeats too.
    source = seed_run(database, 60)

    async def scenario():
        await service.create(source, payload())
        result = await finished(service)
        assert result.counts.total == 60 and result.counts.relevant == 60
        assert len(worker.calls) == 60 and len(client.calls) == 61
        assert len(service.repository.items(result.id, limit=50).items) == 50
        assert len(service.repository.items(result.id, limit=50, offset=50).items) == 10
        assert len(service.repository.items(result.id, limit=100).items) == 60

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "count,terminal,code",
    [
        (0, "completed_empty", "ai_summary_empty_source"),
        (101, "completed_with_results", "ai_summary_source_limit"),
        (1, None, "ai_summary_source_active"),
    ],
)
def test_admission_rejects_before_media_or_model(tmp_path, count, terminal, code):
    database, _, service, _, client, worker, _ = environment(tmp_path)
    source = seed_run(database, count, terminal=terminal)

    async def scenario():
        with pytest.raises(SummaryError, match=code):
            await service.create(source, payload())
        assert worker.calls == client.calls == []
        assert service.repository.list(source).summaries == []

    asyncio.run(scenario())


def test_revision_staleness_replay_conflict_and_operation_exclusion(tmp_path):
    _, source, service, settings, client, worker, _ = environment(tmp_path)
    client.gate = asyncio.Event()

    async def scenario():
        with pytest.raises(AIError, match="ai_configuration_changed"):
            await service.create(source, payload(revision=2))
        assert worker.calls == []
        requested = payload()
        run = await service.create(source, requested)
        await asyncio.wait_for(client.entered.wait(), 5)
        assert (await service.create(source, requested)).id == run.id
        for change in (
            payload(force=True, request_id=requested.request_id),
            payload(revision=2, request_id=requested.request_id),
        ):
            with pytest.raises(SummaryError, match="ai_summary_request_conflict"):
                await service.create(source, change)
        with pytest.raises(AIError, match="ai_operation_active"):
            await service.create(source, payload())
        with pytest.raises(AIError, match="ai_operation_active"):
            settings.save(AISettingsUpdate(base_url=BASE, model=MODEL))
        with pytest.raises(AIError, match="ai_operation_active"):
            await settings.test_connection(1)
        await service.cancel(run.id)
        settings.save(AISettingsUpdate(base_url=BASE, model=MODEL))

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["acquisition", "analysis", "composition"])
def test_cancel_settles_owned_work_releases_leases_preserves_completed_items(
    tmp_path, stage
):
    _, source, service, settings, client, worker, coordinator = environment(tmp_path)
    blocker = worker if stage == "acquisition" else client
    blocker.gate = asyncio.Event()
    client.block_stage = stage

    async def scenario():
        run = await service.create(source, payload())
        await asyncio.wait_for(blocker.entered.wait(), 5)
        result = await service.cancel(run.id)
        assert (
            result.status == "cancelled"
            and result.counts.pending == result.counts.analysing == 0
        )
        assert result.counts.relevant == (1 if stage == "composition" else 0)
        assert coordinator._owner is None
        assert not list((tmp_path / "media").iterdir())
        assert await service.cancel(run.id) == result
        settings.save(AISettingsUpdate(base_url=BASE, model=MODEL))
        await service.shutdown()

    asyncio.run(scenario())


def test_browser_contention_fails_without_stealing_paused_owner(tmp_path):
    _, source, service, _, client, worker, coordinator = environment(tmp_path)

    async def scenario():
        owner = BrowserOperationOwner("search_batch", uuid4())
        assert await coordinator.try_claim(owner)
        await service.create(source, payload())
        result = await finished(service)
        assert (
            result.status == "failed"
            and result.error.code == "browser_operation_active"
        )
        assert await coordinator.is_owned_by(owner)
        assert worker.calls == client.calls == []
        await coordinator.release(owner)

    asyncio.run(scenario())


def test_summary_bound_fails_before_composition_without_losing_item_analysis(tmp_path):
    _, source, service, _, client, worker, _ = environment(
        tmp_path, count=7, media=False
    )
    worker.body = "文" * 19000

    async def scenario():
        await service.create(source, payload())
        result = await finished(service)
        assert result.status == "failed" and result.error.code == "request_too_large"
        assert result.counts.relevant == 7 and len(client.calls) == 7
        assert result.usage.attempted_requests == 7

    asyncio.run(scenario())


def test_missing_usage_is_unknown_and_secret_answer_not_persisted(tmp_path):
    database, source, service, _, client, _, _ = environment(tmp_path)
    client.usage = None
    client.item_answers = [
        {"decision": "relevant", "reason": KEY, "evidence_summary": "内容。"}
    ]

    async def scenario():
        await service.create(source, payload())
        result = await finished(service)
        assert result.usage.complete is False and result.usage.total_tokens is None
        item = service.repository.items(result.id).items[0]
        assert item.status == "failed" and item.error.code == "credential_leakage"
        assert KEY not in item.model_dump_json()
        with database.connect() as connection:
            rows = connection.execute(
                "SELECT reason,evidence_summary,error_json FROM ai_summary_items"
            ).fetchall()
        assert KEY not in repr([tuple(row) for row in rows])

    asyncio.run(scenario())
