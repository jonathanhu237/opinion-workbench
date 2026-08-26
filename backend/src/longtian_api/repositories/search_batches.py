"""SQLite repository for durable multi-platform search batches."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from longtian_api.database import Database
from longtian_api.repositories.search_runs import (
    SearchRunRecord,
    SearchRunRepository,
    SearchRunStatus,
)
from longtian_api.search_platforms import SearchPlatform

SearchBatchStatus = Literal[
    "queued",
    "running",
    "paused_for_manual_action",
    "completed",
    "completed_with_failures",
    "cancelled",
    "internal_error",
]
SearchBatchItemStatus = Literal[
    "queued",
    "running",
    "paused_for_manual_action",
    "completed",
    "failed",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class SearchBatchAttemptRecord:
    attempt_number: int
    run: SearchRunRecord


@dataclass(frozen=True, slots=True)
class SearchBatchItemRecord:
    position: int
    platform: SearchPlatform
    status: SearchBatchItemStatus
    attempt_count: int
    latest_attempt: SearchBatchAttemptRecord | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class SearchBatchRecord:
    id: int
    monitoring_rule_id: int | None
    rule_name: str
    terms: tuple[str, ...]
    max_results_per_term: int
    status: SearchBatchStatus
    current_item_position: int | None
    items: tuple[SearchBatchItemRecord, ...]
    created_at: str
    started_at: str | None
    finished_at: str | None


class SearchBatchRepositoryError(Exception):
    """Base class for safe batch repository failures."""


class SearchBatchNotFoundError(SearchBatchRepositoryError):
    """The requested batch does not exist."""


class SearchBatchNotActiveError(SearchBatchRepositoryError):
    """The requested batch cannot accept the transition."""


class SearchBatchNotPausedError(SearchBatchRepositoryError):
    """The requested batch is not waiting for manual action."""


class SearchBatchRepositoryUnavailableError(SearchBatchRepositoryError):
    """SQLite could not complete a batch operation safely."""


class SearchBatchRepository:
    """Own batch SQL and immutable links to existing single-platform runs."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._runs = SearchRunRepository(database)

    def initialize(self) -> None:
        self._database.initialize()
        self.reconcile_interrupted_items()

    def reconcile_interrupted_items(self) -> int:
        """Project already-reconciled child attempts back onto active batches."""
        with _translate_storage_errors(), self._write_connection() as connection:
            rows = connection.execute(
                """
                SELECT items.batch_id, items.position, runs.status
                FROM search_batch_items AS items
                LEFT JOIN search_batch_attempts AS attempts
                  ON attempts.batch_id = items.batch_id
                 AND attempts.item_position = items.position
                 AND attempts.attempt_number = (
                   SELECT MAX(latest.attempt_number)
                   FROM search_batch_attempts AS latest
                   WHERE latest.batch_id = items.batch_id
                     AND latest.item_position = items.position
                 )
                LEFT JOIN search_runs AS runs ON runs.id = attempts.search_run_id
                WHERE items.status = 'running'
                """
            ).fetchall()
            timestamp = _utc_timestamp()
            for row in rows:
                run_status = str(row["status"] or "internal_error")
                if run_status in {"queued", "running"}:
                    connection.execute(
                        """
                        UPDATE search_runs
                        SET status = 'internal_error', finished_at = ?
                        WHERE id = (
                          SELECT search_run_id FROM search_batch_attempts
                          WHERE batch_id = ? AND item_position = ?
                          ORDER BY attempt_number DESC LIMIT 1
                        ) AND status IN ('queued', 'running')
                        """,
                        (timestamp, int(row["batch_id"]), int(row["position"])),
                    )
                connection.execute(
                    """
                    UPDATE search_batch_items
                    SET status = 'failed', finished_at = ?
                    WHERE batch_id = ? AND position = ? AND status = 'running'
                    """,
                    (timestamp, int(row["batch_id"]), int(row["position"])),
                )
            return len(rows)

    def create_batch(
        self,
        *,
        monitoring_rule_id: int,
        rule_name: str,
        terms: Sequence[str],
        platforms: Sequence[SearchPlatform],
        max_results_per_term: int,
    ) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                INSERT INTO search_batches (
                  monitoring_rule_id, rule_name, max_results_per_term, status,
                  current_item_position, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, 'queued', NULL, ?, NULL, NULL)
                """,
                (monitoring_rule_id, rule_name, max_results_per_term, timestamp),
            )
            batch_id = cursor.lastrowid
            if batch_id is None:
                raise sqlite3.DatabaseError("SQLite did not return a batch ID")
            connection.executemany(
                """
                INSERT INTO search_batch_terms (batch_id, position, value)
                VALUES (?, ?, ?)
                """,
                ((batch_id, position, value) for position, value in enumerate(terms)),
            )
            connection.executemany(
                """
                INSERT INTO search_batch_items (
                  batch_id, position, platform, status, created_at,
                  started_at, finished_at
                ) VALUES (?, ?, ?, 'queued', ?, NULL, NULL)
                """,
                (
                    (batch_id, position, platform, timestamp)
                    for position, platform in enumerate(platforms)
                ),
            )
        return self.get(int(batch_id))

    def mark_running(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_batches
                SET status = 'running', started_at = COALESCE(started_at, ?),
                    finished_at = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (_utc_timestamp(), batch_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, batch_id)
        return self.get(batch_id)

    def next_queued_item(self, batch_id: int) -> SearchBatchItemRecord | None:
        record = self.get(batch_id)
        return next((item for item in record.items if item.status == "queued"), None)

    def create_attempt(self, batch_id: int, position: int) -> SearchRunRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            batch = connection.execute(
                """
                SELECT monitoring_rule_id, rule_name, max_results_per_term
                FROM search_batches WHERE id = ? AND status = 'running'
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                _raise_missing_or_inactive(connection, batch_id)
            item = connection.execute(
                """
                SELECT platform FROM search_batch_items
                WHERE batch_id = ? AND position = ? AND status = 'queued'
                """,
                (batch_id, position),
            ).fetchone()
            if item is None:
                raise SearchBatchNotActiveError
            term_rows = connection.execute(
                """
                SELECT position, value FROM search_batch_terms
                WHERE batch_id = ? ORDER BY position ASC
                """,
                (batch_id,),
            ).fetchall()
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                INSERT INTO search_runs (
                  monitoring_rule_id, platform, rule_name, max_results_per_term,
                  status, current_term_position, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, 'queued', NULL, ?, NULL, NULL)
                """,
                (
                    batch["monitoring_rule_id"],
                    item["platform"],
                    batch["rule_name"],
                    batch["max_results_per_term"],
                    timestamp,
                ),
            )
            run_id = cursor.lastrowid
            if run_id is None:
                raise sqlite3.DatabaseError("SQLite did not return a run ID")
            connection.executemany(
                """
                INSERT INTO search_run_terms (run_id, position, value)
                VALUES (?, ?, ?)
                """,
                (
                    (run_id, int(row["position"]), str(row["value"]))
                    for row in term_rows
                ),
            )
            attempt_row = connection.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt
                FROM search_batch_attempts
                WHERE batch_id = ? AND item_position = ?
                """,
                (batch_id, position),
            ).fetchone()
            attempt_number = int(attempt_row["next_attempt"])
            connection.execute(
                """
                INSERT INTO search_batch_attempts (
                  batch_id, item_position, attempt_number, search_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (batch_id, position, attempt_number, run_id, timestamp),
            )
            connection.execute(
                """
                UPDATE search_batch_items
                SET status = 'running', started_at = COALESCE(started_at, ?),
                    finished_at = NULL
                WHERE batch_id = ? AND position = ?
                """,
                (timestamp, batch_id, position),
            )
            connection.execute(
                """
                UPDATE search_batches SET current_item_position = ? WHERE id = ?
                """,
                (position, batch_id),
            )
        return self._runs.get(int(run_id))

    def finish_item(
        self, batch_id: int, position: int, run_status: SearchRunStatus
    ) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            batch = connection.execute(
                "SELECT status FROM search_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise SearchBatchNotFoundError
            batch_status = str(batch["status"])
            timestamp = _utc_timestamp()
            if batch_status == "cancelled":
                item_status: SearchBatchItemStatus = "cancelled"
            elif run_status in {"completed_with_results", "completed_empty"}:
                item_status = "completed"
            elif run_status == "manual_challenge_required":
                item_status = "paused_for_manual_action"
            else:
                item_status = "failed"
            connection.execute(
                """
                UPDATE search_batch_items
                SET status = ?, finished_at = ?
                WHERE batch_id = ? AND position = ? AND status = 'running'
                """,
                (item_status, timestamp, batch_id, position),
            )
            if item_status == "paused_for_manual_action":
                connection.execute(
                    """
                    UPDATE search_batches
                    SET status = 'paused_for_manual_action',
                        current_item_position = ?, finished_at = NULL
                    WHERE id = ? AND status = 'running'
                    """,
                    (position, batch_id),
                )
        return self.get(batch_id)

    def finalize(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            batch = connection.execute(
                "SELECT status FROM search_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise SearchBatchNotFoundError
            if str(batch["status"]) == "cancelled":
                pass
            else:
                counts = connection.execute(
                    """
                    SELECT
                      SUM(CASE WHEN status IN (
                        'queued', 'running', 'paused_for_manual_action'
                      ) THEN 1 ELSE 0 END) AS active_count,
                      SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END)
                        AS failure_count
                    FROM search_batch_items WHERE batch_id = ?
                    """,
                    (batch_id,),
                ).fetchone()
                if int(counts["active_count"] or 0) != 0:
                    raise SearchBatchNotActiveError
                terminal = (
                    "completed_with_failures"
                    if int(counts["failure_count"] or 0) > 0
                    else "completed"
                )
                connection.execute(
                    """
                    UPDATE search_batches
                    SET status = ?, current_item_position = NULL, finished_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (terminal, _utc_timestamp(), batch_id),
                )
        return self.get(batch_id)

    def fail_batch(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_batches
                SET status = 'internal_error', finished_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (_utc_timestamp(), batch_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, batch_id)
            connection.execute(
                """
                UPDATE search_batch_items
                SET status = 'failed', finished_at = ?
                WHERE batch_id = ? AND status IN ('queued', 'running')
                """,
                (_utc_timestamp(), batch_id),
            )
        return self.get(batch_id)

    def continue_batch(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            batch = connection.execute(
                """
                SELECT current_item_position FROM search_batches
                WHERE id = ? AND status = 'paused_for_manual_action'
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                if (
                    connection.execute(
                        "SELECT 1 FROM search_batches WHERE id = ?", (batch_id,)
                    ).fetchone()
                    is None
                ):
                    raise SearchBatchNotFoundError
                raise SearchBatchNotPausedError
            position = int(batch["current_item_position"])
            connection.execute(
                """
                UPDATE search_batch_items
                SET status = 'queued', finished_at = NULL
                WHERE batch_id = ? AND position = ?
                  AND status = 'paused_for_manual_action'
                """,
                (batch_id, position),
            )
            connection.execute(
                """
                UPDATE search_batches SET status = 'running', finished_at = NULL
                WHERE id = ?
                """,
                (batch_id,),
            )
        return self.get(batch_id)

    def cancel_batch(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_batches
                SET status = 'cancelled', finished_at = ?
                WHERE id = ? AND status IN (
                  'queued', 'running', 'paused_for_manual_action'
                )
                """,
                (_utc_timestamp(), batch_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, batch_id)
            connection.execute(
                """
                UPDATE search_batch_items
                SET status = 'cancelled', finished_at = ?
                WHERE batch_id = ? AND status IN (
                  'queued', 'paused_for_manual_action'
                )
                """,
                (_utc_timestamp(), batch_id),
            )
        return self.get(batch_id)

    def get(self, batch_id: int) -> SearchBatchRecord:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                row = connection.execute(
                    "SELECT * FROM search_batches WHERE id = ?", (batch_id,)
                ).fetchone()
                if row is None:
                    raise SearchBatchNotFoundError
                terms = tuple(
                    str(term["value"])
                    for term in connection.execute(
                        """
                        SELECT value FROM search_batch_terms
                        WHERE batch_id = ? ORDER BY position ASC
                        """,
                        (batch_id,),
                    ).fetchall()
                )
                item_rows = connection.execute(
                    """
                    SELECT * FROM search_batch_items
                    WHERE batch_id = ? ORDER BY position ASC
                    """,
                    (batch_id,),
                ).fetchall()
                item_metadata = []
                for item in item_rows:
                    attempts = connection.execute(
                        """
                        SELECT attempt_number, search_run_id
                        FROM search_batch_attempts
                        WHERE batch_id = ? AND item_position = ?
                        ORDER BY attempt_number DESC
                        """,
                        (batch_id, int(item["position"])),
                    ).fetchall()
                    item_metadata.append((item, attempts))
            finally:
                connection.close()
            items = tuple(
                _assemble_item(self._runs, item, attempts)
                for item, attempts in item_metadata
            )
            return SearchBatchRecord(
                id=int(row["id"]),
                monitoring_rule_id=(
                    int(row["monitoring_rule_id"])
                    if row["monitoring_rule_id"] is not None
                    else None
                ),
                rule_name=str(row["rule_name"]),
                terms=terms,
                max_results_per_term=int(row["max_results_per_term"]),
                status=cast(SearchBatchStatus, str(row["status"])),
                current_item_position=(
                    int(row["current_item_position"])
                    if row["current_item_position"] is not None
                    else None
                ),
                items=items,
                created_at=str(row["created_at"]),
                started_at=str(row["started_at"]) if row["started_at"] else None,
                finished_at=str(row["finished_at"]) if row["finished_at"] else None,
            )

    def list(
        self, *, limit: int, before_id: int | None
    ) -> tuple[tuple[SearchBatchRecord, ...], int | None]:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                if before_id is None:
                    rows = connection.execute(
                        "SELECT id FROM search_batches ORDER BY id DESC LIMIT ?",
                        (limit + 1,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT id FROM search_batches
                        WHERE id < ? ORDER BY id DESC LIMIT ?
                        """,
                        (before_id, limit + 1),
                    ).fetchall()
            finally:
                connection.close()
            selected = rows[:limit]
            records = tuple(self.get(int(row["id"])) for row in selected)
            next_before_id = records[-1].id if len(rows) > limit and records else None
            return records, next_before_id

    def list_attempts(
        self, batch_id: int, position: int
    ) -> tuple[SearchBatchAttemptRecord, ...]:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                exists = connection.execute(
                    """
                    SELECT 1 FROM search_batch_items
                    WHERE batch_id = ? AND position = ?
                    """,
                    (batch_id, position),
                ).fetchone()
                if exists is None:
                    if (
                        connection.execute(
                            "SELECT 1 FROM search_batches WHERE id = ?", (batch_id,)
                        ).fetchone()
                        is None
                    ):
                        raise SearchBatchNotFoundError
                    return ()
                rows = connection.execute(
                    """
                    SELECT attempt_number, search_run_id
                    FROM search_batch_attempts
                    WHERE batch_id = ? AND item_position = ?
                    ORDER BY attempt_number DESC
                    """,
                    (batch_id, position),
                ).fetchall()
            finally:
                connection.close()
            return tuple(
                SearchBatchAttemptRecord(
                    attempt_number=int(row["attempt_number"]),
                    run=self._runs.get(int(row["search_run_id"])),
                )
                for row in rows
            )

    def active_or_paused(self) -> SearchBatchRecord | None:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT id FROM search_batches
                    WHERE status IN ('queued', 'running', 'paused_for_manual_action')
                    ORDER BY id ASC LIMIT 1
                    """
                ).fetchone()
            finally:
                connection.close()
            return self.get(int(row["id"])) if row is not None else None

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _assemble_item(
    runs: SearchRunRepository,
    row: sqlite3.Row,
    attempts: Sequence[sqlite3.Row],
) -> SearchBatchItemRecord:
    latest = (
        SearchBatchAttemptRecord(
            attempt_number=int(attempts[0]["attempt_number"]),
            run=runs.get(int(attempts[0]["search_run_id"])),
        )
        if attempts
        else None
    )
    return SearchBatchItemRecord(
        position=int(row["position"]),
        platform=cast(SearchPlatform, str(row["platform"])),
        status=cast(SearchBatchItemStatus, str(row["status"])),
        attempt_count=len(attempts),
        latest_attempt=latest,
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
    )


def _raise_missing_or_inactive(connection: sqlite3.Connection, batch_id: int) -> None:
    if (
        connection.execute(
            "SELECT 1 FROM search_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        is None
    ):
        raise SearchBatchNotFoundError
    raise SearchBatchNotActiveError


@contextmanager
def _translate_storage_errors() -> Iterator[None]:
    try:
        yield
    except (
        SearchBatchNotFoundError,
        SearchBatchNotActiveError,
        SearchBatchNotPausedError,
    ):
        raise
    except (OSError, sqlite3.Error):
        raise SearchBatchRepositoryUnavailableError from None


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
