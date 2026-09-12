"""v28 search-run status migration preserves history and invariants."""

import sqlite3
from pathlib import Path

import pytest

import opinion_workbench_api.database as migrations


def _database_at_v27(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    for version in range(1, 28):
        getattr(migrations, f"_migrate_to_version_{version}")(connection)
    return connection


def test_v28_adds_explicit_incomplete_status_without_losing_history(tmp_path: Path):
    connection = _database_at_v27(tmp_path / "status.sqlite3")
    try:
        connection.execute(
            """
            INSERT INTO search_runs (
              monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at, execution_start_term_position,
              search_protocol_version
            ) VALUES (NULL, 'wb', '迁移测试', 3, 'completed_empty', 0,
                      '2026-09-05T00:00:00+00:00', 0, 2)
            """
        )
        run_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO search_run_terms (run_id, position, value) VALUES (?, 0, ?)",
            (run_id, "龙田街道"),
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq = 41 WHERE name = 'search_runs'"
        )
        migrations._migrate_to_version_28(connection)

        assert connection.execute("PRAGMA user_version").fetchone()[0] == 28
        connection.execute(
            "UPDATE search_runs SET status = 'completed_with_incomplete' WHERE id = ?",
            (run_id,),
        )
        assert (
            connection.execute(
                "SELECT rule_name FROM search_runs WHERE id = ?", (run_id,)
            ).fetchone()[0]
            == "迁移测试"
        )
        cursor = connection.execute(
            """
            INSERT INTO search_runs (
              monitoring_rule_id, platform, rule_name, max_results_per_term,
              status, current_term_position, created_at
            ) VALUES (NULL, 'wb', '序列测试', 3, 'completed_empty', 0, '2026-09-05')
            """
        )
        assert cursor.lastrowid == 42
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE search_runs SET execution_start_term_position = 1 WHERE id = ?",
                (run_id,),
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
