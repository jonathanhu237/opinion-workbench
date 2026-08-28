"""Additive v12 schema: independent evidence, durable claims and frozen intents."""

import hashlib
import sqlite3
from datetime import UTC, datetime

from longtian_api.schemas.analysis_settings import (
    DEFAULT_INITIAL_INSTRUCTIONS,
    DEFAULT_REPORT_INSTRUCTIONS,
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
)


def migrate(connection: sqlite3.Connection) -> None:
    # Called by the database owner inside its version-checked write transaction.
    statements = [
        """CREATE TABLE analysis_prompt_versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          stage TEXT NOT NULL CHECK(stage IN ('initial','report')),
          instructions TEXT NOT NULL CHECK(length(instructions) BETWEEN 1 AND 8000),
          content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
          schema_version TEXT NOT NULL, created_at TEXT NOT NULL
        )""",
        """CREATE TABLE analysis_settings (
          id INTEGER PRIMARY KEY CHECK(id=1),
          initial_prompt_version_id INTEGER NOT NULL REFERENCES
            analysis_prompt_versions(id),
          report_prompt_version_id INTEGER NOT NULL REFERENCES
            analysis_prompt_versions(id),
          enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
          approved_configuration_revision INTEGER
            CHECK(approved_configuration_revision>0),
          revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
          activation_content_id INTEGER NOT NULL CHECK(activation_content_id>=0),
          CHECK(enabled=0 OR approved_configuration_revision IS NOT NULL)
        )""",
        """CREATE TABLE content_analysis_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT UNIQUE,
          trigger TEXT NOT NULL CHECK(trigger IN ('manual','automatic')),
          automatic_origin TEXT UNIQUE,
          configuration_revision INTEGER NOT NULL CHECK(configuration_revision>0),
          base_url TEXT NOT NULL, model TEXT NOT NULL,
          initial_prompt_version_id INTEGER NOT NULL REFERENCES
            analysis_prompt_versions(id),
          report_prompt_version_id INTEGER NOT NULL REFERENCES
            analysis_prompt_versions(id),
          force_refresh INTEGER NOT NULL CHECK(force_refresh IN (0,1)),
          status TEXT NOT NULL CHECK(status IN
            ('queued','running','completed','cancelled',
            'interrupted','configuration_blocked')),
          queue_reason TEXT CHECK(queue_reason IN
            ('ai_operation_active','browser_operation_active')),
          created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
          CHECK((status IN ('queued','running'))=(finished_at IS NULL))
        )""",
        """CREATE TABLE content_analysis_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id INTEGER NOT NULL REFERENCES content_analysis_jobs(id) ON DELETE
            RESTRICT,
          content_id INTEGER NOT NULL REFERENCES search_contents(id) ON DELETE RESTRICT,
          source_run_id INTEGER NOT NULL,
          position INTEGER NOT NULL CHECK(position>=0),
          source_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
          observation_hash TEXT NOT NULL, cache_key TEXT NOT NULL,
          input_json TEXT, input_fingerprint TEXT, output_json TEXT,
          reused_from_attempt_id INTEGER REFERENCES content_analysis_attempts(id) ON
            DELETE RESTRICT,
          attempted INTEGER NOT NULL DEFAULT 0 CHECK(attempted IN (0,1)),
          usage_json TEXT, error_json TEXT,
          status TEXT NOT NULL CHECK(status IN
            ('queued','acquiring','analysing','completed',
            'input_incomplete','unsupported','failed','cancelled','interrupted')),
          created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
          UNIQUE(job_id,content_id), UNIQUE(job_id,position),
          FOREIGN KEY(source_run_id,content_id) REFERENCES
            search_run_contents(run_id,search_content_id),
          CHECK((status IN ('queued','acquiring','analysing'))=(finished_at IS NULL)),
          CHECK((status='completed')=(output_json IS NOT NULL)),
          CHECK(status!='completed' OR (input_json IS NOT NULL AND input_fingerprint
            IS NOT NULL
            AND error_json IS NULL AND (attempted=1 OR reused_from_attempt_id IS NOT
              NULL))),
          CHECK(usage_json IS NULL OR attempted=1),
          CHECK(reused_from_attempt_id IS NULL OR
            (reused_from_attempt_id<id AND status='completed' AND attempted=0 AND
              usage_json IS NULL))
        )""",
        """CREATE INDEX ix_content_analysis_attempts_content ON
          content_analysis_attempts(content_id,id DESC)""",
        """CREATE INDEX ix_content_analysis_attempts_cache ON
          content_analysis_attempts(cache_key,id DESC)
           WHERE status='completed' AND reused_from_attempt_id IS NULL""",
        """CREATE TABLE content_analysis_claims (
          content_id INTEGER PRIMARY KEY REFERENCES search_contents(id) ON DELETE
            RESTRICT,
          eligibility_origin TEXT NOT NULL CHECK(eligibility_origin IN
            ('new','historical')),
          discovery_run_id INTEGER,
          auto_ready INTEGER NOT NULL DEFAULT 0 CHECK(auto_ready IN (0,1)),
          legacy_state TEXT CHECK(legacy_state IN
            ('legacy_completed','legacy_attempted')),
          first_attempt_id INTEGER REFERENCES content_analysis_attempts(id),
          latest_attempt_id INTEGER REFERENCES content_analysis_attempts(id),
          active_job_id INTEGER REFERENCES content_analysis_jobs(id),
          active_legacy_summary_id INTEGER REFERENCES ai_summary_runs(id),
          known_input_fingerprint TEXT,
          FOREIGN KEY(discovery_run_id,content_id) REFERENCES
            search_run_contents(run_id,search_content_id),
          CHECK(active_job_id IS NULL OR active_legacy_summary_id IS NULL)
        )""",
        """CREATE TABLE content_analysis_requests (
          request_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL,
          job_id INTEGER REFERENCES content_analysis_jobs(id),
          admitted_count INTEGER NOT NULL CHECK(admitted_count>=0),
          already_active_count INTEGER NOT NULL CHECK(already_active_count>=0)
        )""",
        """CREATE TABLE analysis_completion_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id INTEGER NOT NULL UNIQUE REFERENCES content_analysis_jobs(id) ON
            DELETE RESTRICT,
          settled_at TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','consumed'))
        )""",
        """CREATE TABLE collection_analysis_handoffs (
          origin TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          job_id INTEGER REFERENCES content_analysis_jobs(id)
        )""",
        """CREATE TRIGGER analysis_prompt_immutable BEFORE UPDATE ON
          analysis_prompt_versions
           BEGIN SELECT RAISE(ABORT,'immutable prompt'); END""",
        """CREATE TRIGGER analysis_attempt_terminal_immutable BEFORE UPDATE ON
          content_analysis_attempts
           WHEN OLD.status NOT IN ('queued','acquiring','analysing')
           BEGIN SELECT RAISE(ABORT,'immutable terminal attempt'); END""",
        """CREATE TRIGGER analysis_attempt_snapshot_immutable
           BEFORE UPDATE OF job_id,content_id,source_run_id,position,source_json,
             first_seen_at,observation_hash,cache_key,created_at
           ON content_analysis_attempts
           BEGIN SELECT RAISE(ABORT,'immutable attempt snapshot'); END""",
        """CREATE TRIGGER analysis_job_snapshot_immutable
           BEFORE UPDATE OF request_id,trigger,automatic_origin,
             configuration_revision,base_url,model,initial_prompt_version_id,
             report_prompt_version_id,force_refresh,created_at
           ON content_analysis_jobs
           BEGIN SELECT RAISE(ABORT,'immutable job snapshot'); END""",
        """CREATE TRIGGER legacy_analysis_claim_guard BEFORE INSERT ON ai_summary_items
           WHEN EXISTS (SELECT 1 FROM content_analysis_claims WHERE
             content_id=NEW.content_id
             AND active_job_id IS NOT NULL)
           BEGIN SELECT RAISE(ABORT,'content already claimed'); END""",
        """CREATE TRIGGER legacy_analysis_claim_insert AFTER INSERT ON ai_summary_items
           BEGIN UPDATE content_analysis_claims SET
             legacy_state=CASE WHEN legacy_state='legacy_completed' OR
               NEW.status='completed'
               THEN 'legacy_completed' ELSE 'legacy_attempted' END,
             active_legacy_summary_id=CASE WHEN EXISTS(SELECT 1 FROM ai_summary_runs
               WHERE id=NEW.summary_run_id AND status IN ('queued','running'))
               THEN NEW.summary_run_id ELSE active_legacy_summary_id END
             WHERE content_id=NEW.content_id; END""",
        """CREATE TRIGGER legacy_analysis_claim_finish AFTER UPDATE OF status ON
          ai_summary_items
           WHEN NEW.status='completed'
           BEGIN UPDATE content_analysis_claims SET legacy_state='legacy_completed'
             WHERE content_id=NEW.content_id; END""",
        """CREATE TRIGGER legacy_analysis_claim_release AFTER UPDATE OF status ON
          ai_summary_runs
           WHEN NEW.status NOT IN ('queued','running')
           BEGIN UPDATE content_analysis_claims SET active_legacy_summary_id=NULL
             WHERE active_legacy_summary_id=NEW.id; END""",
        """CREATE TRIGGER legacy_analysis_known_input AFTER UPDATE OF input_hash ON
          ai_summary_items
           WHEN NEW.input_hash IS NOT NULL AND NEW.input_json IS NOT NULL
           BEGIN UPDATE content_analysis_claims SET
             known_input_fingerprint=NEW.input_hash
             WHERE content_id=NEW.content_id AND
               active_legacy_summary_id=NEW.summary_run_id; END""",
    ]
    for statement in statements:
        connection.execute(statement)
    now = datetime.now(UTC).isoformat()
    ids = []
    for stage, text, schema in (
        ("initial", DEFAULT_INITIAL_INSTRUCTIONS, INITIAL_SCHEMA_VERSION),
        ("report", DEFAULT_REPORT_INSTRUCTIONS, REPORT_SCHEMA_VERSION),
    ):
        ids.append(
            connection.execute(
                """INSERT INTO
                  analysis_prompt_versions(stage,instructions,content_hash,
                    schema_version,created_at) VALUES (?,?,?,?,?)""",
                (stage, text, hashlib.sha256(text.encode()).hexdigest(), schema, now),
            ).lastrowid
        )
    connection.execute(
        """INSERT INTO
          analysis_settings(id,initial_prompt_version_id,report_prompt_version_id,activation_content_id)
           VALUES (1,?,?,(SELECT COALESCE(MAX(id),0) FROM search_contents))""",
        ids,
    )
    connection.execute("""
      INSERT INTO
        content_analysis_claims(content_id,eligibility_origin,discovery_run_id,
        legacy_state,active_legacy_summary_id)
      SELECT c.id,'historical',
        (SELECT MIN(run_id) FROM search_run_contents WHERE search_content_id=c.id),
        CASE WHEN EXISTS(SELECT 1 FROM ai_summary_items WHERE content_id=c.id AND
          status='completed')
          THEN 'legacy_completed'
          WHEN EXISTS(SELECT 1 FROM ai_summary_items WHERE content_id=c.id) THEN
            'legacy_attempted' END,
        (SELECT i.summary_run_id FROM ai_summary_items i JOIN ai_summary_runs r ON
          r.id=i.summary_run_id
          WHERE i.content_id=c.id AND r.status IN ('queued','running') ORDER BY i.id
            DESC LIMIT 1)
      FROM search_contents c
    """)
    connection.execute("""UPDATE content_analysis_claims SET known_input_fingerprint=(
      SELECT i.input_hash FROM ai_summary_items i WHERE
        i.content_id=content_analysis_claims.content_id
        AND i.input_json IS NOT NULL AND i.input_hash IS NOT NULL ORDER BY i.id DESC
          LIMIT 1)""")
