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

Database version 10 preserves the existing batch/run history and adds durable recovery metadata:

```text
search_batches(
  id, monitoring_rule_id, rule_name, max_results_per_term, status,
  current_item_position, control_revision, created_at, started_at, finished_at
)
search_batch_terms(batch_id, position, value)
search_batch_items(
  batch_id, position, platform, status, pause_reason, completion_basis,
  created_at, started_at, finished_at
)
search_batch_attempts(
  batch_id, item_position, attempt_number, search_run_id, created_at
)
search_run_term_completions(
  run_id, term_position, proof, result_count, completed_at, recorded_at
)
search_batch_recoveries(
  id, batch_id, item_position, previous_control_revision, previous_batch_status,
  previous_item_status, previous_batch_finished_at, previous_item_finished_at, recovered_at
)
```

Every run also stores immutable `execution_start_term_position` and `search_protocol_version`.
Old rows use offset 0 / protocol 1; every new run writer explicitly stores protocol 2. A new attempt
retains the full immutable terms snapshot even when it executes only a suffix.

Required identities and exclusivity are:

```text
PRIMARY KEY search_batch_terms(batch_id, position)
PRIMARY KEY search_batch_items(batch_id, position)
UNIQUE      search_batch_items(batch_id, platform)
PRIMARY KEY search_batch_attempts(batch_id, item_position, attempt_number)
UNIQUE      search_batch_attempts(search_run_id)
PRIMARY KEY search_run_term_completions(run_id, term_position)
FOREIGN KEY search_run_term_completions(run_id, term_position) -> search_run_terms(run_id, position)
UNIQUE INDEX one active search_batches row where status is queued/running/paused
```

The HTTP boundary is:

```http
POST /api/v1/search-batches
GET  /api/v1/search-batches?limit=20&before_id=<optional-int64>
GET  /api/v1/search-batches/{batch_id}
GET  /api/v1/search-batches/{batch_id}/items/{position}/attempts
GET  /api/v1/search-batches/{batch_id}/items/{position}/results?kind=all|new|repeated&limit=50&offset=0
POST /api/v1/search-batches/{batch_id}/continue
POST /api/v1/search-batches/{batch_id}/skip
POST /api/v1/search-batches/{batch_id}/manual-page
POST /api/v1/search-batches/{batch_id}/items/{position}/recover
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
- Item status is `queued | running | paused_for_manual_action | completed | failed | skipped | cancelled`.
- `current_item_position` is informative progress state; clients derive terminality from the status
  and must not use a null position as the only completion signal.

Control bodies are strict, exact objects; missing legacy bodies fail validation:

```text
continue / skip / manual-page: {item_position, expected_run_id, expected_revision}
recover:                      {expected_run_id, expected_revision}
cancel:                       {expected_revision}
```

Positions are integers 0–4; IDs are 1..signed-int64 max and revisions 0..signed-int64 max.
`expected_run_id` can be null only for a recorded pre-attempt restart pause. Create/continue/skip/
recover/cancel return 202 detail. Manual-page returns 200 `{outcome}`; it is not a search or login check.

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
- Read item metadata, latest attempts, checkpoints and counts in one explicit SQLite read
  transaction. Drain threaded database writes before cancellation/ownership transfer; cancelling
  an `asyncio.to_thread` await does not stop its thread. Use `services/settled_tasks.py` at this boundary.
- If runner persistence fails, the `internal_error` fallback settles still-active child runs and
  items atomically before ownership release. Preserve already committed successful runs and project
  their items completed; never leave an orphan active run or relabel success as an item failure.
- Every control compares the observed revision, current item and latest run in the same transaction
  as the transition. Increment `control_revision` on control-state changes; an old run ID alone
  does not fence the gap before a new attempt is created. Late callbacks require active-run and
  current-attempt predicates. Never hold the service lock while awaiting a finalizer that needs it.

#### Serial state machine

- Execute exactly one item at a time in stored catalog position. A later item cannot start until the
  latest attempt for every earlier item is terminal.
- Each item attempt is an immutable child `search_run`. `completed_with_results` and
  `completed_empty` complete the item. Every other persisted platform outcome pauses the item and
  batch with `pause_reason=attempt_failed`; preserve the failed run and do not dispatch a later
  platform. Explicit batch cancellation is different and remains terminal.
- `POST /continue` is valid only while paused with a trusted checkpoint. Queue that item and create
  a new immutable attempt at its first unconfirmed term. Send only the suffix to the worker; never
  mutate the prior run or repeat confirmed terms. If every term is already proved, finish the item
  with `completion_basis=confirmed_terms` without creating a run or issuing an empty command.
- `POST /skip` marks only the guarded paused item `skipped`, retains its attempts/results and then
  advances to the next queued item. Skipped is terminal but never success.
- `POST /cancel` is valid only for an active batch. It cancels the current worker operation, marks
  the current and every queued item cancelled, preserves completed/failed attempts and observations,
  then releases ownership. A raced cancellation must release ownership idempotently even if the
  runner has not reached its `finally` block.
- Finalize as `completed` only when every item completed; use `completed_with_failures` when every
  item is terminal and any item skipped/failed. Counts are derived from items.
- On startup, reclaim paused ownership without worker launch, connection or search. Interrupted
  running/queued work pauses with `pause_reason=process_interrupted`, including a null-attempt pause.
  A run that already committed success before its item transition keeps that success: reconcile
  the item using database-only work, then pause the next unfinished item or finalize the batch.
  No startup path searches or automatically retries. Terminal batches never restart.
- Only explicit `/items/{position}/recover` can reopen a `failed` item in a
  `completed_with_failures` batch, and only with no other browser owner. Atomically append the old
  batch/item status and finish timestamps to `search_batch_recoveries`, reopen that item as paused,
  and leave every other item untouched. This performs no search. Successful/cancelled/internal-error
  batches are not recoverable. An old failed item's latest *run* may be cancelled; that does not
  mean the batch itself was cancelled.

#### Checkpoint proof and manual page

- Protocol v2 emits ordered `term_started -> items -> term_completed` for every suffix-local term,
  including valid empty results. The run service maps `original = execution_start + local` once.
  Await each persistence callback before processing the next frame; prove result count, order and
  provenance transactionally. Neither an item nor `term_started` proves completion.
- Completion proofs are `worker_term_completed | legacy_next_term_started | legacy_run_succeeded`.
  Explicit completion has a backend acknowledgement time. Legacy inference has null `completed_at`;
  never invent historical per-term times. Valid old success proves all terms; valid old progress p
  proves only positions before p. Do not infer a missing v2 completion from v2 progress.
- Derive one contiguous completed prefix over all immutable attempts. Validate snapshots, platforms,
  attempt order, offset, current position, proof sequence and observed counts. Corrupt/missing proof
  means recovery unavailable, not a full retry disguised as continuation. Skip/cancel remain usable.
  A crash before persistence may repeat the unconfirmed term; this is not exactly-once platform I/O.
- In v2, current progress can be the last confirmed term (completion committed) or the next
  unconfirmed term (start committed), not a jump beyond missing proof rows. A successful v2 run
  requires proof for every suffix term. Legacy success remains governed by its distinct v1 proof.
- `manual_page` is a separate search-v2 command with exact UUID/platform and `action=show|close`,
  no URL, terms or browser secrets. Show focuses the current-generation trusted task-owned page
  without reload/probe/search; if none survives, explicitly open the platform's fixed homepage once.
  Never enumerate or reacquire user tabs. Disconnect callbacks must match their session generation.
- Show outcomes are `opened_existing | opened_homepage | browser_unavailable | navigation_failed |
  internal_error | cancelled`. None means authenticated or CAPTCHA solved; an API challenge can
  leave only a normal homepage. Navigation is bounded to 30s, overall operation to 45s, cancel grace
  to 3s. Failed show keeps the batch paused. Internal close is narrow/idempotent and does not launch
  a worker or reconnect when no live transport exists. Skip/cancel drain any pending show before
  transferring browser ownership.

#### API and frontend projection

- Batch list order is `id DESC` with `before_id`; batch child runs are excluded from the new primary
  history and remain reachable through batch detail. `scope=standalone` preserves pagination for
  legacy single-platform history and deep links.
- Detail returns snapshots, ordered items, latest attempts, revision, counts and timestamps.
  Item checkpoint fields are `completed_term_count`, `remaining_term_count`, `next_term_position`,
  `checkpoint_basis=explicit|legacy_inferred|mixed|unknown`, and `recovery_available`. The last field
  means proof trust, not that the browser is free or the item is eligible for recovery. Invalid proof
  projects 0 completed / N remaining / null next / unknown / false. Valid preflight with no proofs
  projects 0 / N / 0 / unknown / true. Completed items report `completion_basis=attempt_success` or
  `confirmed_terms`; only paused items have a non-null pause reason.
- Attempt history remains **attempt-number descending**. Aggregate results group content identity
  across all item attempts. The earliest attempt relationship supplies `kind` and `source_run_id`;
  union matched terms in original snapshot order. A/B followed by B/C displays A/B/C, not four rows
  or a changed classification for B. Preserve existing result ordering, filters and pagination.
- React submits one batch, navigates to `/collection-batches/:batchId`, and polls only while active.
  The detail view shows the fixed platform execution rail, aggregate progress, each latest result,
  retry history, and cause-specific Chinese guidance. Paused state exposes Shadcn `打开平台`,
  `继续采集`, `跳过此平台`, `取消批次`, with local loading locks and `aria-live` feedback. Unknown
  structure must not promise login will fix it. Do not change theme/fonts or add fake telemetry.
- TanStack Query owns server state; URL `platform`, `kind`, `offset` owns result selection. Controls
  have no automatic retry; stale responses refetch and never overwrite a newer cached revision.
  Aggregate XHS opening uses the recorded `source_run_id`, not the latest attempt, and is disabled
  while the batch owns the browser.
- Runtime decoders reject catalog-order drift, item/latest-run platform or status inconsistency,
  impossible paused/completed aggregates, unknown fields, and malformed timestamps/counts. Do not
  repair an inconsistent response in the UI. Valid exceptions include queued items with a previous
  failed attempt, null-attempt restart pauses and confirmed-terms completion with a failed latest run.
- A running item may have a terminal latest run in the real interval before the item-finalization
  commit. Accept that transition without fabricating a completed/paused item. Batch-only readonly
  attempt summaries may show actual missing child terms (including count 0) or a bounded historical
  out-of-range current position when `recovery_available=false`. Normal trusted checkpoints require
  matching term counts and in-range progress. Independent-run decoding/reads remain strict; do not
  synthesize lost terms or relax the whole application to make diagnostics render.

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
| Stale revision/item/run | HTTP 409 `search_batch_state_changed` | Do not act on a later pause or close another operation's page |
| Untrusted checkpoint | HTTP 409 `search_batch_recovery_unavailable` | No retry; leave skip/cancel available |
| Ineligible old item recovery | HTTP 409 `search_batch_item_not_recoverable` | Preserve all terminal history |
| SQLite unavailable or rule-load storage failure | HTTP 503 `search_storage_unavailable` | Constant message; no path/SQL/raw exception |
| Child completes with results or empty | item `completed` | Continue with the next item |
| Child reaches any persisted platform failure | batch/item `paused_for_manual_action` | Keep ownership and trusted owned page; do not bypass or advance |
| User shows the platform | fixed `{outcome}` | No search, probe or proof of login; remain paused |
| User continues with unconfirmed terms | new suffix-only child attempt | Preserve prior run, counts and original positions |
| User continues with all terms proved | item `completed`, basis `confirmed_terms` | No new attempt/worker request; retain failed latest run |
| User skips the paused platform | item `skipped` | Preserve results and advance; final status is not all-success |
| User cancels an active batch | batch/items `cancelled` | Preserve prior observations and release ownership once |
| Startup finds unfinished work | pause at first unfinished item | No browser launch, new attempt or automatic search |

### 5. Good / Base / Bad Cases

- **Good:** The request lists `xhs, toutiao, wb`; storage normalizes it to
  `toutiao, wb, xhs`, runs only one child at a time, and links each result page to its own durable
  run. Weibo fails on term 7 after six confirmed terms: the batch pauses, explicit continue sends
  terms 7..N only, and Xiaohongshu starts only after success or explicit skip.
- **Base:** One selected platform produces one child attempt and a completed batch while the legacy
  run detail and global deduplication behavior remain unchanged.
- **Bad:** React fires five standalone requests, two pages control Chrome concurrently, a failed
  platform silently advances without operator intent, `continue` repeats all completed terms,
  missing proof is treated as completion, or recovery overwrites prior attempts/finish timestamps.

### 6. Tests Required

1. Migration: fresh v10, real historical v9→v10, earlier supported upgrade paths, partial-DDL
   rollback, repeated initialization, forward rejection, foreign keys/indexes/active unique index,
   identical old columns/IDs/timestamps/relations and null legacy completion times. Seed old schemas
   using historical SQL, never a new repository that already requires future columns.
2. Repository: atomic batch/term/item creation, catalog order, duplicate-platform rejection, attempt
   relation rollback with run/terms/item state, immutable attempt numbering, rule deletion, list
   cursor, guarded cancellation/finalization, proof validation, missing/corrupt snapshots, no-work
   completion, append-only recovery audit and startup reconciliation without worker launch.
3. Service/API: strict 202/200 models, every 404/409/422/503 mapping, one browser owner across account/
   standalone/batch features, all-failure pause, zero-result completion, two successive suffix
   resumes, stale/double controls, delayed DB writes, pending page-show cancel, cleanup failures,
   final-result loss, success-before-item-transition crash gap, shutdown and no-I/O restart recovery.
4. Frontend: Shadcn checkbox default-all/subset/empty validation, stable catalog order, runtime
   decoder rejection cases, active-only polling, batch history and deep links, platform result links,
   all four recovery controls, historical failed recovery, no-work and unavailable-proof projections,
   merged result counts/source attempts/URL filters, stale-cache fencing, keyboard/focus and narrow layout.
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
       -> failure: pause; explicit show: stay paused; explicit skip/success: next item
       -> explicit continue: new suffix attempt or no-work confirmed completion
  -> derive final batch status -> release owner exactly once
```
