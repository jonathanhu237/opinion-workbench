# Batch Search Guidelines

> Executable cross-layer contract for durable, serial multi-platform collection batches.

## Scenario: Durable serial multi-platform collection batch

### 1. Scope / Trigger

Use this contract when one user action must search one monitoring-rule snapshot on 1–5 supported
platforms. The batch is the durable orchestration record; every platform attempt remains an ordinary
`search_run` so existing normalization, deduplication, result pages, terminal statuses, and adapters
stay authoritative.

Use this boundary instead of running several `POST /search-runs` requests in React. Client-side
sequencing is not durable across refresh or application restart and cannot enforce one borrowed
browser owner across the whole batch.

### 2. Signatures

Database version 7 keeps every version-6 table unchanged and adds:

```text
search_batches(
  id, monitoring_rule_id, rule_name, max_results_per_term, status,
  current_item_position, created_at, started_at, finished_at
)
search_batch_terms(batch_id, position, value)
search_batch_items(
  batch_id, position, platform, status, created_at, started_at, finished_at
)
search_batch_attempts(
  batch_id, item_position, attempt_number, search_run_id, created_at
)
```

Required identities and exclusivity are:

```text
PRIMARY KEY search_batch_terms(batch_id, position)
PRIMARY KEY search_batch_items(batch_id, position)
UNIQUE      search_batch_items(batch_id, platform)
PRIMARY KEY search_batch_attempts(batch_id, item_position, attempt_number)
UNIQUE      search_batch_attempts(search_run_id)
UNIQUE INDEX one active search_batches row where status is queued/running/paused
```

The HTTP boundary is:

```http
POST /api/v1/search-batches
GET  /api/v1/search-batches?limit=20&before_id=<optional-int64>
GET  /api/v1/search-batches/{batch_id}
GET  /api/v1/search-batches/{batch_id}/items/{position}/attempts
POST /api/v1/search-batches/{batch_id}/continue
POST /api/v1/search-batches/{batch_id}/cancel
GET  /api/v1/search-runs?scope=standalone&limit=20&before_id=<optional-int64>
```

Create input is strict and exact:

```json
{
  "monitoring_rule_id": 1,
  "platforms": ["toutiao", "wb", "ks", "dy", "xhs"],
  "max_results_per_term": 10
}
```

- `platforms` contains 1–5 unique supported literals. The service always stores them in catalog
  order `toutiao -> wb -> ks -> dy -> xhs`, regardless of request order.
- Batch status is `queued | running | paused_for_manual_action | completed |
  completed_with_failures | cancelled | internal_error`.
- Item status is `queued | running | paused_for_manual_action | completed | failed | cancelled`.
- `current_item_position` is informative progress state; clients derive terminality from the status
  and must not use a null position as the only completion signal.

### 3. Contracts

#### Admission, ownership, and persistence

- Create snapshots the enabled rule name and ordered terms, inserts every selected platform item,
  claims one lifespan-owned `search_batch` browser operation, and returns HTTP 202 before browser
  work finishes. Creation of batch, terms, and items is one transaction.
- Only one batch may be active or paused. The partial unique index is the durable backstop; the
  shared `BrowserOperationCoordinator` also excludes standalone searches and account checks.
- The batch owns the coordinator for its entire queued/running/paused lifetime. Child runs execute
  through the reusable single-run boundary without independently claiming or releasing it.
- Browser/network work never runs in a SQLite transaction. Creating an attempt atomically inserts
  its run, term snapshot, attempt relation, and item transition so no orphan child can be observed.
- Rule deletion uses `ON DELETE SET NULL`; batch name and terms remain immutable snapshots.
  Attempt rows use `ON DELETE RESTRICT` for their child runs.

#### Serial state machine

- Execute exactly one item at a time in stored catalog position. A later item cannot start until the
  latest attempt for every earlier item is terminal.
- Each item attempt is an immutable child `search_run`. `completed_with_results` and
  `completed_empty` complete the item. Login, block/rate-limit, structure change, browser
  unavailable, timeout, cancellation, or internal failure fail that item and ordinary failures
  continue with the next queued platform.
- `manual_challenge_required` is different: mark the item and batch
  `paused_for_manual_action`, retain batch ownership, preserve the visible official page, and do not
  start a later platform.
- `POST /continue` is valid only while paused. It returns the paused item to the queue; the runner
  creates a new attempt number and a new child run before retrying that same platform. Never mutate
  or reuse the prior attempt.
- `POST /cancel` is valid only for an active batch. It cancels the current worker operation, marks
  the current and every queued item cancelled, preserves completed/failed attempts and observations,
  then releases ownership. A raced cancellation must release ownership idempotently even if the
  runner has not reached its `finally` block.
- Finalize as `completed` only when every item completed; use `completed_with_failures` when every
  item is terminal and at least one failed. Public history derives terminal-item counts from items.
- On process startup, a paused batch remains paused and reclaims browser ownership without starting
  work. A running batch reconciles its interrupted active attempt as a real failure and resumes from
  the next queued item. Terminal batches never restart.

#### API and frontend projection

