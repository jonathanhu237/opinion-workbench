"""Converge the local product database on the single Weibo platform."""

from __future__ import annotations

import re
import sqlite3

PLATFORM_TABLES = (
    "search_runs",
    "search_contents",
    "search_batch_items",
    "ai_summary_runs",
    "collection_schedule_platforms",
    "automation_task_platforms",
)

# These are the operator-reviewed disabled task definitions found during the
# one-time local cleanup. There is no stable migration-owned identifier for
# them in the historical schema, so keep the exact inventory explicit rather
# than broadening the deletion to every task with a similar shape.
OBSOLETE_AUTOMATION_TASK_NAMES = (
    "2026-08-31验收·龙田自动链路",
    "2026-09-01验收·三平台各一条",
    "2026-09-01验收·最终三平台各一条",
    "龙田街道舆情值守",
)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _create_platform_guard(connection: sqlite3.Connection, table: str) -> None:
    """Enforce the current invariant for both fresh and upgraded databases."""
    if not _table_exists(connection, table):
        return
    safe_name = table.replace("-", "_")
    connection.execute(
        f"""CREATE TRIGGER IF NOT EXISTS {safe_name}_weibo_only_insert
        BEFORE INSERT ON {table}
        WHEN NEW.platform <> 'wb'
        BEGIN SELECT RAISE(ABORT, 'only Weibo is supported'); END"""
    )
    connection.execute(
        f"""CREATE TRIGGER IF NOT EXISTS {safe_name}_weibo_only_update
        BEFORE UPDATE OF platform ON {table}
        WHEN NEW.platform <> 'wb'
        BEGIN SELECT RAISE(ABORT, 'only Weibo is supported'); END"""
    )


def _tighten_platform_constraints(connection: sqlite3.Connection) -> None:
    """Rebuild platform-bearing tables with a real final Weibo CHECK.

    SQLite cannot add a CHECK constraint with ALTER TABLE.  v26 therefore
    performs a transactional table replacement after obsolete rows are gone.
    The wrapper temporarily disables FK enforcement while the parent tables
    are replaced, then the final foreign-key check runs before the transaction
    is committed and the connection setting is restored.
    """
    for table in PLATFORM_TABLES:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row is None or row[0] is None:
            continue
        table_sql = str(row[0])
        tightened_sql, replacements = re.subn(
            r"CHECK\s*\(\s*platform\s+IN\s*\(.*?\)\s*\)",
            "CHECK (platform = 'wb')",
            table_sql,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if replacements != 1:
            raise sqlite3.DatabaseError(
                f"Cannot tighten the platform constraint for {table}."
            )

        temporary = f"{table}__weibo_v26"
        tightened_sql = re.sub(
            rf"^(CREATE TABLE\s+)(?:\"{re.escape(table)}\"|{re.escape(table)})",
            lambda match, temporary=temporary: f'{match.group(1)}"{temporary}"',
            tightened_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        if tightened_sql == table_sql:
            raise sqlite3.DatabaseError(f"Cannot rename the rebuilt table {table}.")

        index_sql = [
            str(index[0])
            for index in connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (table,),
            ).fetchall()
        ]
        trigger_sql = [
            str(trigger[0])
            for trigger in connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name=? AND sql IS NOT NULL",
                (table,),
            ).fetchall()
        ]
        sequence = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name=?", (table,)
        ).fetchone()
        columns = [
            str(column[1])
            for column in connection.execute(f'PRAGMA table_info("{table}")')
        ]
        quoted_columns = ", ".join(f'"{column}"' for column in columns)

        connection.execute(tightened_sql)
        connection.execute(
            f'INSERT INTO "{temporary}" ({quoted_columns}) '
            f'SELECT {quoted_columns} FROM "{table}"'
        )
        connection.execute(f'DROP TABLE "{table}"')
        connection.execute(f'ALTER TABLE "{temporary}" RENAME TO "{table}"')

        if sequence is not None:
            sequence_value = sequence[0]
            updated = connection.execute(
                "UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?",
                (sequence_value, table),
            ).rowcount
            if updated == 0:
                connection.execute(
                    "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
                    (table, sequence_value),
                )
        for statement in index_sql:
            connection.execute(statement)
        for statement in trigger_sql:
            connection.execute(statement)


