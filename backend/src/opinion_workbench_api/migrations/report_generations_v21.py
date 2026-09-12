"""Manual report ownership and saved acquisition, separate from automation."""


def migrate(connection):
    connection.execute("""CREATE TABLE report_generations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL UNIQUE,
        intent_json TEXT NOT NULL,
        intent_hash TEXT NOT NULL,
        analysis_job_id INTEGER NOT NULL UNIQUE
            REFERENCES content_analysis_jobs(id) ON DELETE RESTRICT,
        report_request_id TEXT NOT NULL UNIQUE,
        report_id INTEGER UNIQUE REFERENCES topic_report_runs(id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK(status IN (
            'summarising','reporting','completed','empty','failed',
            'configuration_blocked','cancelled','interrupted')),
        created_at TEXT NOT NULL,
        finished_at TEXT,
        CHECK((status IN ('summarising','reporting')) = (finished_at IS NULL)),
        CHECK(status NOT IN ('reporting','completed','empty') OR report_id IS NOT NULL)
    )""")
    connection.execute("""CREATE TRIGGER report_generation_intent_immutable
        BEFORE UPDATE ON report_generations WHEN
        NEW.request_id IS NOT OLD.request_id OR NEW.intent_json IS NOT OLD.intent_json
        OR NEW.intent_hash IS NOT OLD.intent_hash
        OR NEW.analysis_job_id IS NOT OLD.analysis_job_id
        OR NEW.report_request_id IS NOT OLD.report_request_id
        OR NEW.created_at IS NOT OLD.created_at
        OR (OLD.report_id IS NOT NULL AND NEW.report_id IS NOT OLD.report_id)
        BEGIN SELECT RAISE(ABORT, 'immutable report generation intent'); END""")
    connection.execute("""CREATE INDEX ix_report_generations_status
        ON report_generations(status,id)""")
    connection.execute("""CREATE TABLE content_materials (
        content_id INTEGER PRIMARY KEY
            REFERENCES search_contents(id) ON DELETE RESTRICT,
        observation_hash TEXT NOT NULL,
        input_json TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL,
        saved_at TEXT NOT NULL
    )""")
