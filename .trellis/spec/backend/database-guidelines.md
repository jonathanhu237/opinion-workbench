# Database Guidelines

> SQLite persistence conventions for the local single-user application.

## Overview

The product uses Python's standard-library `sqlite3` module for small local aggregates. The first
database-backed aggregate is monitoring rules. Add an ORM or async database package only when a
separately approved feature demonstrates that explicit SQL and connection-per-operation no longer
fit the data model.

The default product database is `runtime/longtian.sqlite3`. `runtime/` is user-owned local state and
must be ignored by Git, including SQLite WAL and SHM sidecars. Do not place product data in the
unrelated `db_data/` PostgreSQL directory or in source/package folders.

## Layer ownership

```text
API route -> service -> repository -> sqlite3
```

- Routes own HTTP translation and public response models.
- Services own normalization, semantic validation, product errors, and typed projections.
- Repositories own connection creation, bound SQL, transactions, row assembly, and ordering.
- Database path resolution and migrations have one backend owner; routes and services never rebuild
  the path.
- Frontend components never know table or migration details.

## Connections and queries

- Open and close one connection per repository operation in the same worker thread.
- Use synchronous service/repository functions from plain `def` FastAPI path operations. If startup
  needs synchronous migration work inside async lifespan, call it through `run_in_threadpool`.
- Do not store `sqlite3.Connection` in application state and do not set `check_same_thread=False`.
- Configure every connection with `sqlite3.Row`, `PRAGMA foreign_keys = ON`, and a bounded five-second
  busy timeout. Enable WAL during initialization.
- Bind every product value as a SQL parameter. Never interpolate values into SQL.
- Return rows in an explicit deterministic order; never rely on SQLite's incidental row order.
- Keep network, browser, model, and filesystem-export work outside database transactions.

## Transactions

- Use `isolation_level=None` with explicit `BEGIN IMMEDIATE`, `COMMIT`, and `ROLLBACK` for writes.
- A service operation that replaces an aggregate and its children is one transaction. Partial parent
  or child updates are invalid.
- Keep transactions short and rollback on every exception before closing the connection.
- Read multi-query aggregate projections in one explicit read transaction. A batch item, its latest
  attempt, proof prefix and result counts must describe the same SQLite snapshot, not four points
  in time. This still allows legitimate transitions between separately committed run/item records.
- Async services that own a browser/runner must await `services/settled_tasks.database_call` for
  writes and drain the thread on cancellation before terminalization or releasing ownership.
  Cancelling the await of plain `asyncio.to_thread` does not cancel the SQLite transaction. Keep
  active-run/current-attempt guards inside writes as a second fence against late callbacks.
- Enforce invariants in both service validation (clear product feedback) and database constraints
  (race/corruption guard).

## Migrations and seed data

- Use SQLite `PRAGMA user_version` as the application-owned schema version.
- Initialization reads the current version, rejects databases newer than the application, and runs
  pending migrations in order.
- Each migration takes `BEGIN IMMEDIATE`, rereads the current version after acquiring the lock,
  executes explicit statements, sets `user_version`, and commits atomically.
- Do not rely on `executescript()` transaction behavior.
- Initial product data belongs inside the migration that creates its schema. Do not run an
  unconditional startup seed: deleting or editing seeded data must survive restart.
- Migration failures fail application startup. Never serve an empty projection when the source of
  truth could not initialize.
- Version 10 adds immutable execution offsets, completion proofs and guarded batch recovery. Infer
  only justified old prefixes and leave historical completion times null. Preserve every old column,
  ID, observation and relationship; append an audit record before explicitly reopening terminal
  history. See [Batch Search](./batch-search-guidelines.md) for the executable recovery contract.

## Naming and stored values

- Use plural `snake_case` table names, singular `snake_case` columns, and descriptive `ix_...`
  indexes.
- Stable integer IDs use `INTEGER PRIMARY KEY AUTOINCREMENT` when later aggregates may persist a
  reference and ID reuse would be unsafe.
- Store timestamps as UTC ISO-8601 text unless an aggregate specifies a stronger public contract.
- Store both operator-facing values and service-owned normalized identity values when uniqueness
  must preserve the original search/display text.
- Keep normalization columns, positions, timestamps, and internal paths out of public API models
  unless a real product consumer needs them.

## Testing requirements

- Tests use a temporary on-disk SQLite file. Do not use plain `:memory:` with connection-per-operation
  because each connection receives a different database.
