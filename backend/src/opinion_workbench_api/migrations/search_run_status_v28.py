"""v28: expose an explicit terminal status for incomplete search coverage."""

import sqlite3

_COLUMNS = (
    "id",
    "monitoring_rule_id",
    "platform",
    "rule_name",
    "max_results_per_term",
    "status",
    "current_term_position",
    "created_at",
    "started_at",
    "finished_at",
    "execution_start_term_position",
    "search_protocol_version",
    "failure_reason",
    "execution_limit",
)


def migrate(connection: sqlite3.Connection) -> None:
    """Rebuild the run table so SQLite enforces the new terminal status."""
    columns = tuple(
        str(row[1]) for row in connection.execute("PRAGMA table_info(search_runs)")
    )
    if columns != _COLUMNS:
        raise sqlite3.DatabaseError("Unexpected search_runs schema for v28 migration")

    connection.execute(
        """
        CREATE TABLE search_runs_v28 (
          id                       INTEGER PRIMARY KEY AUTOINCREMENT,
          monitoring_rule_id       INTEGER
                                   REFERENCES monitoring_rules(id)
                                   ON DELETE SET NULL,
          platform                 TEXT NOT NULL CHECK (platform = 'wb'),
          rule_name                TEXT NOT NULL,
          max_results_per_term     INTEGER NOT NULL
                                   CHECK (max_results_per_term BETWEEN 1 AND 50),
          status                   TEXT NOT NULL CHECK (status IN (
                                     'queued', 'running',
                                     'completed_with_results', 'completed_empty',
                                     'completed_with_incomplete',
                                     'login_required', 'manual_challenge_required',
                                     'platform_blocked_or_rate_limited',
                                     'structure_changed', 'browser_unavailable',
                                     'timed_out', 'cancelled', 'internal_error'
                                   )),
          current_term_position    INTEGER CHECK (current_term_position >= 0),
          created_at               TEXT NOT NULL,
          started_at               TEXT,
          finished_at              TEXT,
          execution_start_term_position
                                   INTEGER NOT NULL DEFAULT 0 CHECK
                                   (execution_start_term_position BETWEEN 0 AND 19),
          search_protocol_version  INTEGER NOT NULL DEFAULT 1 CHECK
                                   (search_protocol_version IN (1, 2)),
          failure_reason           TEXT CHECK (
                                     failure_reason IS NULL OR (
                                       status = 'structure_changed' AND
                                       failure_reason IN (
                                         'page_state_unrecognized',
                                         'search_context_unavailable',
                                         'search_response_incompatible',
                                         'search_results_incompatible',
                                         'search_pagination_incompatible'
                                       )
                                     )
                                   ),
          execution_limit          TEXT CHECK (
                                     execution_limit IS NULL OR (
                                       status = 'timed_out' AND
                                       execution_limit IN ('requests','pages','time')
                                     )
                                   )
        )
        """
    )
    quoted = ", ".join(f'"{column}"' for column in _COLUMNS)
    connection.execute(
        f'INSERT INTO "search_runs_v28" ({quoted}) SELECT {quoted} FROM "search_runs"'
    )

    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'search_runs'"
    ).fetchone()
    connection.execute("DROP TRIGGER IF EXISTS search_run_execution_immutable")
    connection.execute("DROP TRIGGER IF EXISTS search_runs_weibo_only_insert")
    connection.execute("DROP TRIGGER IF EXISTS search_runs_weibo_only_update")
    connection.execute("DROP INDEX IF EXISTS ix_search_runs_status_id")
    connection.execute("DROP INDEX IF EXISTS ix_search_runs_rule_id")
    connection.execute("DROP TABLE search_runs")
    connection.execute('ALTER TABLE "search_runs_v28" RENAME TO "search_runs"')
    connection.execute(
        "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
    )
    connection.execute(
        "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
    )
    connection.execute(
        """
        CREATE TRIGGER search_run_execution_immutable
        BEFORE UPDATE OF execution_start_term_position, search_protocol_version
        ON search_runs
        BEGIN SELECT RAISE(ABORT, 'immutable execution'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER search_runs_weibo_only_insert
        BEFORE INSERT ON search_runs
        WHEN NEW.platform <> 'wb'
        BEGIN SELECT RAISE(ABORT, 'only Weibo is supported'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER search_runs_weibo_only_update
        BEFORE UPDATE OF platform ON search_runs
        WHEN NEW.platform <> 'wb'
        BEGIN SELECT RAISE(ABORT, 'only Weibo is supported'); END
        """
    )
    if sequence is not None:
        updated = connection.execute(
            "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'search_runs'",
            (sequence[0],),
        ).rowcount
        if updated == 0:
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                ("search_runs", sequence[0]),
            )
