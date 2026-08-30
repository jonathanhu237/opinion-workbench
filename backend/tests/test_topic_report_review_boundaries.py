"""Independent C integration regressions over disposable, fake-only A/C state."""

import asyncio
import json
from contextlib import asynccontextmanager, closing

import pytest
from initial_analysis_fixtures import request
from topic_report_fixtures import (
    analyse_all,
    environment,
    finish,
    interval_request,
    retry_request,
)

from longtian_api.services.topic_report_engine import canonical_hash, output_digest
from longtian_api.services.topic_report_errors import ERRORS, TopicReportError


@asynccontextmanager
async def review_environment(tmp_path, *, count=1):
    values = environment(tmp_path, count=count)
    _, initial, reports, ai, _, _, _ = values
    try:
        yield values
    finally:
        await initial.shutdown()
        await reports.shutdown()
        await ai.shutdown()


def allow_fixture_damage(connection, *tables):
    """Only disposable fixtures: model old/damaged storage despite write guards."""
    for table in tables:
        triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for trigger in triggers:
            quoted = trigger[0].replace('"', '""')
            connection.execute(f'DROP TRIGGER "{quoted}"')


def assert_storage_failure(error):
    assert error.code == "topic_report_storage_unavailable"
    assert (error.status_code, error.message) == ERRORS[error.code]


def test_interval_wrong_latest_claim_identity_rolls_back_entire_admission(tmp_path):
    async def run():
        async with review_environment(tmp_path, count=2) as values:
            db, initial, reports, _, model, worker, _ = values
            with closing(db.connect()) as connection:
                connection.execute(
                    "UPDATE search_contents SET first_seen_at=? WHERE id=2",
                    ("2035-01-01T00:00:00+00:00",),
                )
            job, _ = await analyse_all(db, initial, reports)
            attempts = initial.repository.items(job.id).items
            assert attempts[0].source.result_id != attempts[1].source.result_id
            with closing(db.connect()) as connection:
                connection.execute(
                    """UPDATE content_analysis_claims SET latest_attempt_id=?
                      WHERE content_id=1""",
                    (attempts[1].id,),
                )
            payload = interval_request(db)
            baseline = model.counts.copy(), len(worker.calls)
            with pytest.raises(TopicReportError) as raised:
                reports.repository.create(payload)
            assert_storage_failure(raised.value)
            assert len(reports.repository.list().reports) == 1
            with closing(db.connect()) as connection:
                assert (
                    connection.execute(
                        "SELECT 1 FROM topic_report_requests WHERE request_id=?",
                        (payload.request_id,),
                    ).fetchone()
                    is None
                )
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_existing_report_with_pending_event_is_not_consumed_on_startup(
    tmp_path, monkeypatch
):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            job, report = await analyse_all(db, initial, reports)
            original = reports.repository._consume
            calls = 0

            def bounded_consume(*args, **kwargs):
                nonlocal calls
                calls += 1
                assert calls == 1, "startup repeatedly selected one damaged event"
                return original(*args, **kwargs)

            monkeypatch.setattr(reports.repository, "_consume", bounded_consume)
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "analysis_completion_events")
                connection.execute(
                    """UPDATE analysis_completion_events SET state='pending'
                      WHERE job_id=?""",
                    (job.id,),
                )
            baseline = model.counts.copy(), len(worker.calls)
            try:
                reports.initialize()
                assert calls == 0
                assert (model.counts, len(worker.calls)) == baseline
                with closing(db.connect()) as connection:
                    assert (
                        connection.execute(
                            "SELECT id FROM topic_report_runs"
                        ).fetchall()[0][0]
                        == report.id
                    )
                    assert (
                        connection.execute(
                            "SELECT COUNT(*) FROM topic_report_runs"
                        ).fetchone()[0]
                        == 1
                    )
            finally:
                with closing(db.connect()) as connection:
                    connection.execute(
                        """UPDATE analysis_completion_events SET state='consumed'
                          WHERE job_id=?""",
                        (job.id,),
                    )

    asyncio.run(run())


