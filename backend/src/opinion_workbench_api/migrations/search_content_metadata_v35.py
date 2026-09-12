"""v35: retain bounded rendered topic and interaction metadata."""

from __future__ import annotations

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info("search_contents")')
    }
    if "hashtags_json" not in columns:
        connection.execute(
            "ALTER TABLE search_contents ADD COLUMN hashtags_json TEXT NOT NULL "
            "DEFAULT '[]'"
        )
    if "interaction_stats_json" not in columns:
        connection.execute(
            "ALTER TABLE search_contents ADD COLUMN interaction_stats_json TEXT "
            "NOT NULL DEFAULT '{}'"
        )
