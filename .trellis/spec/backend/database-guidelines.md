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

## Common mistakes

- Holding one connection across FastAPI worker threads.
- Disabling the SQLite thread check instead of fixing connection ownership.
- Creating schema or seed rows on every request or every startup.
- Using `INSERT OR IGNORE` to hide normalization or migration defects.
- Returning raw `sqlite3` exceptions, SQL, paths, or product values to an API or log.
- Allowing a future collection/browser call to run while a write transaction is open.