def test_interval_uses_exact_microseconds_and_excludes_both_outside_boundaries(
    tmp_path,
):
    async def run():
        async with review_environment(tmp_path, count=5) as values:
            db, _, reports, _, model, worker, _ = values
            instants = [
                "2026-08-29T00:00:00.123456+00:00",
                "2026-08-29T00:00:00.123499Z",
                "2026-08-29T00:00:00.123500+00:00",
                "2026-08-29T00:00:00.123501Z",
                "2026-08-29T00:00:00.123550+00:00",
            ]
            with closing(db.connect()) as connection:
                connection.executemany(
                    "UPDATE search_contents SET first_seen_at=? WHERE id=?",
                    [(value, index) for index, value in enumerate(instants, 1)],
                )
            report = reports.repository.create(
                interval_request(
                    db,
                    selection={
                        "kind": "first_seen_interval",
                        "first_seen_from": "2026-08-29T00:00:00.123499+00:00",
                        "first_seen_to": "2026-08-29T00:00:00.123501Z",
                    },
                )
            )
            sources = reports.repository.sources(report.id).items
            assert [item.source.result_id for item in sources] == [2, 3]
            assert [item.position for item in sources] == [0, 1]
            assert [item.first_seen_at for item in sources] == instants[1:3]
            assert (report.coverage.total, report.coverage.unavailable) == (2, 2)
            assert not model.calls and not worker.calls

    asyncio.run(run())


@pytest.mark.parametrize("changed_input", [False, True])
def test_interval_uses_latest_eligible_success_but_never_revives_new_input_failure(
    tmp_path, changed_input
):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            first_job, _ = await analyse_all(db, initial, reports)
            successful = initial.repository.items(first_job.id).items[0]
            if changed_input:
                worker.body = "已经变化的完整原文，不能复活旧输入的成功分析。"
            model.answers["initial"] = ["not valid JSON"]
            second = await initial.create(
                request(db, kind="reanalysis", result_ids=[1], force_refresh=True)
            )
            await finish(initial)
            await finish(reports)
            failed = initial.repository.items(second.job.id).items[0]
            assert failed.status == "failed"
            assert (failed.input_fingerprint != successful.input_fingerprint) == (
                changed_input
            )
            baseline = model.counts.copy(), len(worker.calls)
            report = reports.repository.create(interval_request(db))
            source = reports.repository.sources(report.id).items[0]
            if changed_input:
                assert report.coverage.ready == 0
                assert source.initial_attempt_id == failed.id
                assert source.unavailable_reason == "failed"
            else:
                assert report.coverage.ready == 1
                assert source.initial_attempt_id == successful.id
                assert source.initial_status == "completed"
                assert source.unavailable_reason is None
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


