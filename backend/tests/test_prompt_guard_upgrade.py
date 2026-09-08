"""Existing installations must accept the new template and retain old history."""

import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_content_analysis_api import saved
from test_report_generations import generation_request
from topic_report_fixtures import api_environment

from longtian_api.repositories import analysis_settings
from longtian_api.repositories.report_generations import ReportGenerationRepository
from longtian_api.repositories.topic_reports import TopicReportRepository
from longtian_api.schemas.report_generations import GenerationCreate
from longtian_api.services.analysis_errors import AnalysisError


def test_upgrade_existing_template_guards_and_preserve_frozen_history(
    tmp_path, monkeypatch
):
    app, database, _, _ = api_environment(tmp_path, count=1)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        saved(client)
    repo = ReportGenerationRepository(database, TopicReportRepository(database))
    old_text = "旧版默认模板：理解来源文字和媒体，保留不确定性。"
    with database.connect() as connection:
        current = analysis_settings.resolve_prompt_choice(
            connection, "initial", {"mode": "default"}
        )
        old = analysis_settings.resolve_prompt_choice(
            connection, "initial", {"mode": "custom", "instructions": old_text}
        )
        # Reproduce v18's pinned default ID surviving a later template seed.
        for prefix in ("analysis_job", "automation_task"):
            for action in ("insert", "update"):
                name = f"{prefix}_prompt_{action}"
                sql = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                    (name,),
                ).fetchone()[0]
                sql = sql.replace(
                    f"WHERE id={current.version_id}", f"WHERE id={old.version_id}"
                )
                connection.execute(f"DROP TRIGGER {name}")
                connection.execute(sql)
        connection.execute("PRAGMA user_version=36")

    original_default = analysis_settings._default_instructions
    with monkeypatch.context() as patch:
        patch.setattr(
            analysis_settings,
            "_default_instructions",
            lambda stage: old_text if stage == "initial" else original_default(stage),
        )
        prior = repo.create_generation(GenerationCreate(**generation_request([1])))
        repo.initialize()  # interrupted terminal history, as after an app restart
    with database.connect() as connection:
        connection.execute("PRAGMA user_version=36")
    payload = GenerationCreate(**generation_request([1]))
    with pytest.raises(AnalysisError, match="analysis_storage_unavailable"):
        repo.create_generation(payload)
    with database.connect() as connection:
        before = [
            tuple(r)
            for r in connection.execute(
                "SELECT * FROM content_analysis_jobs ORDER BY id"
            )
        ]
    database.initialize()
    database.initialize()  # idempotent restart
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 37
        assert [
            tuple(r)
            for r in connection.execute(
                "SELECT * FROM content_analysis_jobs ORDER BY id"
            )
        ] == before
        # Read-only historical projection is valid, but cannot execute as the
        # current default. Hash/collision checks are shared by both paths.
        assert (
            analysis_settings.read_prompt(
                connection, old.version_id, mode="default", historical=True
            ).instructions
            == old_text
        )
        with pytest.raises(AnalysisError):
            analysis_settings.prompt_snapshot(
                connection, "initial", old.version_id, mode="default"
            )
        columns = [
            r[1]
            for r in connection.execute("PRAGMA table_info(content_analysis_jobs)")
            if r[1] != "id"
        ]
        values = dict(
            connection.execute(
                "SELECT * FROM content_analysis_jobs WHERE id=?", (prior.analysis.id,)
            ).fetchone()
        )
        values["request_id"] = str(uuid4())
        with pytest.raises(sqlite3.IntegrityError, match="prompt choice is invalid"):
            connection.execute(
                f"INSERT INTO content_analysis_jobs ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                [values[k] for k in columns],
            )
    history = repo.read_generation(prior.id)
    assert history.analysis.initial_prompt.instructions == old_text
    result = repo.create_generation(payload)
    assert result.analysis.initial_prompt.version_id == current.version_id
    assert repo.replay_generation(payload).id == result.id
    assert len(repo.list_generations().items) == 2
