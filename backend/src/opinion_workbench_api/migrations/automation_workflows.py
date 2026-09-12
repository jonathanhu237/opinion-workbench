"""v15: durable fixed-pipeline automatic opinion workflows."""

# SQL constraints are kept readable as schema-shaped blocks.
# ruff: noqa: E501

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    """Create automation state without rewriting any prior aggregate."""
    # The batch adapter uses the same durable operation key as the workflow
    # stage.  It lives on the proven batch aggregate so a process crash between
    # child creation and workflow-link persistence can be replayed safely.
    connection.execute(
        "ALTER TABLE search_batches ADD COLUMN workflow_operation_key TEXT"
    )
    connection.execute(
        """CREATE UNIQUE INDEX ux_search_batches_workflow_operation
           ON search_batches(workflow_operation_key)
           WHERE workflow_operation_key IS NOT NULL"""
    )
    statements = (
        """CREATE TABLE automation_tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
          normalized_name TEXT NOT NULL UNIQUE,
          monitoring_rule_id INTEGER REFERENCES monitoring_rules(id)
            ON DELETE SET NULL,
          max_results_per_term INTEGER NOT NULL DEFAULT 10 CHECK(
            typeof(max_results_per_term)='integer' AND max_results_per_term BETWEEN 1 AND 50),
          analysis_goal TEXT NOT NULL CHECK(length(analysis_goal) BETWEEN 1 AND 4000),
          schedule_kind TEXT NOT NULL CHECK(schedule_kind IN ('interval','daily')),
          interval_minutes INTEGER CHECK(interval_minutes IS NULL OR
            (typeof(interval_minutes)='integer' AND interval_minutes BETWEEN 1 AND 43200)),
          daily_time TEXT,
          timezone TEXT,
          enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
          revision INTEGER NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 9007199254740991),
          next_due_at TEXT,
          anchor_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          CHECK((schedule_kind='interval' AND interval_minutes IS NOT NULL
                 AND daily_time IS NULL AND timezone IS NULL)
             OR (schedule_kind='daily' AND interval_minutes IS NULL
                 AND daily_time IS NOT NULL AND timezone IS NOT NULL)),
          CHECK((enabled=0 AND next_due_at IS NULL AND anchor_at IS NULL)
             OR (enabled=1 AND next_due_at IS NOT NULL AND anchor_at IS NOT NULL))
        )""",
        """CREATE TABLE automation_task_platforms (
          task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 4),
          platform TEXT NOT NULL CHECK(platform IN ('toutiao','wb','ks','dy','xhs')),
          PRIMARY KEY(task_id, position), UNIQUE(task_id, platform)
        )""",
        """CREATE TABLE automation_occurrences (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          task_revision INTEGER NOT NULL CHECK(task_revision BETWEEN 1 AND 9007199254740991),
          due_at TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('claimed','admitted','skipped','missed','interrupted')),
          reason TEXT CHECK(reason IN ('previous_run_active','browser_operation_active',
            'browser_unavailable','monitoring_rule_not_found','monitoring_rule_disabled',
            'invalid_monitoring_rule','too_many_search_terms','configuration_unavailable',
            'offline','clock_jump','storage_unavailable','dispatch_interrupted')),
          run_id INTEGER UNIQUE REFERENCES automation_runs(id) ON DELETE RESTRICT,
          missed_count INTEGER NOT NULL DEFAULT 0 CHECK(missed_count>=0),
          missed_until TEXT,
          created_at TEXT NOT NULL,
          admitted_at TEXT,
          UNIQUE(task_id, task_revision, due_at),
          CHECK((status='claimed' AND reason IS NULL AND run_id IS NULL)
            OR (status='admitted' AND reason IS NULL AND run_id IS NOT NULL)
            OR (status='skipped' AND reason IS NOT NULL AND run_id IS NULL
                AND missed_count=0 AND missed_until IS NULL)
            OR (status='missed' AND reason IN ('offline','clock_jump') AND run_id IS NULL
                AND missed_count>0 AND missed_until IS NOT NULL)
            OR (status='interrupted' AND reason='dispatch_interrupted' AND run_id IS NULL)),
          CHECK((status='missed')=(missed_count>0 AND missed_until IS NOT NULL))
        )""",
        """CREATE TABLE automation_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          admission_key TEXT NOT NULL UNIQUE,
          request_id TEXT UNIQUE,
          task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          trigger TEXT NOT NULL CHECK(trigger IN ('scheduled','manual')),
          task_revision INTEGER NOT NULL CHECK(task_revision BETWEEN 1 AND 9007199254740991),
          snapshot_json TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('queued','collecting','analysing','reporting',
            'completed','failed','cancelled','interrupted','configuration_blocked')),
          active_stage TEXT CHECK(active_stage IN ('collection','initial_analysis','topic_report')),
          cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
          outcome TEXT CHECK(outcome IN ('completed','no_new_sources','cancelled')),
          topic_report_id INTEGER,
          error_json TEXT,
          revision INTEGER NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND 9007199254740991),
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          CHECK((status IN ('queued','collecting','analysing','reporting'))=(finished_at IS NULL)),
          CHECK(status!='completed' OR outcome IS NOT NULL)
        )""",
        """CREATE TABLE automation_stage_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE RESTRICT,
          stage TEXT NOT NULL CHECK(stage IN ('collection','initial_analysis','topic_report')),
          attempt_number INTEGER NOT NULL CHECK(attempt_number>=1),
          operation_key TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed',
            'cancelled','interrupted','configuration_blocked')),
          child_kind TEXT,
          child_id INTEGER,
          input_hash TEXT,
          output_hash TEXT,
          input_count INTEGER NOT NULL DEFAULT 0 CHECK(input_count>=0),
          success_count INTEGER NOT NULL DEFAULT 0 CHECK(success_count>=0),
          failure_count INTEGER NOT NULL DEFAULT 0 CHECK(failure_count>=0),
          usage_attempted INTEGER NOT NULL DEFAULT 0 CHECK(usage_attempted>=0),
          usage_tokens INTEGER CHECK(usage_tokens IS NULL OR usage_tokens>=0),
          error_json TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          UNIQUE(run_id,stage,attempt_number),
          CHECK((status IN ('queued','running'))=(finished_at IS NULL)),
          CHECK(success_count+failure_count<=input_count)
        )""",
        """CREATE TABLE automation_task_contents (
          task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          content_id INTEGER NOT NULL REFERENCES search_contents(id) ON DELETE RESTRICT,
          first_run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE RESTRICT,
          first_collection_run_id INTEGER,
          first_seen_at TEXT NOT NULL,
          PRIMARY KEY(task_id,content_id)
        )""",
        """CREATE TABLE automation_run_contents (
          run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE RESTRICT,
          task_id INTEGER NOT NULL REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          content_id INTEGER NOT NULL REFERENCES search_contents(id) ON DELETE RESTRICT,
          position INTEGER NOT NULL CHECK(position>=0),
          PRIMARY KEY(run_id,content_id), UNIQUE(run_id,position)
        )""",
        """CREATE TABLE automation_requests (
          request_id TEXT PRIMARY KEY,
          action TEXT NOT NULL CHECK(action IN ('run_now','cancel','retry')),
          task_id INTEGER REFERENCES automation_tasks(id) ON DELETE RESTRICT,
          run_id INTEGER REFERENCES automation_runs(id) ON DELETE RESTRICT,
          intent_hash TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        )""",
        """CREATE TRIGGER automation_task_rule_deleted AFTER UPDATE OF
          monitoring_rule_id ON automation_tasks
          WHEN NEW.monitoring_rule_id IS NULL AND OLD.monitoring_rule_id IS NOT NULL
          BEGIN
            UPDATE automation_tasks SET enabled=0,next_due_at=NULL,anchor_at=NULL
              WHERE id=NEW.id;
          END""",
        "CREATE INDEX ix_automation_tasks_due ON automation_tasks(next_due_at,id) WHERE enabled=1",
        "CREATE INDEX ix_automation_occurrences_history ON automation_occurrences(task_id,id DESC)",
        "CREATE INDEX ix_automation_runs_task_history ON automation_runs(task_id,id DESC)",
        "CREATE INDEX ix_automation_runs_active ON automation_runs(task_id,id) WHERE status IN ('queued','collecting','analysing','reporting')",
        "CREATE INDEX ix_automation_stage_attempts_run ON automation_stage_attempts(run_id,stage,attempt_number)",
        "CREATE INDEX ix_automation_task_contents_content ON automation_task_contents(content_id,task_id)",
        "CREATE INDEX ix_automation_run_contents_run ON automation_run_contents(run_id,position)",
        """CREATE TRIGGER automation_run_snapshot_immutable BEFORE UPDATE OF
          admission_key,request_id,task_id,trigger,task_revision,snapshot_json,created_at
          ON automation_runs BEGIN SELECT RAISE(ABORT,'immutable automation snapshot'); END""",
        """CREATE TRIGGER automation_stage_identity_immutable BEFORE UPDATE OF
          run_id,stage,attempt_number,operation_key,created_at
          ON automation_stage_attempts BEGIN SELECT RAISE(ABORT,'immutable automation attempt'); END""",
        """CREATE TRIGGER automation_terminal_attempt_immutable BEFORE UPDATE ON
          automation_stage_attempts WHEN OLD.status NOT IN ('queued','running')
          BEGIN SELECT RAISE(ABORT,'immutable terminal automation attempt'); END""",
        """CREATE TRIGGER automation_task_content_immutable BEFORE UPDATE ON
          automation_task_contents BEGIN SELECT RAISE(ABORT,'immutable task membership'); END""",
    )
    for statement in statements:
        connection.execute(statement)
