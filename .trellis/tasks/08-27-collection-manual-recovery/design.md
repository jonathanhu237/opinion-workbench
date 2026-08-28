# Manual Collection Recovery — Design

## Status and boundaries

Approved for implementation on 2026-08-28 after the user accepted the final planning summary.
The user approved pausing the whole batch on platform failure. One vertical task owns
the browser/worker, durable recovery, and UI contracts because none independently delivers
usable recovery. Live batch operations and Git delivery remain separately scoped.

Supported platforms remain Toutiao, Weibo, Kuaishou, Douyin and Xiaohongshu. One-platform
batches use exactly the same flow. Historical standalone runs stay readable; this task does
not introduce a separate standalone-run recovery UI. The product remains React + FastAPI +
local SQLite with the existing persistent worker borrowing the user's Chrome session.

## 1. State transitions and operator intent

```text
running platform
  -> successful result/recognized empty -> next queued platform
  -> platform failure -> paused batch + paused item + unchanged failed attempt
       -> open platform -> show official page, remain paused
       -> continue -> new attempt at first unconfirmed term
            -> success -> next queued platform
            -> failure -> pause again
       -> skip platform -> skipped item -> next queued platform
       -> cancel batch -> cancelled remainder, retained results
```

- Every persisted platform failure pauses, including login, challenge, block/rate limit,
  unknown structure, unavailable browser, timeout and internal worker failure. No timer,
  page load, poll, or reconnection starts a retry. Explicit user cancellation is not a pause.
- The batch retains the existing single browser-operation owner while paused. Account
  checks, other batches and result-opening operations cannot compete with manual handling.
- Add item status `skipped`. It is terminal but is not success; any skipped/failed item
  makes final aggregate status `completed_with_failures`. Terminal-count labels say
  `已结束`, not `已完成`, when they include skipped/failed items.
- A storage failure that cannot durably record the pause is a service failure, not fake
  recoverability. Stop dispatching further work and show the existing storage error.
- Startup reconciles interrupted running attempts as failures, then pauses their batch
  at the same item. Already-paused batches remain paused. Restore ownership without
  launching the worker, connecting Chrome, or visiting a platform. Unstarted queued work
  also awaits explicit continuation after a process restart; it is not silently retried.

## 2. Durable term completion

### Worker protocol

Upgrade only the separate search protocol from v1 to v2. Auth protocol v2 and standalone
CLI behavior remain unchanged. Reject old/malformed search frames rather than silently
falling back; deploy backend and derivative together and recycle the old owned worker.

Each run retains the full immutable `terms` snapshot and records an immutable
`execution_start_term_position`. The v2 command sends only the remaining suffix, with
request-local positions starting at zero. It adds an exact `term_completed` event carrying
`term_position` and `item_count`, separate from existing `progress/term_started` events.
The run service maps every start/item/completion callback exactly once:
`original_position = execution_start_term_position + local_position`. Product progress,
provenance and completion rows use original positions; worker counts use the suffix length.

- Each adapter emits completion only after finishing all bounded pages, normalization,
  item delivery and terminal-shape checks for that term. A valid zero-result term emits
  completion too. Failure or cancellation must not emit completion for the failed term.
- Strict reader order is start -> zero or more items -> completion -> next start. Persist
  each callback before reading the next frame. Reject items after completion, skipped or
  duplicate completion positions, wrong platform/UUID, and successful final results before
  every requested term completes. Existing limits, secret filtering and cancellation
  correlation remain in force.
- Neither item count, last item timestamp nor `term_started` alone is a completion marker.
  A failed term may be retried from its first page; page-level resume is out of scope.
- Ordered IPC emission is not a database ACK to the producer. A crash before a checkpoint
  commits can repeat that unconfirmed term, even if the remote request succeeded. This
  design promises durable deduplication, not exactly-once platform requests.

### SQLite (next migration after current v9)

Use the existing sqlite3 migration owner and short explicit transactions. Proposed records:

- `search_runs.execution_start_term_position`, immutable, default 0 for legacy, plus
  `search_protocol_version` (old rows 1, every new run writer explicitly 2).
- `search_run_term_completions(run_id, term_position, proof, result_count, completed_at,
  recorded_at)`, keyed by the existing `(run_id, position)` term relation. Proof is exactly
  `worker_term_completed | legacy_next_term_started | legacy_run_succeeded`. V2 completion
  timestamps describe backend acknowledgement, not exact platform execution time. Legacy
  proof has null `completed_at`; never fabricate an old per-term timestamp.
