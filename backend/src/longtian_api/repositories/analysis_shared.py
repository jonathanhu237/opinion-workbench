"""Single transaction and frozen-source boundary for the new analysis families."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import ValidationError

from longtian_api.database import Database
from longtian_api.schemas.analysis_evidence import AnalysisSource
from longtian_api.services.analysis_errors import AnalysisError


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class AnalysisRepository:
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
        except (sqlite3.Error, ValidationError, ValueError, TypeError, KeyError):
            raise AnalysisError("analysis_storage_unavailable") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()


SOURCE_ACTIVE_SQL = """(r.status IN ('queued','running') OR EXISTS (
    SELECT 1 FROM search_batch_attempts ba JOIN search_batches b ON b.id=ba.batch_id
    WHERE ba.search_run_id=r.id AND b.status IN
      ('queued','running','paused_for_manual_action')))
"""


def source_snapshot(
    connection: sqlite3.Connection, content_id: int
) -> tuple[AnalysisSource, sqlite3.Row]:
    row = connection.execute(
        f"""SELECT c.*,r.id AS source_run_id,{SOURCE_ACTIVE_SQL} AS collection_active
          FROM search_contents c JOIN search_run_contents l ON l.search_content_id=c.id
          JOIN search_runs r ON r.id=l.run_id AND r.platform=c.platform
          WHERE c.id=? AND EXISTS(SELECT 1 FROM search_run_content_terms m
            JOIN search_run_terms t ON t.run_id=m.run_id AND t.position=m.term_position
            WHERE m.run_id=r.id AND m.search_content_id=c.id)
          ORDER BY collection_active,r.id LIMIT 1""",
        (content_id,),
    ).fetchone()
    if row is None:
        raise AnalysisError("result_not_found")
    terms = [
        r[0]
        for r in connection.execute(
            """SELECT t.value FROM search_run_content_terms m JOIN search_run_terms t
          ON t.run_id=m.run_id AND t.position=m.term_position
          WHERE m.run_id=? AND m.search_content_id=? ORDER BY m.term_position""",
            (row["source_run_id"], content_id),
        )
    ]
    source = AnalysisSource(
        source_run_id=row["source_run_id"],
        result_id=content_id,
        platform=row["platform"],
        platform_content_id=row["platform_content_id"],
        content_type=row["content_type"],
        title=row["title"],
        snippet=row["snippet"],
        content_url=row["content_url"],
        published_at_text=row["published_at_text"],
        matched_terms=terms,
    )
    return source, row
