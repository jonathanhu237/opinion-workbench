"""v13: append scheduling history, retaining every existing collection/AI row."""

import sqlite3


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE collection_schedules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      monitoring_rule_id INTEGER REFERENCES monitoring_rules(id) ON DELETE SET NULL,
      rule_name TEXT NOT NULL,
      max_results_per_term INTEGER NOT NULL
        CHECK(max_results_per_term BETWEEN 1 AND 50),
      interval_minutes INTEGER NOT NULL CHECK(typeof(interval_minutes)='integer'
        AND interval_minutes BETWEEN 1 AND 43200),
      enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
      revision INTEGER NOT NULL DEFAULT 1
        CHECK(revision BETWEEN 1 AND 9007199254740991),
      anchor_at TEXT, next_due_at TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      CHECK((enabled=0 AND anchor_at IS NULL AND next_due_at IS NULL) OR
            (enabled=1 AND anchor_at IS NOT NULL AND next_due_at IS NOT NULL))
    )""")
    connection.execute("""CREATE TABLE collection_schedule_platforms (
      schedule_id INTEGER NOT NULL REFERENCES collection_schedules(id)
        ON DELETE RESTRICT,
      position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 4),
      platform TEXT NOT NULL CHECK(platform IN ('toutiao','wb','ks','dy','xhs')),
      PRIMARY KEY(schedule_id, position), UNIQUE(schedule_id, platform)
    )""")
    connection.execute("""CREATE TABLE collection_occurrences (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      schedule_id INTEGER NOT NULL REFERENCES collection_schedules(id)
        ON DELETE RESTRICT,
      schedule_revision INTEGER NOT NULL
        CHECK(schedule_revision BETWEEN 1 AND 9007199254740991),
      due_at TEXT NOT NULL,
      dispatch_token TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL CHECK(status IN
        ('claimed','dispatched','skipped','missed','interrupted')),
      reason TEXT CHECK(reason IN ('browser_operation_active','browser_unavailable',
        'monitoring_rule_not_found','monitoring_rule_disabled','invalid_monitoring_rule',
        'too_many_search_terms','schedule_changed','storage_unavailable',
        'dispatch_interrupted','offline','clock_jump')),
      batch_id INTEGER UNIQUE REFERENCES search_batches(id) ON DELETE RESTRICT,
      missed_count INTEGER NOT NULL DEFAULT 0
        CHECK(missed_count BETWEEN 0 AND 9007199254740991),
      missed_until TEXT,
      created_at TEXT NOT NULL, dispatched_at TEXT, launch_started_at TEXT,
      UNIQUE(schedule_id,schedule_revision,due_at),
      CHECK((batch_id IS NULL AND dispatched_at IS NULL
             AND launch_started_at IS NULL) OR
            (batch_id IS NOT NULL AND dispatched_at IS NOT NULL)),
      CHECK((status='claimed' AND reason IS NULL AND batch_id IS NULL) OR
            (status='dispatched' AND reason IS NULL AND batch_id IS NOT NULL) OR
            (status='skipped' AND batch_id IS NULL AND reason IS NOT NULL AND
              reason NOT IN ('offline','clock_jump','dispatch_interrupted')) OR
            (status='missed' AND batch_id IS NULL AND reason IS NOT NULL
              AND reason IN ('offline','clock_jump')) OR
            (status='interrupted' AND reason IS NOT NULL
              AND reason='dispatch_interrupted')),
      CHECK((status='missed' AND missed_count>0 AND missed_until IS NOT NULL) OR
            (status!='missed' AND missed_count=0 AND missed_until IS NULL))
    )""")
    connection.execute("""CREATE INDEX ix_collection_schedules_due
      ON collection_schedules(next_due_at,id) WHERE enabled=1""")
    connection.execute("""CREATE INDEX ix_collection_occurrences_history
      ON collection_occurrences(schedule_id,id DESC)""")
