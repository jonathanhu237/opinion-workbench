# Monitoring Rules

> Executable storage, service, API, and consumer contracts for reusable monitoring rules.

## Scenario: Persisted monitoring objects and optional issue keywords

### 1. Scope / Trigger

Use this contract when changing monitoring-rule persistence, HTTP behavior, validation, or the
collection-task reader. A rule defines only what to search. Platform selection, browser
control, scheduling, collection execution, result merging, and MediaCrawler invocation belong to
other modules.

### 2. Signatures

Database version 1 owns the rule and ordered object rows; version 9 adds ordered issue rows:

```text
monitoring_rules(id, name, normalized_name, enabled, created_at, updated_at)
monitoring_rule_terms(id, rule_id, value, normalized_value, position)
monitoring_rule_issue_terms(id, rule_id, value, normalized_value, position)
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
compose_monitoring_terms(monitoring_objects: Sequence[str], issue_keywords: Sequence[str]) -> tuple[str, ...]
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
{
  "id": 1,
  "name": "道路问题",
  "monitoring_objects": ["示例街道", "示例社区"],
  "issue_keywords": ["积水", "噪音"],
  "terms": ["示例街道 积水", "示例街道 噪音", "示例社区 积水", "示例社区 噪音"],
  "enabled": true
}
```

- POST accepts `name: str`, `monitoring_objects: list[str]`, optional
  `issue_keywords: list[str] = []`, and optional `enabled: bool = true`.
- PUT is a full replacement and requires `name`, `monitoring_objects`, `issue_keywords`, and
  `enabled`, including an explicit empty issue list. Enabled toggles must preserve both groups.
- `terms` is derived and read-only. Unknown fields, client-supplied `terms`, mixed legacy/new writes
  and non-strict types are rejected. Ship frontend/backend together; do not infer old write intent.
- Path IDs are integers from 1 through `9_223_372_036_854_775_807`; reject larger positive values at
  the HTTP boundary before they reach SQLite.
- Names are 1–80 Unicode code points after outer trimming. Each object, issue and resulting query
  has 1–100 code points; one rule has 1–100 objects, 0–100 issues and 1–100 effective queries.
- Empty issues mean each object is searched unchanged. Otherwise combine each object with each
  issue using exactly one separating space, in object-major input order. Preserve internal spaces
  and punctuation; do not parse Boolean syntax or promise strict AND semantics on platforms.
- Validate the product count before allocating combinations. The same pure composition helper
  validates writes and derives read projections; do not store a second materialized query list.
- Duplicate identity is outer trim + Unicode NFKC + `casefold()`. Names are unique globally;
  each input group and generated queries must also be unique within their respective lists.
  Reject generated collisions even when input groups themselves are unique; never silently
  deduplicate or truncate. Store trimmed display/search values without rewriting internal whitespace.
- List order is ascending stable rule ID. Each input group is ordered by stored position. Read
  child groups without multiplying them through a two-child-table join; replace both atomically.
- Migration 9 adds only the empty issue table with per-rule value/position uniqueness and
  `ON DELETE CASCADE`. Existing `monitoring_rule_terms` are objects, including old complete phrases;
  do not split or rewrite them. Preserve v8 AI settings and run/batch snapshots, IDs and relations.
- Both group tables use `value TEXT NOT NULL`. Keep their code-point length validation in the
  shared service: SQLite `length(TEXT)` stops at NUL, unlike Python `len()`. Adding a length CHECK
  only to issue rows makes a service-valid phrase fail storage while the same object phrase works.
  Test this boundary without changing old object semantics or weakening the 100-code-point limit.
- Migration 1 alone seeds one enabled five-term default rule. Startup must never recreate a rule the
  operator edited or deleted.
- `list_enabled()` is the approved collection reader and excludes disabled rules. Collectors use its
  derived `terms`, not either input group. Existing run/batch snapshots remain immutable after edits.
- Saving 21–100 effective queries is supported with a visible execution warning. Single runs and
  batches still reject more than 20 queries with `too_many_search_terms`; do not raise this limit,
  silently truncate or split into extra runs.
- Frontend preview uses a pure local helper, with no network on edits. Valid preview ordering and
  content match the server; backend Unicode normalization remains authoritative.
