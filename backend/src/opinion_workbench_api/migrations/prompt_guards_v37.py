"""Refresh v18 default-template guards after the v34 text-only transition.

Only admission guards change; immutable jobs, prompt rows and reports retain
exactly the snapshots with which they were originally created.
"""

import sqlite3

from opinion_workbench_api.repositories.analysis_settings import resolve_prompt_choice
from opinion_workbench_api.schemas.analysis_settings import (
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)


def migrate(connection: sqlite3.Connection) -> None:
    initial = resolve_prompt_choice(connection, "initial", {"mode": "default"})
    report = resolve_prompt_choice(connection, "report", {"mode": "default"})
    columns = (
        "initial_prompt_mode,initial_prompt_version_id,"
        "report_prompt_mode,report_prompt_version_id"
    )
    for prefix, table, modes in (
        ("analysis_job", "content_analysis_jobs", "'default','custom','legacy'"),
        ("automation_task", "automation_tasks", "'default','custom'"),
    ):
        task = table == "automation_tasks"
        extra = (
            """
          OR NOT EXISTS (SELECT 1 FROM analysis_prompt_versions p
            WHERE p.id=NEW.report_prompt_version_id
              AND (p.instructions=NEW.analysis_goal
                OR NEW.analysis_goal='使用已保存提示词版本 '||p.id))
          OR (NEW.report_prompt_mode='default' AND NOT EXISTS
            (SELECT 1 FROM analysis_prompt_versions p
             WHERE p.id=NEW.report_prompt_version_id
               AND p.instructions=NEW.analysis_goal))
        """
            if task
            else ""
        )
        for action in ("insert", "update"):
            name = f"{prefix}_prompt_{action}"
            message = f"{prefix.replace('_', ' ')} prompt choice is invalid"
            event = (
                "INSERT"
                if action == "insert"
                else (f"UPDATE OF {columns}" + (",analysis_goal" if task else ""))
            )
            connection.execute(f"DROP TRIGGER IF EXISTS {name}")
            connection.execute(f"""CREATE TRIGGER {name}
              BEFORE {event} ON {table}
              WHEN NEW.initial_prompt_version_id IS NULL
                OR NEW.report_prompt_version_id IS NULL
                OR NEW.initial_prompt_mode NOT IN ({modes})
                OR NEW.report_prompt_mode NOT IN ({modes})
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
                       analysis_prompt_versions WHERE id={initial.version_id})))
                OR (NEW.report_prompt_mode='default' AND NOT EXISTS
                  (SELECT 1 FROM analysis_prompt_versions p
                   WHERE p.id=NEW.report_prompt_version_id
                     AND p.instructions=(SELECT instructions FROM
                       analysis_prompt_versions WHERE id={report.version_id})))
                {extra}
              BEGIN
                SELECT RAISE(ABORT, '{message}');
              END""")
