"""v34: seed the text-only initial-understanding prompt.

The prompt rows are immutable history.  Keep the previous default row for old
jobs and add the new code-owned default so future admissions cannot reuse the
pre-scope-switch media prompt.
"""

from __future__ import annotations

import hashlib
import sqlite3

from opinion_workbench_api.repositories.analysis_shared import timestamp
from opinion_workbench_api.schemas.analysis_settings import (
    DEFAULT_INITIAL_INSTRUCTIONS,
    INITIAL_SCHEMA_VERSION,
)


def migrate(connection: sqlite3.Connection) -> None:
    digest = hashlib.sha256(DEFAULT_INITIAL_INSTRUCTIONS.encode("utf-8")).hexdigest()
    rows = connection.execute(
        """SELECT instructions FROM analysis_prompt_versions
           WHERE stage='initial' AND schema_version=? AND content_hash=?""",
        (INITIAL_SCHEMA_VERSION, digest),
    ).fetchall()
    if rows:
        if any(row[0] != DEFAULT_INITIAL_INSTRUCTIONS for row in rows):
            raise sqlite3.DatabaseError("Initial prompt hash collision")
        return
    connection.execute(
        """INSERT INTO analysis_prompt_versions(
           stage,instructions,content_hash,schema_version,created_at)
           VALUES ('initial', ?, ?, ?, ?)""",
        (DEFAULT_INITIAL_INSTRUCTIONS, digest, INITIAL_SCHEMA_VERSION, timestamp()),
    )