- Derive the contiguous completed prefix from the union of proof rows across item attempts;
  do not maintain another mutable batch cursor/count. Public `checkpoint_basis` is
  `explicit | legacy_inferred | mixed | unknown`; `next_term_position` is null when the
  whole snapshot is confirmed, accompanied by `remaining_term_count=0`.
- Add item `pause_reason` (`attempt_failed | process_interrupted | null`) and
  `completion_basis` (`attempt_success | confirmed_terms | null`).
- `search_batches.control_revision` is incremented on control-state transitions, including
  continue, pause, skip, cancel and explicit historical recovery. Rebuild affected CHECK
  constraints for `skipped` without changing existing IDs, foreign keys or observations.
- An append-only `search_batch_recoveries` relation records batch/item identity, previous
  control revision, previous batch status and batch/item finish timestamps plus recovery
  time whenever an old failed item is explicitly reopened. Reopening cannot erase the
  original terminal timestamp from history.

Completion inserts validate the active run, expected term, prior completions and current item
inside one short transaction. Derived progress cannot move beyond the first unconfirmed term.
New attempts inherit the confirmed
prefix but never rewrite old runs. Every attempt retains the full snapshot; matched-term
positions and original detail URLs remain meaningful.

If the final term completion was committed but cleanup/final worker result failed, the cursor
may equal `term_count` while the attempt truthfully failed. On explicit continue, finish the
item with `completion_basis=confirmed_terms`, retain the failed attempt, and issue no empty
search command and no duplicate request. UI and response decoders must accept this explicit
basis instead of inventing a successful latest attempt.

### Legacy records

Old terminal success proves all terms completed. For a failed old attempt, a persisted start
position p can conservatively support only terms before p if its full snapshot and producer
order are valid; never mark p complete. Record this as `legacy_inferred`, not an explicit
completion event. A valid preflight failure with no started term confirms no new work.
Do not apply legacy inference to v2 runs missing a completion. Inconsistent snapshots,
out-of-range positions or holes fail closed as recovery-unavailable, with skip/cancel still
available; do not silently restart from zero and claim no completed terms will repeat.
No migration changes old attempt outcomes or performs work.

Batch 8's paused XHS item can continue from its recorded interrupted term under this rule.
Its earlier failed Toutiao item is not automatically requeued or substituted for XHS.

## 3. Explicit recovery of an existing failed item

To cover already-recorded failures, add an explicit `recover` action for one `failed` item
in a `completed_with_failures` batch. It is allowed only when no batch/search/account operation
owns the browser. Claim the coordinator and durably reopen that batch/item as paused, without
searching; the user then opens the platform, continues or skips using the ordinary flow.

Preserve the failed run, all other completed/skipped items, rule snapshot and observations.
Do not restore completed work to the queue. This action does not reopen cancelled/successful
batches, switch away from a different paused item, or automatically retry other failed items.
Concurrent recovery competes through the existing partial unique active-batch index plus the
coordinator; failed admission releases the newly claimed owner. Its audit record and state
transition commit together. A conflict makes no changes. Batch 8 therefore requires resolving/skipping its
current XHS pause before manually recovering its earlier failed Toutiao item.

## 4. Browser handoff is not verification

Extend the persistent worker with a strict, bounded search-v2 `manual_page` command:
`action=show|close`, fresh request UUID, exact platform. Backend verifies the paused batch,
current item and latest attempt before issuing it under the existing batch owner. It accepts
no browser URL, profile path, cookies or caller-provided script.

- Keep the current-generation task-owned official search page on every non-success,
  non-cancel failure when the page is still usable and trusted. Preserve the underlying
  constant failure category; never swallow an unsafe navigation or protocol error.
- `show` focuses that page without reloading it. If no usable trusted owned page remains,
  create/register one page and navigate once to the platform's fixed official homepage.
  Do not enumerate or operate unrelated user tabs. An unsafe/stale handle is never trusted.
- `show` never calls search, `open_result`, auth checking, signer or cookie extraction;
  it does not click, inspect challenge internals, fill inputs, or manufacture a challenge URL.
