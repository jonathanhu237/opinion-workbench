"""Actual persisted A -> C pipeline with fake model calls and no browser/network."""

import asyncio

import pytest
from initial_analysis_fixtures import request
from topic_report_fixtures import (
    analyse_all,
    environment,
    finish,
    interval_request,
    retry_request,
)

from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
)


def test_ten_members_eight_successes_settle_one_report(tmp_path):
    async def run():
        db, initial, reports, ai, model, worker, coordinator = environment(tmp_path)

        worker.partial.update({"1008", "1009"})
        model.decisions.update({2: "irrelevant", 3: "uncertain"})
        job, report = await analyse_all(db, initial, reports)
        assert report.status == "completed", report
        assert report.coverage.total == 10
        assert (
            report.coverage.ready,
            report.coverage.unavailable,
            report.coverage.relevant,
            report.coverage.irrelevant,
            report.coverage.uncertain,
        ) == (10, 0, 8, 1, 1)
        assert model.counts == {"initial": 10, "judgment": 10, "leaf": 1}
        assert len(worker.calls) == 10 and coordinator._owner is None
        await reports.initial_analysis_finished(job.id)
        await finish(reports)
        assert len(reports.repository.list().reports) == 1
        assert (
            reports.repository.section(report.id, report.root_section_id).source_count
            == 8
        )
        assert len(reports.repository.sources(report.id, limit=1, offset=9).items) == 1
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("count", [101, 1001])
def test_all_sources_judged_bounded_tree_and_text_only_retry(tmp_path, count):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=count)

        _, report = await analyse_all(db, initial, reports)
        assert report.status == "completed", report
        assert model.counts["judgment"] == count
        assert report.coverage.relevant == count
        assert report.nodes.composition.total > 1
        baseline = model.counts.copy(), len(worker.calls)
        retried = await reports.retry(report.id, retry_request(report))
        await finish(reports)
        retried = reports.repository.read(retried.id)
        assert retried.status == "completed", retried
        assert retried.nodes.judgments.reused == count
        assert retried.nodes.composition.reused == report.nodes.composition.total
        assert retried.usage.total.attempted_requests == 0
        assert (model.counts, len(worker.calls)) == baseline
        root = reports.repository.section(retried.id, retried.root_section_id)
        assert root.source_count == count
        assert all(
            reports.repository.section(retried.id, child.id).report_id == retried.id
            for child in root.children
        )
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_failed_composition_retry_preserves_judgments_usage_and_evidence(
    tmp_path,
):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=9)

        model.answers["leaf"] = ["invalid JSON"] * 2
        _, report = await analyse_all(db, initial, reports)
        assert report.status == "failed", report
        assert report.coverage.relevant == 9
        assert (
            report.nodes.composition.failed == 1
            and report.nodes.composition.completed == 1
        )
        assert report.usage.composition.accounted_requests == 3
        baseline = len(worker.calls), model.counts["initial"], model.counts["judgment"]
        retried = await reports.retry(report.id, retry_request(report))
        await finish(reports)
        assert reports.repository.read(retried.id).status == "completed"
        assert (
            len(worker.calls),
            model.counts["initial"],
            model.counts["judgment"],
        ) == baseline
        assert model.counts["leaf"] == 4 and model.counts["overview"] == 1
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


@pytest.mark.parametrize("ready", [False, True])
def test_empty_outcomes_do_not_invent_calls(tmp_path, ready):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=2)

        if ready:
            model.decisions = {1: "irrelevant", 2: "uncertain"}
        else:
            worker.partial.update({"1000", "1001"})
        _, report = await analyse_all(db, initial, reports)
        assert report.status == ("empty" if ready else "completed"), report
        assert report.empty_reason == ("no_relevant_sources" if ready else None)
        assert model.counts["judgment"] == 2
        assert model.counts["leaf"] == (0 if ready else 1)
        assert model.counts["overview"] == 0
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_interval_with_no_results_is_empty_without_model(tmp_path):
    async def run():
        db, initial, reports, ai, model, _, _ = environment(tmp_path, count=0)

        report = await reports.create(interval_request(db))
        await finish(reports)
        assert reports.repository.read(report.id).status == "empty"
        assert not model.calls
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_cancelled_initial_job_does_not_emit_report(tmp_path):
    async def run():
        db, initial, reports, ai, model, _, _ = environment(tmp_path, count=2)

        model.block_stage = "initial"
        admission = await initial.create(request(db))
        await model.entered.wait()
        await initial.cancel(admission.job.id)
        assert reports.repository.list().reports == []
        assert model.counts["judgment"] == 0
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())


def test_current_source_edits_never_replace_frozen_report_or_retry_origins(
    tmp_path,
):
    async def run():
        db, initial, reports, ai, model, worker, _ = environment(tmp_path, count=0)
        repository = SearchRunRepository(db)
        collection = repository.create_run(
            monitoring_rule_id=1,
            platform="wb",
            rule_name="来源快照",
            terms=("历史词",),
            max_results_per_term=10,
        )
        repository.mark_running(collection.id)
        repository.set_progress(collection.id, 0)
        identity = "5012345678901234"
        url = f"https://m.weibo.cn/detail/{identity}"
        repository.observe_item(
            run_id=collection.id,
            term_position=0,
            item=SearchContentInput(
                identity,
                "post",
                "冻结标题",
                "冻结摘要",
                "",
                "",
                "昨天",
                url,
                "2026-08-28T00:00:00+00:00",
            ),
        )
        repository.complete_term(collection.id, 0, 1)
        repository.finish(collection.id, "completed_with_results")
        initial.on_job_finished = None
        admission = await initial.create(request(db))
        await finish(initial)
        frozen = initial.repository.items(admission.job.id).items[0]
        with db.connect() as connection:
            connection.execute(
                "UPDATE search_contents SET title='新的标题',snippet='新的摘要'"
            )
        await reports.initial_analysis_finished(admission.job.id)
        await finish(reports)
        report = reports.repository.list().reports[0]
        assert report.status == "completed"
        assert reports.repository.sources(report.id).items[0].source == frozen.source
        leaf = reports.repository.section(report.id, report.root_section_id)
        assert leaf.sources[0].source == frozen.source
        assert (
            leaf.sources[0].source.source_run_id,
            leaf.sources[0].source.result_id,
        ) == (collection.id, 1)
        baseline = model.counts.copy(), len(worker.calls)
        retried = await reports.retry(report.id, retry_request(report))
        await finish(reports)
        assert reports.repository.sources(retried.id).items[0].source == frozen.source
        assert (model.counts, len(worker.calls)) == baseline
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()

    asyncio.run(run())
