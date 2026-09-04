"""v17: add durable soft-deletion state to automatic workflow tasks."""

import sqlite3

# SQL constraints are kept readable as schema-shaped blocks.
# ruff: noqa: E501


def migrate(connection: sqlite3.Connection) -> None:
    """Add task deletion state without rewriting workflow history.

    Automatic workflow child tables intentionally keep their restrictive
    foreign keys.  A task is therefore hidden and fenced from future work by
    updating only its own configuration row; its immutable runs and child
    history remain readable through their independent IDs.
    """
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(automation_tasks)")
    }
    if "deleted_at" not in columns:
        connection.execute("ALTER TABLE automation_tasks ADD COLUMN deleted_at TEXT")

    # Keep the invariant in SQLite as well as in the repository transaction.
    # The INSERT guard protects hand-written/repair SQL, while the UPDATE guard
    # protects any future writer that does not use the repository.
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS automation_task_deleted_state_insert
           BEFORE INSERT ON automation_tasks
           WHEN NEW.deleted_at IS NOT NULL AND
             (NEW.enabled != 0 OR NEW.next_due_at IS NOT NULL OR NEW.anchor_at IS NOT NULL)
           BEGIN
             SELECT RAISE(ABORT, 'deleted automation task must be disabled');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS automation_task_deleted_state_update
           BEFORE UPDATE ON automation_tasks
           WHEN NEW.deleted_at IS NOT NULL AND
             (NEW.enabled != 0 OR NEW.next_due_at IS NOT NULL OR NEW.anchor_at IS NOT NULL)
           BEGIN
             SELECT RAISE(ABORT, 'deleted automation task must be disabled');
           END"""
    )
    # A monitoring rule has ON DELETE SET NULL.  SQLite implements that
    # referential action as an UPDATE of monitoring_rule_id on the referencing
    # task.  Permit that one storage-owned cleanup update, but keep every
    # other field of a tombstone immutable.  The historical rule-deleted
    # trigger is recreated below so its follow-up disable update does not run
    # for an already-deleted task.
    connection.execute("DROP TRIGGER IF EXISTS automation_task_rule_deleted")
    connection.execute(
        """CREATE TRIGGER automation_task_rule_deleted AFTER UPDATE OF
          monitoring_rule_id ON automation_tasks
          WHEN NEW.monitoring_rule_id IS NULL AND OLD.monitoring_rule_id IS NOT NULL
            AND NEW.deleted_at IS NULL
          BEGIN
            UPDATE automation_tasks SET enabled=0,next_due_at=NULL,anchor_at=NULL
              WHERE id=NEW.id;
          END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS automation_task_deleted_immutable
           BEFORE UPDATE ON automation_tasks
           WHEN OLD.deleted_at IS NOT NULL AND NOT (
             NEW.id IS OLD.id
             AND NEW.name IS OLD.name
             AND NEW.normalized_name IS OLD.normalized_name
             AND NEW.monitoring_rule_id IS NULL
             AND OLD.monitoring_rule_id IS NOT NULL
             AND NEW.max_results_per_term IS OLD.max_results_per_term
             AND NEW.analysis_goal IS OLD.analysis_goal
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
