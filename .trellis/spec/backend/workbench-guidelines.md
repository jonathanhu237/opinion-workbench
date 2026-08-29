# Homepage Workbench

## Scenario: Read-only duty snapshot

### 1. Scope / Trigger

Use this contract when changing the `/` workbench, any task status that it
projects, or `GET /api/v1/workbench`. The page answers two questions only:
what currently needs attention, and what is the newest trustworthy report.
It discovers and summarizes public opinion; it must not add manual
follow-up/handled/read state, daily-discovery KPIs, charts, or raw-result feeds.

### 2. Signatures

- `GET /api/v1/workbench -> WorkbenchSnapshot`
- `WorkbenchService.read() -> WorkbenchSnapshot`
- `WorkbenchRepository.read(observed_at: str) -> WorkbenchSnapshot`
- Frontend boundary: `fetchWorkbench(signal?: AbortSignal) -> Promise<WorkbenchSnapshot>`
- Query key: `['workbench']`; refresh is 5 seconds with active work and 30
  seconds while idle.
- Platform readiness remains `GET /api/v1/platform-connections`; it is not
  persisted into the workbench response.

The endpoint is additive and reads existing SQLite tables. It has no request
body, environment key, migration, or write-side command.

### 3. Contracts

`WorkbenchSnapshot` has these exact top-level fields:

```text
observed_at: UTC timestamp
attention: WorkbenchAttention[0..100]
activity: { collection, initial_analysis, report }
next_collection: earliest enabled, available, valid future schedule | null
latest_report: newest readable completed/empty report | null
```

Attention carries typed evidence (`kind`, `severity`, `status`, `reason`,
`resource_id`, `owner`, `occurred_at`, `unsuccessful_count`), never a stored URL
or raw exception. The frontend owns these routes:

```text
collection_schedule -> /collection-runs?schedule=:id
collection_batch    -> /collection-batches/:id
initial_analysis    -> /results?job=:id
report              -> /results?report=:id
platform readiness  -> /platform-accounts
```

Persistent projection rules:

- Read every persistent section using one explicit SQLite read transaction.
- An enabled schedule is attention when its current rule is missing, disabled,
  invalid under `compose_monitoring_terms`, over `MAX_SEARCH_TERMS`, or its
  latest occurrence for the current revision is skipped/missed/interrupted.
- Do not present an invalid schedule as `next_collection`; continue searching
  in due-time/ID order for the earliest valid schedule.
- A newer healthy terminal state clears an older unhealthy state for the same
  natural owner. A running successor does not yet clear the older terminal
  failure.
- Cancelled work and intentionally disabled schedules are not attention.
- `latest_report` selects the newest `completed` or truthful `empty` report.
  A newer failed report is attention but does not replace the last readable
  report.
- Validate completed report root documents with the existing topic-report
  models. Never fall back silently past corrupt persisted output.

The frontend combines two independent queries. `not_checked` and `checking`
prevent an all-normal claim; `coming_soon` is excluded from the readiness
denominator. A failed refetch retains last validated data and labels it stale.
Controls are refresh or navigation only.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Workbench service disabled | `503 workbench_unavailable` |
| SQLite/read-model/strict document failure | bounded `503`; no private detail |
| Missing or disabled schedule rule | schedule attention; exclude from next |
| Invalid composed rule | `invalid_monitoring_rule`; exclude from next |
| More than `MAX_SEARCH_TERMS` | `too_many_search_terms`; exclude from next |
| Newer report failed | report attention plus older readable report |
| No readable report or schedule | truthful `null`; frontend explains empty state |
| Platform endpoint unavailable | persistent snapshot still renders; readiness unknown |
| Cached refetch fails | retain content, expose last `observed_at`, mark stale |
| Protocol-invalid JSON | frontend invalid-response error; do not coerce values |

All responses use `Cache-Control: no-store`. Product errors use the standard
`{"detail":{"code":...,"message":...}}` envelope.

### 5. Good / Base / Bad Cases

- Good: an enabled valid schedule and fully connected catalog produce a known
  duty state and the globally earliest `next_collection`.
- Base: an empty database produces no attention, no activity, no report, and no
  next collection; the UI renders explanatory empty copy instead of zeros.
- Good: a failed report is shown as attention while the previous completed or
  empty report stays readable.
- Bad: a rule was edited into 21 effective search terms; the schedule must be
  attention and cannot be shown as the next executable collection.
- Bad: platform readiness is unknown; the UI must not say “当前运行正常”.

### 6. Tests Required

- Backend temporary-SQLite tests assert empty projection, global due ordering,
  invalid-rule exclusion, current-revision occurrence ownership, later-success
  clearing, cancellation/disable exclusions, progress counts, strict completed
  and empty reports, newer-failure coexistence, safe 503s, and zero writes or
  worker/browser/model calls across repeated GETs.
- Frontend API tests assert exact Zod decoding, abort propagation, and bounded
  error mapping.
- Route tests assert loading, empty, normal, unknown, attention, active, stale,
  partial/full error, report variants, exact links, and absence of manual
  handling/KPI/raw-result copy or mutation calls.
- Run backend Ruff/pytest and frontend frozen install, Prettier, Oxlint,
  TypeScript, Vitest, and build gates. Route changes require desktop and narrow
  loopback browser QA with no overflow, console errors, or mutation requests.

### 7. Wrong vs Correct

#### Wrong

```python
# Enabled alone does not mean executable.
SELECT * FROM collection_schedules
WHERE enabled = 1
ORDER BY next_due_at
LIMIT 1
```

```tsx
// Unknown readiness must not be coerced to healthy or zero.
const normal = attention.length === 0
```

#### Correct

```python
# Inspect candidates in deterministic due order and return the first whose
# current enabled rule composes successfully within MAX_SEARCH_TERMS.
for schedule in enabled_future_schedules:
    if current_rule_issue(schedule.monitoring_rule_id) is None:
        return schedule
```

```tsx
const fullyKnown =
  snapshot !== undefined &&
  platformCatalog !== undefined &&
  healthConnected &&
  unknownPlatforms === 0 &&
  !stale
```

