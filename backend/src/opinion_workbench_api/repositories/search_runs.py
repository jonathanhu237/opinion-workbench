"""SQLite repository for durable product search runs and discoveries."""

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.platform_access import PlatformAccessRepository
from opinion_workbench_api.schemas.platform_access import (
    PlatformAccessDiagnostic,
    PlatformAccessSnapshot,
    default_platform_access_snapshot,
)
from opinion_workbench_api.search_failure_reasons import (
    SearchFailureReason,
    is_search_failure_reason,
)
from opinion_workbench_api.search_platforms import SearchPlatform
from opinion_workbench_api.services.collector_contracts import (
    SearchTermDiagnostic as CollectorSearchTermDiagnostic,
)
from opinion_workbench_api.services.native_browser_contracts import ExecutionLimit

SearchRunStatus = Literal[
    "queued",
    "running",
    "completed_with_results",
    "completed_empty",
    "completed_with_incomplete",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "timed_out",
    "cancelled",
    "internal_error",
]
SearchRunOrdering = Literal["latest", "platform"]
DiscoveryKind = Literal["new", "repeated"]


def _metadata_json(hashtags, interaction_stats):
    tags = []
    for value in hashtags or ():
        if not isinstance(value, str):
            continue
        value = " ".join(value.split())[:50]
        if value and value not in tags:
            tags.append(value)
        if len(tags) >= 32:
            break
    stats = {}
    for key, value in (interaction_stats or {}).items():
        if key not in {"likes", "comments", "shares", "favorites"}:
            continue
        if value is None or (type(value) is int and 0 <= value <= 2**53 - 1):
            stats[key] = value
    return json.dumps(tags, ensure_ascii=False), json.dumps(
        stats, ensure_ascii=False, sort_keys=True
    )


def _metadata_from_row(row):
    try:
        values = json.loads(row["hashtags_json"] or "[]")
        hashtags = (
            tuple(value for value in values if isinstance(value, str))
            if isinstance(values, list)
            else ()
        )
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        hashtags = ()
    try:
        values = json.loads(row["interaction_stats_json"] or "{}")
        interaction_stats = (
            {
                key: value
                for key, value in values.items()
                if key in {"likes", "comments", "shares", "favorites"}
                and (value is None or (type(value) is int and 0 <= value <= 2**53 - 1))
            }
            if isinstance(values, dict)
            else {}
        )
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        interaction_stats = {}
    return hashtags, interaction_stats


