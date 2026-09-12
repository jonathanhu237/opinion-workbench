"""v33: persist the text-insufficient empty-report reason.

The report graph predates the text-only analysis scope and its SQLite CHECK
constraint only admitted the two older empty reasons.  Rebuild that one table
without changing any report rows or graph references.
"""

from __future__ import annotations

import re
import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='topic_report_runs'"
    ).fetchone()
    if row is None or row[0] is None:
        return
    original_sql = str(row[0])
    widened_sql, count = re.subn(
        r"CHECK\s*\(\s*empty_reason\s+IN\s*\(\s*'no_ready_sources'\s*,\s*'no_relevant_sources'\s*\)\s*\)",
        (
            "CHECK(empty_reason IN ("
            "'no_ready_sources','no_relevant_sources','text_insufficient'))"
        ),
        original_sql,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if count == 0:
        # The migration is idempotent when a database was created from a newer
        # schema or a compatible table definition.
        if "text_insufficient" in original_sql:
            return
        raise sqlite3.DatabaseError("Cannot widen topic report empty reason")
    temporary = "topic_report_runs__text_insufficient_v33"
    widened_sql = re.sub(
        r"^(CREATE TABLE\s+)(?:\"topic_report_runs\"|topic_report_runs)",
        rf'\1"{temporary}"',
        widened_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if widened_sql == original_sql:
        raise sqlite3.DatabaseError("Cannot rename topic report table")

    indexes = [
        str(item[0])
        for item in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name=? AND sql IS NOT NULL",
            ("topic_report_runs",),
        ).fetchall()
    ]
    triggers = [
        (str(item[0]), str(item[1]))
        for item in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name=? AND sql IS NOT NULL",
            ("topic_report_runs",),
        ).fetchall()
    ]
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name=?", ("topic_report_runs",)
    ).fetchone()
    columns = [
        str(item[1])
        for item in connection.execute('PRAGMA table_info("topic_report_runs")')
    ]
    quoted = ", ".join(f'"{column}"' for column in columns)
    for name, _ in triggers:
        connection.execute(f'DROP TRIGGER IF EXISTS "{name}"')
    connection.execute(widened_sql)
    connection.execute(
        f'INSERT INTO "{temporary}" ({quoted}) SELECT {quoted} FROM "topic_report_runs"'
    )
    connection.execute('DROP TABLE "topic_report_runs"')
    connection.execute(f'ALTER TABLE "{temporary}" RENAME TO "topic_report_runs"')
    if sequence is not None:
        updated = connection.execute(
            "UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?",
            (sequence[0], "topic_report_runs"),
        ).rowcount
        if updated == 0:
            connection.execute(
                "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)",
                ("topic_report_runs", sequence[0]),
            )
    for statement in indexes:
        connection.execute(statement)
    for _, statement in triggers:
        connection.execute(statement)