def _delete_topic_report_graph(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_reports AS
        SELECT DISTINCT report_id FROM topic_report_sources
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """DELETE FROM topic_report_node_children
        WHERE node_id IN (
          SELECT id FROM topic_report_nodes WHERE report_id IN
          (SELECT report_id FROM _weibo_removed_reports)
        ) OR child_id IN (
          SELECT id FROM topic_report_nodes WHERE report_id IN
          (SELECT report_id FROM _weibo_removed_reports)
        )"""
    )
    connection.execute(
        """DELETE FROM topic_report_node_sources
        WHERE node_id IN (
          SELECT id FROM topic_report_nodes WHERE report_id IN
          (SELECT report_id FROM _weibo_removed_reports)
        ) OR source_id IN (
          SELECT id FROM topic_report_sources WHERE report_id IN
          (SELECT report_id FROM _weibo_removed_reports)
        )"""
    )
    connection.execute(
        """DELETE FROM topic_report_nodes
        WHERE report_id IN (SELECT report_id FROM _weibo_removed_reports)"""
    )
    connection.execute(
        """DELETE FROM topic_report_sources
        WHERE report_id IN (SELECT report_id FROM _weibo_removed_reports)"""
    )
    connection.execute(
        """DELETE FROM topic_report_requests
        WHERE report_id IN (SELECT report_id FROM _weibo_removed_reports)"""
    )
    connection.execute(
        """DELETE FROM topic_report_runs
        WHERE id IN (SELECT report_id FROM _weibo_removed_reports)"""
    )