@dataclass(frozen=True, slots=True)
class SearchRunRecord:
    id: int
    monitoring_rule_id: int | None
    platform: SearchPlatform
    rule_name: str
    terms: tuple[str, ...]
    max_results_per_term: int
    status: SearchRunStatus
    current_term_position: int | None
    new_count: int
    repeated_count: int
    total_count: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    failure_reason: SearchFailureReason | None = None
    execution_start_term_position: int = 0
    search_protocol_version: int = 2
    execution_limit: ExecutionLimit | None = None
    incomplete_terms: tuple[CollectorSearchTermDiagnostic, ...] = ()
    max_total_results: int | None = None
    ordering: SearchRunOrdering = "platform"
    platform_access_snapshot: PlatformAccessSnapshot | None = None
    access_waiting: bool = False
    access_notice: PlatformAccessDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class SearchContentInput:
    platform_content_id: str
    content_type: str
    title: str
    snippet: str
    creator_hash: str
    publisher_name: str
    published_at_text: str
    content_url: str
    observed_at: str
    hashtags: tuple[str, ...] = ()
    interaction_stats: dict[str, int | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchResultRecord:
    id: int
    platform: SearchPlatform
    platform_content_id: str
    content_type: str
    title: str
    snippet: str
    creator_hash: str
    publisher_name: str
    published_at_text: str
    content_url: str
    first_seen_at: str
    last_seen_at: str
    discovery_kind: DiscoveryKind
    first_observed_at: str
    last_observed_at: str
    matched_terms: tuple[str, ...]
    hashtags: tuple[str, ...] = ()
    interaction_stats: dict[str, int | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchResultOpenTargetRecord:
    platform: SearchPlatform
    platform_content_id: str
    matched_terms: tuple[str, ...]
    # Historical in-process callers may only have the platform/id/terms
    # projection.  Production rows always provide the canonical URL, while a
    # missing default is rejected before any browser navigation.
    content_url: str = ""


@dataclass(frozen=True, slots=True)
class SearchResultSourceRecord:
    """Internal stored identity; no caller-provided navigation target is accepted."""

    run_id: int
    result_id: int
    platform: SearchPlatform
    platform_content_id: str
    content_type: str
    content_url: str
    title: str
    snippet: str
    matched_terms: tuple[str, ...]
    collection_active: bool
    # Added after the original acquisition contract. Defaults keep old
    # in-process callers valid while new source metadata travels with the
    # frozen record.
    publisher_name: str = ""
    published_at_text: str = ""
    hashtags: tuple[str, ...] = ()
    interaction_stats: dict[str, int | None] = field(default_factory=dict)


class SearchRunRepositoryError(Exception):
    """Base class for safe repository failure categories."""


class SearchRunNotFoundError(SearchRunRepositoryError):
    """The requested durable run does not exist."""


class SearchRunNotActiveError(SearchRunRepositoryError):
    """The requested run cannot accept a transition or observation."""


class SearchResultNotFoundError(SearchRunRepositoryError):
    """The requested global result does not belong to the requested run."""


class SearchRunRepositoryUnavailableError(SearchRunRepositoryError):
    """SQLite could not complete an operation safely."""


class SearchRunRepository:
    """Own search-run SQL, deterministic projections, and item transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def initialize(self) -> None:
        self._database.initialize()
        self.reconcile_active_runs()

    def reconcile_active_runs(self) -> int:
        with _translate_storage_errors(), self._write_connection() as connection:
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET status = 'internal_error', failure_reason = NULL,
                    finished_at = ?, access_wait_json = NULL
                WHERE status IN ('queued', 'running')
                """,
                (timestamp,),
            )
            return cursor.rowcount

    def create_run(
        self,
        *,
        monitoring_rule_id: int,
        platform: SearchPlatform,
        rule_name: str,
        terms: Sequence[str],
        max_results_per_term: int,
        max_total_results: int | None = None,
        ordering: SearchRunOrdering | None = None,
        platform_access_snapshot: PlatformAccessSnapshot | None = None,
    ) -> SearchRunRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                INSERT INTO search_runs (
                  monitoring_rule_id, platform, rule_name, max_results_per_term,
                  status, current_term_position, created_at, started_at, finished_at,
                  execution_start_term_position, search_protocol_version,
                  max_total_results, ordering, platform_access_snapshot_json
                ) VALUES (?, ?, ?, ?, 'queued', NULL, ?, NULL, NULL, 0, 2, ?, ?, ?)
                """,
                (
                    monitoring_rule_id,
                    platform,
                    rule_name,
                    max_results_per_term,
                    timestamp,
                    max_total_results,
                    ordering or ("latest" if platform == "wb" else "platform"),
                    _snapshot_json(
                        platform_access_snapshot
                        or PlatformAccessRepository(self._database).snapshot()
                    ),
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
                ((run_id, position, value) for position, value in enumerate(terms)),
            )
            return _read_run(connection, run_id)

    def collection_content_ids(self, run_id: int) -> set[str]:
        with _translate_storage_errors(), self._write_connection() as connection:
            _read_run(connection, run_id)
            return _collection_content_ids(connection, run_id)

    def collection_term_content_ids(self, run_id: int) -> dict[int, set[str]]:
        with _translate_storage_errors(), self._write_connection() as connection:
            _read_run(connection, run_id)
            return _collection_term_content_ids(connection, run_id)

    def mark_running(self, run_id: int) -> SearchRunRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET status = 'running', failure_reason = NULL, started_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (_utc_timestamp(), run_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, run_id)
            return _read_run(connection, run_id)

    def ensure_platform_access_snapshot(
        self, run_id: int, snapshot: PlatformAccessSnapshot
    ) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            connection.execute(
                """UPDATE search_runs
                   SET platform_access_snapshot_json=?
                   WHERE id=? AND platform_access_snapshot_json IS NULL""",
                (snapshot.model_dump_json(), run_id),
            )

    def set_access_waiting(self, run_id: int, value) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            connection.execute(
                "UPDATE search_runs SET access_wait_json=? WHERE id=?",
                (json.dumps(value, ensure_ascii=False) if value else None, run_id),
            )

    def set_access_notice(
        self, run_id: int, diagnostic: PlatformAccessDiagnostic | None
    ) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            connection.execute(
                "UPDATE search_runs SET access_notice_json=? WHERE id=?",
                (diagnostic.model_dump_json() if diagnostic else None, run_id),
            )

    def set_progress(self, run_id: int, term_position: int) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            run = _require_active_writer(connection, run_id)
            if run["search_protocol_version"] == 2 and run["max_total_results"] is None:
                current = run["current_term_position"]
                expected = (
                    run["execution_start_term_position"]
                    if current is None
                    else current + 1
                )
                if term_position != expected or (
                    current is not None
                    and connection.execute(
                        "SELECT 1 FROM search_run_term_completions WHERE run_id = ? "
                        "AND term_position = ?",
                        (run_id, current),
                    ).fetchone()
                    is None
                ):
                    raise SearchRunNotActiveError
            if (
                connection.execute(
                    "SELECT 1 FROM search_run_terms WHERE run_id = ? AND position = ?",
                    (run_id, term_position),
                ).fetchone()
                is None
            ):
                raise SearchRunNotActiveError
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET current_term_position = ?
                WHERE id = ? AND status = 'running'
                """,
                (term_position, run_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, run_id)

    def complete_term(self, run_id: int, term_position: int, item_count: int) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            run = _require_active_writer(connection, run_id)
            completed = connection.execute(
                "SELECT COUNT(*) FROM search_run_term_completions WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM search_run_content_terms WHERE run_id = ? AND "
                "term_position = ?",
                (run_id, term_position),
            ).fetchone()[0]
            if (
                run["search_protocol_version"] != 2
                or term_position != run["current_term_position"]
                or (
                    run["max_total_results"] is None
                    and term_position
                    != run["execution_start_term_position"] + completed
                )
                or type(item_count) is not int
                or item_count != count
                or not 0
                <= item_count
                <= (run["max_total_results"] or run["max_results_per_term"])
            ):
                raise SearchRunNotActiveError
            timestamp = _utc_timestamp()
            connection.execute(
                """INSERT INTO search_run_term_completions
                   (run_id, term_position, proof, result_count, completed_at,
                   recorded_at)
                   VALUES (?, ?, 'worker_term_completed', ?, ?, ?)""",
                (run_id, term_position, item_count, timestamp, timestamp),
            )

    def record_incomplete_terms(
        self,
        run_id: int,
        diagnostics: Sequence[CollectorSearchTermDiagnostic],
    ) -> None:
        """Persist bounded omission-recovery outcomes before the run closes."""
        if not diagnostics:
            return
        with _translate_storage_errors(), self._write_connection() as connection:
            run = _require_active_writer(connection, run_id)
            for diagnostic in diagnostics:
                if (
                    type(diagnostic.position) is not int
                    or not 0 <= diagnostic.position < 20
                    or diagnostic.reason != "view_all_unresolved"
                    or type(diagnostic.result_count) is not int
                    or not 0
                    <= diagnostic.result_count
                    <= (run["max_total_results"] or run["max_results_per_term"])
                    or connection.execute(
                        "SELECT 1 FROM search_run_terms "
                        "WHERE run_id = ? AND position = ?",
                        (run_id, diagnostic.position),
                    ).fetchone()
                    is None
                    or connection.execute(
                        "SELECT 1 FROM search_run_term_completions WHERE run_id = ? "
                        "AND term_position = ?",
                        (run_id, diagnostic.position),
                    ).fetchone()
                    is None
                ):
                    raise SearchRunNotActiveError
                observed = connection.execute(
                    "SELECT COUNT(*) FROM search_run_content_terms WHERE run_id = ? "
                    "AND term_position = ?",
                    (run_id, diagnostic.position),
                ).fetchone()[0]
                if observed != diagnostic.result_count:
                    raise SearchRunNotActiveError
                connection.execute(
                    """INSERT OR IGNORE INTO search_run_term_diagnostics
                       (run_id, term_position, reason, result_count, recorded_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        diagnostic.position,
                        diagnostic.reason,
                        diagnostic.result_count,
                        _utc_timestamp(),
                    ),
                )

    def observe_item(
        self,
        *,
        run_id: int,
        term_position: int,
        item: SearchContentInput,
    ) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            active = _require_active_writer(connection, run_id)
            if active["search_protocol_version"] == 2 and (
                active["current_term_position"] != term_position
                or connection.execute(
                    "SELECT 1 FROM search_run_term_completions WHERE run_id = ? AND "
                    "term_position = ?",
                    (run_id, term_position),
                ).fetchone()
                is not None
            ):
                raise SearchRunNotActiveError
            platform = cast(SearchPlatform, str(active["platform"]))
            term = connection.execute(
                """
                SELECT 1 FROM search_run_terms
                WHERE run_id = ? AND position = ?
                """,
                (run_id, term_position),
            ).fetchone()
            if term is None:
                raise sqlite3.IntegrityError("invalid term position")

            if active["max_total_results"] is not None:
                admitted = _collection_content_ids(connection, run_id)
                if (
                    item.platform_content_id not in admitted
                    and len(admitted) >= active["max_total_results"]
                ):
                    raise SearchRunNotActiveError
            elif active["search_protocol_version"] == 2:
                admitted = _collection_term_content_ids(connection, run_id).get(
                    term_position, set()
                )
                if (
                    item.platform_content_id not in admitted
                    and len(admitted) >= active["max_results_per_term"]
                ):
                    raise SearchRunNotActiveError

            content_row = connection.execute(
                """
                SELECT id FROM search_contents
                WHERE platform = ? AND platform_content_id = ?
                """,
                (platform, item.platform_content_id),
            ).fetchone()
            created = content_row is None
            if created:
                hashtags_json, interaction_stats_json = _metadata_json(
                    item.hashtags, item.interaction_stats
                )
                cursor = connection.execute(
                    """
                    INSERT INTO search_contents (
                      platform, platform_content_id, content_type, title, snippet,
                      creator_hash, publisher_name, published_at_text, content_url,
                      first_seen_at, last_seen_at, hashtags_json,
                      interaction_stats_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        platform,
                        item.platform_content_id,
                        item.content_type,
                        item.title,
                        item.snippet,
                        item.creator_hash,
                        item.publisher_name,
                        item.published_at_text,
                        item.content_url,
                        item.observed_at,
                        item.observed_at,
                        hashtags_json,
                        interaction_stats_json,
                    ),
                )
                content_id = cursor.lastrowid
                if content_id is None:
                    raise sqlite3.DatabaseError("SQLite did not return a content ID")
            else:
                content_id = int(content_row["id"])
                hashtags_json, interaction_stats_json = _metadata_json(
                    item.hashtags, item.interaction_stats
                )
                connection.execute(
                    """
                    UPDATE search_contents
                    SET
                      content_type = CASE WHEN ? != '' THEN ? ELSE content_type END,
                      title = CASE WHEN ? != '' THEN ? ELSE title END,
                      snippet = CASE WHEN ? != '' THEN ? ELSE snippet END,
                      creator_hash = CASE WHEN ? != '' THEN ? ELSE creator_hash END,
                      publisher_name = CASE WHEN ? != '' THEN ? ELSE publisher_name END,
                      published_at_text = CASE
                        WHEN ? != '' THEN ? ELSE published_at_text
                      END,
                      content_url = CASE WHEN ? != '' THEN ? ELSE content_url END,
                      hashtags_json = CASE WHEN ? != '[]' THEN ? ELSE hashtags_json END,
                      interaction_stats_json = CASE
                        WHEN ? != '{}' THEN ? ELSE interaction_stats_json
                      END,
                      last_seen_at = MAX(last_seen_at, ?)
                    WHERE id = ?
                    """,
                    (
                        item.content_type,
                        item.content_type,
                        item.title,
                        item.title,
                        item.snippet,
                        item.snippet,
                        item.creator_hash,
                        item.creator_hash,
                        item.publisher_name,
                        item.publisher_name,
                        item.published_at_text,
                        item.published_at_text,
                        item.content_url,
                        item.content_url,
                        hashtags_json,
                        hashtags_json,
                        interaction_stats_json,
                        interaction_stats_json,
                        item.observed_at,
                        content_id,
                    ),
                )

            relationship = connection.execute(
                """
                SELECT discovery_kind FROM search_run_contents
                WHERE run_id = ? AND search_content_id = ?
                """,
                (run_id, content_id),
            ).fetchone()
            if relationship is None:
                connection.execute(
                    """
                    INSERT INTO search_run_contents (
                      run_id, search_content_id, discovery_kind,
                      first_observed_at, last_observed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        content_id,
                        "new" if created else "repeated",
                        item.observed_at,
                        item.observed_at,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE search_run_contents
                    SET last_observed_at = MAX(last_observed_at, ?)
                    WHERE run_id = ? AND search_content_id = ?
                    """,
                    (item.observed_at, run_id, content_id),
                )

            existing_term = connection.execute(
                """
                SELECT 1 FROM search_run_content_terms
                WHERE run_id = ? AND search_content_id = ? AND term_position = ?
                """,
                (run_id, content_id, term_position),
            ).fetchone()
            if existing_term is None:
                connection.execute(
                    """
                    INSERT INTO search_run_content_terms (
                      run_id, search_content_id, term_position, observed_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (run_id, content_id, term_position, item.observed_at),
                )
            if created:
                connection.execute(
                    """INSERT INTO content_analysis_claims
                       (content_id,eligibility_origin,discovery_run_id)
                       VALUES (?,'new',?)""",
                    (content_id, run_id),
                )

    def finish(
        self,
        run_id: int,
        status: SearchRunStatus,
        failure_reason: SearchFailureReason | None = None,
        execution_limit: ExecutionLimit | None = None,
    ) -> SearchRunRecord:
        if status in {"queued", "running"}:
            raise ValueError("terminal status required")
        if execution_limit is not None and (
            status != "timed_out"
            or execution_limit not in ("requests", "pages", "time")
        ):
            raise ValueError("execution limit requires timed_out status")
        if failure_reason is not None and (
            status != "structure_changed"
            or not is_search_failure_reason(failure_reason)
        ):
            raise ValueError("failure reason requires structure_changed status")
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET status = ?, failure_reason = ?, finished_at = ?,
                    execution_limit = ?, access_wait_json = NULL
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (status, failure_reason, _utc_timestamp(), execution_limit, run_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, run_id)
            return _read_run(connection, run_id)

    def get(self, run_id: int) -> SearchRunRecord:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                connection.execute("BEGIN")
                return _read_run(connection, run_id)
            finally:
                connection.close()

    def list(
        self, *, limit: int, before_id: int | None, standalone_only: bool = False
    ) -> tuple[tuple[SearchRunRecord, ...], int | None]:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                clauses: list[str] = []
                parameters: list[object] = []
                if before_id is not None:
                    clauses.append("runs.id < ?")
                    parameters.append(before_id)
                if standalone_only:
                    clauses.append(
                        "NOT EXISTS (SELECT 1 FROM search_batch_attempts AS attempts "
                        "WHERE attempts.search_run_id = runs.id)"
                    )
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                parameters.append(limit + 1)
                rows = connection.execute(
                    f"""
                    SELECT runs.id FROM search_runs AS runs{where}
                    ORDER BY runs.id DESC LIMIT ?
                    """,  # noqa: S608 - clauses are selected from fixed literals.
                    parameters,
                ).fetchall()
                selected = rows[:limit]
                records = tuple(
                    _read_run(connection, int(row["id"])) for row in selected
                )
                next_before_id = (
                    records[-1].id if len(rows) > limit and records else None
                )
                return records, next_before_id
            finally:
                connection.close()

    def list_results(
        self,
        *,
        run_id: int,
        kind: Literal["all", "new", "repeated"],
        limit: int,
        offset: int,
    ) -> tuple[tuple[SearchResultRecord, ...], int]:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                if (
                    connection.execute(
                        "SELECT 1 FROM search_runs WHERE id = ?", (run_id,)
                    ).fetchone()
                    is None
                ):
                    raise SearchRunNotFoundError
                parameters: list[object] = [run_id]
                kind_clause = ""
                if kind != "all":
                    kind_clause = " AND links.discovery_kind = ?"
                    parameters.append(kind)
                total_row = connection.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM search_run_contents AS links
                    WHERE links.run_id = ?{kind_clause}
                    """,  # noqa: S608 - clause is selected from a closed enum.
                    parameters,
                ).fetchone()
                parameters.extend((limit, offset))
                rows = connection.execute(
                    f"""
                    SELECT
                      contents.id, contents.platform, contents.platform_content_id,
                      contents.content_type, contents.title, contents.snippet,
                      contents.creator_hash, contents.publisher_name,
                      contents.published_at_text, contents.content_url,
                      contents.hashtags_json, contents.interaction_stats_json,
                      contents.first_seen_at, contents.last_seen_at,
                      links.discovery_kind, links.first_observed_at,
                      links.last_observed_at
                    FROM search_run_contents AS links
                    JOIN search_contents AS contents
                      ON contents.id = links.search_content_id
                    WHERE links.run_id = ?{kind_clause}
                    ORDER BY
                      CASE links.discovery_kind WHEN 'new' THEN 0 ELSE 1 END,
                      links.first_observed_at DESC,
                      contents.id ASC
                    LIMIT ? OFFSET ?
                    """,  # noqa: S608 - clause is selected from a closed enum.
                    parameters,
                ).fetchall()
                records = tuple(
                    _assemble_result(connection, run_id, row) for row in rows
                )
                return records, int(total_row["count"] if total_row else 0)
            finally:
                connection.close()

    def get_result_open_target(
        self, *, run_id: int, result_id: int
    ) -> SearchResultOpenTargetRecord:
        source = self.get_result_source(run_id=run_id, result_id=result_id)
        return SearchResultOpenTargetRecord(
            platform=source.platform,
            platform_content_id=source.platform_content_id,
            content_url=source.content_url,
            matched_terms=source.matched_terms,
        )

    def get_result_source(
        self, *, run_id: int, result_id: int
    ) -> SearchResultSourceRecord:
        """Prove the relation and read its ordered provenance in one snapshot."""
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                connection.execute("BEGIN")
                row = connection.execute(
                    """
                    SELECT contents.platform, contents.platform_content_id,
                      contents.content_type, contents.content_url,
                      contents.title, contents.snippet,
                      contents.publisher_name, contents.published_at_text,
                      contents.hashtags_json, contents.interaction_stats_json,
                      runs.platform AS run_platform,
                      (runs.status IN ('queued', 'running') OR EXISTS (
                        SELECT 1 FROM search_batch_attempts AS attempts
                        JOIN search_batches AS batches ON batches.id = attempts.batch_id
                        WHERE attempts.search_run_id = runs.id
                          AND batches.status IN (
                            'queued', 'running', 'paused_for_manual_action'
                          )
                      )) AS collection_active
                    FROM search_run_contents AS links
                    JOIN search_contents AS contents
                      ON contents.id = links.search_content_id
                    JOIN search_runs AS runs ON runs.id = links.run_id
                    WHERE links.run_id = ? AND contents.id = ?
                    """,
                    (run_id, result_id),
                ).fetchone()
                if row is None:
                    raise SearchResultNotFoundError
                if row["run_platform"] != row["platform"]:
                    raise sqlite3.DatabaseError("Search source platform mismatch")
                term_rows = connection.execute(
                    """
                    SELECT terms.value
                    FROM search_run_content_terms AS matches
                    JOIN search_run_terms AS terms
                      ON terms.run_id = matches.run_id
                     AND terms.position = matches.term_position
                    WHERE matches.run_id = ? AND matches.search_content_id = ?
                    ORDER BY matches.term_position ASC
                    """,
                    (run_id, result_id),
                ).fetchall()
                matched_terms = tuple(str(term["value"]) for term in term_rows)
                if not matched_terms:
                    raise sqlite3.DatabaseError("Search result has no matched terms")
                hashtags, interaction_stats = _metadata_from_row(row)
                return SearchResultSourceRecord(
                    run_id=run_id,
                    result_id=result_id,
                    platform=cast(SearchPlatform, str(row["platform"])),
                    platform_content_id=str(row["platform_content_id"]),
                    content_type=str(row["content_type"]),
                    content_url=str(row["content_url"]),
                    title=str(row["title"]),
                    snippet=str(row["snippet"]),
                    matched_terms=matched_terms,
                    collection_active=bool(row["collection_active"]),
                    publisher_name=str(row["publisher_name"]),
                    published_at_text=str(row["published_at_text"]),
                    hashtags=hashtags,
                    interaction_stats=interaction_stats,
                )
            finally:
                connection.close()

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


def _read_run(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    allow_empty_terms: bool = False,
) -> SearchRunRecord:
    row = connection.execute(
        """
        SELECT
          runs.*,
          SUM(CASE WHEN links.discovery_kind = 'new' THEN 1 ELSE 0 END) AS new_count,
          SUM(CASE WHEN links.discovery_kind = 'repeated' THEN 1 ELSE 0 END)
            AS repeated_count,
          COUNT(links.search_content_id) AS total_count
        FROM search_runs AS runs
        LEFT JOIN search_run_contents AS links ON links.run_id = runs.id
        WHERE runs.id = ?
        GROUP BY runs.id
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise SearchRunNotFoundError
    term_rows = connection.execute(
        """
        SELECT value FROM search_run_terms
        WHERE run_id = ? ORDER BY position ASC
        """,
        (run_id,),
    ).fetchall()
    terms = tuple(str(term["value"]) for term in term_rows)
    if not terms and not allow_empty_terms:
        raise sqlite3.DatabaseError("Search run has no terms")
    diagnostic_rows = connection.execute(
        """
        SELECT diagnostics.term_position, terms.value, diagnostics.reason,
               diagnostics.result_count
        FROM search_run_term_diagnostics AS diagnostics
        JOIN search_run_terms AS terms
          ON terms.run_id = diagnostics.run_id
         AND terms.position = diagnostics.term_position
        WHERE diagnostics.run_id = ?
        ORDER BY diagnostics.term_position ASC
        """,
        (run_id,),
    ).fetchall()
    incomplete_terms = tuple(
        CollectorSearchTermDiagnostic(
            position=int(row["term_position"]),
            reason=str(row["reason"]),  # type: ignore[arg-type]
            result_count=int(row["result_count"]),
        )
        for row in diagnostic_rows
    )
    failure_reason = row["failure_reason"]
    if failure_reason is not None and not is_search_failure_reason(failure_reason):
        raise sqlite3.DatabaseError("Search run has an unknown failure reason")
    return SearchRunRecord(
        id=int(row["id"]),
        monitoring_rule_id=(
            int(row["monitoring_rule_id"])
            if row["monitoring_rule_id"] is not None
            else None
        ),
        platform=cast(SearchPlatform, str(row["platform"])),
        rule_name=str(row["rule_name"]),
        terms=terms,
        max_results_per_term=int(row["max_results_per_term"]),
        max_total_results=row["max_total_results"],
        status=str(row["status"]),  # type: ignore[arg-type]
        current_term_position=(
            int(row["current_term_position"])
            if row["current_term_position"] is not None
            else None
        ),
        new_count=int(row["new_count"] or 0),
        repeated_count=int(row["repeated_count"] or 0),
        total_count=int(row["total_count"] or 0),
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
        failure_reason=cast(SearchFailureReason | None, failure_reason),
        execution_start_term_position=int(row["execution_start_term_position"]),
        search_protocol_version=int(row["search_protocol_version"]),
        execution_limit=cast(ExecutionLimit | None, row["execution_limit"]),
        incomplete_terms=incomplete_terms,
        ordering=cast(SearchRunOrdering, str(row["ordering"])),
        platform_access_snapshot=_decode_snapshot(row["platform_access_snapshot_json"]),
        access_waiting=bool(row["access_wait_json"]),
        access_notice=_decode_access_notice(row["access_notice_json"]),
    )


def _assemble_result(
    connection: sqlite3.Connection, run_id: int, row: sqlite3.Row
) -> SearchResultRecord:
    term_rows = connection.execute(
        """
        SELECT terms.value
        FROM search_run_content_terms AS matches
        JOIN search_run_terms AS terms
          ON terms.run_id = matches.run_id
         AND terms.position = matches.term_position
        WHERE matches.run_id = ? AND matches.search_content_id = ?
        ORDER BY matches.term_position ASC
        """,
        (run_id, int(row["id"])),
    ).fetchall()
    return assemble_result(row, tuple(str(term["value"]) for term in term_rows))


def assemble_result(
    row: sqlite3.Row, matched_terms: tuple[str, ...]
) -> SearchResultRecord:
    """Share the safe normalized projection with batch-wide result queries."""
    hashtags, interaction_stats = _metadata_from_row(row)
    return SearchResultRecord(
        id=int(row["id"]),
        platform=cast(SearchPlatform, str(row["platform"])),
        platform_content_id=str(row["platform_content_id"]),
        content_type=str(row["content_type"]),
        title=str(row["title"]),
        snippet=str(row["snippet"]),
        creator_hash=str(row["creator_hash"]),
        publisher_name=str(row["publisher_name"]),
        published_at_text=str(row["published_at_text"]),
        content_url=str(row["content_url"]),
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
        discovery_kind=str(row["discovery_kind"]),  # type: ignore[arg-type]
        first_observed_at=str(row["first_observed_at"]),
        last_observed_at=str(row["last_observed_at"]),
        matched_terms=matched_terms,
        hashtags=hashtags,
        interaction_stats=interaction_stats,
    )


def _collection_content_ids(connection: sqlite3.Connection, run_id: int) -> set[str]:
    rows = connection.execute(
        """SELECT DISTINCT contents.platform_content_id
           FROM search_run_contents links
           JOIN search_contents contents ON contents.id=links.search_content_id
           WHERE links.run_id=? OR links.run_id IN (
             SELECT sibling.search_run_id FROM search_batch_attempts current
             JOIN search_batch_attempts sibling ON sibling.batch_id=current.batch_id
               AND sibling.item_position=current.item_position
             WHERE current.search_run_id=?
           )""",
        (run_id, run_id),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _collection_term_content_ids(
    connection: sqlite3.Connection, run_id: int
) -> dict[int, set[str]]:
    rows = connection.execute(
        """SELECT DISTINCT links.term_position, contents.platform_content_id
           FROM search_run_content_terms links
           JOIN search_contents contents ON contents.id=links.search_content_id
           WHERE links.run_id=? OR links.run_id IN (
             SELECT sibling.search_run_id FROM search_batch_attempts current
             JOIN search_batch_attempts sibling ON sibling.batch_id=current.batch_id
               AND sibling.item_position=current.item_position
             WHERE current.search_run_id=?
           )""",
        (run_id, run_id),
    ).fetchall()
    result: dict[int, set[str]] = {}
    for row in rows:
        result.setdefault(int(row[0]), set()).add(str(row[1]))
    return result


def _require_active_writer(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM search_runs WHERE id = ? AND status = 'running'", (run_id,)
    ).fetchone()
    if row is None:
        _raise_missing_or_inactive(connection, run_id)
    attempt = connection.execute(
        """SELECT batches.status AS batch_status, items.status AS item_status,
                  attempts.attempt_number, (
                    SELECT MAX(a.attempt_number) FROM search_batch_attempts AS a
                    WHERE a.batch_id = attempts.batch_id AND a.item_position =
                    attempts.item_position
                  ) AS latest
           FROM search_batch_attempts AS attempts
           JOIN search_batches AS batches ON batches.id = attempts.batch_id
           JOIN search_batch_items AS items ON items.batch_id = attempts.batch_id
             AND items.position = attempts.item_position
           WHERE attempts.search_run_id = ?""",
        (run_id,),
    ).fetchone()
    if attempt is not None and (
        attempt["batch_status"] != "running"
        or attempt["item_status"] != "running"
        or attempt["attempt_number"] != attempt["latest"]
    ):
        raise SearchRunNotActiveError
    return row


def _raise_missing_or_inactive(connection: sqlite3.Connection, run_id: int) -> None:
    if (
        connection.execute(
            "SELECT 1 FROM search_runs WHERE id = ?", (run_id,)
        ).fetchone()
        is None
    ):
        raise SearchRunNotFoundError
    raise SearchRunNotActiveError


@contextmanager
def _translate_storage_errors() -> Iterator[None]:
    try:
        yield
    except (
        SearchResultNotFoundError,
        SearchRunNotFoundError,
        SearchRunNotActiveError,
    ):
        raise
    except (OSError, sqlite3.Error):
        raise SearchRunRepositoryUnavailableError from None


def _decode_snapshot(value):
    if not value:
        return default_platform_access_snapshot(basis="legacy_unavailable")
    try:
        return PlatformAccessSnapshot.model_validate_json(value)
    except (TypeError, ValueError):
        return default_platform_access_snapshot(basis="legacy_unavailable")


def _snapshot_json(value: PlatformAccessSnapshot) -> str:
    return value.model_dump_json()


def _decode_access_notice(value):
    if not value:
        return None
    try:
        return PlatformAccessDiagnostic.model_validate_json(value)
    except (TypeError, ValueError):
        return None


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