- Frontend rule trimming matches Python `str.strip()`, including NEL and C0 separator whitespace
  while preserving U+FEFF. Use the shared `trimRuleValue` for names, input groups, previews and
  decoder checks; JavaScript's native `trim()` has different membership and can reject valid old
  phrases or silently change them. Full Python `casefold()` still belongs to backend validation.
- The default database is ignored user state at `runtime/longtian.sqlite3`; no API projection exposes
  paths, timestamps, normalized values, or row positions.

### 4. Validation & Error Matrix

All expected failures use `{"detail":{"code":"...","message":"..."}}`.

| Condition | Status | Code |
| --- | --- | --- |
| Malformed JSON, wrong type, unknown field, or invalid path/query | 422 | `invalid_request` |
| Blank or over-limit semantic value | 422 | `invalid_monitoring_rule` |
| Duplicate normalized object, issue or generated query | 422 | `duplicate_monitoring_rule_term` |
| Duplicate normalized rule name | 409 | `monitoring_rule_name_conflict` |
| Missing positive rule ID | 404 | `monitoring_rule_not_found` |
| Unexpected read/write/storage failure | 503 | `monitoring_rule_storage_unavailable` |

Storage failures use constant Chinese guidance and never include SQL, a filesystem path, request
values, rule terms, or raw SQLite exceptions.

The frontend treats `(HTTP status, product error code)` as one protocol contract. It may show a
field-level product message only when both match this matrix; a known code paired with the wrong
status is protocol drift and maps to `invalid_response`.

### 5. Good / Base / Bad Cases

- Good: two objects and two issues produce four ordered queries; reopen/edit/toggle retains both
  original groups. A batch created before an edit retains its original effective-query snapshot.
- Base: initialize a fresh database twice and receive one default rule, not two.
- Bad: edit expanded `terms` instead of original groups, drop issues during an enabled toggle,
  silently remove generated collisions, reinterpret old phrases, recreate deleted defaults, return
  normalization columns or launch a worker/model while maintaining a rule.

### 6. Tests Required

- Migration: fresh/repeated initialization, populated v8→v9, forward-version rejection,
  transactional DDL rollback, WAL/pragmas, unchanged old phrases/IDs/disabled states/AI settings and
  run/batch history, one-time seed and deletion persistence.
- Repository/service: CRUD across reopen, stable ID/term order, enabled filtering, normalized
  conflicts, both-group atomic replace rollback, empty issues, object-major multi-word combinations,
  generated collisions, 100-character queries, 20/21 and 100/101 counts and sanitized unavailability.
- API: exact 200/201/204 bodies, 404/409/422/503 envelopes, strict malformed requests, and OpenAPI
  response models, including positive IDs above SQLite's signed-int64 maximum.
- Cross-boundary: prove rule CRUD launches no platform/browser worker and that the frontend decoder
  accepts only the exact public projection and exact status/code error pairs.
- Frontend: live preview/count, optional empty input, group-preserving edit/toggle, 21–100 warning,
  invalid input/response handling, Python-equivalent whitespace/BOM-name compatibility, pending
  state, keyboard/focus and narrow long-content layout.
- Collectors: both standalone runs and batches receive effective queries, preserve the 20-query
  gate, frozen history and existing result deduplication.

### 7. Wrong vs Correct

#### Wrong

```python
service.initialize()
service.create_rule(DEFAULT_RULE)  # recreates operator-deleted data on every startup
```

```typescript
updateMonitoringRule(id, { name: rule.name, terms: rule.terms, enabled: false })
// Invalid write shape: expanded terms lose the two editable groups.
```

#### Correct

```python
# Migration 1 creates the schema and seed inside one BEGIN IMMEDIATE transaction.
service.initialize()  # later startups only observe PRAGMA user_version
```

```typescript
updateMonitoringRule(id, {
  name: rule.name,
  monitoring_objects: rule.monitoring_objects,
  issue_keywords: rule.issue_keywords,
  enabled: false,
})
```

Collectors call `list_enabled()` and pass its ordered terms to their own execution boundary;
monitoring-rule routes and services never import MediaCrawler or platform-connection code.