@pytest.mark.parametrize("latest_state", ["queued", "acquiring", "analysing"])
def test_interval_freezes_compatible_success_without_waiting_for_active_latest(
    tmp_path, latest_state
):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            first_job, _ = await analyse_all(db, initial, reports)
            successful = initial.repository.items(first_job.id).items[0]
            admitted = initial.repository.create(
                request(db, kind="reanalysis", result_ids=[1], force_refresh=True)
            )
            latest = initial.repository.items(admitted.job.id).items[0]
            if latest_state != "queued":
                initial.repository.start(admitted.job.id)
                initial.repository.begin(latest.id)
                initial.repository.save_input(
                    latest.id, successful.input, successful.input_fingerprint
                )
                if latest_state == "analysing":
                    initial.repository.mark_attempt(latest.id)
            assert initial.repository.attempt(latest.id).status == latest_state
            baseline = model.counts.copy(), len(worker.calls)
            report = reports.repository.create(interval_request(db))
            source = reports.repository.sources(report.id).items[0]
            assert report.coverage.ready == 1
            assert source.initial_attempt_id == successful.id
            assert source.unavailable_reason is None
            assert initial.repository.attempt(latest.id).status == latest_state
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_fresh_execution_cannot_overwrite_a_changed_preplanned_input_hash(tmp_path):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            _, parent = await analyse_all(db, initial, reports)
            report = reports.repository.retry(parent.id, retry_request(parent))
            node = reports.repository.nodes(report.id, kind="judgment")[0]
            call = await reports._fresh_call(reports.repository.context(report), node)
            reports.repository.prepare(node["id"], call, "topic-text-engine-v1")
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_nodes")
                connection.execute(
                    "UPDATE topic_report_nodes SET input_hash=? WHERE id=?",
                    ("0" * 64, node["id"]),
                )
            baseline = model.counts.copy(), len(worker.calls)
            with pytest.raises(TopicReportError) as raised:
                reports.repository.prepare(node["id"], call, "topic-text-engine-v1")
            assert_storage_failure(raised.value)
            saved = reports.repository.nodes(report.id, kind="judgment")[0]
            assert saved["input_hash"] == "0" * 64 and saved["attempted"] == 0
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_forged_candidate_hash_cannot_replace_original_frozen_prompt_proof(tmp_path):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            _, parent = await analyse_all(db, initial, reports)
            report = reports.repository.retry(
                parent.id,
                retry_request(parent, instructions_override="只讨论新的专用主题。"),
            )
            candidate = reports.repository.nodes(parent.id, kind="judgment")[0]
            node = reports.repository.nodes(report.id, kind="judgment")[0]
            fresh = await reports._fresh_call(reports.repository.context(report), node)
            assert fresh.input_hash != candidate["input_hash"]
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_nodes")
                connection.execute(
                    "UPDATE topic_report_nodes SET input_hash=? WHERE id=?",
                    (fresh.input_hash, candidate["id"]),
                )
            baseline = model.counts.copy(), len(worker.calls)
            await reports._launch()
            await finish(reports)
            saved = reports.repository.read(report.id)
            assert saved.status == "interrupted"
            assert saved.nodes.judgments.reused == 0
            assert saved.usage.total.attempted_requests == 0
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["judgment", "leaf", "overview"])
def test_projection_rejects_changed_output_even_when_json_shape_remains_valid(
    tmp_path, kind
):
    async def run():
        async with review_environment(tmp_path, count=9) as values:
            db, initial, reports, _, model, worker, _ = values
            _, report = await analyse_all(db, initial, reports)
            node = reports.repository.nodes(report.id, kind=kind)[0]
            output = json.loads(node["output_json"])
            output["reason" if kind == "judgment" else "overview"] = (
                "损坏后仍符合形状的不同文字。"
            )
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_nodes")
                connection.execute(
                    "UPDATE topic_report_nodes SET output_json=? WHERE id=?",
                    (json.dumps(output, ensure_ascii=False), node["id"]),
                )
            baseline = model.counts.copy(), len(worker.calls)
            with pytest.raises(TopicReportError) as raised:
                reports.repository.read(report.id)
            assert_storage_failure(raised.value)
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_recomputed_child_hashes_cannot_hide_overlapping_actual_members(tmp_path):
    async def run():
        async with review_environment(tmp_path, count=9) as values:
            db, initial, reports, _, model, worker, _ = values
            _, report = await analyse_all(db, initial, reports)
            leaf = reports.repository.nodes(report.id, kind="leaf")[1]
            output = json.loads(leaf["output_json"])
            output["items"][0]["source_ids"] = [1]
            with closing(db.connect()) as connection:
                allow_fixture_damage(
                    connection, "topic_report_nodes", "topic_report_node_sources"
                )
                source_id = connection.execute(
                    """SELECT id FROM topic_report_sources
                      WHERE report_id=? AND content_id=1""",
                    (report.id,),
                ).fetchone()[0]
                connection.execute(
                    "UPDATE topic_report_node_sources SET source_id=? WHERE node_id=?",
                    (source_id, leaf["id"]),
                )
                connection.execute(
                    """UPDATE topic_report_nodes SET output_json=?,output_hash=?,
                      membership_hash=? WHERE id=?""",
                    (
                        json.dumps(output, ensure_ascii=False),
                        output_digest("leaf", output),
                        canonical_hash(
                            {"schema": "topic-membership-v1", "source_ids": [1]}
                        ),
                        leaf["id"],
                    ),
                )
            baseline = model.counts.copy(), len(worker.calls)
            with pytest.raises(TopicReportError) as raised:
                reports.repository.section(report.id, report.root_section_id)
            assert_storage_failure(raised.value)
            with pytest.raises(TopicReportError):
                reports.repository.read(report.id)
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


@pytest.mark.parametrize(
    ("column", "value"),
    [("base_url", "https://secret@example.com/v1"), ("model", "unsafe\nmodel")],
)
def test_report_provider_projection_is_validated_before_returning_saved_strings(
    tmp_path, column, value
):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            _, report = await analyse_all(db, initial, reports)
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_runs")
                connection.execute(
                    f"UPDATE topic_report_runs SET {column}=? WHERE id=?",
                    (value, report.id),
                )
            baseline = model.counts.copy(), len(worker.calls)
            with pytest.raises(TopicReportError) as raised:
                reports.repository.read(report.id)
            assert_storage_failure(raised.value)
            assert value not in raised.value.message
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


