"""The single settings row contains only an opaque credential reference."""

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from opinion_workbench_api.database import Database


class AISettingsStorageError(Exception):
    pass


@dataclass(frozen=True)
class AISettingsRecord:
    base_url: str
    model: str
    secret_ref: str = field(repr=False)
    revision: int


class AISettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def read(self) -> AISettingsRecord | None:
        try:
            connection = self.database.connect()
            try:
                row = connection.execute(
                    "SELECT base_url, model, secret_ref, revision "
                    "FROM ai_settings WHERE id = 1"
                ).fetchone()
                return AISettingsRecord(**dict(row)) if row is not None else None
            finally:
                connection.close()
        except sqlite3.Error:
            raise AISettingsStorageError() from None

    def replace(self, record: AISettingsRecord) -> None:
        try:
            connection = self.database.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO ai_settings
                        (id, base_url, model, secret_ref, revision, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        base_url = excluded.base_url, model = excluded.model,
                        secret_ref = excluded.secret_ref, revision = excluded.revision,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.base_url,
                        record.model,
                        record.secret_ref,
                        record.revision,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except sqlite3.Error:
            raise AISettingsStorageError() from None
