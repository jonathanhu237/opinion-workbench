"""v18: freeze the two prompt choices on every automation task.

The first automation schema stored one mutable ``analysis_goal`` string.  v18
keeps that column as a private compatibility mirror, while adding immutable
prompt-version references and explicit default/custom modes.  Existing tasks
are backfilled from the prompt that was effective at migration time; their
history is never rewritten.
"""

import hashlib
import sqlite3
from datetime import UTC, datetime

from opinion_workbench_api.schemas.analysis_settings import (
    DEFAULT_INITIAL_INSTRUCTIONS,
    DEFAULT_REPORT_INSTRUCTIONS,
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)

# SQL constraints are intentionally kept readable as schema-shaped blocks.
# ruff: noqa: E501


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _prompt(
    connection: sqlite3.Connection,
    *,
    stage: str,
    instructions: str,
    schema_version: str,
    mode: str,
) -> int:
    digest = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
    rows = connection.execute(
        """SELECT id,instructions FROM analysis_prompt_versions
           WHERE stage=? AND schema_version=? AND content_hash=? ORDER BY id""",
        (stage, schema_version, digest),
    ).fetchall()
    if rows:
        # Treat a collision as corruption even if a matching row is also
        # present.  Returning the first matching row would make the outcome
        # depend on insertion order and leave an ambiguous immutable catalog.
        if any(row["instructions"] != instructions for row in rows):
            raise sqlite3.DatabaseError("prompt hash collision during v18 migration")
        return int(rows[0]["id"])
    cursor = connection.execute(
        """INSERT INTO analysis_prompt_versions(
          stage,instructions,content_hash,schema_version,created_at)
          VALUES (?,?,?,?,?)""",
        (stage, instructions, digest, schema_version, _now()),
    )
    return int(cursor.lastrowid)


