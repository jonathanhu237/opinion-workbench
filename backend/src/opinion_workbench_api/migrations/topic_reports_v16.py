"""v16: add the automatic-report operation key to historical v15 databases.

The report graph was introduced by v14 before automatic workflows existed.  A
later source revision accidentally changed that v14 migration in place, so
some v15 databases have ``workflow_operation_key`` while databases that were
created through the original migration chain do not.  This migration
normalises the one table whose shape differs.  The database wrapper runs this
module with foreign-key enforcement temporarily disabled while the table is
rebuilt; it restores enforcement and checks the complete graph before commit.
"""

import sqlite3

_RUN_COLUMNS = (
    "id",
    "request_id",
    "workflow_operation_key",
    "trigger",
    "initial_job_id",
    "completion_event_id",
    "parent_report_id",
    "selection_json",
    "prompt_json",
    "configuration_revision",
    "base_url",
    "model",
    "status",
    "revision",
    "cancel_requested",
    "root_section_id",
    "empty_reason",
    "queue_reason",
    "recovery_reason",
    "error_json",
    "created_at",
    "started_at",
    "finished_at",
)

_RUN_TABLE_SQL = """CREATE TABLE {table_name} (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT UNIQUE,
  workflow_operation_key TEXT UNIQUE,
  trigger TEXT NOT NULL CHECK(trigger IN ('automatic','interval','retry')),
  initial_job_id INTEGER REFERENCES content_analysis_jobs(id) ON DELETE
  RESTRICT,
  completion_event_id INTEGER UNIQUE REFERENCES
  analysis_completion_events(id) ON DELETE RESTRICT,
  parent_report_id INTEGER REFERENCES topic_report_runs(id) ON DELETE RESTRICT,
  selection_json TEXT NOT NULL, prompt_json TEXT NOT NULL,
  configuration_revision INTEGER NOT NULL CHECK(configuration_revision
  BETWEEN 1 AND 9007199254740991),
  base_url TEXT NOT NULL, model TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','judging','composing',
  'completed',
    'empty','failed','cancelled','interrupted','configuration_blocked')),
  revision INTEGER NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND
  9007199254740991),
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
  root_section_id INTEGER REFERENCES topic_report_nodes(id) ON DELETE RESTRICT,
  empty_reason TEXT CHECK(empty_reason IN ('no_ready_sources',
  'no_relevant_sources')),
  queue_reason TEXT CHECK(queue_reason='ai_operation_active'),
  recovery_reason TEXT CHECK(recovery_reason='backend_restart'),
  error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
  CHECK((status IN ('queued','judging','composing'))=(finished_at IS NULL)),
  CHECK((status='completed')=(root_section_id IS NOT NULL)),
  CHECK((status='empty')=(empty_reason IS NOT NULL)),
  CHECK((trigger='automatic' AND request_id IS NULL AND parent_report_id IS NULL
    AND ((completion_event_id IS NOT NULL AND initial_job_id IS NOT NULL
          AND workflow_operation_key IS NULL)
      OR (completion_event_id IS NULL
          AND workflow_operation_key IS NOT NULL))) OR
    (trigger='interval' AND request_id IS NOT NULL AND completion_event_id
  IS NULL AND workflow_operation_key IS NULL
    AND initial_job_id IS NULL AND parent_report_id IS NULL) OR
    (trigger='retry' AND request_id IS NOT NULL AND completion_event_id IS NULL
    AND workflow_operation_key IS NULL
    AND parent_report_id IS NOT NULL)),
  CHECK(parent_report_id IS NULL OR parent_report_id<id)
)"""

_RUN_INDEX_SQL = {
    "ix_topic_report_history": """CREATE INDEX ix_topic_report_history ON
      topic_report_runs(initial_job_id, id DESC)""",
    "ix_topic_report_queue": """CREATE INDEX ix_topic_report_queue ON
      topic_report_runs(id) WHERE status='queued'""",
}

_RUN_TRIGGER_SQL = {
    "topic_report_snapshot_immutable": """CREATE TRIGGER
      topic_report_snapshot_immutable BEFORE UPDATE OF
      request_id,workflow_operation_key,trigger,
      initial_job_id,completion_event_id,parent_report_id,selection_json,
      prompt_json,
      configuration_revision,base_url,model,created_at ON topic_report_runs
      BEGIN SELECT RAISE(ABORT,'immutable report snapshot'); END""",
    "topic_report_terminal_immutable": """CREATE TRIGGER
      topic_report_terminal_immutable BEFORE UPDATE ON topic_report_runs
      WHEN OLD.status NOT IN ('queued','judging','composing')
      BEGIN SELECT RAISE(ABORT,'immutable terminal report'); END""",
}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _normalise_sql(sql: str) -> str:
    """Compare SQLite DDL while ignoring formatting and rename quoting."""
    return " ".join(sql.replace('"topic_report_runs"', "topic_report_runs").split())