- Batch list order is `id DESC` with `before_id`; batch child runs are excluded from the new primary
  history and remain reachable through batch detail. `scope=standalone` preserves pagination for
  legacy single-platform history and deep links.
- Detail returns rule/term snapshots, ordered items, latest attempt summaries, aggregate status,
  current position, counts, and timestamps. Attempt history returns all immutable attempts for one
  item in attempt-number order.
- React submits one batch, navigates to `/collection-batches/:batchId`, and polls only while active.
  The detail view shows the fixed platform execution rail, aggregate progress, each latest result,
  retry history, and Chinese failure guidance. Paused state exposes Shadcn `继续` and `取消` actions
  with nearby `aria-live` feedback and disables duplicate mutations.
- Runtime decoders reject catalog-order drift, item/latest-run platform or status inconsistency,
  impossible paused/completed aggregates, unknown fields, and malformed timestamps/counts. Do not
  repair an inconsistent response in the UI.

### 4. Validation & Error Matrix

| Condition | HTTP / state | Required behavior |
| --- | --- | --- |
| Malformed body/query/path, duplicate/empty/unknown platforms | HTTP 422 `invalid_request` | No batch, run, or browser work |
| Rule missing | HTTP 404 `monitoring_rule_not_found` | No batch |
| Rule disabled | HTTP 409 `monitoring_rule_disabled` | No batch; direct operator to enable it |
| Rule has more than 20 terms | HTTP 422 `too_many_search_terms` | No batch; split the rule |
| Another batch/search/account operation owns Chrome | HTTP 409 `browser_operation_active` | Existing operation continues |
| Batch/item missing | HTTP 404 `search_batch_not_found` | No mutation |
| Cancel for a terminal batch | HTTP 409 `search_batch_not_active` | Preserve terminal state |
| Continue for a non-paused batch | HTTP 409 `search_batch_not_paused` | Do not create an attempt |
| SQLite unavailable or rule-load storage failure | HTTP 503 `search_storage_unavailable` | Constant message; no path/SQL/raw exception |
| Child completes with results or empty | item `completed` | Continue with the next item |
| Child reaches an ordinary failure | item `failed` | Continue with the next item; final batch reports failures |
| Child reaches manual challenge | batch/item `paused_for_manual_action` | Keep ownership and visible page; do not bypass or advance |
| User continues a paused batch | new child attempt | Preserve prior run and retry the same position first |
| User cancels an active batch | batch/items `cancelled` | Preserve prior observations and release ownership once |
| Startup finds running batch | interrupted attempt failed, later queued item resumes | No duplicate attempt or concurrent browser work |

### 5. Good / Base / Bad Cases

- **Good:** The request lists `xhs, toutiao, wb`; storage normalizes it to
  `toutiao, wb, xhs`, runs only one child at a time, and links each result page to its own durable
  run. A browser failure on Weibo does not prevent Xiaohongshu from starting.
- **Base:** One selected platform produces one child attempt and a completed batch while the legacy
  run detail and global deduplication behavior remain unchanged.
- **Bad:** React fires five standalone requests, two pages control Chrome concurrently, a failed
  platform aborts all later platforms, a manual challenge is treated as ordinary failure, or
  `continue` rewrites the prior child run.

### 6. Tests Required

1. Migration: fresh v7, exact v6→v7, partial-DDL rollback, repeated initialization, forward-version
   rejection, foreign keys/indexes/partial unique index, and unchanged version-6 row counts.
2. Repository: atomic batch/term/item creation, catalog order, duplicate-platform rejection, attempt
   relation rollback with run/terms/item state, immutable attempt numbering, rule deletion, list
   cursor, cancellation, finalization, and startup reconciliation.
3. Service/API: strict 202/200 models, every 404/409/422/503 mapping, one browser owner across account/
   standalone/batch features, exact serial scheduling, ordinary failure continuation, manual pause,
   repeated continue attempts, cancel races, shutdown, and restart recovery.
4. Frontend: Shadcn checkbox default-all/subset/empty validation, stable catalog order, runtime
   decoder rejection cases, active-only polling, batch history and deep links, platform result links,
   pause/continue/cancel feedback, legacy history cursor loading, keyboard/focus, and mobile layout.
5. Real browser: an approved bounded three-platform batch proving one visible browser operation at a
   time, truthful success/failure guidance, preserved user tabs, result drill-down, cancellation,
   restart persistence, and no secret or term leakage in API/log/schema evidence.

### 7. Wrong vs Correct

#### Wrong

```typescript
// Refresh loses sequencing, and every request competes for the borrowed browser.
await Promise.all(platforms.map((platform) => startStandaloneRun({ platform })))
```

```python
# Retrying a challenge by mutating the old run destroys the audit trail.
await repository.reset_run(paused_attempt.search_run_id)
```

#### Correct

```typescript
const batch = await startSearchBatch({ monitoringRuleId, platforms, maxResultsPerTerm })
navigate(`/collection-batches/${batch.id}`)
```

```text
claim one batch browser owner
  -> for item in persisted catalog order
       -> create immutable child run + attempt relation atomically
       -> await exactly one terminal outcome
       -> ordinary failure: continue; challenge: pause; success: continue
  -> derive final batch status -> release owner exactly once
```
