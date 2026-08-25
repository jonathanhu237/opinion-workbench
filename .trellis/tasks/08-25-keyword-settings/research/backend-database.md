# Research: Monitoring Rules backend and SQLite boundary

- Query: Determine the smallest clean FastAPI/SQLite design for persistent monitoring rules, including migrations, startup seeding, REST/error contracts, tests, and later collection-task reuse.
- Scope: mixed (current repository plus official Python, SQLite, and FastAPI references)
- Date: 2026-08-25

## Findings

### Existing backend constraints and patterns

- The backend currently has only `fastapi[standard]` as a runtime dependency; the locked graph contains FastAPI 0.141.1 and Pydantic 2.13.4, but no SQLAlchemy, SQLModel, Alembic, `aiosqlite`, or other database package (`backend/pyproject.toml:7-9`).
- `create_app()` owns long-lived services in FastAPI lifespan state and accepts a service factory for test isolation (`backend/src/longtian_api/main.py:10-33`). Database initialization should extend this pattern instead of creating a module-global connection.
- Request dependencies retrieve lifespan-owned services from `request.app.state` through typed `Annotated` aliases (`backend/src/longtian_api/api/dependencies.py:10-17`).
- Versioned routes live below `/api/v1`, with each feature router mounted centrally (`backend/src/longtian_api/api/router.py:8-10`).
- Existing endpoints translate expected service errors into the stable `{detail: {code, message}}` envelope and document response models in OpenAPI (`backend/src/longtian_api/api/v1/platform_connections.py:18-52`).
- Existing public Pydantic models normally use `ConfigDict(extra="forbid")`; immutable projections additionally use `frozen=True` (`backend/src/longtian_api/schemas/platform_connections.py:34-79`). Monitoring-rule request schemas should also forbid unknown fields.
- Backend API tests construct apps through `create_app()` and use `with TestClient(...)`, so lifespan startup and shutdown execute (`backend/tests/test_platform_connections.py:313-340`). This is also the pattern recommended by FastAPI for testing lifespan events.
- The database, directory, error, logging, and quality spec files are placeholders, so there is no established ORM, migration, transaction, or naming convention to preserve (`.trellis/spec/backend/database-guidelines.md:7-51`, `.trellis/spec/backend/error-handling.md:7-51`). This task will establish the first real convention and should later update those specs.
- The PRD requires SQLite, idempotent initial geographic data, deterministic non-empty enabled rules, and a stable backend read boundary for later collection (`.trellis/tasks/08-25-keyword-settings/prd.md:15-17`, `48-58`). It explicitly excludes starting MediaCrawler or selecting platforms (`prd.md:78-92`).
- The repository-root `db_data/` is already a PostgreSQL data directory (`PG_VERSION`, `base/`, `pg_wal/`). Do not place the product SQLite file inside it or treat it as the new application database directory.

### Recommended dependency choice

Use Python's standard-library `sqlite3` module with explicit SQL and a small repository layer for this MVP.

Why this is the smallest clean boundary:

- It adds no runtime dependency or lockfile churn.
- This aggregate has two small tables, simple CRUD, and no query composition that benefits materially from an ORM.
- Migrations can be deterministic with SQLite's application-owned `PRAGMA user_version`; SQLite itself intentionally leaves this integer for application use.
- Synchronous FastAPI route functions (`def`, not `async def`) are run in FastAPI's threadpool, preventing these disk calls from blocking the event loop. The repository should open, use, and close one connection per operation in that same thread.
- The repository instance holds only an immutable database path. Do not retain one `sqlite3.Connection` in `app.state`, and do not set `check_same_thread=False`; both would create avoidable cross-thread serialization and lifecycle problems.

Alternatives considered:

- `aiosqlite`: one new dependency and a background-thread wrapper around SQLite. It is reasonable once async workflows perform many database calls, but adds little for a single-user CRUD page with tiny transactions.
- SQLAlchemy + Alembic (or SQLModel): robust for many aggregates and complex migrations, but introduces multiple dependencies, metadata/model duplication, and substantial configuration before the project needs it. Reassess when persisted collection tasks/results add several related aggregates.

