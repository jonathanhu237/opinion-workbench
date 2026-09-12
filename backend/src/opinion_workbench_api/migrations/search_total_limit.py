"""v30: opt-in latest-first collection with a frozen batch-wide unique cap."""

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    # NULL deliberately retains the meaning of existing configurations/history.
    for table in (
        "search_runs",
        "search_batches",
        "collection_schedules",
        "automation_tasks",
    ):
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN max_total_results INTEGER "
            "CHECK (max_total_results IS NULL OR "
            "(typeof(max_total_results)='integer' "
            "AND max_total_results BETWEEN 1 AND 50))"
        )
    for table in ("search_runs", "search_batches"):
        connection.execute(
            f"CREATE TRIGGER {table}_total_limit_immutable "
            f"BEFORE UPDATE OF max_total_results ON {table} "
            "WHEN NEW.max_total_results IS NOT OLD.max_total_results "
            "BEGIN SELECT RAISE(ABORT, 'collection limit snapshot is immutable'); END"
        )
    connection.execute(
        "CREATE TRIGGER automation_task_deleted_total_immutable "
        "BEFORE UPDATE OF max_total_results ON automation_tasks "
        "WHEN OLD.deleted_at IS NOT NULL AND "
        "NEW.max_total_results IS NOT OLD.max_total_results "
        "BEGIN SELECT RAISE(ABORT, 'deleted automation task is immutable'); END"
    )