def _run_table_sql(table_name: str) -> str:
    return _RUN_TABLE_SQL.format(table_name=table_name)


def _run_schema_is_current(connection: sqlite3.Connection) -> bool:
    """Require the complete owned run-table shape, not just its new column."""
    table = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='topic_report_runs'"
    ).fetchone()
    if table is None or table[0] is None:
        return False
    if _normalise_sql(table[0]) != _normalise_sql(_run_table_sql("topic_report_runs")):
        return False

    indexes = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='topic_report_runs' AND sql IS NOT NULL"
        )
    }
    if set(indexes) != set(_RUN_INDEX_SQL):
        return False
    if any(
        _normalise_sql(indexes[name]) != _normalise_sql(sql)
        for name, sql in _RUN_INDEX_SQL.items()
    ):
        return False

    triggers = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='topic_report_runs'"
        )
    }
    if set(triggers) != set(_RUN_TRIGGER_SQL):
        return False
    return all(
        _normalise_sql(triggers[name]) == _normalise_sql(sql)
        for name, sql in _RUN_TRIGGER_SQL.items()
    )


def _create_run_table(
    connection: sqlite3.Connection, table_name: str = "topic_report_runs_v16"
) -> None:
    connection.execute(_run_table_sql(table_name))


def _recreate_run_indexes_and_triggers(connection: sqlite3.Connection) -> None:
    for statement in (*_RUN_INDEX_SQL.values(), *_RUN_TRIGGER_SQL.values()):
        connection.execute(statement)


def migrate(connection: sqlite3.Connection) -> None:
    """Normalise ``topic_report_runs`` while retaining every historical value."""
    if not _table_exists(connection, "topic_report_runs"):
        raise sqlite3.DatabaseError("topic_report_runs is missing before v16 migration")

    # A v15 database produced by the amended v14 source already has the exact
    # final table shape.  Do not rewrite its report rows or AUTOINCREMENT state.
    if _run_schema_is_current(connection):
        return

    previous_sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='topic_report_runs'"
    ).fetchone()
    previous_legacy_alter_table = connection.execute(
        "PRAGMA legacy_alter_table"
    ).fetchone()[0]
    connection.execute("PRAGMA legacy_alter_table = ON")
    try:
        # The indexes/triggers belong to the old table and would otherwise
        # collide when the replacement is renamed into place.
        connection.execute("DROP INDEX IF EXISTS ix_topic_report_queue")
        connection.execute("DROP INDEX IF EXISTS ix_topic_report_history")
        connection.execute("DROP TRIGGER IF EXISTS topic_report_snapshot_immutable")
        connection.execute("DROP TRIGGER IF EXISTS topic_report_terminal_immutable")

        _create_run_table(connection)
        source_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(topic_report_runs)")
        }
        old_columns = set(_RUN_COLUMNS) - {"workflow_operation_key"}
        if source_columns not in (old_columns, set(_RUN_COLUMNS)):
            raise sqlite3.DatabaseError("Unexpected topic_report_runs v15 columns")
        source_sql = ",".join(
            (
                '"workflow_operation_key"'
                if column == "workflow_operation_key" and column in source_columns
                else "NULL"
                if column == "workflow_operation_key"
                else f'"{column}"'
            )
            for column in _RUN_COLUMNS
        )
        new_column_sql = ",".join(_RUN_COLUMNS)
        connection.execute(
            f"""INSERT INTO topic_report_runs_v16 ({new_column_sql})
                SELECT {source_sql}
                FROM topic_report_runs"""
        )

        # With legacy_alter_table enabled, all graph tables keep pointing to
        # the final name during the swap.  The new table's self-reference also
        # intentionally names that final table (see _create_run_table).
        connection.execute(
            "ALTER TABLE topic_report_runs RENAME TO topic_report_runs_v15"
        )
        connection.execute("DROP TABLE topic_report_runs_v15")
        connection.execute(
            "ALTER TABLE topic_report_runs_v16 RENAME TO topic_report_runs"
        )
        _recreate_run_indexes_and_triggers(connection)

        if previous_sequence is None:
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name='topic_report_runs'"
            )
        else:
            updated = connection.execute(
                "UPDATE sqlite_sequence SET seq=? WHERE name='topic_report_runs'",
                (previous_sequence[0],),
            ).rowcount
            if updated == 0:
                connection.execute(
                    "INSERT INTO sqlite_sequence(name,seq) "
                    "VALUES('topic_report_runs',?)",
                    (previous_sequence[0],),
                )
    finally:
        connection.execute(
            f"PRAGMA legacy_alter_table = {int(previous_legacy_alter_table)}"
        )