- Fixed show outcomes: `opened_existing`, `opened_homepage`, `browser_unavailable`,
  `navigation_failed`, `internal_error`, `cancelled`. Only the first two mean an official page was shown.
  None means authenticated, verified or recovered. In particular, an API-level challenge
  can leave a normal homepage with no visible CAPTCHA; UI must say this accurately.
- `close` has exactly `closed | not_present | browser_unavailable | internal_error | cancelled`
  outcomes and is an idempotent narrow cleanup command. With no live transport it does not
  reconnect just to close a nonexistent page. Skip/cancel settles or cancels an in-flight
  show operation and clears only owned pages before another platform can start.
- Continuing ends manual handling. The next explicit search may then recreate the owned
  search page and refresh platform-scoped session state through the existing adapter.
- Bound show by the existing navigation timeout (30 seconds), existing 45-second open-operation
  budget and 3-second correlated cancellation grace;
  keep correlated cancellation available. A failed show leaves the batch paused. Search
  timeouts and worker recycle retain existing bounded cancellation/transport-release rules.

No manual handling token, CAPTCHA URL, screenshot, raw response or browser state is persisted.
Losing the browser connection invalidates the in-memory page handle, not durable progress.

## 5. API contracts and stale-action fencing

Retain the route/service/repository separation and strict request/response validation.
New recovery controls carry the observed `expected_revision` and `expected_run_id`; the
server derives platform/terms from storage. Compare these and current item/status in the same
transaction that applies the transition. Revision closes the race between requeueing and
creating a new attempt, where an old run ID alone is not sufficient.

| Endpoint | Meaning | Response |
| --- | --- | --- |
| `POST /search-batches/{id}/continue` | Current paused item, explicit suffix retry or confirmed no-work completion | 202 detail |
| `POST /search-batches/{id}/skip` | Mark current paused item skipped and advance | 202 detail |
| `POST /search-batches/{id}/manual-page` | Bounded show operation while remaining paused | 200 fixed outcome |
| `POST /search-batches/{id}/items/{position}/recover` | Reopen one eligible old failed item as paused, without searching | 202 detail |
| `POST /search-batches/{id}/cancel` | Cancel active batch/remainder; guard expected revision | 202 detail |
| `GET /search-batches/{id}/items/{position}/results` | Union of platform results over all attempts | 200 result page |

New bodies are exact objects; `expected_run_id` is required for an existing paused/failed
attempt, and nullable only in an explicitly modelled pre-attempt restart pause. No-body legacy
continue clients fail validation instead of accidentally acting on a later pause. Cancel needs
only the batch revision. Keep exact 404/409/422/503 envelopes and add stable codes for stale
recovery state and an item/batch not eligible for recovery. Old API errors and unrelated routes
remain unchanged. Duplicate/late requests must not create attempts, skip a later platform or
close the page of a newly-running operation.

Continue/skip/manual-page bodies are exactly `{item_position, expected_run_id, expected_revision}`;
recover takes position from the path and exactly `{expected_run_id, expected_revision}`;
cancel takes exactly `{expected_revision}`. IDs are 1..signed-int64 max; revision is
0..signed-int64 max, and positions are 0..4. Stale controls use HTTP 409 `search_batch_state_changed`; invalid
checkpoint proof uses 409 `search_batch_recovery_unavailable`; a terminal batch/item not
eligible for explicit recover uses 409 `search_batch_item_not_recoverable`. The manual-page
response is exactly `{outcome}` with the fixed show-outcome enum. The worker close command
is internal; it is not an arbitrary public page-management API.

Detail adds revision and, per item, confirmed progress/provenance, aggregate new/repeated/total
counts and completion basis. The last attempt remains separately visible. A queued item may
retain a previous terminal attempt during a guarded continuation; do not remove its history to
satisfy the old frontend decoder. Paused states may carry any supported failure category, or
a documented interrupted/pre-attempt state, not only a CAPTCHA.

Keep item metadata/latest run/checkpoint/count reads within one explicit SQLite read
transaction to avoid torn projections during a transition. Drain in-flight threaded writes
before terminalization/ownership transfer; cancelling an `asyncio.to_thread` await does not
stop that write. Late callbacks must satisfy active-run/current-attempt SQL predicates and
cannot mutate a cancelled, skipped or replaced attempt. Do not hold the service lock while
awaiting a runner/manual task whose finalizer needs that lock.

## 6. Result and count semantics

