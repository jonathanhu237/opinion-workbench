"""Bounded repair and per-stage retry through the real database/API pipeline."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from initial_analysis_fixtures import UNDERSTANDING, request
from test_ai_analysis import CONFIGURATION, USAGE
from test_content_analysis_api import saved
from test_report_generations import generation_request, save_body
from topic_report_fixtures import api_environment, environment, finish

import opinion_workbench_api.database as migrations
from opinion_workbench_api.schemas.topic_reports import ReportCancel
from opinion_workbench_api.services.ai_analysis import AIAnalysisError
from opinion_workbench_api.services.ai_client import (
    AICompletion,
    encode_completion_request,
)
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.content_understanding import parse_understanding
from opinion_workbench_api.services.json_output import decode_answer


@pytest.mark.parametrize(
    "text",
    [
        '{"a":"原文",}',
        '{"a":"原文" "b":2}',
        "{'a':'原文'}",
    ],
)
def test_syntax_repair_preserves_content(text):
    assert decode_answer(text)["a"] == "原文"


@pytest.mark.parametrize(
    "text",
    [
        '{"a":"原文"',
        '{"a":"原文}',
        '{"a":}',
        '{"a":undefined}',
        '{"a":1,"a":2}',
        '{"a":1,"a":2,}',
        '{"a":NaN}',
        '解释：{"a":1}',
        '{"a":1}{"a":2}',
        '{"a":[1,,2]}',
        '{,"a":1}',
        '{"a":truee}',
        '{"a":1 "b" 2}',
        '{"a":1, "b":}',
    ],
)
def test_ambiguous_truncated_or_duplicate_output_is_not_salvaged(text):
    with pytest.raises(ValueError):
        decode_answer(text)


def test_repaired_json_still_requires_schema_and_credentials_validation():
    for value, code in [
        ({**UNDERSTANDING, "media_observations": [{}]}, "invalid_schema"),
        (
            {**UNDERSTANDING, "summary": CONFIGURATION.api_key.get_secret_value()},
            "credential_leakage",
        ),
    ]:
        text = json.dumps(value)[:-1] + ",}"
        with pytest.raises(AIAnalysisError) as error:
            parse_understanding(
                AICompletion(text, USAGE), api_key=CONFIGURATION.api_key
            )
        assert error.value.code == code


def test_json_mode_only_for_verified_provider_and_json_tasks():
    config = replace(
        CONFIGURATION,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.5-omni-plus",
    )

    def encoded(configuration, text):
        return json.loads(
            encode_completion_request(
                configuration,
                messages=[{"role": "system", "content": text}],
                max_tokens=2048,
            )
        )

    assert encoded(config, "输出 JSON")["response_format"] == {"type": "json_object"}
    assert "response_format" not in encoded(config, "Reply OK")
    assert "response_format" not in encoded(replace(config, model="other"), "JSON")
    assert "response_format" not in encoded(
        replace(config, base_url="https://example.com/v1"), "JSON"
    )


@pytest.mark.parametrize("stage", ["initial", "judgment", "leaf"])
@pytest.mark.parametrize("failure", ["invalid", '{"missing":"schema"}'])
def test_output_failure_retries_only_current_step_once(tmp_path, stage, failure):
    app, database, model, media = api_environment(tmp_path, count=1)
    save_body(database, 1)
    model.answers[stage] = [failure]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{admitted.json()['id']}"
        ).json()
        assert result["status"] == "completed", result
        assert model.counts[stage] == 2
        assert all(
            model.counts[other] == 1
            for other in ("initial", "judgment", "leaf")
            if other != stage
        )
        assert not media.calls
        usage = (
            result["analysis"]["usage"]
            if stage == "initial"
            else result["report"]["usage"][
                "judgment" if stage == "judgment" else "composition"
            ]
        )
        assert usage["attempted_requests"] == usage["accounted_requests"] == 2
        assert usage["total_tokens"] == model.usage.total_tokens * 2
        assert usage["complete"]


@pytest.mark.parametrize("stage", ["initial", "judgment", "leaf"])
def test_two_bad_outputs_are_terminal_and_accounted(tmp_path, stage):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database, 1)
    model.answers[stage] = ["invalid", "invalid"]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{admitted.json()['id']}"
        ).json()
        assert result["status"] == "failed", result
        assert model.counts[stage] == 2


def test_transport_failure_on_retry_keeps_first_usage_but_marks_incomplete(tmp_path):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database, 1)
    model.answers["initial"] = ["invalid", AIError("ai_timeout")]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{admitted.json()['id']}"
        ).json()
        usage = result["analysis"]["usage"]
        assert result["status"] == "failed"
        assert model.counts["initial"] == 2
        assert usage["attempted_requests"] == 2 and usage["accounted_requests"] == 1
        assert usage["total_tokens"] == model.usage.total_tokens
        assert not usage["complete"]


@pytest.mark.parametrize("stage", ["initial", "judgment", "leaf"])
@pytest.mark.parametrize(
    "error",
    [AIError("ai_timeout"), AIAnalysisError("credentials", "credential_leakage")],
)
def test_credentials_and_transport_errors_do_not_trigger_output_retry(
    tmp_path, stage, error
):
    app, database, model, _ = api_environment(tmp_path, count=1)
    save_body(database, 1)
    model.answers[stage] = [error]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        client.portal.call(finish, app.state.report_generation_service)
        assert (
            client.get(f"/api/v1/report-generations/{admitted.json()['id']}").json()[
                "status"
            ]
            == "failed"
        )
        assert model.counts[stage] == 1


def test_overview_retry_does_not_repeat_leaf_or_initial_steps(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=9)
    for identity in range(1, 10):
        save_body(database, identity)
    model.answers["overview"] = ["invalid"]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request(list(range(1, 10)))
        )
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{admitted.json()['id']}"
        ).json()
        assert result["status"] == "completed"
        assert model.counts == {"initial": 9, "judgment": 9, "leaf": 2, "overview": 2}
        assert result["report"]["usage"]["composition"]["attempted_requests"] == 4
        assert not media.calls


def test_v29_is_additive_idempotent_and_retains_history(tmp_path):
    with sqlite3.connect(tmp_path / "migration.sqlite3", isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for version in range(1, 29):
            getattr(migrations, f"_migrate_to_version_{version}")(conn)
        conn.execute("""INSERT INTO search_runs (monitoring_rule_id,platform,rule_name,
            max_results_per_term,status,current_term_position,created_at,
            execution_start_term_position,search_protocol_version)
            VALUES (NULL,'wb','保留记录',3,'completed_empty',0,'2026-09-06',0,2)""")
        before = [tuple(row) for row in conn.execute("SELECT * FROM search_runs")]
        migrations._migrate_to_version_29(conn)
        migrations._migrate_to_version_29(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 29
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM search_runs")
        ] == before
        for table in ("content_analysis_attempts", "topic_report_nodes"):
            columns = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            assert {"retry_attempted", "retry_usage_json"} <= columns
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
def test_stop_during_output_retry_keeps_first_usage_without_more_calls(tmp_path, stop):
    async def run():
        db, initial, reports, ai, model, *_ = environment(tmp_path, count=1)
        entered = asyncio.Event()
        original = model.complete
        model.answers["judgment"] = ["invalid"]

        async def blocked(*args, **kwargs):
            if model.counts["judgment"] == 1:
                entered.set()
                await asyncio.Event().wait()
            return await original(*args, **kwargs)

        model.complete = blocked
        try:
            admitted = await initial.create(request(db))
            await finish(initial)
            await asyncio.wait_for(entered.wait(), 5)
            report = reports.repository.list(initial_job_id=admitted.job.id).reports[0]
            if stop == "cancel":
                await reports.cancel(
                    report.id,
                    ReportCancel(
                        request_id=str(uuid4()), expected_revision=report.revision
                    ),
                )
            else:
                await reports.shutdown()
            stopped = reports.repository.read(report.id)
            assert stopped.status == (
                "cancelled" if stop == "cancel" else "interrupted"
            )
            assert stopped.usage.total.attempted_requests == 2
            assert stopped.usage.total.accounted_requests == 1
            assert stopped.usage.total.total_tokens == model.usage.total_tokens
            assert not stopped.usage.total.complete
            assert not model.counts["leaf"]
            reports.initialize()
            assert model.counts["judgment"] == 1
        finally:
            await initial.shutdown()
            await reports.shutdown()
            await ai.shutdown()

    asyncio.run(run())


def test_leaf_retry_supplies_citation_error_and_exact_required_sources(tmp_path):
    app, database, model, media = api_environment(tmp_path, count=1)
    save_body(database, 1)
    original = model.complete

    async def needs_feedback(*args, **kwargs):
        messages = kwargs["messages"]
        user = messages[1]["content"]
        payload = json.loads(user) if isinstance(user, str) else {}
        if "sources" in payload and len(messages) == 2:
            model.answers["leaf"] = [
                {
                    "overview": "来源称有相关情况。",
                    "items": [{"text": "相关情况尚未核实。", "source_ids": [999]}],
                }
            ]
        return await original(*args, **kwargs)

    model.complete = needs_feedback
    # The API fixture binds the transport method during construction.
    with TestClient(app, base_url="http://127.0.0.1") as client:
        app.state.ai_settings_service._client.complete = needs_feedback
        saved(client)
        admitted = client.post(
            "/api/v1/report-generations", json=generation_request([1])
        )
        client.portal.call(finish, app.state.report_generation_service)
        result = client.get(
            f"/api/v1/report-generations/{admitted.json()['id']}"
        ).json()
        assert result["status"] == "completed"
        attempts = [messages for stage, messages in model.calls if stage == "leaf"]
        assert len(attempts) == 2
        assert attempts[0] == attempts[1][:2]
        feedback = json.loads(attempts[1][-1]["content"])
        assert feedback["validation_error"] == "invalid_citations"
        assert feedback["required_source_ids"] == [1]
        assert model.counts["initial"] == model.counts["judgment"] == 1
