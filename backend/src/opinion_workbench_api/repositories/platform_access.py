"""Durable application-local pacing settings and cross-task platform state."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from opinion_workbench_api.database import Database
from opinion_workbench_api.schemas.platform_access import (
    PlatformAccessBasis,
    PlatformAccessDiagnostic,
    PlatformAccessSettings,
    PlatformAccessSnapshot,
    PlatformAccessUpdate,
    PlatformIntervals,
    default_platform_access_snapshot,
    default_platform_intervals,
)
from opinion_workbench_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform
from opinion_workbench_api.services.analysis_errors import AnalysisError


class PlatformAccessConflict(AnalysisError):
    """The settings revision changed between read and complete replacement."""

    def __init__(self):
        super().__init__("platform_access_settings_conflict")


class PlatformAccessRepository:
    """Keep settings and the last controlled access in SQLite, never in a UI."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        self.database.initialize()
        with self._connection(write=True) as connection:
            # This is deliberately idempotent so a read-only service fixture can
            # be composed with an older temporary database during a rolling update.
            row = connection.execute(
                "SELECT id FROM platform_access_settings WHERE id=1"
            ).fetchone()
            if row is None:
                intervals = default_platform_intervals()
                connection.execute(
                    """INSERT INTO platform_access_settings
                       (id, revision, interval_seconds_json, updated_at)
                       VALUES (1, 1, ?, ?)""",
                    (json.dumps(intervals.model_dump(), sort_keys=True), _now()),
                )
            for platform in SEARCH_PLATFORMS:
                connection.execute(
                    """INSERT OR IGNORE INTO platform_access_state
                       (platform, last_access_started_at, blocked_until,
                        diagnostic_json, updated_at)
                       VALUES (?, NULL, NULL, NULL, ?)""",
                    (platform, _now()),
                )

    def read(self) -> PlatformAccessSettings:
        with self._connection() as connection:
            return self._read(connection)

    def _read(self, connection) -> PlatformAccessSettings:
        row = connection.execute(
            "SELECT * FROM platform_access_settings WHERE id=1"
        ).fetchone()
        if row is None:
            raise AnalysisError("platform_access_settings_unavailable")
        intervals = _decode_intervals(row["interval_seconds_json"])
        try:
            updated = datetime.fromisoformat(row["updated_at"])
            if updated.tzinfo is None:
                raise ValueError("updated_at must include timezone")
            return PlatformAccessSettings(
                revision=int(row["revision"]),
                interval_seconds=intervals,
                updated_at=updated,
            )
        except (TypeError, ValueError, OverflowError):
            raise AnalysisError("platform_access_settings_unavailable") from None

    def replace(self, payload: PlatformAccessUpdate) -> PlatformAccessSettings:
        # Pydantic validates the complete map before this method is called. The
        # single UPDATE is still guarded by revision, so no partial platform map
        # can become visible to a concurrent task.
        with self._connection(write=True) as connection:
            current = self._read(connection)
            if current.revision != payload.expected_revision:
                raise PlatformAccessConflict
            changed = connection.execute(
                """UPDATE platform_access_settings
                   SET revision=revision+1, interval_seconds_json=?, updated_at=?
                   WHERE id=1 AND revision=?""",
                (
                    json.dumps(
                        payload.interval_seconds.model_dump(),
                        sort_keys=True,
                    ),
                    _now(),
                    payload.expected_revision,
                ),
            )
            if changed.rowcount != 1:
                raise PlatformAccessConflict
            return self._read(connection)

    def snapshot(
        self, *, basis: PlatformAccessBasis = "explicit"
    ) -> PlatformAccessSnapshot:
        with self._connection() as connection:
            return self.snapshot_from_connection(connection, basis=basis)

    def snapshot_from_connection(
        self, connection, *, basis: PlatformAccessBasis = "explicit"
    ) -> PlatformAccessSnapshot:
        try:
            settings = self._read(connection)
        except AnalysisError:
            table = connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type='table' AND name='platform_access_settings'"""
            ).fetchone()
            if table is not None:
                # A present but malformed/empty settings row is an unavailable
                # configuration, not a historical database that lacks v39.
                raise
            # Historical databases can be read before the v39 service has had a
            # chance to initialize its singleton. A safe snapshot is explicit
            # about that compatibility path and never claims a historical 5s run.
            return default_platform_access_snapshot(basis="legacy_unavailable")
        return PlatformAccessSnapshot(
            interval_seconds=settings.interval_seconds,
            basis=basis,
        )

    def state(self, platform: SearchPlatform | str) -> dict[str, object]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM platform_access_state WHERE platform=?", (platform,)
            ).fetchone()
            if row is None:
                raise AnalysisError("platform_access_settings_unavailable")
            _validate_access_state_values(row, platform=str(platform))
            return dict(row)

    def reserve_access(
        self,
        platform: SearchPlatform,
        started_at: str,
        earliest_next_allowed_at: str | None = None,
        *,
        interval_seconds: int | None = None,
        allow_early: bool = False,
    ) -> bool:
        """Atomically reserve a controlled start and persist its boundary.

        The coordinator normally serializes this call in memory, but the
        SQLite-side check also protects two coordinators sharing the same
        local database.  ``earliest_next_allowed_at`` is never shortened by a
        newer task's smaller interval.
        """
        started = parse_timestamp(started_at)
        requested = parse_timestamp(earliest_next_allowed_at)
        if started is None or (
            earliest_next_allowed_at is not None and requested is None
        ):
            raise AnalysisError("platform_access_settings_unavailable")
        if interval_seconds is not None and (
            type(interval_seconds) is not int or not 1 <= interval_seconds <= 300
        ):
            raise AnalysisError("platform_access_settings_unavailable")
        if type(allow_early) is not bool:
            raise AnalysisError("platform_access_settings_unavailable")
        with self._connection(write=True) as connection:
            current = connection.execute(
                """SELECT last_access_started_at,earliest_next_allowed_at,
                          blocked_until,diagnostic_json
                   FROM platform_access_state WHERE platform=?""",
                (platform,),
            ).fetchone()
            if current is not None:
                _validate_access_state_values(current, platform=str(platform))
            # A block may be recorded after the coordinator's preceding state
            # read. Never let this reservation clear that diagnostic or start a
            # request while it is active; the caller will re-read and surface
            # the durable pause.
            if current is not None and (
                current["blocked_until"] is not None
                or current["diagnostic_json"] is not None
            ):
                return False
            if interval_seconds is not None and not allow_early:
                last = parse_timestamp(
                    current["last_access_started_at"] if current else None
                )
                earliest = parse_timestamp(
                    current["earliest_next_allowed_at"] if current else None
                )
                required = earliest
                if last is not None:
                    boundary = last + timedelta(seconds=interval_seconds)
                    required = max(required, boundary) if required else boundary
                if required is not None and started < required:
                    return False
            # An explicit recovery may bypass the current boundary once, but
            # it must not shorten the durable boundary that another task (or a
            # restarted coordinator) already established. The actual retry
            # start is still recorded below, so subsequent ordinary starts
            # pace from both timestamps.
            existing = parse_timestamp(
                current["earliest_next_allowed_at"] if current else None
            )
            if existing is not None and (requested is None or existing > requested):
                earliest_next_allowed_at = existing.isoformat()
            connection.execute(
                """INSERT INTO platform_access_state
                   (platform,last_access_started_at,earliest_next_allowed_at,
                    blocked_until,diagnostic_json,updated_at)
                   VALUES (?, ?, ?, NULL, NULL, ?)
                   ON CONFLICT(platform) DO UPDATE SET
                     last_access_started_at=excluded.last_access_started_at,
                     earliest_next_allowed_at=excluded.earliest_next_allowed_at,
                     updated_at=excluded.updated_at""",
                (platform, started_at, earliest_next_allowed_at, _now()),
            )
            return True

    def record_block(
        self,
        platform: SearchPlatform,
        diagnostic: PlatformAccessDiagnostic,
    ) -> None:
        if diagnostic.platform != platform:
            raise AnalysisError("platform_access_settings_unavailable")
        with self._connection(write=True) as connection:
            previous = connection.execute(
                "SELECT diagnostic_json FROM platform_access_state WHERE platform=?",
                (platform,),
            ).fetchone()
            previous_diagnostic = None
            if previous is not None and previous[0]:
                try:
                    previous_diagnostic = PlatformAccessDiagnostic.model_validate_json(
                        previous[0]
                    )
                except (TypeError, ValueError):
                    previous_diagnostic = None
            deadlines = [
                value.retry_after_at
                for value in (previous_diagnostic, diagnostic)
                if value is not None and value.retry_after_at is not None
            ]
            retry_after_at = max(deadlines) if deadlines else None
            if previous_diagnostic is not None:
                generic = (
                    diagnostic.status_code is None
                    and diagnostic.platform_code is None
                    and not diagnostic.manual_challenge_required
                    and diagnostic.basis == "explicit_platform_evidence"
                )
                diagnostic = diagnostic.model_copy(
                    update={
                        "status_code": diagnostic.status_code
                        if diagnostic.status_code is not None
                        else previous_diagnostic.status_code,
                        "platform_code": diagnostic.platform_code
                        if diagnostic.platform_code is not None
                        else previous_diagnostic.platform_code,
                        "retry_after_at": retry_after_at,
                        "manual_challenge_required": (
                            diagnostic.manual_challenge_required
                            or previous_diagnostic.manual_challenge_required
                        ),
                        **(
                            {
                                "stage": previous_diagnostic.stage,
                                "basis": previous_diagnostic.basis,
                            }
                            if generic
                            else {}
                        ),
                    }
                )
            elif retry_after_at != diagnostic.retry_after_at:
                diagnostic = diagnostic.model_copy(
                    update={"retry_after_at": retry_after_at}
                )
            connection.execute(
                """INSERT INTO platform_access_state
                   (platform,last_access_started_at,blocked_until,diagnostic_json,updated_at)
                   VALUES (?, NULL, ?, ?, ?)
                   ON CONFLICT(platform) DO UPDATE SET
                     blocked_until=excluded.blocked_until,
                     diagnostic_json=excluded.diagnostic_json,
                     updated_at=excluded.updated_at""",
                (
                    platform,
                    retry_after_at.isoformat() if retry_after_at is not None else None,
                    diagnostic.model_dump_json(),
                    _now(),
                ),
            )

    def acknowledge_block(self, platform: SearchPlatform) -> None:
        with self._connection(write=True) as connection:
            connection.execute(
                """UPDATE platform_access_state
                   SET blocked_until=NULL, diagnostic_json=NULL, updated_at=?
                   WHERE platform=?""",
                (_now(), platform),
            )

    def block_record(self, platform: SearchPlatform | str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT blocked_until, diagnostic_json, updated_at
                   FROM platform_access_state WHERE platform=?""",
                (platform,),
            ).fetchone()
            if row is None:
                return None
            _validate_access_state_values(row, platform=str(platform))
            return dict(row)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except (sqlite3.Error, OSError):
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise AnalysisError("platform_access_settings_unavailable") from None
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()