Query the union of `search_run_contents` through the item's attempt relations. One platform
content ID appears once. Use the earliest observation relationship within this batch item to
classify new/repeated, so discovering it in attempt 1 and seeing it again in attempt 2 does not
inflate counts or convert the aggregate from new to repeated. Merge matched terms in original
batch order; never infer provenance from current mutable monitoring-rule input.

Keep global first-seen/last-seen behavior and each run's own historical classifications unchanged.
Do not sum latest-attempt counts or independent run counts. Use the existing result filters and
pagination limits (1–50), deterministic ordering and bounded normalized result shape; changing
publication-time sorting is a separate task. Existing per-term/per-attempt request limits remain
unchanged; the aggregate can include distinct partial results from more than one attempt.

For XHS result opening, return a deterministic supporting `source_run_id` that actually owns the
result relation, and reuse its existing narrow result-open endpoint. Other platform links remain
unchanged. While the batch holds browser ownership, XHS opening remains unavailable with clear
feedback; it must not interrupt the paused manual page. Read-only result browsing is available.

## 7. UI design

Use the existing batch-detail route, platform rail and Shadcn/Base UI components. Do not change
the palette, fonts, sidebar or product identity. The compact pause card shows platform, confirmed
term progress, failed/next term and one cause-specific explanation, followed by:

`打开平台` · `继续采集` · `跳过此平台` · `取消批次`

`opened_*` feedback says only `已在谷歌浏览器中打开平台页面`. A challenge message asks the user
to look for the platform's verification prompt and explains when none is visible; a parser
failure says the results could not be recognized, not that the user needs to log in again.
Opening a page never starts collection. A repeated failure remains paused and updates its cause.

Each platform card shows aggregate counts, full-snapshot progress and old-attempt links. Reuse
the existing result-card presentation in an expanded results section on batch detail; selected
platform/filter/offset live in URL search params, not a second mutable data store. Eligible old
failed items have `处理此平台`; unavailable recovery does not silently replace the current pause.

TanStack Query owns resource state and invalidation. No client-side retry queue or durable local
checkpoint. Lock conflicting controls during mutations, visibly label the active operation,
preserve a bounded cancel path, announce outcomes near the controls, and refetch on stale-state
errors without automatically repeating the mutation. Maintain keyboard/focus behavior, semantic
buttons, accessible text status and mobile wrapping. See the targeted UI research for evidence.

## 8. Compatibility, rollout and risks

- Main edits local source; validation is on Centaurus after code-only one-way rsync. Never
  copy runtime DB, browser profile, keys, `.git` or local dependencies. Lightweight local
  browser acceptance uses the existing previously approved architecture, not heavy local tests.
- Back up the local SQLite database privately before an approved migration/restart. Validate
  v9-to-next-version migration and rollback on isolated copies first. This planning turn never
  mutates or backs up runtime data. Preserve existing paused work across deployment.
- Backend and worker protocol changes ship together. Do not downgrade a migrated live DB with
  old code; use a private pre-upgrade backup only after explicit direction and explain that it
  cannot contain post-upgrade observations. No automatic destructive rollback.
- Preserve unrelated AI-settings/monitoring-rule edits. Derivative source stays a submodule;
  when Git delivery is requested, push its clean revision before updating the parent gitlink.
- Platform restrictions, real CAPTCHA availability and schema drift remain external constraints.
  This feature supplies an honest recovery path, not a promise that manual work fixes every
  failure. Exact historical Toutiao parsing diagnosis remains outside this task.

## Evidence

`research/backend-checkpoint-contract.md`, `research/browser-handoff-contract.md` and
`research/ui-recovery-evidence.md` record current code anchors, limits and validation targets.
Research contains alternative proposals; the canonical choices here are suffix-local IPC
mapped once by the service, proof-tagged completion rows with derived progress, guarded bodies
on every recovery control, revision-guarded cancel, and explicit audited historical recovery.
In particular, do not adopt the browser research's initial bodyless endpoint suggestion.
Fine-grained stage/evidence-source diagnostics suggested in research are deferred: retain the
existing truthful terminal category plus safe restart/recovery reasons for this MVP; opening
a page never asserts that a visible challenge was detected.

The PRD is authoritative for product acceptance; this design changes the old ordinary-failure
auto-advance and full-platform retry contracts deliberately, not by weakening validations.