def migrate(connection: sqlite3.Connection) -> None:
    """Add prompt-choice columns and backfill every existing task."""

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(automation_tasks)")
    }
    if "initial_prompt_mode" not in columns:
        connection.execute(
            """ALTER TABLE automation_tasks ADD COLUMN initial_prompt_mode TEXT
               NOT NULL DEFAULT 'custom'
               CHECK(initial_prompt_mode IN ('default','custom'))"""
        )
    if "initial_prompt_version_id" not in columns:
        connection.execute(
            """ALTER TABLE automation_tasks ADD COLUMN initial_prompt_version_id
               INTEGER REFERENCES analysis_prompt_versions(id)"""
        )
    if "report_prompt_mode" not in columns:
        connection.execute(
            """ALTER TABLE automation_tasks ADD COLUMN report_prompt_mode TEXT
               NOT NULL DEFAULT 'custom'
               CHECK(report_prompt_mode IN ('default','custom'))"""
        )
    if "report_prompt_version_id" not in columns:
        connection.execute(
            """ALTER TABLE automation_tasks ADD COLUMN report_prompt_version_id
               INTEGER REFERENCES analysis_prompt_versions(id)"""
        )

    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(content_analysis_jobs)")
    }
    if "initial_prompt_mode" not in job_columns:
        connection.execute(
            """ALTER TABLE content_analysis_jobs ADD COLUMN initial_prompt_mode TEXT
               NOT NULL DEFAULT 'custom'
               CHECK(initial_prompt_mode IN ('default','custom','legacy'))"""
        )
    if "report_prompt_mode" not in job_columns:
        connection.execute(
            """ALTER TABLE content_analysis_jobs ADD COLUMN report_prompt_mode TEXT
               NOT NULL DEFAULT 'custom'
               CHECK(report_prompt_mode IN ('default','custom','legacy'))"""
        )

    settings = connection.execute(
        """SELECT initial_prompt_version_id,report_prompt_version_id
           FROM analysis_settings WHERE id=1"""
    ).fetchone()
    if settings is None:
        raise sqlite3.DatabaseError("analysis settings missing during v18 migration")
    initial_row = connection.execute(
        "SELECT instructions FROM analysis_prompt_versions WHERE id=?",
        (settings["initial_prompt_version_id"],),
    ).fetchone()
    if initial_row is None:
        raise sqlite3.DatabaseError("initial prompt missing during v18 migration")

    # Capture the old shared initial prompt before resetting the settings
    # pointers.  If it was a custom immutable version, every task receives
    # that exact historical version; otherwise it receives the code-owned
    # default row.
    initial_instructions = str(initial_row["instructions"])
    initial_is_default = initial_instructions == DEFAULT_INITIAL_INSTRUCTIONS
    canonical_initial_id = _prompt(
        connection,
        stage="initial",
        instructions=DEFAULT_INITIAL_INSTRUCTIONS,
        schema_version=INITIAL_SCHEMA_VERSION,
        mode="default",
    )
    canonical_report_id = _prompt(
        connection,
        stage="report",
        instructions=DEFAULT_REPORT_INSTRUCTIONS,
        schema_version=REPORT_SCHEMA_VERSION,
        mode="default",
    )
    initial_id = _prompt(
        connection,
        stage="initial",
        instructions=DEFAULT_INITIAL_INSTRUCTIONS
        if initial_is_default
        else initial_instructions,
        schema_version=INITIAL_SCHEMA_VERSION,
        mode="default" if initial_is_default else "custom",
    )

    connection.execute(
        """UPDATE analysis_settings
           SET initial_prompt_version_id=?,report_prompt_version_id=?
           WHERE id=1""",
        (canonical_initial_id, canonical_report_id),
    )

    # A database can be reopened through an older migration path during a
    # repair; remove the prior v18 snapshot guard before filling the additive
    # mode columns again.
    connection.execute("DROP TRIGGER IF EXISTS analysis_job_snapshot_immutable")
    # v17's tombstone guard predates the new prompt columns.  Temporarily drop
    # it while backfilling deleted rows, then recreate the complete guard after
    # all task rows have their immutable prompt references.
    connection.execute("DROP TRIGGER IF EXISTS automation_task_deleted_immutable")

    for row in connection.execute(
        """SELECT j.id,pi.instructions AS initial_instructions,
                  pr.instructions AS report_instructions
           FROM content_analysis_jobs j
           JOIN analysis_prompt_versions pi ON pi.id=j.initial_prompt_version_id
           JOIN analysis_prompt_versions pr ON pr.id=j.report_prompt_version_id
           ORDER BY j.id"""
    ).fetchall():
        connection.execute(
            """UPDATE content_analysis_jobs SET initial_prompt_mode=?,
                      report_prompt_mode=? WHERE id=?""",
            (
                "default"
                if row["initial_instructions"] == DEFAULT_INITIAL_INSTRUCTIONS
                else "legacy",
                "default"
                if row["report_instructions"] == DEFAULT_REPORT_INSTRUCTIONS
                else "legacy",
                row["id"],
            ),
        )

    # Job prompt source is part of its immutable request snapshot.  Existing
    # v12 triggers cannot mention columns added later, so replace that guard
    # and validate both source modes/references for new writes as well.
    connection.execute("DROP TRIGGER IF EXISTS analysis_job_prompt_insert")
    connection.execute("DROP TRIGGER IF EXISTS analysis_job_prompt_update")
    connection.execute(
        f"""CREATE TRIGGER analysis_job_prompt_insert
           BEFORE INSERT ON content_analysis_jobs
           WHEN NEW.initial_prompt_version_id IS NULL
             OR NEW.report_prompt_version_id IS NULL
             OR NEW.initial_prompt_mode NOT IN ('default','custom','legacy')
             OR NEW.report_prompt_mode NOT IN ('default','custom','legacy')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.initial_prompt_version_id AND p.stage='initial'
                 AND p.schema_version='{INITIAL_SCHEMA_VERSION}')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id AND p.stage='report'
                 AND p.schema_version='{REPORT_SCHEMA_VERSION}')
             OR (NEW.initial_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.initial_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_initial_id})))
             OR (NEW.report_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.report_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_report_id})))
           BEGIN
             SELECT RAISE(ABORT, 'analysis job prompt choice is invalid');
           END"""
    )
    connection.execute(
        f"""CREATE TRIGGER analysis_job_prompt_update
           BEFORE UPDATE OF initial_prompt_mode,initial_prompt_version_id,
             report_prompt_mode,report_prompt_version_id ON content_analysis_jobs
           WHEN NEW.initial_prompt_version_id IS NULL
             OR NEW.report_prompt_version_id IS NULL
             OR NEW.initial_prompt_mode NOT IN ('default','custom','legacy')
             OR NEW.report_prompt_mode NOT IN ('default','custom','legacy')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.initial_prompt_version_id AND p.stage='initial'
                 AND p.schema_version='{INITIAL_SCHEMA_VERSION}')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id AND p.stage='report'
                 AND p.schema_version='{REPORT_SCHEMA_VERSION}')
             OR (NEW.initial_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.initial_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_initial_id})))
             OR (NEW.report_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.report_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_report_id})))
           BEGIN
             SELECT RAISE(ABORT, 'analysis job prompt choice is invalid');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER analysis_job_snapshot_immutable
           BEFORE UPDATE OF request_id,trigger,automatic_origin,
             configuration_revision,base_url,model,initial_prompt_mode,
             initial_prompt_version_id,report_prompt_mode,
             report_prompt_version_id,force_refresh,created_at
           ON content_analysis_jobs
           BEGIN SELECT RAISE(ABORT,'immutable job snapshot'); END"""
    )

    rows = connection.execute(
        "SELECT id,analysis_goal FROM automation_tasks ORDER BY id"
    ).fetchall()
    for row in rows:
        # ``analysis_goal`` was already constrained to nonblank UTF-8 prose.
        # It represented a task-specific report instruction, so migration keeps
        # it explicitly custom even when its text happens to match the built-in
        # report template.
        report_instructions = str(row["analysis_goal"])
        report_id = _prompt(
            connection,
            stage="report",
            instructions=report_instructions,
            schema_version=REPORT_SCHEMA_VERSION,
            mode="custom",
        )
        connection.execute(
            """UPDATE automation_tasks SET
              initial_prompt_mode=?,initial_prompt_version_id=?,
              report_prompt_mode=?,report_prompt_version_id=? WHERE id=?""",
            (
                "default" if initial_is_default else "custom",
                initial_id,
                "custom",
                report_id,
                row["id"],
            ),
        )

    # A new writer must provide both references.  SQLite cannot add a NOT NULL
    # foreign-key column to a populated table, so these triggers provide the
    # same invariant for both ordinary SQL and repository writes.
    connection.execute("DROP TRIGGER IF EXISTS automation_task_prompt_insert")
    connection.execute("DROP TRIGGER IF EXISTS automation_task_prompt_update")
    connection.execute(
        f"""CREATE TRIGGER automation_task_prompt_insert
           BEFORE INSERT ON automation_tasks
           WHEN NEW.initial_prompt_version_id IS NULL
             OR NEW.report_prompt_version_id IS NULL
             OR NEW.initial_prompt_mode NOT IN ('default','custom')
             OR NEW.report_prompt_mode NOT IN ('default','custom')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.initial_prompt_version_id AND p.stage='initial'
                 AND p.schema_version='{INITIAL_SCHEMA_VERSION}')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id AND p.stage='report'
                 AND p.schema_version='{REPORT_SCHEMA_VERSION}')
             OR (NEW.initial_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.initial_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_initial_id})))
             OR (NEW.report_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.report_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_report_id})
                  AND p.instructions=NEW.analysis_goal))
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id
                 AND (p.instructions=NEW.analysis_goal
                   OR NEW.analysis_goal='使用已保存提示词版本 '||p.id))
           BEGIN
             SELECT RAISE(ABORT, 'automation task prompt choice is invalid');
           END"""
    )
    connection.execute(
        f"""CREATE TRIGGER automation_task_prompt_update
           BEFORE UPDATE OF initial_prompt_mode,initial_prompt_version_id,
             report_prompt_mode,report_prompt_version_id,analysis_goal
             ON automation_tasks
           WHEN NEW.initial_prompt_version_id IS NULL
             OR NEW.report_prompt_version_id IS NULL
             OR NEW.initial_prompt_mode NOT IN ('default','custom')
             OR NEW.report_prompt_mode NOT IN ('default','custom')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.initial_prompt_version_id AND p.stage='initial'
                 AND p.schema_version='{INITIAL_SCHEMA_VERSION}')
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id AND p.stage='report'
                 AND p.schema_version='{REPORT_SCHEMA_VERSION}')
             OR (NEW.initial_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.initial_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_initial_id})))
             OR (NEW.report_prompt_mode='default' AND NOT EXISTS
               (SELECT 1 FROM analysis_prompt_versions p
                WHERE p.id=NEW.report_prompt_version_id
                  AND p.instructions=(SELECT instructions FROM
                    analysis_prompt_versions WHERE id={canonical_report_id})
                  AND p.instructions=NEW.analysis_goal))
             OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
               WHERE p.id=NEW.report_prompt_version_id
                 AND (p.instructions=NEW.analysis_goal
                   OR NEW.analysis_goal='使用已保存提示词版本 '||p.id))
           BEGIN
             SELECT RAISE(ABORT, 'automation task prompt choice is invalid');
           END"""
    )

    # v17 made deleted task rows immutable.  Recreate that guard with the new
    # prompt fields included, while retaining the rule-deletion cleanup escape.
    connection.execute("DROP TRIGGER IF EXISTS automation_task_deleted_immutable")
    connection.execute(
        """CREATE TRIGGER automation_task_deleted_immutable
           BEFORE UPDATE ON automation_tasks
           WHEN OLD.deleted_at IS NOT NULL AND NOT (
             NEW.id IS OLD.id
             AND NEW.name IS OLD.name
             AND NEW.normalized_name IS OLD.normalized_name
             AND NEW.monitoring_rule_id IS NULL
             AND OLD.monitoring_rule_id IS NOT NULL
             AND NEW.max_results_per_term IS OLD.max_results_per_term
             AND NEW.analysis_goal IS OLD.analysis_goal
             AND NEW.initial_prompt_mode IS OLD.initial_prompt_mode
             AND NEW.initial_prompt_version_id IS OLD.initial_prompt_version_id
             AND NEW.report_prompt_mode IS OLD.report_prompt_mode
             AND NEW.report_prompt_version_id IS OLD.report_prompt_version_id
             AND NEW.schedule_kind IS OLD.schedule_kind
             AND NEW.interval_minutes IS OLD.interval_minutes
             AND NEW.daily_time IS OLD.daily_time
             AND NEW.timezone IS OLD.timezone
             AND NEW.enabled IS OLD.enabled
             AND NEW.revision IS OLD.revision
             AND NEW.next_due_at IS OLD.next_due_at
             AND NEW.anchor_at IS OLD.anchor_at
             AND NEW.deleted_at IS OLD.deleted_at
             AND NEW.created_at IS OLD.created_at
             AND NEW.updated_at IS OLD.updated_at
           )
           BEGIN
             SELECT RAISE(ABORT, 'deleted automation task is immutable');
           END"""
    )