def _delete_analysis_graph(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_attempts AS
        SELECT id, job_id FROM content_analysis_attempts
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)
           OR source_run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_jobs AS
        SELECT DISTINCT removed.job_id
        FROM _weibo_removed_attempts removed
        WHERE NOT EXISTS (
          SELECT 1 FROM content_analysis_attempts survivor
          WHERE survivor.job_id = removed.job_id
            AND NOT EXISTS (
              SELECT 1 FROM _weibo_removed_attempts removed_survivor
              WHERE removed_survivor.id = survivor.id
            )
        )"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_summary_runs AS
        SELECT DISTINCT summary_run_id FROM ai_summary_items
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)
        UNION
        SELECT id FROM ai_summary_runs
        WHERE platform <> 'wb'
           OR source_run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )

    # A report generation owns both a job and an optional topic report. Remove
    # the generation first so the RESTRICT foreign keys remain meaningful.
    connection.execute(
        """DELETE FROM report_generations
        WHERE analysis_job_id IN (SELECT job_id FROM _weibo_removed_jobs)
           OR report_id IN (SELECT report_id FROM _weibo_removed_reports)"""
    )

    # Legacy summary items can reuse one another. Clearing the reuse pointer is
    # safe here because the entire affected run is being removed.
    connection.execute(
        """UPDATE ai_summary_items SET reused_from_item_id=NULL
        WHERE summary_run_id IN (
          SELECT summary_run_id FROM _weibo_removed_summary_runs
        )"""
    )
    connection.execute(
        """DELETE FROM ai_summary_items
        WHERE summary_run_id IN (
          SELECT summary_run_id FROM _weibo_removed_summary_runs
        )"""
    )
    connection.execute(
        """DELETE FROM ai_summary_runs
        WHERE id IN (SELECT summary_run_id FROM _weibo_removed_summary_runs)"""
    )

    # Claims are rebuilt by later analysis admissions. Removing the claim for a
    # deleted content item also removes pointers to deleted attempt/job rows.
    # A mixed historical job may still contain a valid Weibo attempt, so clear
    # only pointers to attempts that are about to disappear and keep the job
    # and surviving attempts intact.
    connection.execute(
        """DELETE FROM content_analysis_claims
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """UPDATE content_analysis_claims SET first_attempt_id=NULL
        WHERE first_attempt_id IN (SELECT id FROM _weibo_removed_attempts)"""
    )
    connection.execute(
        """UPDATE content_analysis_claims SET latest_attempt_id=NULL
        WHERE latest_attempt_id IN (SELECT id FROM _weibo_removed_attempts)"""
    )
    connection.execute(
        """UPDATE content_analysis_claims SET active_job_id=NULL
        WHERE active_job_id IN (SELECT job_id FROM _weibo_removed_jobs)"""
    )

    # A reused surviving attempt can point at an obsolete attempt. The normal
    # terminal-attempt guard intentionally forbids this mutation, so suspend
    # that guard for this one-time referential repair and preserve the output
    # as an ordinary attempted result after clearing the obsolete pointer.
    terminal_trigger = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' "
        "AND name='analysis_attempt_terminal_immutable'"
    ).fetchone()
    if terminal_trigger is not None and terminal_trigger[0] is not None:
        connection.execute("DROP TRIGGER analysis_attempt_terminal_immutable")
        connection.execute(
            """UPDATE content_analysis_attempts
            SET reused_from_attempt_id=NULL, attempted=1
            WHERE reused_from_attempt_id IN (SELECT id FROM _weibo_removed_attempts)
              AND id NOT IN (SELECT id FROM _weibo_removed_attempts)"""
        )
        connection.execute(terminal_trigger[0])

    # Remove only the obsolete attempts. In a mixed job, the surviving Weibo
    # attempts keep their job, completion event and report-generation history.
    connection.execute(
        """DELETE FROM content_analysis_attempts
        WHERE id IN (SELECT id FROM _weibo_removed_attempts)"""
    )
    connection.execute(
        """DELETE FROM content_analysis_requests
        WHERE job_id IN (SELECT job_id FROM _weibo_removed_jobs)"""
    )
    connection.execute(
        """DELETE FROM analysis_completion_events
        WHERE job_id IN (SELECT job_id FROM _weibo_removed_jobs)"""
    )
    connection.execute(
        """DELETE FROM collection_analysis_handoffs
        WHERE job_id IN (SELECT job_id FROM _weibo_removed_jobs)"""
    )
    connection.execute(
        """DELETE FROM content_analysis_jobs
        WHERE id IN (SELECT job_id FROM _weibo_removed_jobs)"""
    )


def _delete_search_graph(connection: sqlite3.Connection) -> None:
    # Recovery rows deliberately reject both DELETE and UPDATE in the live
    # schema.  The migration is the one trusted place allowed to prune an
    # obsolete item and, for a mixed batch, move the surviving Weibo item to
    # the product's only supported position (0).
    connection.execute("DROP TRIGGER IF EXISTS search_recovery_immutable")
    connection.execute("DROP TRIGGER IF EXISTS search_recovery_no_delete")

    connection.execute(
        """DELETE FROM collection_occurrences
        WHERE batch_id IN (SELECT batch_id FROM _weibo_removed_batches)"""
    )
    connection.execute(
        """DELETE FROM search_batch_recoveries
        WHERE batch_id IN (SELECT batch_id FROM _weibo_removed_batches)
           OR EXISTS (
             SELECT 1 FROM _weibo_removed_batch_items removed
             WHERE removed.batch_id = search_batch_recoveries.batch_id
               AND removed.position = search_batch_recoveries.item_position
           )"""
    )
    connection.execute(
        """DELETE FROM search_batch_attempts
        WHERE batch_id IN (SELECT batch_id FROM _weibo_removed_batches)
           OR search_run_id IN (SELECT id FROM _weibo_removed_runs)
           OR EXISTS (
             SELECT 1 FROM _weibo_removed_batch_items removed
             WHERE removed.batch_id = search_batch_attempts.batch_id
               AND removed.position = search_batch_attempts.item_position
           )"""
    )
    connection.execute(
        """DELETE FROM search_batch_items
        WHERE batch_id IN (SELECT batch_id FROM _weibo_removed_batches)
           OR EXISTS (
             SELECT 1 FROM _weibo_removed_batch_items removed
             WHERE removed.batch_id = search_batch_items.batch_id
               AND removed.position = search_batch_items.position
           )"""
    )
    connection.execute(
        """DELETE FROM search_batch_terms
        WHERE batch_id IN (SELECT batch_id FROM _weibo_removed_batches)"""
    )
    connection.execute(
        """DELETE FROM search_batches
        WHERE id IN (SELECT batch_id FROM _weibo_removed_batches)"""
    )

    # A historical batch could contain (for example) an XHS item at position
    # 0 and a valid Weibo item at position 1.  Keep that batch and all Weibo
    # history, but compact the surviving item to the fixed Weibo position so
    # current APIs can read it without carrying a legacy platform index.
    connection.execute(
        """UPDATE search_batch_attempts
        SET item_position = 0
        WHERE EXISTS (
          SELECT 1 FROM search_batch_items item
          JOIN _weibo_removed_batch_items removed
            ON removed.batch_id = item.batch_id
          WHERE item.batch_id = search_batch_attempts.batch_id
            AND item.platform = 'wb'
            AND item.position = search_batch_attempts.item_position
        )"""
    )
    connection.execute(
        """UPDATE search_batch_recoveries
        SET item_position = 0
        WHERE EXISTS (
          SELECT 1 FROM search_batch_items item
          JOIN _weibo_removed_batch_items removed
            ON removed.batch_id = item.batch_id
          WHERE item.batch_id = search_batch_recoveries.batch_id
            AND item.platform = 'wb'
            AND item.position = search_batch_recoveries.item_position
        )"""
    )
    connection.execute(
        """UPDATE search_batches
        SET current_item_position = 0
        WHERE current_item_position IS NOT NULL
          AND id IN (
            SELECT DISTINCT item.batch_id
            FROM search_batch_items item
            JOIN _weibo_removed_batch_items removed
              ON removed.batch_id = item.batch_id
            WHERE item.platform = 'wb'
          )"""
    )
    connection.execute(
        """UPDATE search_batch_items
        SET position = 0
        WHERE platform = 'wb'
          AND position <> 0
          AND batch_id IN (
            SELECT DISTINCT batch_id FROM _weibo_removed_batch_items
          )"""
    )
    connection.execute(
        """UPDATE search_batches
        SET status = (
          SELECT CASE item.status
            WHEN 'failed' THEN 'completed_with_failures'
            WHEN 'completed' THEN 'completed'
            WHEN 'skipped' THEN 'completed'
            WHEN 'cancelled' THEN 'cancelled'
            WHEN 'paused_for_manual_action' THEN 'paused_for_manual_action'
            WHEN 'running' THEN 'running'
            ELSE 'queued'
          END
          FROM search_batch_items item
          WHERE item.batch_id = search_batches.id AND item.platform = 'wb'
        )
        WHERE id IN (SELECT DISTINCT batch_id FROM _weibo_removed_batch_items)
          AND EXISTS (
            SELECT 1 FROM search_batch_items item
            WHERE item.batch_id = search_batches.id AND item.platform = 'wb'
          )"""
    )

    connection.execute(
        """CREATE TRIGGER search_recovery_immutable BEFORE UPDATE ON
        search_batch_recoveries
        BEGIN SELECT RAISE(ABORT, 'immutable recovery'); END"""
    )
    connection.execute(
        """CREATE TRIGGER search_recovery_no_delete BEFORE DELETE ON
        search_batch_recoveries
        BEGIN SELECT RAISE(ABORT, 'immutable recovery'); END"""
    )

    connection.execute(
        """DELETE FROM search_run_content_terms
        WHERE search_content_id IN (SELECT id FROM _weibo_removed_contents)
           OR run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )
    connection.execute(
        """DELETE FROM search_run_contents
        WHERE search_content_id IN (SELECT id FROM _weibo_removed_contents)
           OR run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )
    connection.execute(
        """DELETE FROM search_run_term_completions
        WHERE run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )
    connection.execute(
        """DELETE FROM search_run_terms
        WHERE run_id IN (SELECT id FROM _weibo_removed_runs)"""
    )
    connection.execute(
        """DELETE FROM search_runs
        WHERE id IN (SELECT id FROM _weibo_removed_runs)"""
    )


