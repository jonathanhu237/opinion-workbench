"""v36: persist the ordering semantics used by each search run."""

from __future__ import annotations

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in connection.execute('PRAGMA table_info("search_runs")')
    }
    if "ordering" in columns:
        return
    connection.execute(
        "ALTER TABLE search_runs ADD COLUMN ordering TEXT NOT NULL DEFAULT 'platform' "
        "CHECK (ordering IN ('latest','platform'))"
    )