Because Python 3.11 is supported (`backend/pyproject.toml:6`), use `sqlite3.connect(..., isolation_level=None)` plus explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`; do not use the newer `autocommit=` parameter introduced after Python 3.11.

### Database location and connection policy

- Proposed default: repository-root `runtime/longtian.sqlite3`, with a `create_app(database_path=...)` or service-factory override for tests and future packaging. The parent directory is created at startup.
- Add `/runtime/` (or at minimum `/runtime/*.sqlite3*`) to `.gitignore`; WAL mode also creates `-wal` and `-shm` sidecars. Runtime/browser-session data must not become Git input.
- Keep path resolution in one backend helper; API, service, and repository code should never reconstruct it.
- On every connection:
  - set `row_factory = sqlite3.Row`;
  - execute `PRAGMA foreign_keys = ON` before any transaction (SQLite does not guarantee this default);
  - use a bounded lock wait (`timeout=5.0` or `PRAGMA busy_timeout=5000`);
  - use bound SQL parameters for all product data.
- At initialization, set `PRAGMA journal_mode = WAL`. WAL is persistent and permits the later collector to read while the operator edits a rule. Keep transactions short; no network/browser work may occur inside a transaction.

### Schema and deterministic ordering

Migration version 1 should create both tables and insert the initial rule in the same transaction:

```sql
CREATE TABLE monitoring_rules (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE monitoring_rule_terms (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id          INTEGER NOT NULL
                   REFERENCES monitoring_rules(id) ON DELETE CASCADE,
  value            TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  position         INTEGER NOT NULL CHECK (position >= 0),
  UNIQUE (rule_id, normalized_value),
  UNIQUE (rule_id, position)
);

CREATE INDEX ix_monitoring_rules_enabled_id
  ON monitoring_rules(enabled, id);
```

- `AUTOINCREMENT` avoids reusing a deleted rule ID, which matters once a future collection task persists a `rule_id`.
- Rules are returned in `id ASC` creation order; terms are returned in `position ASC` input order. No user-facing reorder feature or `sort_order` column is needed yet.
- Store timestamps as UTC ISO-8601 text for diagnostics/future concurrency, but the MVP API need not expose them unless the UI has a real use for them.
- Store the trimmed display/search value in `value`. Build `normalized_value` and `normalized_name` from Unicode NFKC + `casefold()` + outer-whitespace trimming for duplicate identity only. Do not collapse internal whitespace or replace the stored value, because that would silently change the user's search query.
- Enforce uniqueness both in application validation (clear feedback) and database constraints (race/corruption guard).

### Migration and one-time seed behavior

- A `Database.initialize()` method should run in app lifespan before requests are served.
- Read `PRAGMA user_version`; reject a database whose version is newer than the application supports.
- For each pending migration, acquire `BEGIN IMMEDIATE`, re-read the current version after the lock, execute individual parameterized statements, set `PRAGMA user_version = N`, then commit. Roll back on any failure. Avoid relying on `executescript()` transaction behavior.
- Migration 1 inserts one enabled rule named `龙田街道及四个社区` with ordered terms:
  1. `龙田街道`
  2. `龙田社区`
  3. `老坑社区`
  4. `竹坑社区`
  5. `南布社区`
- Put this insert inside migration 1, not in an unconditional startup `INSERT OR IGNORE`. A migration seed runs exactly once; if the operator later edits or deletes the default rule, restart must respect that choice rather than recreating it.
- Initialization failure should fail app startup. Serving the UI while its source of truth is unavailable would produce misleading empty state. Runtime operation failures should be mapped to a sanitized product error instead.

### Clean application boundary

Recommended flow:

```text
HTTP request
  -> monitoring_rules router / Pydantic request contract
  -> MonitoringRuleService (normalization, semantic validation, domain errors)
  -> MonitoringRuleRepository (transactions and SQL only)
  -> SQLite
```

- `MonitoringRuleRepository` owns connection creation, SQL, row assembly, and atomic replacement of a rule plus all terms.
- `MonitoringRuleService` owns limits, normalization, duplicate detection, stable ordering guarantees, and product error codes. It returns typed immutable rule projections, following the existing service-to-schema pattern.
- Updating a rule is a full transaction: update the parent, delete existing terms, insert replacement terms in position order, and commit. Any error rolls the entire replacement back.
- A lifespan-created service is exposed with `MonitoringRuleServiceDep`, matching the existing dependency pattern. With connection-per-operation there is no database connection to close at shutdown.

### Proposed REST contract

Public resource shape:

```json
{
  "id": 1,
  "name": "龙田街道及四个社区",
  "terms": ["龙田街道", "龙田社区", "老坑社区", "竹坑社区", "南布社区"],
  "enabled": true
}
```

Endpoints:

- `GET /api/v1/monitoring-rules` -> `200 {"rules": [...]}` in stable order.
- `GET /api/v1/monitoring-rules?enabled=true` -> the same response shape containing only enabled rules. This is the stable selection contract for a future collection task; `enabled=false` is also useful to the settings UI but optional.
- `POST /api/v1/monitoring-rules` -> `201` with the created rule. Body: `{name, terms, enabled?}`; `enabled` defaults to `true`.
- `PUT /api/v1/monitoring-rules/{rule_id}` -> `200` with the fully replaced rule. Body: `{name, terms, enabled}`. A full resource replacement is simpler and less ambiguous than optional-field PATCH semantics for this single-user page.
- `DELETE /api/v1/monitoring-rules/{rule_id}` -> `204` with an empty body; a missing ID returns `404`.

A separate `GET /{id}` and enable-only endpoint are not required for this page. They can be added when another backend workflow actually needs them.

Suggested MVP limits (technical defaults requiring design confirmation, not yet user decisions):

- rule name: 1-80 Unicode code points after trim;
- term: 1-100 code points after trim;
- terms per rule: 1-100;
- `rule_id`: positive integer;
- request models: `ConfigDict(extra="forbid", strict=True)`.

The API receives `terms` as an ordered JSON array. Parsing multiline/comma-separated paste input belongs to the frontend form boundary; the backend validates the resulting array and preserves its order.

### Validation and error behavior

- Reject empty/whitespace-only names and terms, empty term lists, over-limit values, wrong types, unknown fields, and normalized duplicates.
- Reject rather than silently discard duplicate terms; return a clear Chinese message such as `同一条监控规则中不能包含重复关键词。`. Silent deduplication would prevent the UI from telling the operator that pasted input changed.
- Keep the existing error envelope:

```json
{"detail": {"code": "monitoring_rule_not_found", "message": "未找到该监控规则。"}}
```

Recommended stable codes/statuses:

- `invalid_monitoring_rule` -> 422, semantic validation failure;
- `duplicate_monitoring_rule_term` -> 422;
- `monitoring_rule_name_conflict` -> 409;
- `monitoring_rule_not_found` -> 404;
- `monitoring_rule_storage_unavailable` -> 503 with `监控规则暂时无法读取或保存，请稍后重试。`.

FastAPI's default request-validation response is technical and not the existing product envelope. Add an app-level `RequestValidationError` handler that returns a stable Chinese `invalid_request` response (and document it as a shared API contract), or a monitoring-router-specific route class if changing the rest of the API is considered too broad. Test unknown fields and wrong JSON types explicitly.

Catch and translate known SQLite constraint failures in the repository/service. Do not return exception strings, SQL, parameter values, or the database path. Unexpected SQLite errors may be logged with a stable operation name and exception class, but avoid logging the user's terms.

### Lifespan and testing implications

- Extend `create_app()` with an injectable monitoring-rule service factory or database path, initialize/migrate it before `yield`, then set it on `application.state`. Keep the current platform-service shutdown in `finally`.
- All existing tests that call default `create_app()` would otherwise create the real runtime database. Update them to use a temporary database factory/path, or provide a shared `tmp_path` app fixture. Do not use plain `:memory:` with connection-per-operation because each connection gets a separate database.
- Keep `with TestClient(app)` so startup migration/seed runs; FastAPI explicitly documents this requirement.
- Minimum backend regression coverage:
  - fresh database creates schema and the five-term seed once;
  - reopen the same path creates no duplicate; deleting the seed and reopening does not resurrect it;
  - CRUD persists across requests and app restart;
  - list and term ordering is deterministic;
  - normalized duplicate name/term conflicts are atomic and return stable codes;
  - failed full update preserves the previous rule and terms;
  - enabled filtering excludes disabled rules but the unfiltered list retains them;
  - malformed/unknown payloads and invalid IDs return Chinese envelopes;
  - simulated database failure never exposes the filesystem path or raw SQLite message;
  - OpenAPI documents success and 404/409/422/503 error models;
  - monitoring-rule calls never touch `PlatformConnectionService`, launch a worker, or import MediaCrawler.

### Later collection-task consumption without MediaCrawler work now

- Treat `MonitoringRuleService.list_enabled()` (or repository equivalent) as the backend application boundary. A future collection service should inject it directly rather than make an HTTP request back into the same process or parse frontend state.
- The future task can persist a selected `rule_id`, resolve the latest enabled rule at execution time, and iterate `terms` in stored position order. Each term remains an independent OR-style search, matching the PRD and the current one-keyword-at-a-time adapter.
- Platform IDs, schedules, result merging, and deduplication remain owned by the future collection aggregate. No monitoring-rule module should import `third_party/MediaCrawler`, start the auth worker, or open a browser.
- `GET ...?enabled=true` exists for frontend selection and other local clients; it is not the only internal consumption mechanism.

### Files likely affected during implementation

- `backend/src/longtian_api/database.py` — path resolution, connection helper, `user_version` migration runner, migration-1 schema and seed.
- `backend/src/longtian_api/repositories/__init__.py` and `repositories/monitoring_rules.py` — SQLite CRUD and row assembly.
- `backend/src/longtian_api/services/monitoring_rules.py` — normalization, limits, domain errors, typed read boundary.
- `backend/src/longtian_api/schemas/monitoring_rules.py` — strict request, response, and error models.
- `backend/src/longtian_api/api/v1/monitoring_rules.py` — REST routes and domain-error translation.
- `backend/src/longtian_api/api/dependencies.py` — `MonitoringRuleServiceDep`.
- `backend/src/longtian_api/api/router.py` — router registration.
- `backend/src/longtian_api/main.py` — database/service factory injection, lifespan initialization, validation handler if selected.
- `backend/tests/test_monitoring_rules.py` — migration, persistence, CRUD, failure, contract, and no-browser coverage.
- `backend/tests/test_health.py` and `backend/tests/test_platform_connections.py` — temporary DB injection after startup begins initializing persistence.
- `.gitignore` — SQLite database and WAL/SHM sidecars under `runtime/`.
- `README.md` and/or `backend/README.md` — document local database location and reset/backup behavior.
- `backend/pyproject.toml` and `backend/uv.lock` — no change under the recommended standard-library approach.

## Files Found

- `backend/pyproject.toml` — Python/runtime constraints and the current dependency set.
- `backend/src/longtian_api/main.py` — app factory and lifespan-owned service lifecycle.
- `backend/src/longtian_api/api/dependencies.py` — typed app-state dependency pattern.
- `backend/src/longtian_api/api/router.py` — `/api/v1` feature-router composition.
- `backend/src/longtian_api/api/v1/platform_connections.py` — current route-level product-error translation and OpenAPI response pattern.
- `backend/src/longtian_api/schemas/platform_connections.py` — strict public schema/error-envelope pattern.
- `backend/src/longtian_api/services/platform_connections.py` — current service/domain-error style and deferred worker launch.
- `backend/tests/test_health.py` — minimal app-factory/TestClient contract test.
- `backend/tests/test_platform_connections.py` — factory injection, lifespan tests, exact error assertions, and OpenAPI checks.
- `.gitignore` — ignores the old `db_data/` and logs, but not SQLite/WAL files under `runtime/`.
- `runtime/platform_sessions/` — existing empty runtime namespace; no current backend path convention references it.
- `db_data/` — existing local PostgreSQL cluster, not an appropriate SQLite target.

## External References

- [Python 3.11 `sqlite3` documentation](https://docs.python.org/3.11/library/sqlite3.html) — built-in DB-API, connection/thread rules, explicit transactions, placeholders, and row factories.
- [SQLite PRAGMA documentation](https://www.sqlite.org/pragma.html) — `user_version`, `foreign_keys`, `busy_timeout`, and persistent WAL behavior.
- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/) — initialize shared application resources before accepting requests.
- [FastAPI testing lifespan](https://fastapi.tiangolo.com/advanced/testing-events/) — `TestClient` must be used as a context manager for lifespan execution.
- Local locked versions observed on 2026-08-25: FastAPI 0.141.1, Pydantic 2.13.4, Python requirement `>=3.11`.

## Related Specs

- `.trellis/spec/backend/index.md` — backend spec index; database/error/directory/quality entries are currently placeholders.
- `.trellis/spec/backend/database-guidelines.md` — should receive the selected SQLite connection/migration conventions after implementation.
- `.trellis/spec/backend/error-handling.md` — should receive the stable product-error envelope and request-validation decision.
- `.trellis/spec/backend/directory-structure.md` — should document the new repository/database boundary if established.
- `.trellis/spec/guides/cross-layer-thinking-guide.md:19-72` — requires explicit contracts and one owner per boundary.
- `.trellis/spec/guides/code-reuse-thinking-guide.md` — normalization and error-envelope logic should have one shared owner.

## Caveats / Not Found

- No established application database, ORM, repository, migration runner, database configuration, backup flow, or database tests were found.
- The proposed field limits (80/100/100), runtime path, and global-versus-router-scoped request-validation handler are technical recommendations, not confirmed product decisions.
- The PRD mentions the current adapter's comma-separated independent searches, but the monitoring-rule task must not wire or validate MediaCrawler execution. Collection semantics beyond ordered enabled terms remain deferred.
- SQLite backup/export, concurrent multiple backend processes, collection-task foreign keys, rule-version snapshots, and delete behavior when future tasks reference a rule require decisions in later tasks.
