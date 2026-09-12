"""v27: persist keywords that ended with incomplete omission recovery."""

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    """Add an append-only diagnostic table without rewriting search history."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS search_run_term_diagnostics (
          run_id INTEGER NOT NULL,
          term_position INTEGER NOT NULL,
          reason TEXT NOT NULL CHECK (reason IN ('view_all_unresolved')),
          result_count INTEGER NOT NULL CHECK (result_count BETWEEN 0 AND 50),
          recorded_at TEXT NOT NULL,
          PRIMARY KEY (run_id, term_position),
          FOREIGN KEY (run_id, term_position)
            REFERENCES search_run_terms(run_id, position) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_search_run_term_diagnostics_run
          ON search_run_term_diagnostics(run_id, term_position)
        """
    )
