"""v31: reopen the platform catalog after the Weibo-only migration.

The v26 cleanup intentionally removed obsolete rows.  This migration only
widens the durable CHECK constraints for future work; it never reconstructs
deleted history.
"""

from __future__ import annotations

import re
import sqlite3

PLATFORMS = "'toutiao','wb','ks','dy','xhs'"
PLATFORM_TABLES = (
    "search_runs",
    "search_contents",
    "search_batch_items",
    "ai_summary_runs",
    "collection_schedule_platforms",
    "automation_task_platforms",
)


def migrate(connection: sqlite3.Connection) -> None:
    previous_fk = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if previous_fk:
        connection.execute("PRAGMA foreign_keys = OFF")
    try:
        # Rebuilding one table temporarily invalidates triggers on related
        # tables. Keep their definitions in memory and recreate them after all
        # six tables have their widened shape.
        trigger_rows = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND sql IS NOT NULL"
        ).fetchall()
        triggers = [
            (str(row[0]), str(row[1]))
            for row in trigger_rows
            if "weibo_only" not in str(row[0])
        ]
        for name, _ in trigger_rows:
            connection.execute(f'DROP TRIGGER IF EXISTS "{name}"')
        for table in PLATFORM_TABLES:
            _widen_table(connection, table)
        for _, statement in triggers:
            connection.execute(statement)
    finally:
        if previous_fk:
            connection.execute("PRAGMA foreign_keys = ON")


def _widen_table(connection: sqlite3.Connection, table: str) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return
    original_sql = str(row[0])
    widened_sql, count = re.subn(
        r"CHECK\s*\(\s*platform\s*=\s*'wb'\s*\)",
        f"CHECK (platform IN ({PLATFORMS}))",
        original_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if count != 1:
        raise sqlite3.DatabaseError(f"Cannot widen platform constraint for {table}")
    temporary = f"{table}__multi_v31"
    widened_sql = re.sub(
        rf"^(CREATE TABLE\s+)(?:\"{re.escape(table)}\"|{re.escape(table)})",
        rf'\1"{temporary}"',
        widened_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if widened_sql == original_sql:
        raise sqlite3.DatabaseError(f"Cannot rename rebuilt table {table}")
    indexes = [
        str(value[0])
        for value in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]
    triggers = [
        (str(value[0]), str(value[1]))
        for value in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name=? AND sql IS NOT NULL",
            (table,),
        ).fetchall()
        if "weibo_only" not in str(value[0])
    ]
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name=?", (table,)
    ).fetchone()
    columns = [
        str(value[1]) for value in connection.execute(f'PRAGMA table_info("{table}")')
    ]
    quoted = ", ".join(f'"{column}"' for column in columns)
    for name, _ in connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
        (table,),
    ).fetchall():
        connection.execute(f'DROP TRIGGER IF EXISTS "{name}"')
    connection.execute(widened_sql)
    connection.execute(
        f'INSERT INTO "{temporary}" ({quoted}) SELECT {quoted} FROM "{table}"'
    )
    connection.execute(f'DROP TABLE "{table}"')
    connection.execute(f'ALTER TABLE "{temporary}" RENAME TO "{table}"')
    if sequence is not None:
        if (
            connection.execute(
                "UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?",
                (sequence[0], table),
            ).rowcount
            == 0
        ):
            connection.execute(
                "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)",
                (table, sequence[0]),
            )
    for statement in indexes:
        connection.execute(statement)
    for _, statement in triggers:
        connection.execute(statement)
