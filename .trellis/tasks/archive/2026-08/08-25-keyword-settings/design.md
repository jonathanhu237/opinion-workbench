# Technical Design: Monitoring Rules

## Summary

Add a local SQLite-backed monitoring-rule resource to FastAPI and a third real React route at
`/monitoring-rules`. The page manages named, enabled rules containing ordered OR-style search terms.
It does not know about platforms, browser sessions, schedules, or collection execution.

## Architecture and boundaries

```text
React route
  -> TanStack Query hook / mutations
  -> strict frontend API decoder
  -> /api/v1/monitoring-rules
  -> MonitoringRuleService
  -> MonitoringRuleRepository
  -> runtime/longtian.sqlite3

Future collection task
  -> MonitoringRuleService.list_enabled()
  -> ordered terms
  -> platform-specific collection owned elsewhere
```

Ownership is deliberately narrow:

- The API schema owns the public JSON shape.
- The service owns normalization, limits, duplicate rules, and product error codes.
- The repository owns SQL, transactions, row assembly, and deterministic ordering.
- The frontend API module owns decoding `unknown` network data.
- React Hook Form owns editor values; TanStack Query owns persisted server state.
- No monitoring-rule module imports MediaCrawler or platform-connection code.

## Domain model

The public rule projection is:

```json
{
  "id": 1,
  "name": "龙田街道及四个社区",
  "terms": ["龙田街道", "龙田社区", "老坑社区", "竹坑社区", "南布社区"],
  "enabled": true
}
```

Rules are returned by ascending stable ID. Terms preserve the operator's input order. The public API
does not expose normalization columns, positions, timestamps, database paths, or future collection
metadata.

### Validation and normalization

- Name: 1–80 Unicode code points after trimming surrounding whitespace.
- Term: 1–100 Unicode code points after trimming surrounding whitespace.
- Terms per rule: 1–100.
- Request bodies reject unknown fields and non-strict types.
- Store the trimmed display value exactly as the search value; do not rewrite internal whitespace.
- Duplicate identity uses Unicode NFKC, `casefold()`, and surrounding-whitespace trimming.
- Rule names are unique after normalization.
- Terms are unique within one rule after normalization; the same term may appear in different rules.
- Reject duplicates with a clear product error instead of silently dropping pasted lines.
- IDs are positive integers.

The frontend mirrors the limits for immediate field feedback, but the backend remains authoritative.
Textarea parsing splits on line breaks, ignores blank lines, trims surrounding whitespace, and sends
an ordered array. Commas remain part of a term because punctuation may be intentional.

## SQLite design

Use the Python 3.11 standard-library `sqlite3` module. The MVP does not add SQLAlchemy, SQLModel,
Alembic, or `aiosqlite`.

The default file is `runtime/longtian.sqlite3`; Git ignores it and its WAL/SHM sidecars. The existing
`db_data/` PostgreSQL directory is unrelated and must not be reused.

Each repository operation opens and closes its own connection in the same worker thread. Do not keep
a connection in `app.state` and do not disable SQLite's thread check. Every connection enables
foreign keys, applies a five-second busy timeout, uses `sqlite3.Row`, and binds all product values as
parameters. Initialization enables WAL mode. Transactions are short and contain no network or
browser work.

### Schema version 1

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

Use `PRAGMA user_version` for application-owned migrations. Initialization rejects a database newer
than the application. Each migration runs under `BEGIN IMMEDIATE`, rechecks the version after taking
the lock, commits atomically, and rolls back on failure.

Migration 1 creates the schema and inserts one enabled `龙田街道及四个社区` rule with the five PRD
terms. The seed exists only inside migration 1. Startup never runs an unconditional seed, so editing
or deleting the default rule is respected after restart.

An update replaces the parent fields and all child terms in one transaction. Any validation,
constraint, or write failure leaves the previous complete rule unchanged.

## FastAPI application boundary

Blocking SQLite work uses plain `def` path operations so FastAPI runs it in the threadpool. Lifespan
initialization calls the synchronous migration function through `run_in_threadpool`; it must not
block the async lifespan that also owns `PlatformConnectionService.shutdown()`.

`create_app()` gains an injectable monitoring-rule service factory. Tests supply a temporary file or
fake service, so existing tests never create the real runtime database. The lifespan initializes the
service before yielding and places it on `application.state`; a typed `Annotated` dependency exposes
it to routes.

### REST contract

All endpoints live under `/api/v1/monitoring-rules`:

| Method | Path | Success |
| --- | --- | --- |
| GET | `` | `200 {"rules": [...]}` |
| GET | `?enabled=true` | `200` with enabled rules only |
| POST | `` | `201` with the created rule |
| PUT | `/{rule_id}` | `200` with the fully replaced rule |
| DELETE | `/{rule_id}` | `204` with no body |

POST accepts `{name, terms, enabled?}` and defaults `enabled` to true. PUT accepts the full
`{name, terms, enabled}` resource body. A separate detail endpoint, PATCH endpoint, reorder endpoint,
and toggle endpoint are unnecessary for the first consumer. The frontend switch sends a full PUT
using the canonical cached rule.

### Error contract

Expected errors use the existing envelope:

```json
{"detail": {"code": "monitoring_rule_not_found", "message": "未找到该监控规则。"}}
```

Stable codes are:

| Code | Status | Meaning |
| --- | --- | --- |
| `invalid_request` | 422 | malformed types or unknown request fields |
| `invalid_monitoring_rule` | 422 | semantic name/term/limit failure |
| `duplicate_monitoring_rule_term` | 422 | duplicate normalized term in one rule |
| `monitoring_rule_name_conflict` | 409 | duplicate normalized rule name |
| `monitoring_rule_not_found` | 404 | missing positive ID |
| `monitoring_rule_storage_unavailable` | 503 | sanitized read/write failure |

