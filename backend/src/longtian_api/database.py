"""SQLite path and migration ownership for local product data."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

CURRENT_DATABASE_VERSION = 25
DEFAULT_RULE_NAME = "龙田街道及四个社区"
DEFAULT_RULE_TERMS = (
    "龙田街道",
    "龙田社区",
    "老坑社区",
    "竹坑社区",
    "南布社区",
)


class DatabaseVersionError(RuntimeError):
    """Raised when the local database is newer than this application."""


def default_database_path() -> Path:
    """Return the repository-local product database path."""
    return Path(__file__).resolve().parents[3] / "runtime" / "longtian.sqlite3"


class Database:
    """Open configured SQLite connections and run application migrations."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_database_path()

    def connect(self) -> sqlite3.Connection:
        """Open one operation-owned connection with the required pragmas."""
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        """Create the database directory and apply pending migrations."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            version = _read_user_version(connection)
            if version > CURRENT_DATABASE_VERSION:
                raise DatabaseVersionError(
                    "The database schema is newer than this application."
                )
            if version < 1:
                _migrate_to_version_1(connection)
                version = 1
            if version < 2:
                _migrate_to_version_2(connection)
                version = 2
            if version < 3:
                _migrate_to_version_3(connection)
                version = 3
            if version < 4:
                _migrate_to_version_4(connection)
                version = 4
            if version < 5:
                _migrate_to_version_5(connection)
                version = 5
            if version < 6:
                _migrate_to_version_6(connection)
                version = 6
            if version < 7:
                _migrate_to_version_7(connection)
                version = 7
            if version < 8:
                _migrate_to_version_8(connection)
                version = 8
            if version < 9:
                _migrate_to_version_9(connection)
                version = 9
            if version < 10:
                _migrate_to_version_10(connection)
                version = 10
            if version < 11:
                _migrate_to_version_11(connection)
                version = 11
            if version < 12:
                _migrate_to_version_12(connection)
                version = 12
            if version < 13:
                _migrate_to_version_13(connection)
                version = 13
            if version < 14:
                _migrate_to_version_14(connection)
                version = 14
            if version < 15:
                _migrate_to_version_15(connection)
                version = 15
            if version < 16:
                _migrate_to_version_16(connection)
                version = 16
            if version < 17:
                _migrate_to_version_17(connection)
                version = 17
            if version < 18:
                _migrate_to_version_18(connection)
                version = 18
            if version < 19:
                _migrate_to_version_19(connection)
                version = 19
            if version < 20:
                _migrate_to_version_20(connection)
                version = 20
            if version < 21:
                _migrate_to_version_21(connection)
                version = 21
            if version < 22:
                _migrate_to_version_22(connection)
            if version < 23:
                _migrate_to_version_23(connection)
            if version < 24:
                _migrate_to_version_24(connection)
                version = 24
            if version < 25:
                _migrate_to_version_25(connection)
        finally:
            connection.close()


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise sqlite3.DatabaseError("SQLite did not return user_version")
    return int(row[0])


def _migrate_to_version_14(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.topic_reports import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 14:
            connection.execute("COMMIT")
            return
        if version != 13:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 14")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_15(connection: sqlite3.Connection) -> None:
    """Append fixed-purpose automatic workflow persistence.

    The migration is deliberately additive.  Existing collection, analysis and
    report history is retained as-is; an installation with no automation rows
    starts with an empty task list and no enabled work.
    """
    from longtian_api.migrations.automation_workflows import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 15:
            connection.execute("COMMIT")
            return
        if version != 14:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 15")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_16(connection: sqlite3.Connection) -> None:
    """Repair the report table shape left behind by historical v15 installs."""
    from longtian_api.migrations.topic_reports_v16 import migrate

    version = _read_user_version(connection)
    if version >= 16:
        return
    if version != 15:
        raise DatabaseVersionError("Unsupported database migration source version.")

    # Replacing a table with FK-referencing graph tables requires SQLite's
    # legacy rename behavior.  The migration copies and verifies every row in
    # one transaction, then restores the connection's normal FK enforcement.
    previous_foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    previous_legacy_alter_table = connection.execute(
        "PRAGMA legacy_alter_table"
    ).fetchone()[0]
    try:
        if previous_foreign_keys:
            connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        migrate(connection)
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after v16 migration")
        connection.execute("PRAGMA user_version = 16")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute(f"PRAGMA foreign_keys = {int(previous_foreign_keys)}")
        # topic_reports_v16 restores this itself, but keep the wrapper's
        # connection setting stable if migration fails before entering it.
        connection.execute(
            f"PRAGMA legacy_alter_table = {int(previous_legacy_alter_table)}"
        )


def _migrate_to_version_17(connection: sqlite3.Connection) -> None:
    """Add soft deletion state for automatic workflow tasks."""
    from longtian_api.migrations.automation_workflows_v17 import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 17:
            connection.execute("COMMIT")
            return
        if version != 16:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 17")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_18(connection: sqlite3.Connection) -> None:
    """Freeze default/custom prompt choices on automation task rows."""
    from longtian_api.migrations.automation_workflows_v18 import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 18:
            connection.execute("COMMIT")
            return
        if version != 17:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 18")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_19(connection: sqlite3.Connection) -> None:
    """Add structured search failure diagnostics without rewriting runs."""
    from longtian_api.migrations.search_runs_v19 import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 19:
            connection.execute("COMMIT")
            return
        if version != 18:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 19")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_24(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.media_cache_v24 import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version < 24:
            if version != 23:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            migrate(connection)
            connection.execute("PRAGMA user_version = 24")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_25(connection: sqlite3.Connection) -> None:
    """Persist the user-facing name of a manual report generation."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version < 25:
            if version != 24:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(report_generations)")
            }
            if "name" not in columns:
                connection.execute(
                    "ALTER TABLE report_generations ADD COLUMN name TEXT"
                )
            connection.execute(
                "UPDATE report_generations SET name=? "
                "WHERE name IS NULL OR trim(name)=''",
                ("",),
            )
            connection.execute(
                """CREATE TRIGGER IF NOT EXISTS report_generation_name_immutable
                BEFORE UPDATE OF name ON report_generations
                WHEN NEW.name IS NOT OLD.name
                BEGIN SELECT RAISE(ABORT, 'immutable report generation name'); END"""
            )
            connection.execute("PRAGMA user_version = 25")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_23(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version < 23:
            if version != 22:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            connection.execute("""
                ALTER TABLE report_generations ADD COLUMN pause_reason TEXT
                CHECK(pause_reason IS NULL OR pause_reason IN ('login_required',
                'manual_challenge_required','platform_blocked_or_rate_limited'))""")
            connection.execute("""
                ALTER TABLE report_generations ADD COLUMN pause_attempt_id
                INTEGER REFERENCES content_analysis_attempts(id)""")
            connection.execute("""
                ALTER TABLE report_generations ADD COLUMN control_revision
                INTEGER NOT NULL DEFAULT 0 CHECK(control_revision>=0)""")
            connection.execute("PRAGMA user_version = 23")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_22(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version < 22:
            if version != 21:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            connection.execute("""
                ALTER TABLE search_runs ADD COLUMN execution_limit TEXT
                CHECK (execution_limit IS NULL OR (status = 'timed_out' AND
                  execution_limit IN ('requests','pages','time')))""")
            connection.execute("PRAGMA user_version = 22")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_21(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.report_generations_v21 import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version < 21:
            if version != 20:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            migrate(connection)
            connection.execute("PRAGMA user_version = 21")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_20(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.manual_reports_v20 import migrate

    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_alter = connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA legacy_alter_table = ON")
        connection.execute("BEGIN IMMEDIATE")
        version = _read_user_version(connection)
        if version < 20:
            if version != 19:
                raise DatabaseVersionError(
                    "Unsupported database migration source version."
                )
            migrate(connection)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.DatabaseError(
                    "Foreign key check failed after v20 migration"
                )
            connection.execute("PRAGMA user_version = 20")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute(f"PRAGMA foreign_keys = {int(foreign_keys)}")
        connection.execute(f"PRAGMA legacy_alter_table = {int(legacy_alter)}")


def _migrate_to_version_13(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.collection_schedules import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 13:
            connection.execute("COMMIT")
            return
        if version != 12:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 13")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_12(connection: sqlite3.Connection) -> None:
    from longtian_api.migrations.initial_analysis import migrate

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 12:
            connection.execute("COMMIT")
            return
        if version != 11:
            raise DatabaseVersionError("Unsupported database migration source version.")
        migrate(connection)
        connection.execute("PRAGMA user_version = 12")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_11(connection: sqlite3.Connection) -> None:
    """Append manual-summary versions without rewriting collection history."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 11:
            connection.execute("COMMIT")
            return
        if version != 10:
            raise DatabaseVersionError("Unsupported database migration source version.")
        connection.execute("""
            CREATE TABLE ai_summary_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL UNIQUE,
              source_run_id INTEGER NOT NULL REFERENCES search_runs(id)
                ON DELETE RESTRICT,
              source_run_status TEXT NOT NULL,
              platform TEXT NOT NULL CHECK (platform IN
                ('wb','dy','ks','xhs','toutiao')),
              rule_name TEXT NOT NULL, terms_json TEXT NOT NULL,
              configuration_revision INTEGER NOT NULL
                CHECK (configuration_revision > 0),
              base_url TEXT NOT NULL, model TEXT NOT NULL,
              force_refresh INTEGER NOT NULL CHECK (force_refresh IN (0,1)),
              analysis_prompt_version TEXT NOT NULL,
              summary_prompt_version TEXT NOT NULL,
              model_input_version TEXT NOT NULL,
              status TEXT NOT NULL CHECK (status IN
                ('queued','running','completed','failed','cancelled','interrupted')),
              phase TEXT NOT NULL CHECK (phase IN ('analysing','summarising')),
              composition_attempted INTEGER NOT NULL DEFAULT 0
                CHECK (composition_attempted IN (0,1)),
              composition_usage_json TEXT, composition_input_hash TEXT,
              document_json TEXT, error_json TEXT,
              created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
              CHECK ((status IN ('queued','running') AND finished_at IS NULL)
                OR (status NOT IN ('queued','running') AND finished_at IS NOT NULL)),
              CHECK ((status = 'completed' AND document_json IS NOT NULL)
                OR (status != 'completed' AND document_json IS NULL)),
              CHECK (composition_usage_json IS NULL OR composition_attempted = 1)
            )
        """)
        connection.execute("""
            CREATE UNIQUE INDEX ix_ai_summary_runs_active ON ai_summary_runs((1))
            WHERE status IN ('queued','running')
        """)
        connection.execute("""
            CREATE INDEX ix_ai_summary_runs_source
              ON ai_summary_runs(source_run_id,id DESC)
        """)
        connection.execute("""
            CREATE TABLE ai_summary_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              summary_run_id INTEGER NOT NULL REFERENCES ai_summary_runs(id)
                ON DELETE RESTRICT,
              content_id INTEGER NOT NULL REFERENCES search_contents(id)
                ON DELETE RESTRICT,
              position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 99),
              source_json TEXT NOT NULL, observation_hash TEXT NOT NULL,
              cache_key TEXT NOT NULL, input_json TEXT, input_hash TEXT,
              status TEXT NOT NULL CHECK (status IN ('pending','analysing','completed',
                'input_incomplete','failed','cancelled','interrupted')),
              decision TEXT CHECK (decision IN ('relevant','irrelevant','uncertain')),
              reason TEXT, evidence_summary TEXT,
              reused_from_item_id INTEGER REFERENCES ai_summary_items(id)
                ON DELETE RESTRICT,
              attempted INTEGER NOT NULL DEFAULT 0 CHECK (attempted IN (0,1)),
              usage_json TEXT, error_json TEXT,
              started_at TEXT, finished_at TEXT,
              UNIQUE (summary_run_id,content_id), UNIQUE (summary_run_id,position),
              CHECK ((status IN ('pending','analysing') AND finished_at IS NULL)
                OR (status NOT IN ('pending','analysing') AND finished_at IS NOT NULL)),
              CHECK ((status = 'completed' AND ((reused_from_item_id IS NOT NULL
                 AND attempted = 0 AND usage_json IS NULL AND decision IS NULL
                 AND reason IS NULL AND evidence_summary IS NULL)
                OR (reused_from_item_id IS NULL AND attempted = 1
                 AND decision IS NOT NULL
                 AND reason IS NOT NULL AND evidence_summary IS NOT NULL
                 AND input_json IS NOT NULL AND input_hash IS NOT NULL)))
                OR (status != 'completed' AND reused_from_item_id IS NULL
                 AND decision IS NULL AND reason IS NULL AND evidence_summary IS NULL)),
              CHECK (usage_json IS NULL OR attempted = 1),
              CHECK (reused_from_item_id IS NULL OR reused_from_item_id < id)
            )
        """)
        connection.execute("""
            CREATE INDEX ix_ai_summary_items_cache
              ON ai_summary_items(cache_key,id DESC)
            WHERE status = 'completed' AND reused_from_item_id IS NULL
        """)
        connection.execute("PRAGMA user_version = 11")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_10(connection: sqlite3.Connection) -> None:
    """Add immutable term proofs and guarded, audited manual recovery."""
    from longtian_api.search_checkpoints import backfill_legacy_completions

    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 10:
            connection.execute("COMMIT")
            return
        if version != 9:
            raise DatabaseVersionError("Unsupported database migration source version.")
        connection.execute("""
            ALTER TABLE search_runs ADD COLUMN execution_start_term_position
            INTEGER NOT NULL DEFAULT 0 CHECK (execution_start_term_position BETWEEN
            0 AND 19)
        """)
        connection.execute("""
            ALTER TABLE search_runs ADD COLUMN search_protocol_version
            INTEGER NOT NULL DEFAULT 1 CHECK (search_protocol_version IN (1, 2))
        """)
        connection.execute("""
            ALTER TABLE search_batches ADD COLUMN control_revision
            INTEGER NOT NULL DEFAULT 0 CHECK (control_revision >= 0)
        """)
        connection.execute("""
            CREATE TABLE search_run_term_completions (
              run_id INTEGER NOT NULL,
              term_position INTEGER NOT NULL,
              proof TEXT NOT NULL CHECK (proof IN (
                'worker_term_completed', 'legacy_next_term_started',
                'legacy_run_succeeded'
              )),
              result_count INTEGER NOT NULL CHECK (result_count BETWEEN 0 AND 50),
              completed_at TEXT,
              recorded_at TEXT NOT NULL,
              PRIMARY KEY (run_id, term_position),
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms(run_id, position) ON DELETE CASCADE,
              CHECK ((proof = 'worker_term_completed' AND completed_at IS NOT NULL)
                OR (proof != 'worker_term_completed' AND completed_at IS NULL))
            )
        """)
        connection.execute("""
            CREATE TABLE search_batch_items_v10 (
              batch_id INTEGER NOT NULL REFERENCES search_batches(id) ON DELETE CASCADE,
              position INTEGER NOT NULL CHECK (position >= 0),
              platform TEXT NOT NULL CHECK (platform IN
              ('toutiao','wb','ks','dy','xhs')),
              status TEXT NOT NULL CHECK (status IN ('queued','running',
                'paused_for_manual_action','completed','failed','cancelled','skipped')),
              created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
              pause_reason TEXT CHECK (pause_reason IN
              ('attempt_failed','process_interrupted')),
              completion_basis TEXT CHECK (completion_basis IN
              ('attempt_success','confirmed_terms')),
              PRIMARY KEY (batch_id, position), UNIQUE (batch_id, platform)
            )
        """)
        connection.execute("""
            INSERT INTO search_batch_items_v10
            SELECT *, CASE WHEN status = 'paused_for_manual_action' THEN
            'attempt_failed' END,
                      CASE WHEN status = 'completed' THEN 'attempt_success' END
            FROM search_batch_items
        """)
        connection.execute("""
            CREATE TABLE search_batch_attempts_v10 (
              batch_id INTEGER NOT NULL, item_position INTEGER NOT NULL,
              attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
              search_run_id INTEGER NOT NULL UNIQUE REFERENCES search_runs(id) ON
              DELETE RESTRICT,
              created_at TEXT NOT NULL,
              PRIMARY KEY (batch_id, item_position, attempt_number),
              FOREIGN KEY (batch_id, item_position)
                REFERENCES search_batch_items_v10(batch_id, position) ON DELETE CASCADE
            )
        """)
        connection.execute(
            "INSERT INTO search_batch_attempts_v10 SELECT * FROM search_batch_attempts"
        )
        connection.execute("DROP TABLE search_batch_attempts")
        connection.execute("DROP TABLE search_batch_items")
        connection.execute(
            "ALTER TABLE search_batch_items_v10 RENAME TO search_batch_items"
        )
        connection.execute(
            "ALTER TABLE search_batch_attempts_v10 RENAME TO search_batch_attempts"
        )
        connection.execute("""
            CREATE INDEX ix_search_batch_attempts_item
            ON search_batch_attempts(batch_id, item_position, attempt_number DESC)
        """)
        connection.execute("""
            CREATE TABLE search_batch_recoveries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              batch_id INTEGER NOT NULL, item_position INTEGER NOT NULL,
              previous_control_revision INTEGER NOT NULL CHECK
              (previous_control_revision >= 0),
              previous_batch_status TEXT NOT NULL CHECK (previous_batch_status =
              'completed_with_failures'),
              previous_item_status TEXT NOT NULL CHECK (previous_item_status =
              'failed'),
              previous_batch_finished_at TEXT NOT NULL,
              previous_item_finished_at TEXT NOT NULL,
              recovered_at TEXT NOT NULL,
              FOREIGN KEY (batch_id, item_position)
                REFERENCES search_batch_items(batch_id, position) ON DELETE RESTRICT
            )
        """)
        backfill_legacy_completions(connection, datetime.now(UTC).isoformat())
        connection.execute("""
            CREATE TRIGGER search_run_execution_immutable
            BEFORE UPDATE OF execution_start_term_position, search_protocol_version
            ON search_runs
            BEGIN SELECT RAISE(ABORT, 'immutable execution'); END
        """)
        connection.execute("""
            CREATE TRIGGER search_completion_immutable BEFORE UPDATE ON
            search_run_term_completions
            BEGIN SELECT RAISE(ABORT, 'immutable completion'); END
        """)
        connection.execute("""
            CREATE TRIGGER search_recovery_immutable BEFORE UPDATE ON
            search_batch_recoveries
            BEGIN SELECT RAISE(ABORT, 'immutable recovery'); END
        """)
        connection.execute("""
            CREATE TRIGGER search_recovery_no_delete BEFORE DELETE ON
            search_batch_recoveries
            BEGIN SELECT RAISE(ABORT, 'immutable recovery'); END
        """)
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after migration")
        connection.execute("PRAGMA user_version = 10")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_9(connection: sqlite3.Connection) -> None:
    """Preserve existing complete phrases as objects; issues start empty."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 9:
            connection.execute("COMMIT")
            return
        if version != 8:
            raise DatabaseVersionError("Unsupported database migration source version.")
        # Match object storage: SQLite length() stops at NUL, so the shared
        # service validator owns Unicode-codepoint length limits for both groups.
        connection.execute(
            """
            CREATE TABLE monitoring_rule_issue_terms (
              id               INTEGER PRIMARY KEY AUTOINCREMENT,
              rule_id          INTEGER NOT NULL
                               REFERENCES monitoring_rules(id) ON DELETE CASCADE,
              value            TEXT NOT NULL,
              normalized_value TEXT NOT NULL,
              position         INTEGER NOT NULL CHECK (position BETWEEN 0 AND 99),
              UNIQUE (rule_id, normalized_value),
              UNIQUE (rule_id, position)
            )
            """
        )
        connection.execute("PRAGMA user_version = 9")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_8(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 8:
            connection.execute("COMMIT")
            return
        if version != 7:
            raise DatabaseVersionError("Unsupported database migration source version.")
        connection.execute(
            """
            CREATE TABLE ai_settings (
              id         INTEGER PRIMARY KEY CHECK (id = 1),
              base_url   TEXT NOT NULL CHECK (length(base_url) BETWEEN 1 AND 2048),
              model      TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
              secret_ref TEXT NOT NULL CHECK (length(secret_ref) = 36),
              revision   INTEGER NOT NULL CHECK (revision > 0),
              updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute("PRAGMA user_version = 8")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_1(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 1:
            connection.execute("COMMIT")
            return
        if version != 0:
            raise DatabaseVersionError("Unsupported database migration source version.")

        connection.execute(
            """
            CREATE TABLE monitoring_rules (
              id              INTEGER PRIMARY KEY AUTOINCREMENT,
              name            TEXT NOT NULL,
              normalized_name TEXT NOT NULL UNIQUE,
              enabled         INTEGER NOT NULL DEFAULT 1
                              CHECK (enabled IN (0, 1)),
              created_at      TEXT NOT NULL,
              updated_at      TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE monitoring_rule_terms (
              id               INTEGER PRIMARY KEY AUTOINCREMENT,
              rule_id          INTEGER NOT NULL
                               REFERENCES monitoring_rules(id) ON DELETE CASCADE,
              value            TEXT NOT NULL,
              normalized_value TEXT NOT NULL,
              position         INTEGER NOT NULL CHECK (position >= 0),
              UNIQUE (rule_id, normalized_value),
              UNIQUE (rule_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX ix_monitoring_rules_enabled_id
            ON monitoring_rules(enabled, id)
            """
        )

        timestamp = datetime.now(UTC).isoformat()
        cursor = connection.execute(
            """
            INSERT INTO monitoring_rules (
              name, normalized_name, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (DEFAULT_RULE_NAME, DEFAULT_RULE_NAME, 1, timestamp, timestamp),
        )
        rule_id = cursor.lastrowid
        if rule_id is None:
            raise sqlite3.DatabaseError("SQLite did not return an inserted rule ID")
        connection.executemany(
            """
            INSERT INTO monitoring_rule_terms (
              rule_id, value, normalized_value, position
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (rule_id, term, term, position)
                for position, term in enumerate(DEFAULT_RULE_TERMS)
            ),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_2(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 2:
            connection.execute("COMMIT")
            return
        if version != 1:
            raise DatabaseVersionError("Unsupported database migration source version.")

        connection.execute(
            """
            CREATE TABLE search_runs (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              platform                 TEXT NOT NULL CHECK (platform = 'toutiao'),
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'completed_with_results', 'completed_empty',
                                         'login_required', 'manual_challenge_required',
                                         'platform_blocked_or_rate_limited',
                                         'structure_changed', 'browser_unavailable',
                                         'timed_out', 'cancelled', 'internal_error'
                                       )),
              current_term_position    INTEGER CHECK (current_term_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_terms (
              run_id     INTEGER NOT NULL
                         REFERENCES search_runs(id) ON DELETE CASCADE,
              position   INTEGER NOT NULL CHECK (position >= 0),
              value      TEXT NOT NULL,
              PRIMARY KEY (run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_contents (
              id                    INTEGER PRIMARY KEY AUTOINCREMENT,
              platform              TEXT NOT NULL CHECK (platform = 'toutiao'),
              platform_content_id   TEXT NOT NULL,
              content_type          TEXT NOT NULL,
              title                 TEXT NOT NULL,
              snippet               TEXT NOT NULL,
              creator_hash          TEXT NOT NULL,
              publisher_name        TEXT NOT NULL,
              published_at_text     TEXT NOT NULL,
              content_url           TEXT NOT NULL,
              first_seen_at         TEXT NOT NULL,
              last_seen_at          TEXT NOT NULL,
              UNIQUE (platform, platform_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_contents (
              run_id              INTEGER NOT NULL
                                  REFERENCES search_runs(id) ON DELETE CASCADE,
              search_content_id   INTEGER NOT NULL
                                  REFERENCES search_contents(id) ON DELETE CASCADE,
              discovery_kind      TEXT NOT NULL
                                  CHECK (discovery_kind IN ('new', 'repeated')),
              first_observed_at   TEXT NOT NULL,
              last_observed_at    TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_content_terms (
              run_id              INTEGER NOT NULL,
              search_content_id   INTEGER NOT NULL,
              term_position       INTEGER NOT NULL,
              observed_at         TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id, term_position),
              FOREIGN KEY (run_id, search_content_id)
                REFERENCES search_run_contents(run_id, search_content_id)
                ON DELETE CASCADE,
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms(run_id, position)
                ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
        )
        connection.execute(
            """
            CREATE INDEX ix_search_run_contents_kind_observed
            ON search_run_contents(run_id, discovery_kind, first_observed_at DESC)
            """
        )
        connection.execute("PRAGMA user_version = 2")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_3(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 3:
            connection.execute("COMMIT")
            return
        if version != 2:
            raise DatabaseVersionError("Unsupported database migration source version.")

        connection.execute(
            """
            CREATE TABLE search_runs_v3 (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              platform                 TEXT NOT NULL
                                       CHECK (platform IN ('toutiao', 'wb')),
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'completed_with_results', 'completed_empty',
                                         'login_required', 'manual_challenge_required',
                                         'platform_blocked_or_rate_limited',
                                         'structure_changed', 'browser_unavailable',
                                         'timed_out', 'cancelled', 'internal_error'
                                       )),
              current_term_position    INTEGER CHECK (current_term_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_terms_v3 (
              run_id     INTEGER NOT NULL
                         REFERENCES search_runs_v3(id) ON DELETE CASCADE,
              position   INTEGER NOT NULL CHECK (position >= 0),
              value      TEXT NOT NULL,
              PRIMARY KEY (run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_contents_v3 (
              id                    INTEGER PRIMARY KEY AUTOINCREMENT,
              platform              TEXT NOT NULL
                                    CHECK (platform IN ('toutiao', 'wb')),
              platform_content_id   TEXT NOT NULL,
              content_type          TEXT NOT NULL,
              title                 TEXT NOT NULL,
              snippet               TEXT NOT NULL,
              creator_hash          TEXT NOT NULL,
              publisher_name        TEXT NOT NULL,
              published_at_text     TEXT NOT NULL,
              content_url           TEXT NOT NULL,
              first_seen_at         TEXT NOT NULL,
              last_seen_at          TEXT NOT NULL,
              UNIQUE (platform, platform_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_contents_v3 (
              run_id              INTEGER NOT NULL
                                  REFERENCES search_runs_v3(id) ON DELETE CASCADE,
              search_content_id   INTEGER NOT NULL
                                  REFERENCES search_contents_v3(id) ON DELETE CASCADE,
              discovery_kind      TEXT NOT NULL
                                  CHECK (discovery_kind IN ('new', 'repeated')),
              first_observed_at   TEXT NOT NULL,
              last_observed_at    TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_content_terms_v3 (
              run_id              INTEGER NOT NULL,
              search_content_id   INTEGER NOT NULL,
              term_position       INTEGER NOT NULL,
              observed_at         TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id, term_position),
              FOREIGN KEY (run_id, search_content_id)
                REFERENCES search_run_contents_v3(run_id, search_content_id)
                ON DELETE CASCADE,
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms_v3(run_id, position)
                ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            INSERT INTO search_runs_v3
            SELECT * FROM search_runs ORDER BY id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_terms_v3
            SELECT * FROM search_run_terms ORDER BY run_id, position
            """
        )
        connection.execute(
            """
            INSERT INTO search_contents_v3
            SELECT * FROM search_contents ORDER BY id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_contents_v3
            SELECT * FROM search_run_contents ORDER BY run_id, search_content_id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms_v3
            SELECT * FROM search_run_content_terms
            ORDER BY run_id, search_content_id, term_position
            """
        )

        for table in (
            "search_run_content_terms",
            "search_run_contents",
            "search_run_terms",
            "search_contents",
            "search_runs",
        ):
            connection.execute(f"DROP TABLE {table}")

        for old_name, stable_name in (
            ("search_runs_v3", "search_runs"),
            ("search_run_terms_v3", "search_run_terms"),
            ("search_contents_v3", "search_contents"),
            ("search_run_contents_v3", "search_run_contents"),
            ("search_run_content_terms_v3", "search_run_content_terms"),
        ):
            connection.execute(f"ALTER TABLE {old_name} RENAME TO {stable_name}")

        connection.execute(
            "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
        )
        connection.execute(
            """
            CREATE INDEX ix_search_run_contents_kind_observed
            ON search_run_contents(run_id, discovery_kind, first_observed_at DESC)
            """
        )
        connection.execute("PRAGMA user_version = 3")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_4(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 4:
            connection.execute("COMMIT")
            return
        if version != 3:
            raise DatabaseVersionError("Unsupported database migration source version.")

        sequence_rows = connection.execute(
            """
            SELECT name, seq FROM sqlite_sequence
            WHERE name IN ('search_runs', 'search_contents')
            """
        ).fetchall()
        sequences = {str(row["name"]): int(row["seq"]) for row in sequence_rows}

        connection.execute(
            """
            CREATE TABLE search_runs_v4 (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              platform                 TEXT NOT NULL
                                       CHECK (platform IN ('toutiao', 'wb', 'ks')),
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'completed_with_results', 'completed_empty',
                                         'login_required', 'manual_challenge_required',
                                         'platform_blocked_or_rate_limited',
                                         'structure_changed', 'browser_unavailable',
                                         'timed_out', 'cancelled', 'internal_error'
                                       )),
              current_term_position    INTEGER CHECK (current_term_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_terms_v4 (
              run_id     INTEGER NOT NULL
                         REFERENCES search_runs_v4(id) ON DELETE CASCADE,
              position   INTEGER NOT NULL CHECK (position >= 0),
              value      TEXT NOT NULL,
              PRIMARY KEY (run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_contents_v4 (
              id                    INTEGER PRIMARY KEY AUTOINCREMENT,
              platform              TEXT NOT NULL
                                    CHECK (platform IN ('toutiao', 'wb', 'ks')),
              platform_content_id   TEXT NOT NULL,
              content_type          TEXT NOT NULL,
              title                 TEXT NOT NULL,
              snippet               TEXT NOT NULL,
              creator_hash          TEXT NOT NULL,
              publisher_name        TEXT NOT NULL,
              published_at_text     TEXT NOT NULL,
              content_url           TEXT NOT NULL,
              first_seen_at         TEXT NOT NULL,
              last_seen_at          TEXT NOT NULL,
              UNIQUE (platform, platform_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_contents_v4 (
              run_id              INTEGER NOT NULL
                                  REFERENCES search_runs_v4(id) ON DELETE CASCADE,
              search_content_id   INTEGER NOT NULL
                                  REFERENCES search_contents_v4(id) ON DELETE CASCADE,
              discovery_kind      TEXT NOT NULL
                                  CHECK (discovery_kind IN ('new', 'repeated')),
              first_observed_at   TEXT NOT NULL,
              last_observed_at    TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_content_terms_v4 (
              run_id              INTEGER NOT NULL,
              search_content_id   INTEGER NOT NULL,
              term_position       INTEGER NOT NULL,
              observed_at         TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id, term_position),
              FOREIGN KEY (run_id, search_content_id)
                REFERENCES search_run_contents_v4(run_id, search_content_id)
                ON DELETE CASCADE,
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms_v4(run_id, position)
                ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            "INSERT INTO search_runs_v4 SELECT * FROM search_runs ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_terms_v4
            SELECT * FROM search_run_terms ORDER BY run_id, position
            """
        )
        connection.execute(
            "INSERT INTO search_contents_v4 SELECT * FROM search_contents ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_contents_v4
            SELECT * FROM search_run_contents ORDER BY run_id, search_content_id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms_v4
            SELECT * FROM search_run_content_terms
            ORDER BY run_id, search_content_id, term_position
            """
        )

        for table in (
            "search_run_content_terms",
            "search_run_contents",
            "search_run_terms",
            "search_contents",
            "search_runs",
        ):
            connection.execute(f"DROP TABLE {table}")

        for old_name, stable_name in (
            ("search_runs_v4", "search_runs"),
            ("search_run_terms_v4", "search_run_terms"),
            ("search_contents_v4", "search_contents"),
            ("search_run_contents_v4", "search_run_contents"),
            ("search_run_content_terms_v4", "search_run_content_terms"),
        ):
            connection.execute(f"ALTER TABLE {old_name} RENAME TO {stable_name}")

        connection.execute(
            "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
        )
        connection.execute(
            """
            CREATE INDEX ix_search_run_contents_kind_observed
            ON search_run_contents(run_id, discovery_kind, first_observed_at DESC)
            """
        )

        for table_name, sequence in sequences.items():
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = ?", (table_name,)
            )
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                (table_name, sequence),
            )

        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after migration")
        connection.execute("PRAGMA user_version = 4")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_5(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 5:
            connection.execute("COMMIT")
            return
        if version != 4:
            raise DatabaseVersionError("Unsupported database migration source version.")

        sequence_rows = connection.execute(
            """
            SELECT name, seq FROM sqlite_sequence
            WHERE name IN ('search_runs', 'search_contents')
            """
        ).fetchall()
        sequences = {str(row["name"]): int(row["seq"]) for row in sequence_rows}

        connection.execute(
            """
            CREATE TABLE search_runs_v5 (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              platform                 TEXT NOT NULL
                                       CHECK (platform IN (
                                         'toutiao', 'wb', 'ks', 'dy'
                                       )),
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'completed_with_results', 'completed_empty',
                                         'login_required', 'manual_challenge_required',
                                         'platform_blocked_or_rate_limited',
                                         'structure_changed', 'browser_unavailable',
                                         'timed_out', 'cancelled', 'internal_error'
                                       )),
              current_term_position    INTEGER CHECK (current_term_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_terms_v5 (
              run_id     INTEGER NOT NULL
                         REFERENCES search_runs_v5(id) ON DELETE CASCADE,
              position   INTEGER NOT NULL CHECK (position >= 0),
              value      TEXT NOT NULL,
              PRIMARY KEY (run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_contents_v5 (
              id                    INTEGER PRIMARY KEY AUTOINCREMENT,
              platform              TEXT NOT NULL
                                    CHECK (platform IN (
                                      'toutiao', 'wb', 'ks', 'dy'
                                    )),
              platform_content_id   TEXT NOT NULL,
              content_type          TEXT NOT NULL,
              title                 TEXT NOT NULL,
              snippet               TEXT NOT NULL,
              creator_hash          TEXT NOT NULL,
              publisher_name        TEXT NOT NULL,
              published_at_text     TEXT NOT NULL,
              content_url           TEXT NOT NULL,
              first_seen_at         TEXT NOT NULL,
              last_seen_at          TEXT NOT NULL,
              UNIQUE (platform, platform_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_contents_v5 (
              run_id              INTEGER NOT NULL
                                  REFERENCES search_runs_v5(id) ON DELETE CASCADE,
              search_content_id   INTEGER NOT NULL
                                  REFERENCES search_contents_v5(id) ON DELETE CASCADE,
              discovery_kind      TEXT NOT NULL
                                  CHECK (discovery_kind IN ('new', 'repeated')),
              first_observed_at   TEXT NOT NULL,
              last_observed_at    TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_content_terms_v5 (
              run_id              INTEGER NOT NULL,
              search_content_id   INTEGER NOT NULL,
              term_position       INTEGER NOT NULL,
              observed_at         TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id, term_position),
              FOREIGN KEY (run_id, search_content_id)
                REFERENCES search_run_contents_v5(run_id, search_content_id)
                ON DELETE CASCADE,
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms_v5(run_id, position)
                ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            "INSERT INTO search_runs_v5 SELECT * FROM search_runs ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_terms_v5
            SELECT * FROM search_run_terms ORDER BY run_id, position
            """
        )
        connection.execute(
            "INSERT INTO search_contents_v5 SELECT * FROM search_contents ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_contents_v5
            SELECT * FROM search_run_contents ORDER BY run_id, search_content_id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms_v5
            SELECT * FROM search_run_content_terms
            ORDER BY run_id, search_content_id, term_position
            """
        )

        for table in (
            "search_run_content_terms",
            "search_run_contents",
            "search_run_terms",
            "search_contents",
            "search_runs",
        ):
            connection.execute(f"DROP TABLE {table}")

        for old_name, stable_name in (
            ("search_runs_v5", "search_runs"),
            ("search_run_terms_v5", "search_run_terms"),
            ("search_contents_v5", "search_contents"),
            ("search_run_contents_v5", "search_run_contents"),
            ("search_run_content_terms_v5", "search_run_content_terms"),
        ):
            connection.execute(f"ALTER TABLE {old_name} RENAME TO {stable_name}")

        connection.execute(
            "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
        )
        connection.execute(
            """
            CREATE INDEX ix_search_run_contents_kind_observed
            ON search_run_contents(run_id, discovery_kind, first_observed_at DESC)
            """
        )

        for table_name, sequence in sequences.items():
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = ?", (table_name,)
            )
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                (table_name, sequence),
            )

        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after migration")
        connection.execute("PRAGMA user_version = 5")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_6(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 6:
            connection.execute("COMMIT")
            return
        if version != 5:
            raise DatabaseVersionError("Unsupported database migration source version.")

        sequence_rows = connection.execute(
            """
            SELECT name, seq FROM sqlite_sequence
            WHERE name IN ('search_runs', 'search_contents')
            """
        ).fetchall()
        sequences = {str(row["name"]): int(row["seq"]) for row in sequence_rows}

        connection.execute(
            """
            CREATE TABLE search_runs_v6 (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              platform                 TEXT NOT NULL
                                       CHECK (platform IN (
                                         'toutiao', 'wb', 'ks', 'dy', 'xhs'
                                       )),
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'completed_with_results', 'completed_empty',
                                         'login_required', 'manual_challenge_required',
                                         'platform_blocked_or_rate_limited',
                                         'structure_changed', 'browser_unavailable',
                                         'timed_out', 'cancelled', 'internal_error'
                                       )),
              current_term_position    INTEGER CHECK (current_term_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_terms_v6 (
              run_id     INTEGER NOT NULL
                         REFERENCES search_runs_v6(id) ON DELETE CASCADE,
              position   INTEGER NOT NULL CHECK (position >= 0),
              value      TEXT NOT NULL,
              PRIMARY KEY (run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_contents_v6 (
              id                    INTEGER PRIMARY KEY AUTOINCREMENT,
              platform              TEXT NOT NULL
                                    CHECK (platform IN (
                                      'toutiao', 'wb', 'ks', 'dy', 'xhs'
                                    )),
              platform_content_id   TEXT NOT NULL,
              content_type          TEXT NOT NULL,
              title                 TEXT NOT NULL,
              snippet               TEXT NOT NULL,
              creator_hash          TEXT NOT NULL,
              publisher_name        TEXT NOT NULL,
              published_at_text     TEXT NOT NULL,
              content_url           TEXT NOT NULL,
              first_seen_at         TEXT NOT NULL,
              last_seen_at          TEXT NOT NULL,
              UNIQUE (platform, platform_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_contents_v6 (
              run_id              INTEGER NOT NULL
                                  REFERENCES search_runs_v6(id) ON DELETE CASCADE,
              search_content_id   INTEGER NOT NULL
                                  REFERENCES search_contents_v6(id) ON DELETE CASCADE,
              discovery_kind      TEXT NOT NULL
                                  CHECK (discovery_kind IN ('new', 'repeated')),
              first_observed_at   TEXT NOT NULL,
              last_observed_at    TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_run_content_terms_v6 (
              run_id              INTEGER NOT NULL,
              search_content_id   INTEGER NOT NULL,
              term_position       INTEGER NOT NULL,
              observed_at         TEXT NOT NULL,
              PRIMARY KEY (run_id, search_content_id, term_position),
              FOREIGN KEY (run_id, search_content_id)
                REFERENCES search_run_contents_v6(run_id, search_content_id)
                ON DELETE CASCADE,
              FOREIGN KEY (run_id, term_position)
                REFERENCES search_run_terms_v6(run_id, position)
                ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            "INSERT INTO search_runs_v6 SELECT * FROM search_runs ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_terms_v6
            SELECT * FROM search_run_terms ORDER BY run_id, position
            """
        )
        connection.execute(
            "INSERT INTO search_contents_v6 SELECT * FROM search_contents ORDER BY id"
        )
        connection.execute(
            """
            INSERT INTO search_run_contents_v6
            SELECT * FROM search_run_contents ORDER BY run_id, search_content_id
            """
        )
        connection.execute(
            """
            INSERT INTO search_run_content_terms_v6
            SELECT * FROM search_run_content_terms
            ORDER BY run_id, search_content_id, term_position
            """
        )

        for table in (
            "search_run_content_terms",
            "search_run_contents",
            "search_run_terms",
            "search_contents",
            "search_runs",
        ):
            connection.execute(f"DROP TABLE {table}")

        for old_name, stable_name in (
            ("search_runs_v6", "search_runs"),
            ("search_run_terms_v6", "search_run_terms"),
            ("search_contents_v6", "search_contents"),
            ("search_run_contents_v6", "search_run_contents"),
            ("search_run_content_terms_v6", "search_run_content_terms"),
        ):
            connection.execute(f"ALTER TABLE {old_name} RENAME TO {stable_name}")

        connection.execute(
            "CREATE INDEX ix_search_runs_status_id ON search_runs(status, id)"
        )
        connection.execute(
            "CREATE INDEX ix_search_runs_rule_id ON search_runs(monitoring_rule_id)"
        )
        connection.execute(
            """
            CREATE INDEX ix_search_run_contents_kind_observed
            ON search_run_contents(run_id, discovery_kind, first_observed_at DESC)
            """
        )

        for table_name, sequence in sequences.items():
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name = ?", (table_name,)
            )
            connection.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                (table_name, sequence),
            )

        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after migration")
        connection.execute("PRAGMA user_version = 6")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _migrate_to_version_7(connection: sqlite3.Connection) -> None:
    """Add durable multi-platform batch orchestration without rewriting runs."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = _read_user_version(connection)
        if version >= 7:
            connection.execute("COMMIT")
            return
        if version != 6:
            raise DatabaseVersionError("Unsupported database migration source version.")

        connection.execute(
            """
            CREATE TABLE search_batches (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              monitoring_rule_id       INTEGER
                                       REFERENCES monitoring_rules(id)
                                       ON DELETE SET NULL,
              rule_name                TEXT NOT NULL,
              max_results_per_term     INTEGER NOT NULL
                                       CHECK (max_results_per_term BETWEEN 1 AND 50),
              status                   TEXT NOT NULL CHECK (status IN (
                                         'queued', 'running',
                                         'paused_for_manual_action',
                                         'completed', 'completed_with_failures',
                                         'cancelled', 'internal_error'
                                       )),
              current_item_position    INTEGER CHECK (current_item_position >= 0),
              created_at               TEXT NOT NULL,
              started_at               TEXT,
              finished_at              TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_batch_terms (
              batch_id    INTEGER NOT NULL
                          REFERENCES search_batches(id) ON DELETE CASCADE,
              position    INTEGER NOT NULL CHECK (position >= 0),
              value       TEXT NOT NULL,
              PRIMARY KEY (batch_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_batch_items (
              batch_id    INTEGER NOT NULL
                          REFERENCES search_batches(id) ON DELETE CASCADE,
              position    INTEGER NOT NULL CHECK (position >= 0),
              platform    TEXT NOT NULL CHECK (platform IN (
                            'toutiao', 'wb', 'ks', 'dy', 'xhs'
                          )),
              status      TEXT NOT NULL CHECK (status IN (
                            'queued', 'running', 'paused_for_manual_action',
                            'completed', 'failed', 'cancelled'
                          )),
              created_at  TEXT NOT NULL,
              started_at  TEXT,
              finished_at TEXT,
              PRIMARY KEY (batch_id, position),
              UNIQUE (batch_id, platform)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE search_batch_attempts (
              batch_id       INTEGER NOT NULL,
              item_position  INTEGER NOT NULL,
              attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
              search_run_id   INTEGER NOT NULL UNIQUE
                              REFERENCES search_runs(id) ON DELETE RESTRICT,
              created_at      TEXT NOT NULL,
              PRIMARY KEY (batch_id, item_position, attempt_number),
              FOREIGN KEY (batch_id, item_position)
                REFERENCES search_batch_items(batch_id, position)
                ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX ix_search_batches_status_id
            ON search_batches(status, id)
            """
        )
        connection.execute(
            """
            CREATE INDEX ix_search_batches_rule_id
            ON search_batches(monitoring_rule_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX ix_search_batch_attempts_item
            ON search_batch_attempts(batch_id, item_position, attempt_number DESC)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX ux_search_batches_one_active
            ON search_batches((1))
            WHERE status IN ('queued', 'running', 'paused_for_manual_action')
            """
        )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.DatabaseError("Foreign key check failed after migration")
        connection.execute("PRAGMA user_version = 7")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
