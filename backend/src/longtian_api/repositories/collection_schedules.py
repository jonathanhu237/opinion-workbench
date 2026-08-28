"""Short, atomic schedule/occurrence operations; never execute a collector here."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from longtian_api.collection_timing import due_range, utc
from longtian_api.database import Database
from longtian_api.repositories.monitoring_rules import (
    MonitoringRuleNotFoundError,
    MonitoringRuleRecord,
    _read_record,
)
from longtian_api.schemas.collection_schedules import (
    CollectionOccurrence,
    CollectionOccurrenceList,
    OccurrenceReason,
    validate_schedule_platforms,
)
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.collection_schedule_errors import CollectionScheduleError


@dataclass(frozen=True)
class ScheduleRecord:
    id: int
    monitoring_rule_id: int | None
    rule_name: str
    rule: MonitoringRuleRecord | None
    platforms: tuple[SearchPlatform, ...]
    max_results_per_term: int
    interval_minutes: int
    enabled: bool
    revision: int
    anchor_at: str | None
    next_due_at: str | None
    created_at: str
    updated_at: str
    latest_occurrence: CollectionOccurrence | None


@dataclass(frozen=True)
class OccurrenceClaim:
    id: int
    dispatch_token: str
    schedule_id: int
    schedule_revision: int
    monitoring_rule_id: int | None
    platforms: tuple[SearchPlatform, ...]
    max_results_per_term: int


class CollectionScheduleRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = self.database.connect()
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except (sqlite3.Error, OSError, ValidationError, ValueError, TypeError):
            raise CollectionScheduleError(
                "collection_schedule_storage_unavailable"
            ) from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()

    def rule(self, rule_id: int) -> MonitoringRuleRecord:
        with self.connection() as connection:
            rule = _rule(connection, rule_id)
            if rule is None:
                raise CollectionScheduleError("monitoring_rule_not_found")
            return rule

    def save(
        self,
        *,
        schedule_id: int | None,
        expected_revision: int | None,
        rule: MonitoringRuleRecord | None,
        platforms: tuple[SearchPlatform, ...],
        max_results_per_term: int,
        interval_minutes: int,
        enabled: bool,
        now: datetime,
    ) -> ScheduleRecord:
        timestamp = utc(now).isoformat()
        due = (
            (utc(now) + timedelta(minutes=interval_minutes)).isoformat()
            if enabled
            else None
        )
        with self.connection(write=True) as connection:
            old = _row(connection, schedule_id) if schedule_id is not None else None
            if old is not None and old["revision"] != expected_revision:
                raise CollectionScheduleError("collection_schedule_changed")
            if rule is None:
                if old is None or old["monitoring_rule_id"] is not None or enabled:
                    raise CollectionScheduleError("invalid_collection_schedule")
            elif _rule(connection, rule.id) != rule:
                raise CollectionScheduleError("collection_schedule_changed")
            rule_name = rule.name if rule is not None else old["rule_name"]
            values = (
                rule.id if rule else None,
                rule_name,
                max_results_per_term,
                interval_minutes,
                int(enabled),
                timestamp if enabled else None,
                due,
                timestamp,
            )
            if old is None:
                cursor = connection.execute(
                    """INSERT INTO collection_schedules(monitoring_rule_id,rule_name,
                      max_results_per_term,interval_minutes,enabled,anchor_at,next_due_at,
                      updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (*values, timestamp),
                )
                schedule_id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """UPDATE collection_schedules SET monitoring_rule_id=?,rule_name=?,
                      max_results_per_term=?,interval_minutes=?,enabled=?,anchor_at=?,
                      next_due_at=?,updated_at=?,revision=revision+1 WHERE id=?""",
                    (*values, schedule_id),
                )
                connection.execute(
                    "DELETE FROM collection_schedule_platforms WHERE schedule_id=?",
                    (schedule_id,),
                )
            connection.executemany(
                "INSERT INTO collection_schedule_platforms VALUES (?,?,?)",
                (
                    (schedule_id, position, platform)
                    for position, platform in enumerate(platforms)
                ),
            )
            return _read_schedule(connection, schedule_id)

    def get(self, schedule_id: int) -> ScheduleRecord:
        with self.connection() as connection:
            return _read_schedule(connection, schedule_id)

    def list(
        self, *, limit: int, before_id: int | None
    ) -> tuple[list[ScheduleRecord], int | None]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT id FROM collection_schedules WHERE (? IS NULL OR id<?)
                   ORDER BY id DESC LIMIT ?""",
                (before_id, before_id, limit + 1),
            ).fetchall()
            records = [_read_schedule(connection, row["id"]) for row in rows[:limit]]
            return records, records[-1].id if len(rows) > limit else None

    def occurrences(
        self, schedule_id: int, *, limit: int = 50, before_id: int | None = None
    ) -> CollectionOccurrenceList:
        with self.connection() as connection:
            _row(connection, schedule_id)
            rows = connection.execute(
                _OCCURRENCES + " WHERE o.schedule_id=? AND (? IS NULL OR o.id<?)"
                " ORDER BY o.id DESC LIMIT ?",
                (schedule_id, before_id, before_id, limit + 1),
            ).fetchall()
            items = [_occurrence(row) for row in rows[:limit]]
            return CollectionOccurrenceList(
                occurrences=items,
                next_before_id=items[-1].id if len(rows) > limit else None,
            )

    def reconcile_startup(self, now: datetime) -> None:
        with self.connection(write=True) as connection:
            connection.execute("""UPDATE collection_occurrences
              SET status='interrupted',reason='dispatch_interrupted'
              WHERE status='claimed' OR
                (status='dispatched' AND launch_started_at IS NULL)""")
        # Bounded pages, with no collection/model work or per-missed-minute loop.
        while self.advance_due(now, missed_reason="offline"):
            pass

    def advance_due(
        self,
        now: datetime,
        *,
        missed_reason: Literal["offline", "clock_jump"] | None = None,
    ) -> list[OccurrenceClaim] | int:
        """Claim each due key once, advancing it in the SAME transaction."""
        timestamp = utc(now).isoformat()
        claims = []
        with self.connection(write=True) as connection:
            rows = connection.execute(
                """SELECT * FROM collection_schedules WHERE enabled=1 AND next_due_at<=?
                  ORDER BY next_due_at,id LIMIT 100""",
                (timestamp,),
            ).fetchall()
            for row in rows:
                due = datetime.fromisoformat(row["next_due_at"])
                count, last, future = due_range(due, now, row["interval_minutes"])
                missed = missed_reason is not None or count > 1
                token = str(uuid4())
                cursor = connection.execute(
                    """INSERT INTO collection_occurrences(
                      schedule_id,schedule_revision,due_at,
                      dispatch_token,status,reason,missed_count,missed_until,created_at)
                      VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        row["id"],
                        row["revision"],
                        due.isoformat(),
                        token,
                        "missed" if missed else "claimed",
                        (missed_reason or "clock_jump") if missed else None,
                        count if missed else 0,
                        last.isoformat() if missed else None,
                        timestamp,
                    ),
                )
                connection.execute(
                    "UPDATE collection_schedules SET next_due_at=? WHERE id=?",
                    (future.isoformat(), row["id"]),
                )
                if not missed:
                    claims.append(
                        OccurrenceClaim(
                            id=int(cursor.lastrowid),
                            dispatch_token=token,
                            schedule_id=row["id"],
                            schedule_revision=row["revision"],
                            monitoring_rule_id=row["monitoring_rule_id"],
                            platforms=_platforms(connection, row["id"]),
                            max_results_per_term=row["max_results_per_term"],
                        )
                    )
            return len(rows) if missed_reason is not None else claims

    def skip(self, token: str, reason: OccurrenceReason) -> None:
        with self.connection(write=True) as connection:
            connection.execute(
                """UPDATE collection_occurrences SET status=?,reason=?
                  WHERE dispatch_token=? AND status='claimed' AND batch_id IS NULL""",
                (
                    "interrupted" if reason == "dispatch_interrupted" else "skipped",
                    reason,
                    token,
                ),
            )


