"""Transactional batch recovery, immutable attempts and all-attempt projections."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from longtian_api.database import Database
from longtian_api.repositories.collection_schedules import _platforms, _rule
from longtian_api.repositories.platform_access import PlatformAccessRepository
from longtian_api.repositories.search_runs import (
    SearchResultRecord,
    SearchRunOrdering,
    SearchRunRecord,
    SearchRunStatus,
    _read_run,
    assemble_result,
)
from longtian_api.schemas.monitoring_rules import MonitoringRule
from longtian_api.schemas.platform_access import (
    PlatformAccessSnapshot,
    default_platform_access_snapshot,
)
from longtian_api.schemas.search_batches import (
    CompletionBasis,
    PauseReason,
    SearchBatchItemStatus,
    SearchBatchStatus,
)
from longtian_api.search_checkpoints import Checkpoint, item_checkpoint
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.collector_contracts import (
    SearchTermDiagnostic as CollectorSearchTermDiagnostic,
)

ACTIVE = {"queued", "running", "paused_for_manual_action"}
SUCCESS = {
    "completed_with_results",
    "completed_empty",
    "completed_with_incomplete",
}
MANUAL_PAUSE = {
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
}


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
    checkpoint: Checkpoint
    pause_reason: PauseReason | None
    completion_basis: CompletionBasis | None
    new_count: int
    repeated_count: int
    total_count: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    incomplete_terms: tuple[CollectorSearchTermDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchBatchRecord:
    id: int
    monitoring_rule_id: int | None
    rule_name: str
    terms: tuple[str, ...]
    max_results_per_term: int
    status: SearchBatchStatus
    control_revision: int
    current_item_position: int | None
    items: tuple[SearchBatchItemRecord, ...]
    created_at: str
    started_at: str | None
    finished_at: str | None
    max_total_results: int | None = None
    platform_access_snapshot: PlatformAccessSnapshot | None = None


@dataclass(frozen=True, slots=True)
class SearchBatchResultRecord:
    result: SearchResultRecord
    source_run_id: int


class SearchBatchRepositoryError(Exception):
    """Detail-free repository failure."""


class SearchBatchNotFoundError(SearchBatchRepositoryError):
    pass


class SearchBatchNotActiveError(SearchBatchRepositoryError):
    pass


class SearchBatchNotPausedError(SearchBatchRepositoryError):
    pass


class SearchBatchStateChangedError(SearchBatchRepositoryError):
    pass


class SearchBatchRecoveryUnavailableError(SearchBatchRepositoryError):
    pass


class SearchBatchItemNotRecoverableError(SearchBatchRepositoryError):
    pass


class SearchBatchRepositoryUnavailableError(SearchBatchRepositoryError):
    pass


class ScheduledDispatchChangedError(SearchBatchRepositoryError):
    pass


# Every result/count/filter consumes this grouping. Earliest attempt owns kind/source.
_RESULTS = """
WITH observations AS (
  SELECT links.*, attempts.attempt_number,
    ROW_NUMBER() OVER (
      PARTITION BY links.search_content_id ORDER BY attempts.attempt_number
    ) AS ordinal,
    MIN(links.first_observed_at) OVER (PARTITION BY links.search_content_id) AS
    first_at,
    MAX(links.last_observed_at) OVER (PARTITION BY links.search_content_id) AS last_at
  FROM search_batch_attempts AS attempts
  JOIN search_run_contents AS links ON links.run_id = attempts.search_run_id
  WHERE attempts.batch_id = ? AND attempts.item_position = ?
), results AS (
  SELECT contents.*, observations.discovery_kind,
    observations.run_id AS source_run_id, observations.first_at AS first_observed_at,
    observations.last_at AS last_observed_at
  FROM observations JOIN search_contents AS contents
    ON contents.id = observations.search_content_id
  WHERE observations.ordinal = 1
)
"""


class SearchBatchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def initialize(self) -> None:
        self._database.initialize()
        self.reconcile_interrupted_items()

    def reconcile_interrupted_items(self, batch_id: int | None = None) -> int:
        """Pause interrupted work; never retry or advance unfinished platforms."""
        with self._connection(write=True) as connection:
            rows = connection.execute(
                """SELECT id FROM search_batches WHERE status IN ('queued','running')
                   AND (? IS NULL OR id = ?)""",
                (batch_id, batch_id),
            ).fetchall()
            for row in rows:
                identity = int(row["id"])
                timestamp = _utc_timestamp()
                _settle_unfinished_attempts(connection, identity, timestamp)
                item = connection.execute(
                    """SELECT position FROM search_batch_items WHERE batch_id = ?
                       AND status IN ('queued','running')
                       ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END,
                       position LIMIT 1""",
                    (identity,),
                ).fetchone()
                if item is None:
                    _finalize(connection, identity)
                    continue
                position = int(item["position"])
                connection.execute(
                    """UPDATE search_batch_items SET status =
                    'paused_for_manual_action',
                       pause_reason = 'process_interrupted', finished_at = NULL
                       WHERE batch_id = ? AND position = ?""",
                    (identity, position),
                )
                connection.execute(
                    """UPDATE search_batches SET status = 'paused_for_manual_action',
                       current_item_position = ?, finished_at = NULL,
                       control_revision = control_revision + 1 WHERE id = ?""",
                    (position, identity),
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
        max_total_results: int | None = None,
        workflow_operation_key: str | None = None,
        platform_access_snapshot: PlatformAccessSnapshot | None = None,
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            return _insert_batch(
                connection,
                monitoring_rule_id=monitoring_rule_id,
                rule_name=rule_name,
                terms=terms,
                platforms=platforms,
                max_results_per_term=max_results_per_term,
                max_total_results=max_total_results,
                workflow_operation_key=workflow_operation_key,
                platform_access_snapshot=platform_access_snapshot
                or PlatformAccessRepository(self._database).snapshot_from_connection(
                    connection
                ),
            )

    def workflow_batch(self, operation_key: str) -> SearchBatchRecord | None:
        """Return a batch admitted for a workflow stage, if any."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM search_batches WHERE workflow_operation_key=?",
                (operation_key,),
            ).fetchone()
            return _read_batch(connection, int(row[0])) if row is not None else None

    def scheduled_batch(self, dispatch_token: str) -> SearchBatchRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT batch_id FROM collection_occurrences WHERE dispatch_token=?",
                (dispatch_token,),
            ).fetchone()
            return (
                _read_batch(connection, row[0])
                if row is not None and row[0] is not None
                else None
            )

    def create_scheduled_batch(
        self,
        dispatch_token: str,
        rule: MonitoringRule,
        *,
        timestamp: str,
        platform_access_snapshot: PlatformAccessSnapshot | None = None,
    ) -> tuple[SearchBatchRecord, bool]:
        """Existing batch + terms + items + occurrence link commit atomically."""
        with self._connection(write=True) as connection:
            occurrence = connection.execute(
                "SELECT * FROM collection_occurrences WHERE dispatch_token=?",
                (dispatch_token,),
            ).fetchone()
            if occurrence is None:
                raise ScheduledDispatchChangedError
            if occurrence["batch_id"] is not None:
                return _read_batch(connection, occurrence["batch_id"]), False
            schedule = connection.execute(
                "SELECT * FROM collection_schedules WHERE id=?",
                (occurrence["schedule_id"],),
            ).fetchone()
            if (
                occurrence["status"] != "claimed"
                or not schedule["enabled"]
                or schedule["revision"] != occurrence["schedule_revision"]
            ):
                raise ScheduledDispatchChangedError
            current = _rule(connection, schedule["monitoring_rule_id"])
            if (
                current is None
                or not current.enabled
                or current.id != rule.id
                or current.name != rule.name
                or current.monitoring_objects != tuple(rule.monitoring_objects)
                or current.issue_keywords != tuple(rule.issue_keywords)
            ):
                raise ScheduledDispatchChangedError
            platforms = _platforms(connection, schedule["id"])
            record = _insert_batch(
                connection,
                monitoring_rule_id=rule.id,
                rule_name=rule.name,
                terms=tuple(rule.terms),
                platforms=platforms,
                max_results_per_term=schedule["max_results_per_term"],
                max_total_results=schedule["max_total_results"],
                platform_access_snapshot=platform_access_snapshot
                or PlatformAccessRepository(self._database).snapshot_from_connection(
                    connection
                ),
            )
            connection.execute(
                """UPDATE collection_occurrences
                SET batch_id=?,status='dispatched',dispatched_at=?
                WHERE id=? AND status='claimed'""",
                (record.id, timestamp, occurrence["id"]),
            )
            return record, True

    def mark_running(self, batch_id: int) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            if (
                connection.execute(
                    """UPDATE search_batches SET status = 'running',
                   started_at = COALESCE(started_at, ?), control_revision =
                   control_revision + 1
                   WHERE id = ? AND status = 'queued'""",
                    (_utc_timestamp(), batch_id),
                ).rowcount
                == 0
            ):
                _batch_row(connection, batch_id)
                raise SearchBatchNotActiveError
            connection.execute(
                """UPDATE collection_occurrences
                SET launch_started_at=COALESCE(launch_started_at,?)
              WHERE batch_id=? AND status='dispatched'""",
                (_utc_timestamp(), batch_id),
            )
            return _read_batch(connection, batch_id)

    def next_queued_item(self, batch_id: int) -> SearchBatchItemRecord | None:
        record = self.get(batch_id)
        return next((item for item in record.items if item.status == "queued"), None)

    def create_attempt(
        self,
        batch_id: int,
        position: int,
        ordering: SearchRunOrdering | None = None,
    ) -> SearchRunRecord:
        with self._connection(write=True) as connection:
            batch = _batch_row(connection, batch_id)
            item = _item_row(connection, batch_id, position)
            if batch["status"] != "running" or item["status"] != "queued":
                raise SearchBatchNotActiveError
            if (
                connection.execute(
                    """SELECT 1 FROM search_batch_items WHERE batch_id = ?
                   AND (status IN ('running','paused_for_manual_action')
                        OR (position < ? AND status = 'queued'))""",
                    (batch_id, position),
                ).fetchone()
                is not None
            ):
                raise SearchBatchNotActiveError
            checkpoint = item_checkpoint(connection, batch_id, position)
            if not checkpoint.available or checkpoint.next_position is None:
                raise SearchBatchRecoveryUnavailableError
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """INSERT INTO search_runs (monitoring_rule_id, platform, rule_name,
                   max_results_per_term, status, created_at,
                   execution_start_term_position, search_protocol_version,
                   max_total_results, ordering, platform_access_snapshot_json)
                   VALUES (?, ?, ?, ?, 'queued', ?, ?, 2, ?, ?, ?)""",
                (
                    batch["monitoring_rule_id"],
                    item["platform"],
                    batch["rule_name"],
                    batch["max_results_per_term"],
                    timestamp,
                    checkpoint.next_position,
                    batch["max_total_results"],
                    ordering or ("latest" if item["platform"] == "wb" else "platform"),
                    batch["platform_access_snapshot_json"],
                ),
            )
            run_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO search_run_terms (run_id, position, value)
                   SELECT ?, position, value FROM search_batch_terms WHERE batch_id
                   = ?""",
                (run_id, batch_id),
            )
            connection.execute(
                """INSERT INTO search_batch_attempts
                   (batch_id, item_position, attempt_number, search_run_id, created_at)
                   SELECT ?, ?, COALESCE(MAX(attempt_number), 0) + 1, ?, ?
                   FROM search_batch_attempts WHERE batch_id = ? AND item_position =
                   ?""",
                (batch_id, position, run_id, timestamp, batch_id, position),
            )
            connection.execute(
                """UPDATE search_batch_items SET status = 'running',
                   started_at = COALESCE(started_at, ?), finished_at = NULL,
                   pause_reason = NULL
                   WHERE batch_id = ? AND position = ?""",
                (timestamp, batch_id, position),
            )
            connection.execute(
                """UPDATE search_batches SET current_item_position = ?,
                   control_revision = control_revision + 1 WHERE id = ?""",
                (position, batch_id),
            )
            return _read_run(connection, run_id)

    def finish_item(
        self,
        batch_id: int,
        position: int,
        run_status: SearchRunStatus,
        expected_run_id: int | None = None,
        *,
        pause: bool | None = None,
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            batch = _batch_row(connection, batch_id)
            item = _item_row(connection, batch_id, position)
            latest = _latest_run(connection, batch_id, position)
            if (
                item["status"] != "running"
                or batch["status"] != "running"
                or latest is None
                or latest["status"] != run_status
                or (expected_run_id is not None and latest["id"] != expected_run_id)
                or run_status in {"queued", "running"}
            ):
                raise SearchBatchStateChangedError
            success = run_status in SUCCESS
            # ``None`` preserves the repository's historical direct-call
            # behavior. Service orchestration supplies the explicit decision so
            # ordinary item failures can be recorded without pausing the batch.
            if pause is None:
                pause = not success
            # Authentication and platform safety barriers require the user to
            # intervene before the same batch can continue. Other terminal
            # failures belong to this platform item only; they are recorded as
            # failed while the following platform items keep running.
            item_status = (
                "completed"
                if success
                else "paused_for_manual_action"
                if pause
                else "failed"
            )
            batch_status = (
                "running" if success or not pause else "paused_for_manual_action"
            )
            connection.execute(
                """UPDATE search_batch_items SET status = ?, finished_at = ?,
                   pause_reason = ?, completion_basis = ? WHERE batch_id = ? AND
                   position = ?""",
                (
                    item_status,
                    _utc_timestamp() if not pause else None,
                    (
                        "platform_blocked_or_rate_limited"
                        if run_status == "platform_blocked_or_rate_limited"
                        else "attempt_failed"
                    )
                    if pause
                    else None,
                    "attempt_success" if success else None,
                    batch_id,
                    position,
                ),
            )
            connection.execute(
                """UPDATE search_batches SET status = ?, current_item_position = ?,
                   control_revision = control_revision + 1 WHERE id = ?""",
                (
                    batch_status,
                    position,
                    batch_id,
                ),
            )
            return _read_batch(connection, batch_id)

    def finalize(self, batch_id: int) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            _finalize(connection, batch_id)
            return _read_batch(connection, batch_id)

    def fail_batch(self, batch_id: int) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            if _batch_row(connection, batch_id)["status"] not in {"queued", "running"}:
                return _read_batch(connection, batch_id)
            timestamp = _utc_timestamp()
            _settle_unfinished_attempts(connection, batch_id, timestamp)
            connection.execute(
                """UPDATE search_batches SET status = 'internal_error', finished_at = ?,
                   control_revision = control_revision + 1
                   WHERE id = ? AND status IN ('queued','running')""",
                (timestamp, batch_id),
            )
            connection.execute(
                """UPDATE search_batch_items SET status = 'failed', finished_at = ?
                   WHERE batch_id = ? AND status IN ('queued','running')""",
                (timestamp, batch_id),
            )
            return _read_batch(connection, batch_id)

    def validate_control(
        self,
        batch_id: int,
        *,
        item_position: int,
        expected_run_id: int | None,
        expected_revision: int,
    ) -> SearchBatchRecord:
        with self._connection() as connection:
            _guard_pause(
                connection, batch_id, item_position, expected_run_id, expected_revision
            )
            return _read_batch(connection, batch_id)

    def continue_batch(
        self,
        batch_id: int,
        *,
        item_position: int,
        expected_run_id: int | None,
        expected_revision: int,
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            _guard_pause(
                connection, batch_id, item_position, expected_run_id, expected_revision
            )
            checkpoint = item_checkpoint(connection, batch_id, item_position)
            if not checkpoint.available:
                raise SearchBatchRecoveryUnavailableError
            done = checkpoint.remaining == 0
            connection.execute(
                """UPDATE search_batch_items SET status = ?, pause_reason = NULL,
                   finished_at = ?, completion_basis = ? WHERE batch_id = ? AND
                   position = ?""",
                (
                    "completed" if done else "queued",
                    _utc_timestamp() if done else None,
                    "confirmed_terms" if done else None,
                    batch_id,
                    item_position,
                ),
            )
            _resume(connection, batch_id)
            return _read_batch(connection, batch_id)

    def skip_item(
        self,
        batch_id: int,
        *,
        item_position: int,
        expected_run_id: int | None,
        expected_revision: int,
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            _guard_pause(
                connection, batch_id, item_position, expected_run_id, expected_revision
            )
            connection.execute(
                """UPDATE search_batch_items SET status = 'skipped', pause_reason =
                NULL,
                   finished_at = ? WHERE batch_id = ? AND position = ?""",
                (_utc_timestamp(), batch_id, item_position),
            )
            _resume(connection, batch_id)
            return _read_batch(connection, batch_id)

    def recover_item(
        self,
        batch_id: int,
        position: int,
        *,
        expected_run_id: int | None,
        expected_revision: int,
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            batch = _batch_row(connection, batch_id)
            item = _item_row(connection, batch_id, position)
            latest = _latest_run(connection, batch_id, position)
            _guard_revision(batch, expected_revision)
            if latest is None or latest["id"] != expected_run_id:
                raise SearchBatchStateChangedError
            if (
                batch["status"] != "completed_with_failures"
                or item["status"] != "failed"
                or latest["status"] in SUCCESS | {"queued", "running"}
                or batch["finished_at"] is None
                or item["finished_at"] is None
            ):
                raise SearchBatchItemNotRecoverableError
            if (
                connection.execute(
                    "SELECT 1 FROM search_batches WHERE status IN "
                    "('queued','running','paused_for_manual_action')"
                ).fetchone()
                is not None
            ):
                raise SearchBatchStateChangedError
            timestamp = _utc_timestamp()
            connection.execute(
                """INSERT INTO search_batch_recoveries (batch_id, item_position,
                   previous_control_revision, previous_batch_status,
                   previous_item_status,
                   previous_batch_finished_at, previous_item_finished_at, recovered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    position,
                    expected_revision,
                    batch["status"],
                    item["status"],
                    batch["finished_at"],
                    item["finished_at"],
                    timestamp,
                ),
            )
            connection.execute(
                """UPDATE search_batch_items SET status = 'paused_for_manual_action',
                   pause_reason = 'attempt_failed', finished_at = NULL
                   WHERE batch_id = ? AND position = ?""",
                (batch_id, position),
            )
            connection.execute(
                """UPDATE search_batches SET status = 'paused_for_manual_action',
                   current_item_position = ?, finished_at = NULL, control_revision =
                   control_revision + 1
                   WHERE id = ?""",
                (position, batch_id),
            )
            return _read_batch(connection, batch_id)

    def cancel_batch(
        self, batch_id: int, *, expected_revision: int
    ) -> SearchBatchRecord:
        with self._connection(write=True) as connection:
            batch = _batch_row(connection, batch_id)
            _guard_revision(batch, expected_revision)
            if batch["status"] not in ACTIVE:
                raise SearchBatchNotActiveError
            timestamp = _utc_timestamp()
            connection.execute(
                """UPDATE search_batches SET status = 'cancelled', finished_at = ?,
                   control_revision = control_revision + 1 WHERE id = ?""",
                (timestamp, batch_id),
            )
            connection.execute(
                """UPDATE search_runs SET status = 'cancelled', failure_reason = NULL,
                   finished_at = ?
                   WHERE status IN ('queued','running') AND id IN (
                     SELECT search_run_id FROM search_batch_attempts WHERE batch_id = ?
                   )""",
                (timestamp, batch_id),
            )
            connection.execute(
                """UPDATE search_batch_items SET status = 'cancelled', finished_at = ?,
                   pause_reason = NULL WHERE batch_id = ?
                   AND status IN ('queued','running','paused_for_manual_action')""",
                (timestamp, batch_id),
            )
            return _read_batch(connection, batch_id)

    def get(self, batch_id: int) -> SearchBatchRecord:
        with self._connection() as connection:
            return _read_batch(connection, batch_id)

    def ensure_platform_access_snapshot(
        self, batch_id: int, snapshot: PlatformAccessSnapshot
    ) -> None:
        with self._connection(write=True) as connection:
            connection.execute(
                """UPDATE search_batches
                   SET platform_access_snapshot_json=?
                   WHERE id=? AND platform_access_snapshot_json IS NULL""",
                (snapshot.model_dump_json(), batch_id),
            )

    def list(
        self, *, limit: int, before_id: int | None
    ) -> tuple[tuple[SearchBatchRecord, ...], int | None]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM search_batches WHERE (? IS NULL OR id < ?) ORDER BY id "
                "DESC LIMIT ?",
                (before_id, before_id, limit + 1),
            ).fetchall()
            records = tuple(
                _read_batch(connection, int(row["id"])) for row in rows[:limit]
            )
            return records, records[-1].id if len(rows) > limit and records else None

    def list_attempts(
        self, batch_id: int, position: int
    ) -> tuple[SearchBatchAttemptRecord, ...]:
        with self._connection() as connection:
            _item_row(connection, batch_id, position)
            return _attempts(connection, batch_id, position)

    def active_or_paused(self) -> SearchBatchRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM search_batches WHERE status IN "
                "('queued','running','paused_for_manual_action')"
            ).fetchone()
            return _read_batch(connection, row["id"]) if row else None

    def list_results(
        self,
        *,
        batch_id: int,
        position: int,
        kind: Literal["all", "new", "repeated"],
        limit: int,
        offset: int,
    ) -> tuple[tuple[SearchBatchResultRecord, ...], int]:
        with self._connection() as connection:
            _item_row(connection, batch_id, position)
            params = (batch_id, position, kind, kind)
            total = connection.execute(
                _RESULTS + "SELECT COUNT(*) FROM results "
                "WHERE (? = 'all' OR discovery_kind = ?)",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                _RESULTS
                + """SELECT * FROM results WHERE (? = 'all' OR discovery_kind = ?)
                  ORDER BY CASE discovery_kind WHEN 'new' THEN 0 ELSE 1 END,
                  first_observed_at DESC, id ASC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            records = []
            for row in rows:
                terms = connection.execute(
                    """SELECT DISTINCT terms.position, terms.value
                       FROM search_batch_attempts AS attempts
                       JOIN search_run_content_terms AS matches ON matches.run_id =
                       attempts.search_run_id
                       JOIN search_batch_terms AS terms ON terms.batch_id =
                       attempts.batch_id
                         AND terms.position = matches.term_position
                       WHERE attempts.batch_id = ? AND attempts.item_position = ?
                         AND matches.search_content_id = ? ORDER BY terms.position""",
                    (batch_id, position, row["id"]),
                ).fetchall()
                records.append(
                    SearchBatchResultRecord(
                        assemble_result(
                            row, tuple(str(term["value"]) for term in terms)
                        ),
                        int(row["source_run_id"]),
                    )
                )
            return tuple(records), int(total)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            connection = self._database.connect()
            try:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            raise SearchBatchRepositoryUnavailableError from None


def _insert_batch(
    connection: sqlite3.Connection,
    *,
    monitoring_rule_id: int,
    rule_name: str,
    terms: Sequence[str],
    platforms: Sequence[SearchPlatform],
    max_results_per_term: int,
    max_total_results: int | None = None,
    workflow_operation_key: str | None = None,
    platform_access_snapshot: PlatformAccessSnapshot | None = None,
) -> SearchBatchRecord:
    """One insertion owner shared by manual and occurrence-backed admission."""
    timestamp = _utc_timestamp()
    cursor = connection.execute(
        """INSERT INTO search_batches
          (monitoring_rule_id,rule_name,max_results_per_term,status,created_at,
           workflow_operation_key,max_total_results,platform_access_snapshot_json)
          VALUES (?,?,?,'queued',?,?,?,?)""",
        (
            monitoring_rule_id,
            rule_name,
            max_results_per_term,
            timestamp,
            workflow_operation_key,
            max_total_results,
            (
                platform_access_snapshot or default_platform_access_snapshot()
            ).model_dump_json(),
        ),
    )
    batch_id = int(cursor.lastrowid)
    connection.executemany(
        "INSERT INTO search_batch_terms(batch_id,position,value) VALUES (?,?,?)",
        ((batch_id, position, value) for position, value in enumerate(terms)),
    )
    connection.executemany(
        """INSERT INTO search_batch_items(batch_id,position,platform,status,created_at)
      VALUES (?,?,?,'queued',?)""",
        (
            (batch_id, position, platform, timestamp)
            for position, platform in enumerate(platforms)
        ),
    )
    return _read_batch(connection, batch_id)


def _batch_row(connection: sqlite3.Connection, batch_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM search_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        raise SearchBatchNotFoundError
    return row


def _item_row(
    connection: sqlite3.Connection, batch_id: int, position: int
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM search_batch_items WHERE batch_id = ? AND position = ?",
        (batch_id, position),
    ).fetchone()
    if row is None:
        raise SearchBatchNotFoundError
    return row


def _latest_run(
    connection: sqlite3.Connection, batch_id: int, position: int
) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT runs.* FROM search_batch_attempts AS attempts
           JOIN search_runs AS runs ON runs.id = attempts.search_run_id
           WHERE attempts.batch_id = ? AND attempts.item_position = ?
           ORDER BY attempts.attempt_number DESC LIMIT 1""",
        (batch_id, position),
    ).fetchone()