def _delete_automation_graph(connection: sqlite3.Connection) -> None:
    placeholders = ", ".join("?" for _ in OBSOLETE_AUTOMATION_TASK_NAMES)
    connection.execute(
        f"""CREATE TEMP TABLE _weibo_removed_tasks AS
        SELECT id AS task_id FROM automation_tasks
        WHERE enabled = 0 AND name IN ({placeholders})
          AND EXISTS (
            SELECT 1 FROM automation_task_platforms platforms
            WHERE platforms.task_id = automation_tasks.id
              AND platforms.platform <> 'wb'
          )""",
        OBSOLETE_AUTOMATION_TASK_NAMES,
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_auto_runs AS
        SELECT id FROM automation_runs
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)"""
    )
    if (
        connection.execute("SELECT 1 FROM _weibo_removed_auto_runs LIMIT 1").fetchone()
        is not None
    ):
        # Removing a task with run history would either violate the historical
        # foreign keys or silently rewrite the operating record.  The product
        # has no soft-delete representation for obsolete task definitions, so
        # fail the transaction and require an explicit operator decision.
        raise sqlite3.DatabaseError(
            "Cannot remove obsolete automation tasks with run history."
        )

    # Platform rows are business data in their own right. Remove obsolete
    # non-Weibo rows from every task, but keep an unknown task definition and
    # its historical runs intact rather than inferring deletion from its
    # platform shape. A task left with no supported platform is disabled so it
    # cannot be scheduled until an operator edits it.
    connection.execute(
        """CREATE TEMP TABLE _weibo_touched_tasks AS
        SELECT DISTINCT task_id
        FROM automation_task_platforms
        WHERE platform <> 'wb'"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_platformless_tasks AS
        SELECT DISTINCT platforms.task_id AS task_id
        FROM automation_task_platforms platforms
        WHERE platforms.platform <> 'wb'
          AND NOT EXISTS (
            SELECT 1 FROM automation_task_platforms surviving
            WHERE surviving.task_id = platforms.task_id
              AND surviving.platform = 'wb'
          )"""
    )
    connection.execute(
        """DELETE FROM automation_task_platforms
        WHERE platform <> 'wb'"""
    )
    connection.execute(
        """UPDATE automation_tasks
        SET enabled=0, next_due_at=NULL, anchor_at=NULL, updated_at=updated_at
        WHERE id IN (SELECT task_id FROM _weibo_platformless_tasks)
          AND id NOT IN (SELECT task_id FROM _weibo_removed_tasks)"""
    )
    # Keep the preserved task readable through the current API contract. Its
    # old platform is gone, so attach the only legal platform as a disabled
    # placeholder; an operator can edit or delete the task explicitly later.
    connection.execute(
        """INSERT INTO automation_task_platforms(task_id, position, platform)
        SELECT task_id, 0, 'wb'
        FROM _weibo_platformless_tasks
        WHERE task_id NOT IN (SELECT task_id FROM _weibo_removed_tasks)"""
    )
    connection.execute(
        """UPDATE automation_task_platforms
        SET position=0
        WHERE platform='wb'
          AND task_id IN (SELECT task_id FROM _weibo_touched_tasks)"""
    )
    connection.execute(
        """DELETE FROM automation_requests
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)
           OR run_id IN (SELECT id FROM _weibo_removed_auto_runs)"""
    )
    connection.execute(
        """DELETE FROM automation_occurrences
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)
           OR run_id IN (SELECT id FROM _weibo_removed_auto_runs)"""
    )
    connection.execute(
        """DELETE FROM automation_run_contents
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)
           OR run_id IN (SELECT id FROM _weibo_removed_auto_runs)
           OR content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """DELETE FROM automation_stage_attempts
        WHERE run_id IN (SELECT id FROM _weibo_removed_auto_runs)"""
    )
    connection.execute(
        """DELETE FROM automation_task_contents
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)
           OR content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """DELETE FROM automation_runs
        WHERE id IN (SELECT id FROM _weibo_removed_auto_runs)"""
    )
    connection.execute(
        """DELETE FROM automation_task_platforms
        WHERE task_id IN (SELECT task_id FROM _weibo_removed_tasks)"""
    )
    connection.execute(
        """DELETE FROM automation_tasks
        WHERE id IN (SELECT task_id FROM _weibo_removed_tasks)"""
    )


def _delete_schedule_graph(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_schedule_platforms AS
        SELECT DISTINCT schedule_id, position
        FROM collection_schedule_platforms
        WHERE platform <> 'wb'"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_schedules AS
        SELECT DISTINCT removed.schedule_id
        FROM _weibo_removed_schedule_platforms removed
        WHERE NOT EXISTS (
          SELECT 1 FROM collection_schedule_platforms platforms
          WHERE platforms.schedule_id = removed.schedule_id
            AND platforms.platform = 'wb'
        )"""
    )
    connection.execute(
        """DELETE FROM collection_occurrences
        WHERE schedule_id IN (SELECT schedule_id FROM _weibo_removed_schedules)"""
    )
    connection.execute(
        """DELETE FROM collection_schedule_platforms
        WHERE schedule_id IN (SELECT schedule_id FROM _weibo_removed_schedules)
           OR EXISTS (
             SELECT 1 FROM _weibo_removed_schedule_platforms removed
             WHERE removed.schedule_id = collection_schedule_platforms.schedule_id
               AND removed.position = collection_schedule_platforms.position
           )"""
    )
    connection.execute(
        """DELETE FROM collection_schedules
        WHERE id IN (SELECT schedule_id FROM _weibo_removed_schedules)"""
    )
    connection.execute(
        """UPDATE collection_schedule_platforms
        SET position = 0
        WHERE platform = 'wb'
          AND position <> 0
          AND schedule_id IN (
            SELECT DISTINCT schedule_id
            FROM _weibo_removed_schedule_platforms
          )"""
    )