_OCCURRENCES = """SELECT o.*,b.status AS batch_status FROM collection_occurrences o
  LEFT JOIN search_batches b ON b.id=o.batch_id"""


def _occurrence(row: sqlite3.Row) -> CollectionOccurrence:
    return CollectionOccurrence(
        **{key: row[key] for key in CollectionOccurrence.model_fields}
    )


def _row(connection: sqlite3.Connection, schedule_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM collection_schedules WHERE id=?", (schedule_id,)
    ).fetchone()
    if row is None:
        raise CollectionScheduleError("collection_schedule_not_found")
    return row


def _rule(
    connection: sqlite3.Connection, rule_id: int | None
) -> MonitoringRuleRecord | None:
    if rule_id is None:
        return None
    try:
        # Diagnostic schedule projection keeps invalid rules visibly invalid;
        # normal monitoring-rule reads retain their strict nonempty contract.
        return _read_record(connection, rule_id, require_objects=False)
    except MonitoringRuleNotFoundError:
        return None


def _platforms(
    connection: sqlite3.Connection, schedule_id: int
) -> tuple[SearchPlatform, ...]:
    platforms = tuple(
        row[0]
        for row in connection.execute(
            "SELECT platform FROM collection_schedule_platforms"
            " WHERE schedule_id=? ORDER BY position",
            (schedule_id,),
        )
    )
    try:
        validate_schedule_platforms(platforms)
    except ValueError:
        raise sqlite3.DatabaseError("Invalid stored schedule platforms") from None
    return platforms


def _read_schedule(connection: sqlite3.Connection, schedule_id: int) -> ScheduleRecord:
    row = _row(connection, schedule_id)
    latest = connection.execute(
        _OCCURRENCES + " WHERE o.schedule_id=? ORDER BY o.id DESC LIMIT 1",
        (schedule_id,),
    ).fetchone()
    return ScheduleRecord(
        id=row["id"],
        monitoring_rule_id=row["monitoring_rule_id"],
        rule_name=row["rule_name"],
        rule=_rule(connection, row["monitoring_rule_id"]),
        platforms=_platforms(connection, schedule_id),
        max_results_per_term=row["max_results_per_term"],
        interval_minutes=row["interval_minutes"],
        enabled=bool(row["enabled"]),
        revision=row["revision"],
        anchor_at=row["anchor_at"],
        next_due_at=row["next_due_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        latest_occurrence=_occurrence(latest) if latest is not None else None,
    )