def _guard_revision(batch: sqlite3.Row, expected_revision: int) -> None:
    if batch["control_revision"] != expected_revision:
        raise SearchBatchStateChangedError


def _guard_pause(
    connection: sqlite3.Connection,
    batch_id: int,
    position: int,
    run_id: int | None,
    revision: int,
) -> None:
    batch = _batch_row(connection, batch_id)
    _guard_revision(batch, revision)
    if batch["status"] != "paused_for_manual_action":
        raise SearchBatchNotPausedError
    item = _item_row(connection, batch_id, position)
    latest = _latest_run(connection, batch_id, position)
    if (
        batch["current_item_position"] != position
        or item["status"] != "paused_for_manual_action"
        or (latest["id"] if latest else None) != run_id
        or (latest is None and item["pause_reason"] != "process_interrupted")
    ):
        raise SearchBatchStateChangedError


def _resume(connection: sqlite3.Connection, batch_id: int) -> None:
    connection.execute(
        """UPDATE search_batches SET status = 'running', finished_at = NULL,
           started_at = COALESCE(started_at, ?),
           control_revision = control_revision + 1 WHERE id = ?""",
        (_utc_timestamp(), batch_id),
    )


def _finalize(connection: sqlite3.Connection, batch_id: int) -> None:
    batch = _batch_row(connection, batch_id)
    statuses = [
        row[0]
        for row in connection.execute(
            "SELECT status FROM search_batch_items WHERE batch_id = ?", (batch_id,)
        ).fetchall()
    ]
    if batch["status"] not in {"queued", "running"} or any(
        s in ACTIVE for s in statuses
    ):
        raise SearchBatchNotActiveError
    incomplete = (
        connection.execute(
            """
            SELECT 1
            FROM search_batch_attempts AS attempts
            JOIN search_run_term_diagnostics AS diagnostics
              ON diagnostics.run_id = attempts.search_run_id
            WHERE attempts.batch_id = ?
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
        is not None
    )
    connection.execute(
        """UPDATE search_batches SET status = ?, current_item_position = NULL,
           finished_at = ?, control_revision = control_revision + 1 WHERE id = ?""",
        (
            "completed"
            if all(s == "completed" for s in statuses) and not incomplete
            else "completed_with_failures",
            _utc_timestamp(),
            batch_id,
        ),
    )


def _settle_unfinished_attempts(
    connection: sqlite3.Connection, batch_id: int, timestamp: str
) -> None:
    # The run may have committed success just before item finalization failed.
    # Preserve that outcome and timestamp, then terminate only still-active runs.
    connection.execute(
        """UPDATE search_batch_items SET status = 'completed',
           completion_basis = 'attempt_success', pause_reason = NULL,
           finished_at = (
             SELECT runs.finished_at FROM search_batch_attempts AS attempts
             JOIN search_runs AS runs ON runs.id = attempts.search_run_id
             WHERE attempts.batch_id = search_batch_items.batch_id
               AND attempts.item_position = search_batch_items.position
             ORDER BY attempts.attempt_number DESC LIMIT 1
           ) WHERE batch_id = ? AND status = 'running' AND (
             SELECT runs.status FROM search_batch_attempts AS attempts
             JOIN search_runs AS runs ON runs.id = attempts.search_run_id
             WHERE attempts.batch_id = search_batch_items.batch_id
               AND attempts.item_position = search_batch_items.position
             ORDER BY attempts.attempt_number DESC LIMIT 1
           ) IN ('completed_with_results', 'completed_empty',
                 'completed_with_incomplete')""",
        (batch_id,),
    )
    connection.execute(
        """UPDATE search_runs SET status = 'internal_error', failure_reason = NULL,
           finished_at = ?
           WHERE status IN ('queued','running') AND id IN (
             SELECT search_run_id FROM search_batch_attempts WHERE batch_id = ?
           )""",
        (timestamp, batch_id),
    )


def _attempts(
    connection: sqlite3.Connection, batch_id: int, position: int
) -> tuple[SearchBatchAttemptRecord, ...]:
    rows = connection.execute(
        """SELECT attempt_number, search_run_id FROM search_batch_attempts
           WHERE batch_id = ? AND item_position = ? ORDER BY attempt_number DESC""",
        (batch_id, position),
    ).fetchall()
    return tuple(
        SearchBatchAttemptRecord(
            int(row["attempt_number"]),
            # Preserve the actual damaged snapshot for read-only history. The
            # checkpoint validator blocks continuation, not skip or cancel.
            _read_run(connection, int(row["search_run_id"]), allow_empty_terms=True),
        )
        for row in rows
    )


def _read_batch(connection: sqlite3.Connection, batch_id: int) -> SearchBatchRecord:
    row = _batch_row(connection, batch_id)
    terms = tuple(
        str(term[0])
        for term in connection.execute(
            "SELECT value FROM search_batch_terms WHERE batch_id = ? ORDER BY position",
            (batch_id,),
        ).fetchall()
    )
    items = []
    for item in connection.execute(
        "SELECT * FROM search_batch_items WHERE batch_id = ? ORDER BY position",
        (batch_id,),
    ).fetchall():
        position = int(item["position"])
        attempts = _attempts(connection, batch_id, position)
        counts = connection.execute(
            _RESULTS
            + """SELECT COUNT(*) AS total, COALESCE(SUM(discovery_kind = 'new'), 0)
            AS new,
                          COALESCE(SUM(discovery_kind = 'repeated'), 0) AS repeated
                          FROM results""",
            (batch_id, position),
        ).fetchone()
        diagnostic_rows = connection.execute(
            """
            SELECT term_position, value, reason, result_count
            FROM (
              SELECT terms.position AS term_position, terms.value,
                     diagnostics.reason, diagnostics.result_count,
                     ROW_NUMBER() OVER (
                       PARTITION BY terms.position
                       ORDER BY attempts.attempt_number DESC
                     ) AS ordinal
              FROM search_batch_attempts AS attempts
              JOIN search_run_term_diagnostics AS diagnostics
                ON diagnostics.run_id = attempts.search_run_id
              JOIN search_run_terms AS terms
                ON terms.run_id = diagnostics.run_id
               AND terms.position = diagnostics.term_position
              WHERE attempts.batch_id = ? AND attempts.item_position = ?
            )
            WHERE ordinal = 1
            ORDER BY term_position ASC
            """,
            (batch_id, position),
        ).fetchall()
        items.append(
            SearchBatchItemRecord(
                position=position,
                platform=cast(SearchPlatform, item["platform"]),
                status=item["status"],
                attempt_count=len(attempts),
                latest_attempt=attempts[0] if attempts else None,
                checkpoint=item_checkpoint(connection, batch_id, position),
                pause_reason=item["pause_reason"],
                completion_basis=item["completion_basis"],
                new_count=int(counts["new"]),
                repeated_count=int(counts["repeated"]),
                total_count=int(counts["total"]),
                created_at=item["created_at"],
                started_at=item["started_at"],
                finished_at=item["finished_at"],
                incomplete_terms=tuple(
                    CollectorSearchTermDiagnostic(
                        position=int(diagnostic["term_position"]),
                        reason=str(diagnostic["reason"]),  # type: ignore[arg-type]
                        result_count=int(diagnostic["result_count"]),
                    )
                    for diagnostic in diagnostic_rows
                ),
            )
        )
    return SearchBatchRecord(
        id=int(row["id"]),
        monitoring_rule_id=row["monitoring_rule_id"],
        rule_name=row["rule_name"],
        terms=terms,
        max_results_per_term=int(row["max_results_per_term"]),
        max_total_results=row["max_total_results"],
        status=row["status"],
        control_revision=int(row["control_revision"]),
        current_item_position=row["current_item_position"],
        items=tuple(items),
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        platform_access_snapshot=_decode_snapshot(row["platform_access_snapshot_json"]),
    )


def _decode_snapshot(value):
    if not value:
        return default_platform_access_snapshot(basis="legacy_unavailable")
    try:
        return PlatformAccessSnapshot.model_validate_json(value)
    except (TypeError, ValueError):
        return default_platform_access_snapshot(basis="legacy_unavailable")


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
