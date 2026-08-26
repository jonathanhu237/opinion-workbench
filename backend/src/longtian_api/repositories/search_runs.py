"""SQLite repository for durable product search runs and discoveries."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from longtian_api.database import Database
from longtian_api.search_platforms import SearchPlatform

SearchRunStatus = Literal[
    "queued",
    "running",
    "completed_with_results",
    "completed_empty",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "timed_out",
    "cancelled",
    "internal_error",
]
DiscoveryKind = Literal["new", "repeated"]


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


@dataclass(frozen=True, slots=True)
class SearchResultOpenTargetRecord:
    platform: SearchPlatform
    platform_content_id: str
    matched_terms: tuple[str, ...]


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
                SET status = 'internal_error', finished_at = ?
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
    ) -> SearchRunRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            timestamp = _utc_timestamp()
            cursor = connection.execute(
                """
                INSERT INTO search_runs (
                  monitoring_rule_id, platform, rule_name, max_results_per_term,
                  status, current_term_position, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, 'queued', NULL, ?, NULL, NULL)
                """,
                (
                    monitoring_rule_id,
                    platform,
                    rule_name,
                    max_results_per_term,
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
                ((run_id, position, value) for position, value in enumerate(terms)),
            )
            return _read_run(connection, run_id)

    def mark_running(self, run_id: int) -> SearchRunRecord:
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (_utc_timestamp(), run_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, run_id)
            return _read_run(connection, run_id)

    def set_progress(self, run_id: int, term_position: int) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
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

    def observe_item(
        self,
        *,
        run_id: int,
        term_position: int,
        item: SearchContentInput,
    ) -> None:
        with _translate_storage_errors(), self._write_connection() as connection:
            active = connection.execute(
                """
                SELECT platform FROM search_runs
                WHERE id = ? AND status = 'running'
                """,
                (run_id,),
            ).fetchone()
            if active is None:
                _raise_missing_or_inactive(connection, run_id)
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

            content_row = connection.execute(
                """
                SELECT id FROM search_contents
                WHERE platform = ? AND platform_content_id = ?
                """,
                (platform, item.platform_content_id),
            ).fetchone()
            created = content_row is None
            if created:
                cursor = connection.execute(
                    """
                    INSERT INTO search_contents (
                      platform, platform_content_id, content_type, title, snippet,
                      creator_hash, publisher_name, published_at_text, content_url,
                      first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                content_id = cursor.lastrowid
                if content_id is None:
                    raise sqlite3.DatabaseError("SQLite did not return a content ID")
            else:
                content_id = int(content_row["id"])
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

    def finish(self, run_id: int, status: SearchRunStatus) -> SearchRunRecord:
        if status in {"queued", "running"}:
            raise ValueError("terminal status required")
        with _translate_storage_errors(), self._write_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE search_runs
                SET status = ?, finished_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (status, _utc_timestamp(), run_id),
            )
            if cursor.rowcount == 0:
                _raise_missing_or_inactive(connection, run_id)
            return _read_run(connection, run_id)

    def get(self, run_id: int) -> SearchRunRecord:
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
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
        with _translate_storage_errors():
            connection = self._database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT contents.platform, contents.platform_content_id
                    FROM search_run_contents AS links
                    JOIN search_contents AS contents
                      ON contents.id = links.search_content_id
                    WHERE links.run_id = ? AND contents.id = ?
                    """,
                    (run_id, result_id),
                ).fetchone()
                if row is None:
                    raise SearchResultNotFoundError
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
                return SearchResultOpenTargetRecord(
                    platform=cast(SearchPlatform, str(row["platform"])),
                    platform_content_id=str(row["platform_content_id"]),
                    matched_terms=matched_terms,
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


def _read_run(connection: sqlite3.Connection, run_id: int) -> SearchRunRecord:
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
    if not terms:
        raise sqlite3.DatabaseError("Search run has no terms")
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
        matched_terms=tuple(str(term["value"]) for term in term_rows),
    )


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


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