- Application-factory tests inject a temporary path or fake service and must never write the real
  runtime database.
- Cover fresh migration, repeated initialization, forward-version rejection, idempotent seed
  behavior, persistence across reopen, deterministic ordering, constraint translation, transaction
  rollback, and sanitized storage failure.
- Build old-version fixtures with historical SQL/schema helpers. Do not call current repositories
  against an old schema, and do not fake an old version by relabeling a modern schema. Compare old
  column projections across migrations separately from defaults for genuinely new columns.

## Common mistakes

- Holding one connection across FastAPI worker threads.
- Disabling the SQLite thread check instead of fixing connection ownership.
- Creating schema or seed rows on every request or every startup.
- Using `INSERT OR IGNORE` to hide normalization or migration defects.
- Returning raw `sqlite3` exceptions, SQL, paths, or product values to an API or log.
- Allowing a future collection/browser call to run while a write transaction is open.

## Scenario: Repairing a changed historical migration

### 1. Scope / Trigger

Use this contract when released databases with the same `PRAGMA user_version`
can have different table shapes because an older migration file was edited
after some installations had already run it. Historical migration output is an
immutable compatibility boundary: restore the old migration and add a new
forward-only repair version.

### 2. Signatures

```python
CURRENT_DATABASE_VERSION = 16
Database.initialize()                       # runs pending versions in order
_migrate_to_version_16(sqlite3.Connection)  # accepts only user_version=15
topic_reports_v16.migrate(connection)       # normalizes topic_report_runs
```

Schema 16 adds nullable unique `topic_report_runs.workflow_operation_key` and
the automatic-workflow CHECK/immutability contract. No HTTP payload changes.

### 3. Contracts

- A genuine old v15 table, an empty old v15 table, and an already-correct v15
  table all finish with the exact same v16 table/index/trigger shape.
- Rebuilding `topic_report_runs` preserves every existing report value, ID,
  graph/source/request foreign key, JSON field, timestamp and AUTOINCREMENT
  sequence. The new column is `NULL` for historical rows.
- Table replacement is one `BEGIN IMMEDIATE` transaction. If foreign keys must
  be disabled for the SQLite rename/drop sequence, save and restore both
  `foreign_keys` and `legacy_alter_table`, then require an empty
  `foreign_key_check` before commit.
- Reopen is idempotent. A database newer than 16 is rejected without writes.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| `user_version < 15` enters v16 directly | Reject unsupported source version; earlier migrations own that path. |
| `user_version > 16` | Reject as a forward-version database without changing rows. |
| Missing report table or unexpected source columns | Fail startup and roll back; do not guess a shape. |
| Copy, rename, CHECK, index, trigger or FK validation fails | Roll back table/rows/version and restore connection PRAGMAs. |
| Column exists but owned CHECK/index/trigger SQL is stale | Rebuild to the canonical v16 shape; column presence alone is insufficient proof. |
| Already canonical v15 shape | Advance only the version; do not rewrite report rows or sequence. |

### 5. Good / Base / Bad Cases

- Good: a populated historical v15 report graph migrates to v16 with identical
  old-column projections, IDs, links and sequence, and can admit a workflow report.
- Base: an empty historical v15 database gains the canonical table shape and no
  product rows.
- Bad: edit `migrations/topic_reports.py` to add a new column and keep schema 15;
  already-migrated installations will never execute that DDL.

### 6. Tests Required

- Construct v13, run the historically accurate v14 and v15 migrations, seed a
  report plus dependent source/node membership, then assert exact old-column and
  sequence preservation through v16, FK/integrity success and idempotent reopen.
- Cover an empty historical v15 database and an already-canonical v15 database.
- Inject failure after the real table swap/copy and assert version 15, rows,
  schema, foreign keys and PRAGMA settings are restored.
- Compare canonical table, owned index and owned trigger SQL; do not use only
  `PRAGMA table_info` as the schema proof.

### 7. Wrong vs Correct

Wrong: mutate a released migration and assume the existing version will rerun.

```python
# v14 file edited after release; old user_version=15 databases stay unchanged
CREATE TABLE topic_report_runs (... workflow_operation_key TEXT UNIQUE ...)
```

Correct: preserve v14 history and add an explicit v15-to-v16 repair.

```python
if version < 16:
    _migrate_to_version_16(connection)
# v16 transaction normalizes the complete table/index/trigger contract.
```
