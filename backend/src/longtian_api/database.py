"""SQLite path and migration ownership for local product data."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

CURRENT_DATABASE_VERSION = 9
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
        finally:
            connection.close()


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise sqlite3.DatabaseError("SQLite did not return user_version")
    return int(row[0])


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
