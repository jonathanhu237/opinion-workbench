"""v14: append immutable report graphs; no old evidence or authorization rewrite."""

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE topic_report_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT UNIQUE,
          workflow_operation_key TEXT UNIQUE,
          trigger TEXT NOT NULL CHECK(trigger IN ('automatic','interval','retry')),
          initial_job_id INTEGER REFERENCES content_analysis_jobs(id) ON DELETE
          RESTRICT,
          completion_event_id INTEGER UNIQUE REFERENCES
          analysis_completion_events(id) ON DELETE RESTRICT,
          parent_report_id INTEGER REFERENCES topic_report_runs(id) ON DELETE RESTRICT,
          selection_json TEXT NOT NULL, prompt_json TEXT NOT NULL,
          configuration_revision INTEGER NOT NULL CHECK(configuration_revision
          BETWEEN 1 AND 9007199254740991),
          base_url TEXT NOT NULL, model TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('queued','judging','composing',
          'completed',
            'empty','failed','cancelled','interrupted','configuration_blocked')),
          revision INTEGER NOT NULL DEFAULT 1 CHECK(revision BETWEEN 1 AND
          9007199254740991),
          cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
          root_section_id INTEGER REFERENCES topic_report_nodes(id) ON DELETE RESTRICT,
          empty_reason TEXT CHECK(empty_reason IN ('no_ready_sources',
          'no_relevant_sources')),
          queue_reason TEXT CHECK(queue_reason='ai_operation_active'),
          recovery_reason TEXT CHECK(recovery_reason='backend_restart'),
          error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
          CHECK((status IN ('queued','judging','composing'))=(finished_at IS NULL)),
          CHECK((status='completed')=(root_section_id IS NOT NULL)),
          CHECK((status='empty')=(empty_reason IS NOT NULL)),
          CHECK((trigger='automatic' AND request_id IS NULL AND parent_report_id IS NULL
            AND ((completion_event_id IS NOT NULL AND initial_job_id IS NOT NULL
                  AND workflow_operation_key IS NULL)
              OR (completion_event_id IS NULL
                  AND workflow_operation_key IS NOT NULL))) OR
            (trigger='interval' AND request_id IS NOT NULL AND completion_event_id
          IS NULL AND workflow_operation_key IS NULL
            AND initial_job_id IS NULL AND parent_report_id IS NULL) OR
            (trigger='retry' AND request_id IS NOT NULL AND completion_event_id IS NULL
            AND workflow_operation_key IS NULL
            AND parent_report_id IS NOT NULL)),
          CHECK(parent_report_id IS NULL OR parent_report_id<id)
        )""",
        """CREATE TABLE topic_report_sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          report_id INTEGER NOT NULL REFERENCES topic_report_runs(id) ON DELETE
          RESTRICT,
          content_id INTEGER NOT NULL REFERENCES search_contents(id) ON DELETE RESTRICT,
          position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 9007199254740991),
          source_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
          initial_attempt_id INTEGER REFERENCES content_analysis_attempts(id) ON
          DELETE RESTRICT,
          initial_status TEXT,
          unavailable_reason TEXT CHECK(unavailable_reason IN ('not_analysed',
          'legacy_only',
            'in_progress','input_incomplete','unsupported','failed','cancelled',
          'interrupted','stale_evidence')),
          evidence_json TEXT,
          UNIQUE(report_id,content_id), UNIQUE(report_id,position),
          CHECK((unavailable_reason IS NULL)=(evidence_json IS NOT NULL)),
          CHECK(evidence_json IS NULL OR (initial_attempt_id IS NOT NULL AND
          initial_status='completed'))
        )""",
        """CREATE TABLE topic_report_nodes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          report_id INTEGER NOT NULL REFERENCES topic_report_runs(id) ON DELETE
          RESTRICT,
          node_key TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('judgment',
          'leaf','overview')),
          position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 9007199254740991),
          level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 9007199254740991),
          status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN
            ('queued','running','completed','failed','cancelled','interrupted')),
          engine_version TEXT, input_hash TEXT, prepared_json TEXT, request_hash TEXT,
          output_json TEXT, output_hash TEXT, membership_hash TEXT,
          attempted INTEGER NOT NULL DEFAULT 0 CHECK(attempted IN (0,1)),
          usage_json TEXT, error_json TEXT,
          reused_from_node_id INTEGER REFERENCES topic_report_nodes(id) ON DELETE
          RESTRICT,
          created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
          UNIQUE(report_id,node_key), UNIQUE(report_id,kind,level,position),
          CHECK((status IN ('queued','running'))=(finished_at IS NULL)),
          CHECK((status='completed')=(output_json IS NOT NULL AND output_hash IS NOT
          NULL)),
          CHECK(usage_json IS NULL OR attempted=1),
          CHECK(reused_from_node_id IS NULL OR
            (status='completed' AND attempted=0 AND usage_json IS NULL
              AND reused_from_node_id<id)),
          CHECK((kind='overview' AND level>0) OR (kind!='overview' AND level=0))
        )""",
        """CREATE TABLE topic_report_node_sources (
          node_id INTEGER NOT NULL REFERENCES topic_report_nodes(id) ON DELETE RESTRICT,
          source_id INTEGER NOT NULL REFERENCES topic_report_sources(id) ON DELETE
          RESTRICT,
          position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 9007199254740991),
          PRIMARY KEY(node_id,source_id), UNIQUE(node_id,position)
        )""",
        """CREATE TABLE topic_report_node_children (
          node_id INTEGER NOT NULL REFERENCES topic_report_nodes(id) ON DELETE RESTRICT,
          child_id INTEGER NOT NULL REFERENCES topic_report_nodes(id) ON DELETE
          RESTRICT,
          position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 7),
          PRIMARY KEY(node_id,position), UNIQUE(node_id,child_id),
          CHECK(node_id!=child_id)
        )""",
        """CREATE TABLE topic_report_requests (
          request_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL,
          report_id INTEGER NOT NULL REFERENCES topic_report_runs(id) ON DELETE RESTRICT
        )""",
        """CREATE INDEX ix_topic_report_history ON topic_report_runs(initial_job_id,
          id DESC)""",
        """CREATE INDEX ix_topic_report_queue ON topic_report_runs(id) WHERE
          status='queued'""",
        """CREATE INDEX ix_topic_report_source_history ON
          topic_report_sources(content_id,
          report_id)""",
        """CREATE INDEX ix_topic_report_nodes ON topic_report_nodes(report_id,kind,
          level,position)""",
        """CREATE TRIGGER topic_report_source_immutable BEFORE UPDATE ON
          topic_report_sources
          BEGIN SELECT RAISE(ABORT,'immutable report source'); END""",
        """CREATE TRIGGER topic_report_snapshot_immutable BEFORE UPDATE OF
          request_id,workflow_operation_key,trigger,
          initial_job_id,completion_event_id,parent_report_id,selection_json,
          prompt_json,
          configuration_revision,base_url,model,created_at ON topic_report_runs
          BEGIN SELECT RAISE(ABORT,'immutable report snapshot'); END""",
        """CREATE TRIGGER topic_report_terminal_immutable BEFORE UPDATE ON
          topic_report_runs
          WHEN OLD.status NOT IN ('queued','judging','composing')
          BEGIN SELECT RAISE(ABORT,'immutable terminal report'); END""",
        """CREATE TRIGGER topic_report_node_terminal_immutable BEFORE UPDATE ON
          topic_report_nodes
          WHEN OLD.status NOT IN ('queued','running')
          BEGIN SELECT RAISE(ABORT,'immutable terminal report node'); END""",
        """CREATE TRIGGER topic_report_node_snapshot_immutable
          BEFORE UPDATE OF report_id,node_key,kind,position,level,created_at
          ON topic_report_nodes
          BEGIN SELECT RAISE(ABORT,'immutable report node identity'); END""",
        """CREATE TRIGGER topic_report_node_plan_immutable BEFORE UPDATE OF
          input_hash,membership_hash,engine_version ON topic_report_nodes
          WHEN (OLD.input_hash IS NOT NULL AND NEW.input_hash IS NOT OLD.input_hash)
            OR (OLD.membership_hash IS NOT NULL
              AND NEW.membership_hash IS NOT OLD.membership_hash)
            OR (OLD.engine_version IS NOT NULL
              AND NEW.engine_version IS NOT OLD.engine_version)
          BEGIN SELECT RAISE(ABORT,'immutable report node plan'); END""",
        """CREATE TRIGGER topic_report_members_immutable BEFORE UPDATE
          ON topic_report_node_sources
          BEGIN SELECT RAISE(ABORT,'immutable report members'); END""",
        """CREATE TRIGGER topic_report_children_immutable BEFORE UPDATE
          ON topic_report_node_children
          BEGIN SELECT RAISE(ABORT,'immutable report children'); END""",
        """CREATE TRIGGER topic_report_member_guard BEFORE INSERT ON
          topic_report_node_sources
          WHEN NOT EXISTS(SELECT 1 FROM topic_report_nodes n JOIN topic_report_sources s
            ON s.report_id=n.report_id WHERE n.id=NEW.node_id AND s.id=NEW.source_id
            AND n.status='queued' AND n.input_hash IS NULL)
          BEGIN SELECT RAISE(ABORT,'invalid report member'); END""",
        """CREATE TRIGGER topic_report_child_guard BEFORE INSERT ON
          topic_report_node_children
          WHEN NOT EXISTS(SELECT 1 FROM topic_report_nodes p JOIN topic_report_nodes c
            ON c.report_id=p.report_id WHERE p.id=NEW.node_id AND c.id=NEW.child_id
            AND p.kind='overview' AND p.status='queued' AND p.input_hash IS NULL
            AND c.kind!='judgment' AND c.status='completed'
          AND c.level<p.level)
          BEGIN SELECT RAISE(ABORT,'invalid report child'); END""",
    )
    for statement in statements:
        connection.execute(statement)
