"""v32: mark evidence written under the text-only analysis contract.

Rows written before the scope switch remain readable, but are never selected as
the frozen input for a new analysis/report.  The marker is deliberately
nullable so the migration does not rewrite or reinterpret historical JSON.
"""

from __future__ import annotations

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    for table in ("content_materials", "content_analysis_attempts"):
        columns = {
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        if "analysis_input_version" not in columns:
            connection.execute(
                f'ALTER TABLE "{table}" ADD COLUMN analysis_input_version TEXT'
            )