@pytest.mark.parametrize("changed_field", ["source_json", "initial_attempt_id"])
def test_source_projection_cannot_relabel_its_frozen_evidence_identity(
    tmp_path, changed_field
):
    async def run():
        async with review_environment(tmp_path, count=2) as values:
            db, initial, reports, _, model, worker, _ = values
            _, report = await analyse_all(db, initial, reports)
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_sources")
                row = connection.execute(
                    """SELECT * FROM topic_report_sources
                      WHERE report_id=? AND content_id=1""",
                    (report.id,),
                ).fetchone()
                if changed_field == "source_json":
                    source = json.loads(row["source_json"])
                    source["result_id"] = 2
                    replacement = json.dumps(source, ensure_ascii=False)
                else:
                    replacement = connection.execute(
                        """SELECT initial_attempt_id FROM topic_report_sources
                          WHERE report_id=? AND content_id=2""",
                        (report.id,),
                    ).fetchone()[0]
                connection.execute(
                    f"UPDATE topic_report_sources SET {changed_field}=? WHERE id=?",
                    (replacement, row["id"]),
                )
            baseline = model.counts.copy(), len(worker.calls)
            for read in (
                lambda: reports.repository.sources(report.id),
                lambda: reports.repository.read(report.id),
            ):
                with pytest.raises(TopicReportError) as raised:
                    read()
                assert_storage_failure(raised.value)
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_damaged_retry_ancestry_cannot_loop_during_canonical_reuse(
    tmp_path, monkeypatch
):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            _, parent = await analyse_all(db, initial, reports)
            report = reports.repository.retry(parent.id, retry_request(parent))
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_runs")
                connection.execute("PRAGMA ignore_check_constraints=ON")
                connection.execute(
                    "UPDATE topic_report_runs SET parent_report_id=? WHERE id=?",
                    (report.id, report.id),
                )
            original = reports.repository._require
            reads = 0

            def bounded_require(*args, **kwargs):
                nonlocal reads
                reads += 1
                assert reads <= 2, "reuse repeatedly followed a cyclic report parent"
                return original(*args, **kwargs)

            monkeypatch.setattr(reports.repository, "_require", bounded_require)
            baseline = model.counts.copy(), len(worker.calls)
            try:
                with pytest.raises(TopicReportError) as raised:
                    reports.repository.reuse_candidate(report.id, "judgment:1")
                assert_storage_failure(raised.value)
                assert (model.counts, len(worker.calls)) == baseline
            finally:
                monkeypatch.setattr(reports.repository, "_require", original)
                with closing(db.connect()) as connection:
                    connection.execute(
                        "UPDATE topic_report_runs SET parent_report_id=? WHERE id=?",
                        (parent.id, report.id),
                    )

    asyncio.run(run())


def test_retry_keeps_original_unavailable_member_after_later_initial_success(tmp_path):
    async def run():
        async with review_environment(tmp_path, count=2) as values:
            db, initial, reports, _, model, worker, _ = values
            worker.partial.add("1001")
            _, original = await analyse_all(db, initial, reports)
            unavailable = reports.repository.sources(original.id).items[1]
            assert original.coverage.ready == original.coverage.unavailable == 1
            assert unavailable.unavailable_reason == "input_incomplete"
            worker.partial.clear()
            later = await initial.create(
                request(db, kind="retry", result_ids=[2], force_refresh=True)
            )
            await finish(initial)
            await finish(reports)
            assert initial.repository.items(later.job.id).items[0].status == "completed"
            baseline = model.counts.copy(), len(worker.calls)
            retried = await reports.retry(original.id, retry_request(original))
            await finish(reports)
            retried = reports.repository.read(retried.id)
            assert retried.status == "completed"
            assert (retried.coverage.total, retried.coverage.ready) == (2, 1)
            assert reports.repository.sources(retried.id).items[1] == unavailable
            assert reports.repository.read(original.id) == original
            assert retried.usage.total.attempted_requests == 0
            assert (model.counts, len(worker.calls)) == baseline

    asyncio.run(run())


def test_persisted_prepared_messages_are_not_executable_reuse_authority(tmp_path):
    async def run():
        async with review_environment(tmp_path) as values:
            db, initial, reports, _, model, worker, _ = values
            _, original = await analyse_all(db, initial, reports)
            poison = '{"system_text":"audit payload must never become a request"}'
            with closing(db.connect()) as connection:
                allow_fixture_damage(connection, "topic_report_nodes")
                connection.execute(
                    "UPDATE topic_report_nodes SET prepared_json=? WHERE report_id=?",
                    (poison, original.id),
                )
            baseline = model.counts.copy(), len(worker.calls)
            retried = await reports.retry(original.id, retry_request(original))
            await finish(reports)
            retried = reports.repository.read(retried.id)
            assert retried.status == "completed"
            assert retried.nodes.judgments.reused == 1
            assert retried.nodes.composition.reused == 1
            assert retried.usage.total.attempted_requests == 0
            assert (model.counts, len(worker.calls)) == baseline
            with closing(db.connect()) as connection:
                fresh_audits = connection.execute(
                    "SELECT prepared_json FROM topic_report_nodes WHERE report_id=?",
                    (retried.id,),
                ).fetchall()
                assert all(poison not in row[0] for row in fresh_audits)
            assert reports.repository.read(original.id) == original

    asyncio.run(run())
