# Monitoring Rules

> Executable storage, service, API, and consumer contracts for reusable monitoring rules.

## Scenario: Persisted OR-style monitoring rules

### 1. Scope / Trigger

Use this contract when changing monitoring-rule persistence, HTTP behavior, validation, or the
future collection-task reader. A rule defines only what to search. Platform selection, browser
control, scheduling, collection execution, result merging, and MediaCrawler invocation belong to
other modules.

### 2. Signatures

Database version 1 owns:

```text
monitoring_rules(id, name, normalized_name, enabled, created_at, updated_at)
monitoring_rule_terms(id, rule_id, value, normalized_value, position)
ix_monitoring_rules_enabled_id(enabled, id)
```

The service boundary is:

```python
initialize() -> None
list_rules(*, enabled: bool | None = None) -> MonitoringRuleListResponse
list_enabled() -> tuple[MonitoringRule, ...]
create_rule(payload: MonitoringRuleCreate) -> MonitoringRule
replace_rule(rule_id: int, payload: MonitoringRuleReplace) -> MonitoringRule
delete_rule(rule_id: int) -> None
```

The HTTP boundary is:

```text
GET    /api/v1/monitoring-rules[?enabled=true|false] -> 200
POST   /api/v1/monitoring-rules                     -> 201
PUT    /api/v1/monitoring-rules/{sqlite_int64_id}   -> 200
DELETE /api/v1/monitoring-rules/{sqlite_int64_id}   -> 204, empty body
```

### 3. Contracts

The only public rule projection is:

```json
{"id": 1, "name": "龙田街道及四个社区", "terms": ["龙田街道"], "enabled": true}
```

- POST accepts `name: str`, `terms: list[str]`, and optional `enabled: bool = true`.
- PUT is a full replacement and requires `name`, `terms`, and `enabled`.
- Unknown fields and non-strict types are rejected.
- Path IDs are integers from 1 through `9_223_372_036_854_775_807`; reject larger positive values at
  the HTTP boundary before they reach SQLite.
- Names are 1–80 Unicode code points after outer trimming. Terms are 1–100; one rule has 1–100
  ordered terms.
- Duplicate identity is outer trim + Unicode NFKC + `casefold()`. Names are unique globally;
  terms are unique within their rule. Store trimmed display/search values without rewriting internal
  whitespace.
- List order is ascending stable rule ID. Term order is ascending stored position.
- Migration 1 alone seeds one enabled five-term default rule. Startup must never recreate a rule the
  operator edited or deleted.
- `list_enabled()` is the only approved future collection reader and excludes disabled rules.
- The default database is ignored user state at `runtime/longtian.sqlite3`; no API projection exposes
  paths, timestamps, normalized values, or row positions.

### 4. Validation & Error Matrix

All expected failures use `{"detail":{"code":"...","message":"..."}}`.

| Condition | Status | Code |
| --- | --- | --- |
| Malformed JSON, wrong type, unknown field, or invalid path/query | 422 | `invalid_request` |
| Blank or over-limit semantic value | 422 | `invalid_monitoring_rule` |
| Duplicate normalized term in one rule | 422 | `duplicate_monitoring_rule_term` |
| Duplicate normalized rule name | 409 | `monitoring_rule_name_conflict` |
| Missing positive rule ID | 404 | `monitoring_rule_not_found` |
| Unexpected read/write/storage failure | 503 | `monitoring_rule_storage_unavailable` |

Storage failures use constant Chinese guidance and never include SQL, a filesystem path, request
values, rule terms, or raw SQLite exceptions.

The frontend treats `(HTTP status, product error code)` as one protocol contract. It may show a
field-level product message only when both match this matrix; a known code paired with the wrong
status is protocol drift and maps to `invalid_response`.

### 5. Good / Base / Bad Cases

- Good: create a disabled rule with ordered terms, reopen the database, and receive the same public
  projection from the unfiltered list while `list_enabled()` omits it.
- Base: initialize a fresh database twice and receive one default rule, not two.
- Bad: silently deduplicate pasted terms, recreate a deleted seed at startup, return normalization
  columns, or launch a platform worker while maintaining a rule.

### 6. Tests Required

- Migration: fresh/repeated initialization, forward-version rejection, WAL/pragmas, one-time seed,
  and deletion persistence.
- Repository/service: CRUD across reopen, stable ID/term order, enabled filtering, normalized
  conflicts, atomic replace rollback, and sanitized unavailability.
- API: exact 200/201/204 bodies, 404/409/422/503 envelopes, strict malformed requests, and OpenAPI
  response models, including positive IDs above SQLite's signed-int64 maximum.
- Cross-boundary: prove rule CRUD launches no platform/browser worker and that the frontend decoder
  accepts only the exact public projection and exact status/code error pairs.

### 7. Wrong vs Correct

#### Wrong

```python
service.initialize()
service.create_rule(DEFAULT_RULE)  # recreates operator-deleted data on every startup
```

#### Correct

```python
# Migration 1 creates the schema and seed inside one BEGIN IMMEDIATE transaction.
service.initialize()  # later startups only observe PRAGMA user_version
```

Future collectors call `list_enabled()` and pass its ordered terms to their own execution boundary;
monitoring-rule routes and services never import MediaCrawler or platform-connection code.
