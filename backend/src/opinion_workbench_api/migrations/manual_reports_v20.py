"""v20: allow explicit manual selection while preserving every report graph."""

import sqlite3

from opinion_workbench_api.migrations.topic_reports_v16 import (
    _RUN_COLUMNS,
    _RUN_INDEX_SQL,
    _RUN_TABLE_SQL,
    _RUN_TRIGGER_SQL,
)


def migrate(connection: sqlite3.Connection) -> None:
    # The v16 schema is an immutable historical definition. Extend only origin;
    # sources, graph identities, retry ancestry and snapshot triggers stay intact.
    sql = _RUN_TABLE_SQL.replace(
        "trigger IN ('automatic','interval','retry')",
        "trigger IN ('automatic','interval','manual','retry')",
    ).replace("trigger='interval'", "trigger IN ('interval','manual')")
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='topic_report_runs'"
    ).fetchone()
    for name in _RUN_INDEX_SQL:
        connection.execute(f"DROP INDEX {name}")
    for name in _RUN_TRIGGER_SQL:
        connection.execute(f"DROP TRIGGER {name}")
    connection.execute(sql.format(table_name="topic_report_runs_v20"))
    columns = ",".join(_RUN_COLUMNS)
    connection.execute(
        f"INSERT INTO topic_report_runs_v20 ({columns}) "
        f"SELECT {columns} FROM topic_report_runs"
    )
    connection.execute("DROP TABLE topic_report_runs")
    connection.execute("ALTER TABLE topic_report_runs_v20 RENAME TO topic_report_runs")
    for statement in (*_RUN_INDEX_SQL.values(), *_RUN_TRIGGER_SQL.values()):
        connection.execute(statement)
    if sequence is not None:
        connection.execute(
            "UPDATE sqlite_sequence SET seq=? WHERE name='topic_report_runs'",
            (sequence[0],),
        )