Add a shared `RequestValidationError` handler that returns the stable Chinese `invalid_request`
envelope while preserving status 422. Verify existing successful and documented platform error
contracts remain unchanged. Known SQLite constraints map to domain errors; unexpected storage errors
never return or log rule values, SQL, raw exceptions, or the database path.

## Frontend UX design

### Visual direction

Preserve the current civic palette, typography, spacing tokens, shell width, and shadcn `base-nova`
foundation. Do not apply the unrelated dark operations-dashboard palette returned by generic design
search, and do not regenerate global theme variables. This page is a compact utility screen, not a
landing page or dashboard.

The characteristic element is functional: each rule row is organized around its real wrapping
search-term chips. There are no KPI cards, decorative charts, fake readiness states, platform logos,
or ambient animation.

```text
Desktop
┌─ 监控规则 ───────────────────────────── [新建规则] ─┐
│ 设置需要持续关注的搜索词。每个搜索词会分别用于搜索。 │
├────────────────────────────────────────────────────┤
│ 龙田街道及四个社区           [已启用] [编辑] [删除] │
│ [龙田街道] [龙田社区] [老坑社区] [竹坑社区] [南布社区]│
└────────────────────────────────────────────────────┘

Mobile
┌─ 监控规则 ──────────────────┐
│ 设置需要持续关注的搜索词……  │
│ [新建规则                 ] │
├────────────────────────────┤
│ 龙田街道及四个社区 [已启用] │
│ [龙田街道] [龙田社区]       │
│ [编辑]              [删除] │
└────────────────────────────┘
```

Add `/monitoring-rules` as the third real route and sidebar destination. Replace the shell's
two-route title ternary with an explicit pathname-to-title mapping so future routes do not silently
appear as `工作台`.

Render a semantic list of rule articles rather than a table. Terms wrap as outline badges and break
long unspaced text without horizontal overflow. Every row shows explicit `已启用` or `已停用` text,
a labelled Switch, and visible shadcn `编辑` and `删除` Buttons. The Switch updates only that row and
uses a full PUT. Mobile controls remain at least 44 px tall.

### Editor and deletion

Use one controlled shadcn Dialog for create and edit:

- `规则名称`: Input.
- `搜索词`: Textarea, one term per line.
- Helper: `每行输入一个搜索词，粘贴多行可批量添加。系统会分别搜索这些词。`
- Create defaults to enabled. Enabled state is maintained through the row Switch.
- Submit action: `保存` / `保存中…`; close only after success.

Use a controlled shadcn AlertDialog for deletion with `删除“{name}”？`, `删除后无法恢复。`, `取消`,
and `删除`. Keep it open and show the product error if deletion fails.

Add only the named shadcn consumers: Dialog, AlertDialog, Field, Textarea, and Switch. Review generated
source and dependency changes; reject theme rewrites. Do not add Table, Data Table, Dropdown Menu,
Drawer, Tabs, Select, Sonner, Motion, or a second responsive component mode.

### State, feedback, and accessibility

- `lib/api/monitoring-rules.ts` owns Zod response decoding, requests, query key, and API errors.
- `hooks/use-monitoring-rules.ts` owns the reusable query with the request AbortSignal and no
  automatic retry; the page offers an explicit retry action.
- Mutations are route-owned until another consumer exists. They invalidate or update the canonical
  query cache only after success; there is no optimistic write.
- React state stores only editor mode, delete target, and a short polite success message. React Hook
  Form exclusively owns field values and maps backend field errors with `setError`.
- Initial loading uses stable Skeleton rows plus `正在读取监控规则…` as a live status.
- Empty state says `还没有监控规则` and offers `新建规则` without sample data.
- Initial failure retains an actionable `重新加载`; cached data remains visible on background errors.
- Pending controls communicate `保存中…`, `正在更新…`, or `删除中…` and prevent duplicate actions.
- Labels and action-specific accessible names include the rule name. Base UI owns dialog focus trap,
  dismissal, and focus return. Status is never color-only.
- Verify 375 px, the exact 48 rem navigation boundary, desktop, keyboard flow, console output, and
  absence of horizontal overflow.

## Compatibility and failure recovery

- Platform account APIs, connection state, worker lifecycle, and frontend route behavior remain
  unchanged.
- Database startup failure fails FastAPI startup rather than serving a false empty list.
- Runtime storage failure leaves the last frontend cache visible when possible and exposes only a
  recoverable Chinese error.
- The SQLite file and sidecars are runtime data, never committed.
- Rollback preserves the SQLite file for recovery. Reverting the feature code does not delete user
  data; operators may back up or move `runtime/longtian.sqlite3` before a manual reset.

## Testing strategy

Backend tests cover migration/version handling, one-time seed behavior, CRUD persistence across app
restart, ordering, normalized duplicates, transaction rollback, enabled filtering, request/error
contracts, OpenAPI, storage sanitization, and proof that no browser/worker boundary is touched.

Frontend tests cover strict decoding, loading/empty/error/retry, real row rendering, create/edit,
textarea parsing and validation, toggle success/failure, delete confirmation/failure, cache updates,
navigation/focus, mobile layout semantics, and absence of platform or collection actions.

Run all frozen backend and frontend gates, `git diff --check`, a recursive submodule cleanliness
check, and loopback desktop/mobile browser smoke tests.
