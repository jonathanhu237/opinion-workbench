"""Add immutable report and platform-pacing snapshots.

The migration is additive apart from rebuilding the batch-item table so a
platform rate-limit pause can be represented distinctly from a failed attempt.
No historical result, input, or report is rewritten into a new success state.
"""

import json
from datetime import UTC, datetime

from longtian_api.search_platforms import SEARCH_PLATFORMS


def migrate(connection):
    now = datetime.now(UTC).isoformat()
    intervals = json.dumps(
        {platform: 5 for platform in SEARCH_PLATFORMS},
        ensure_ascii=False,
        sort_keys=True,
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS platform_access_settings (
          id INTEGER PRIMARY KEY CHECK (id=1),
          revision INTEGER NOT NULL CHECK (revision>0),
          interval_seconds_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """INSERT OR IGNORE INTO platform_access_settings
          (id,revision,interval_seconds_json,updated_at) VALUES (1,1,?,?)""",
        (intervals, now),
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS platform_access_state (
          platform TEXT PRIMARY KEY CHECK (platform IN
            ('wb','dy','ks','xhs','toutiao')),
          last_access_started_at TEXT,
          earliest_next_allowed_at TEXT,
          blocked_until TEXT,
          diagnostic_json TEXT,
          updated_at TEXT NOT NULL
        )"""
    )
    _add_column(
        connection,
        "platform_access_state",
        "earliest_next_allowed_at TEXT",
    )
    for platform in SEARCH_PLATFORMS:
        connection.execute(
            """INSERT OR IGNORE INTO platform_access_state
              (platform,last_access_started_at,earliest_next_allowed_at,
               blocked_until,diagnostic_json,updated_at)
              VALUES (?,NULL,NULL,NULL,NULL,?)""",
            (platform, now),
        )

    _add_column(
        connection,
        "search_batches",
        "platform_access_snapshot_json TEXT",
    )
    _add_column(
        connection,
        "search_runs",
        "platform_access_snapshot_json TEXT",
    )
    _add_column(connection, "search_runs", "access_wait_json TEXT")
    _add_column(connection, "search_runs", "access_notice_json TEXT")
    _add_column(
        connection,
        "content_analysis_jobs",
        "summary_concurrency INTEGER NOT NULL DEFAULT 1 "
        "CHECK(summary_concurrency IN (1,2,4,8,16))",
    )
    _add_column(
        connection,
        "content_analysis_jobs",
        "platform_access_snapshot_json TEXT",
    )
    _add_column(connection, "content_analysis_jobs", "access_wait_json TEXT")
    _add_column(connection, "content_analysis_jobs", "access_notice_json TEXT")
    _add_column(
        connection,
        "content_analysis_jobs",
        "model_retry_notice_json TEXT",
    )
    _add_column(
        connection,
        "content_analysis_attempts",
        "rate_limit_attempts_json TEXT",
    )
    _add_column(
        connection,
        "topic_report_runs",
        "model_retry_notice_json TEXT",
    )
    _add_column(
        connection,
        "topic_report_nodes",
        "rate_limit_attempts_json TEXT",
    )
    _add_column(
        connection,
        "report_generations",
        "last_access_notice_json TEXT",
    )

    # v10's original CHECK only allowed attempt_failed and process_interrupted.
    # Rebuild just this small projection while preserving every row and its
    # composite identity. Child tables are temporarily renamed while foreign
    # keys are disabled by the database migration wrapper.
    _rebuild_batch_items(connection)

    # A historical active row may have no snapshot. Permit exactly one
    # null-to-snapshot materialization during recovery, while preserving
    # immutability for every already-admitted value.
    connection.execute("DROP TRIGGER IF EXISTS content_analysis_snapshot_immutable")
    connection.execute("DROP TRIGGER IF EXISTS search_run_access_snapshot_immutable")
    connection.execute("DROP TRIGGER IF EXISTS search_batch_access_snapshot_immutable")
    connection.execute(
        """CREATE TRIGGER content_analysis_snapshot_immutable
          BEFORE UPDATE OF summary_concurrency,platform_access_snapshot_json
          ON content_analysis_jobs
          WHEN (NEW.summary_concurrency IS NOT OLD.summary_concurrency
                OR (NEW.platform_access_snapshot_json IS NOT
                    OLD.platform_access_snapshot_json
                    AND OLD.platform_access_snapshot_json IS NOT NULL))
          BEGIN SELECT RAISE(ABORT, 'immutable analysis execution snapshot'); END"""
    )
    connection.execute(
        """CREATE TRIGGER search_run_access_snapshot_immutable
          BEFORE UPDATE OF platform_access_snapshot_json ON search_runs
          WHEN NEW.platform_access_snapshot_json IS NOT
               OLD.platform_access_snapshot_json
            AND OLD.platform_access_snapshot_json IS NOT NULL
          BEGIN SELECT RAISE(ABORT, 'immutable search access snapshot'); END"""
    )
    connection.execute(
        """CREATE TRIGGER search_batch_access_snapshot_immutable
          BEFORE UPDATE OF platform_access_snapshot_json ON search_batches
          WHEN NEW.platform_access_snapshot_json IS NOT
               OLD.platform_access_snapshot_json
            AND OLD.platform_access_snapshot_json IS NOT NULL
          BEGIN SELECT RAISE(ABORT, 'immutable batch access snapshot'); END"""
    )


def _add_column(connection, table: str, definition: str) -> None:
    columns = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    name = definition.split()[0]
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _rebuild_batch_items(connection):
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(search_batch_items)")
    }
    if "pause_reason" not in columns:
        return
    # Avoid a second rebuild if a partially upgraded temporary fixture already
    # has the new constraint; SQLite offers no portable CHECK introspection.
    existing = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='search_batch_items'"
    ).fetchone()
    if existing is None or "platform_blocked_or_rate_limited" in (existing[0] or ""):
        return

    connection.execute(
        "ALTER TABLE search_batch_attempts RENAME TO search_batch_attempts_v39"
    )
    connection.execute(
        "ALTER TABLE search_batch_recoveries RENAME TO search_batch_recoveries_v39"
    )
    connection.execute(
        """CREATE TABLE search_batch_items_v39 (
          batch_id INTEGER NOT NULL REFERENCES search_batches(id) ON DELETE CASCADE,
          position INTEGER NOT NULL CHECK (position >= 0),
          platform TEXT NOT NULL CHECK (platform IN ('toutiao','wb','ks','dy','xhs')),
          status TEXT NOT NULL CHECK (status IN ('queued','running',
            'paused_for_manual_action','completed','failed','cancelled','skipped')),
          created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
          pause_reason TEXT CHECK (pause_reason IN
            ('attempt_failed','process_interrupted','platform_blocked_or_rate_limited')),
          completion_basis TEXT CHECK (completion_basis IN
            ('attempt_success','confirmed_terms')),
          PRIMARY KEY (batch_id, position), UNIQUE (batch_id, platform)
        )"""
    )
    connection.execute(
        """INSERT INTO search_batch_items_v39
          SELECT batch_id,position,platform,status,created_at,started_at,finished_at,
                 pause_reason,completion_basis FROM search_batch_items"""
    )
    connection.execute("DROP TABLE search_batch_items")
    connection.execute(
        "ALTER TABLE search_batch_items_v39 RENAME TO search_batch_items"
    )
    connection.execute(
        "ALTER TABLE search_batch_attempts_v39 RENAME TO search_batch_attempts"
    )
    connection.execute(
        "ALTER TABLE search_batch_recoveries_v39 RENAME TO search_batch_recoveries"
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS ix_search_batch_attempts_item
          ON search_batch_attempts(batch_id,item_position,attempt_number DESC)"""
    )