def migrate(connection: sqlite3.Connection) -> None:
    """Remove obsolete platform data and enforce the current Weibo invariant."""
    # Several historical graphs use mutually-referencing RESTRICT foreign keys
    # (for example a completed report points at its root node). Defer those
    # checks until the enclosing migration transaction commits so the complete
    # graph can be removed atomically without weakening the final invariant.
    connection.execute("PRAGMA defer_foreign_keys = ON")
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_contents AS
        SELECT id FROM search_contents WHERE platform <> 'wb'"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_runs AS
        SELECT id FROM search_runs WHERE platform <> 'wb'"""
    )
    # Keep an explicit item-level inventory so a mixed historical batch can
    # retain its valid Weibo side. A batch is removed as a unit only when it
    # has no Weibo item at all.
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_batch_items AS
        SELECT DISTINCT batch_id, position
        FROM search_batch_items
        WHERE platform <> 'wb'"""
    )
    connection.execute(
        """CREATE TEMP TABLE _weibo_removed_batches AS
        SELECT DISTINCT removed.batch_id
        FROM _weibo_removed_batch_items removed
        WHERE NOT EXISTS (
          SELECT 1 FROM search_batch_items item
          WHERE item.batch_id = removed.batch_id AND item.platform = 'wb'
        )"""
    )
    connection.execute(
        """INSERT OR IGNORE INTO _weibo_removed_runs(id)
        SELECT DISTINCT attempt.search_run_id
        FROM search_batch_attempts attempt
        WHERE attempt.batch_id IN (SELECT batch_id FROM _weibo_removed_batches)
           OR EXISTS (
             SELECT 1 FROM _weibo_removed_batch_items removed
             WHERE removed.batch_id = attempt.batch_id
               AND removed.position = attempt.item_position
           )"""
    )
    _delete_automation_graph(connection)
    _delete_topic_report_graph(connection)
    _delete_analysis_graph(connection)
    _delete_search_graph(connection)

    # Material and cache bindings are independent of analysis/report history.
    connection.execute(
        """DELETE FROM media_cache_bindings
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """DELETE FROM content_materials
        WHERE content_id IN (SELECT id FROM _weibo_removed_contents)"""
    )
    connection.execute(
        """DELETE FROM search_contents
        WHERE id IN (SELECT id FROM _weibo_removed_contents)"""
    )

    _delete_schedule_graph(connection)

    # Replace the historical multi-platform CHECK definitions now that all
    # obsolete rows are gone.  This makes the final schema self-describing;
    # the guards below remain a clearer error contract for API callers.
    _tighten_platform_constraints(connection)

    # Keep the old migration chain readable while making current writes
    # impossible to widen back to a multi-platform product.
    for table in PLATFORM_TABLES:
        _create_platform_guard(connection, table)

    for name in (
        "_weibo_removed_contents",
        "_weibo_removed_runs",
        "_weibo_removed_reports",
        "_weibo_removed_attempts",
        "_weibo_removed_jobs",
        "_weibo_removed_summary_runs",
        "_weibo_removed_batch_items",
        "_weibo_removed_batches",
        "_weibo_removed_tasks",
        "_weibo_touched_tasks",
        "_weibo_platformless_tasks",
        "_weibo_removed_auto_runs",
        "_weibo_removed_schedules",
        "_weibo_removed_schedule_platforms",
    ):
        connection.execute(f"DROP TABLE IF EXISTS temp.{name}")

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.DatabaseError(
            "Weibo-only migration left foreign-key violations: "
            + repr([tuple(row) for row in violations])
        )
