"""SQLite path and migration ownership for local product data."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

CURRENT_DATABASE_VERSION = 1
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
        finally:
            connection.close()


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise sqlite3.DatabaseError("SQLite did not return user_version")
    return int(row[0])


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