def _decode_intervals(value: str) -> PlatformIntervals:
    try:
        raw = json.loads(value)
        return PlatformIntervals.model_validate(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise AnalysisError("platform_access_settings_unavailable") from None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_access_state_values(value, *, platform: str | None = None) -> None:
    """Reject corrupted pacing state instead of silently starting early."""
    for key in (
        "last_access_started_at",
        "earliest_next_allowed_at",
        "blocked_until",
        "updated_at",
    ):
        try:
            field = value[key]
        except (IndexError, KeyError, TypeError):
            continue
        if field is not None and parse_timestamp(field) is None:
            raise AnalysisError("platform_access_settings_unavailable")
    try:
        raw = value["diagnostic_json"]
    except (IndexError, KeyError, TypeError):
        raw = None
    try:
        blocked_until = value["blocked_until"]
    except (IndexError, KeyError, TypeError):
        blocked_until = None
    if blocked_until is not None and raw is None:
        raise AnalysisError("platform_access_settings_unavailable")
    if raw is not None:
        if not isinstance(raw, str):
            raise AnalysisError("platform_access_settings_unavailable")
        try:
            diagnostic = PlatformAccessDiagnostic.model_validate_json(raw)
        except (TypeError, ValueError):
            raise AnalysisError("platform_access_settings_unavailable") from None
        if platform is not None and diagnostic.platform != platform:
            raise AnalysisError("platform_access_settings_unavailable")


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, OverflowError):
        return None
    return result if result.tzinfo is not None else result.replace(tzinfo=UTC)
