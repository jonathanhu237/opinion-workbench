"""Print hashes of the v9 search relations in an explicitly isolated fixture DB."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["LEGACY_RECOVERY_DATABASE"]).resolve()
assert path.is_relative_to(Path("/tmp/longtian-recovery-validation.EcUhyX"))
assert path.is_file()
tables = (
    "search_batches",
    "search_batch_terms",
    "search_batch_items",
    "search_batch_attempts",
    "search_runs",
    "search_run_terms",
    "search_contents",
    "search_run_contents",
    "search_run_content_terms",
)
additions = {
    "control_revision",
    "execution_start_term_position",
    "search_protocol_version",
    "pause_reason",
    "completion_basis",
}
snapshot = {}
with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
    for table in tables:
        columns = [
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})")
            if row[1] not in additions
        ]
        assert columns and all(name.replace("_", "").isalnum() for name in columns)
        projection = ",".join(f'"{name}"' for name in columns)
        rows = connection.execute(
            f"SELECT {projection} FROM {table} ORDER BY {projection}"
        ).fetchall()
        digest = hashlib.sha256(
            json.dumps([columns, rows], ensure_ascii=True).encode()
        ).hexdigest()
        snapshot[table] = {"count": len(rows), "sha256": digest}
print(json.dumps(snapshot, sort_keys=True))
