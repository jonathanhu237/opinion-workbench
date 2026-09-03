"""v19: add an optional structured cause for search protocol failures."""

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    """Add the nullable failure diagnostic without rewriting search history."""

    columns = {row[1] for row in connection.execute("PRAGMA table_info(search_runs)")}
    if "failure_reason" in columns:
        return
    connection.execute(
        """ALTER TABLE search_runs ADD COLUMN failure_reason TEXT
           CHECK (
             failure_reason IS NULL OR (
               status = 'structure_changed' AND failure_reason IN (
                 'page_state_unrecognized',
                 'search_context_unavailable',
                 'search_response_incompatible',
                 'search_results_incompatible',
                 'search_pagination_incompatible'
               )
             )
           )"""
    )
