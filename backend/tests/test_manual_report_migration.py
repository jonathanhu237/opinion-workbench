"""Manual selection does not rewrite saved historical report graphs."""

import pytest
from test_topic_report_migrations import (
    _historical_report_projection,
    _historical_v15,
    _seed_historical_report_graph,
)

from longtian_api import database as migrations


def historical_v19(tmp_path):
    database = _historical_v15(tmp_path)
    _seed_historical_report_graph(database)
    with database.connect() as connection:
        for version in range(16, 20):
            getattr(migrations, f"_migrate_to_version_{version}")(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 19
    return database


def test_manual_report_migration_preserves_graphs_and_sequences(tmp_path):
    database = historical_v19(tmp_path)
    before = _historical_report_projection(database)
    database.initialize()
    assert _historical_report_projection(database) == before
    with database.connect() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone()[0] >= 20


def test_manual_report_migration_failure_rolls_back(tmp_path, monkeypatch):
    from longtian_api.migrations import manual_reports_v20

    database = historical_v19(tmp_path)
    before = _historical_report_projection(database)
    migrate = manual_reports_v20.migrate

    def fail_after_copy(connection):
        migrate(connection)
        raise RuntimeError("synthetic report-copy failure")

    monkeypatch.setattr(manual_reports_v20, "migrate", fail_after_copy)
    with pytest.raises(RuntimeError, match="report-copy failure"):
        database.initialize()
    assert _historical_report_projection(database) == before
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 19
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA legacy_alter_table").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
