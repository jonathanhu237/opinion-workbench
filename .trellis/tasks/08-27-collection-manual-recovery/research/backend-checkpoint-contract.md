# Research: Backend durable term checkpoints and manual batch recovery

- Query: What is the smallest reliable backend contract for pausing a whole batch on any platform failure, retaining immutable attempts/results, and continuing only failed or unconfirmed terms?
- Scope: internal; repositories, services, SQLite migrations, FastAPI schemas/routes, worker framing/ordering, adapter completion boundaries, and existing offline tests. Planning only; no product/runtime writes, collection, network/browser/model actions, service operations, or Git operations.
- Date: 2026-08-28
- Status: proposed contract for design review, not implemented or validated against a live database.

## Findings

### 1. Decision summary

1. Keep one full immutable term snapshot per run and add an immutable `execution_start_term_position`. Run a suffix only; translate worker-local positions back to original positions once in the run service.
2. Add positive per-run/per-term completion evidence, independently of content rows. Zero-result successful terms must get the same durable completion acknowledgement as nonempty terms.
3. Upgrade the search protocol to v2 with explicit `term_completed`; leave the separate auth v2 contract unchanged. Await item persistence, then completion persistence, before consuming later frames or terminal success.
4. Derive a platform item's completed prefix and distinct result set across **all** its attempts. Keep individual run status/count/classification semantics unchanged. Do not sum attempts or show only the newest attempt as the platform result.
5. Every non-successful collection outcome pauses the current item and batch; subsequent platforms remain queued. Continue/skip require the exact paused item, expected latest run, and a durable control revision, checked in one transaction.
6. If all terms are confirmed but the last attempt failed after collection, explicit continue completes the item from its checkpoints without a new run or browser call. The failed attempt stays failed.
7. Legacy progress can prove a strictly earlier successful prefix under the inspected v1 producer/consumer contract. It cannot prove the current/final term complete. Label legacy-derived evidence explicitly; do not invent completion timestamps.
8. Legacy paused-item continuation does not automatically reopen historical failures. Parent-provided context says batch 8 has an earlier failed Toutiao item and a currently paused XHS item: continue/skip applies only to XHS while it is paused. The main session subsequently added a narrowly guarded, explicit terminal-failed-item `recover` operation to its **final-review proposal** (section 7); this is not implementation authorization. This research did not inspect batch 8's live rows.

### 2. Files found and code patterns

| File and anchor | Responsibility / established behavior |
| --- | --- |
| `backend/src/longtian_api/database.py:7` | Actual current schema version is 9; older search specs still describe their original v6/v7 additions. |
| `backend/src/longtian_api/database.py:33` | Per-operation SQLite connections, autocommit plus explicit writes, foreign keys, five-second busy timeout. |
| `backend/src/longtian_api/database.py:914` | Current run schema: immutable term snapshots, terminal outcomes, last started position; no completion cursor. |
| `backend/src/longtian_api/database.py:943` | `(run_id, position)` term identity; content-term provenance references it. |
| `backend/src/longtian_api/database.py:954` | Global unique `(platform, platform_content_id)` identity and mutable safe content metadata. |
| `backend/src/longtian_api/database.py:976` | Per-run content classification/provenance; no batch-level content copy is required. |
| `backend/src/longtian_api/database.py:1083` | v7 batch migration pattern, immutable attempt links, restricted child-run deletion, one-active-batch partial unique index. |
| `backend/src/longtian_api/repositories/search_batches.py:210` | One transaction creates a child run, **all** batch terms, next attempt number/link, item running state and current item position. |
| `backend/src/longtian_api/repositories/search_batches.py:300` | Only `manual_challenge_required` currently pauses; all other non-success outcomes become failed items. |
| `backend/src/longtian_api/repositories/search_batches.py:400` | Continue has no item/run precondition token and simply requeues the paused item. |
| `backend/src/longtian_api/repositories/search_batches.py:437` | Cancel marks batch and queued/paused items, leaving a running item for runner finalization. |
| `backend/src/longtian_api/repositories/search_batches.py:463` | Batch detail reads item metadata then opens separate run reads; not one coherent read snapshot. |
| `backend/src/longtian_api/repositories/search_batches.py:626` | Item assembly exposes only the latest run; attempt count is historical, content counts are not aggregated. |
| `backend/src/longtian_api/repositories/search_runs.py:183` | `set_progress` records current started position only and has no repository-level sequential/term-bound validation. |
| `backend/src/longtian_api/repositories/search_runs.py:196` | Each item is an independent short transaction, allowed only while run is running and term exists. |
| `backend/src/longtian_api/repositories/search_runs.py:224` | Global content upsert and new/repeated classification; same-run repeat preserves original classification. |
| `backend/src/longtian_api/repositories/search_runs.py:329` | Idempotent per-content/per-term match relationship. |
| `backend/src/longtian_api/repositories/search_runs.py:346` | Terminal run transition only from queued/running; no resetting terminal attempts. |
| `backend/src/longtian_api/repositories/search_runs.py:406` | Existing result ordering/filter/pagination and matched-term presentation can be reused for item aggregate results. |
| `backend/src/longtian_api/repositories/search_runs.py:523` | Counts derived from persisted relations, not mutable counters. |
| `backend/src/longtian_api/services/search_runs.py:329` | Reusable batch child execution under externally held browser ownership. |
| `backend/src/longtian_api/services/search_runs.py:393` | Run execution awaits threaded progress/item persistence, sends all `record.terms`, then terminalizes. |
| `backend/src/longtian_api/services/search_batches.py:134` | Startup currently reclaims ownership and starts work unless already paused. |
| `backend/src/longtian_api/services/search_batches.py:238` | Continue waits for settling runner outside service lock, then restarts it. |
| `backend/src/longtian_api/services/search_batches.py:320` | Serial runner; ordinary failures currently advance, pauses retain owner. |
| `backend/src/longtian_api/services/browser_operations.py:24` | Shared, in-memory, exact-owner claim/release; no cross-process browser mutex. |
| `backend/src/longtian_api/main.py:60` | Startup reconciles search runs before batch items; batch startup runs at line 84. |
| `backend/src/longtian_api/schemas/search_batches.py:20` | Item status lacks skipped; detail has latest attempt only. |
| `backend/src/longtian_api/api/v1/search_batches.py:81` | Continue is currently a bodyless POST; introducing guarded payloads is an intentional API/client change. |
| `backend/src/longtian_api/services/media_crawler_auth_worker.py:165` | Request-local UUID/platform/progress/item-count correlation. |
| `backend/src/longtian_api/services/media_crawler_auth_worker.py:596` | Reader parses one line then awaits its handler before reading the next. |
| `backend/src/longtian_api/services/media_crawler_auth_worker.py:674` | Started positions exactly sequential; items only current term; success currently requires last start, not explicit completion. |
| `backend/src/longtian_api/services/media_crawler_auth_worker.py:934` | Strict search v1 event parser, bounded frame/UTF-8/duplicate-key/exact-field validation. |
| `third_party/MediaCrawler/tools/search_worker_protocol.py:20` | Search protocol version/size constants; progress type carries no completed phase. |
| `third_party/MediaCrawler/tools/auth_worker.py:593` | Worker translates adapter progress/item callbacks into ordered search frames. |
| `third_party/MediaCrawler/tools/auth_worker.py:308` | Session races search against disconnect and drains search cleanup before reporting disconnect. |

### 3. What legacy progress really proves

The persisted `current_term_position=p` means the backend finished processing a valid `term_started(p)` frame. It is not a completed-term count.

The inference `all positions <p completed their bounded search` is supported by **both** inspected boundaries:

- Consumer: exact next start is enforced at `media_crawler_auth_worker.py:680`; progress callback is awaited at `:689`; item callback is awaited at `:702`; the reader awaits each handler at `:600`. Thus earlier valid item callbacks finish before the saved next start. Completion cannot be inferred from the mere maximum content match position.
- Producers: each outer loop moves to the next term only after all its bounded pages/normalization/item emissions succeed. Errors exit the entire search, not just the term:
  - Toutiao: `third_party/MediaCrawler/media_platform/toutiao/product_search.py:59`, `:72`, `:93`.
  - Weibo: `third_party/MediaCrawler/media_platform/weibo/product_search.py:320`, `:347`, `:357`.
  - Kuaishou: `third_party/MediaCrawler/media_platform/kuaishou/product_search.py:345`, `:378`, `:389`.
  - Douyin: `third_party/MediaCrawler/media_platform/douyin/product_search.py:448`, `:479`, `:484`, `:491`.
  - XHS: `third_party/MediaCrawler/media_platform/xhs/product_search.py:609`, `:652`, `:654`, `:661`. In particular its zero-emission/has-more rejection occurs **after** the page loop and before the next term.

| Legacy evidence | Safe completion proof | Retry point |
| --- | --- | --- |
| Successful terminal run (`completed_with_results` or `completed_empty`) with coherent full snapshot | All its terms; success requires final started position in the production reader (`:711`) | No retry for a completed platform |
| Failed/interrupted run with valid saved start `p` and verified v1 snapshot/producer contract | Strict prefix `[0,p)` including empty successful terms | `p`, or a later prefix already proved by another attempt |
| Failure before first saved start / `current_term_position=NULL` | No per-term completion proved | Earliest still-unconfirmed term, normally 0 |
| Content matches for current term / many rows / hard limit reached | Only that those observations were persisted | Current term still unconfirmed |
| `p=N-1` without successful terminal result | Only `[0,N-1)` | Last term must be retried |
| Last item emitted, or remote work apparently finished, but progress/terminal persistence lost | No additional durable completion proof | Earliest unconfirmed term |
| New v2 run missing a completion row | No legacy inference is allowed | Earliest missing v2 confirmation |

Legacy proof relies on product-owned records and the inspected producer semantics, not on a cryptographic audit trail: old rows do not store worker build/version or every frame. An out-of-range cursor, noncontiguous snapshot, inconsistent content provenance, or mismatched batch/run snapshot must not be silently turned into trusted completions. Report unavailable/legacy-unknown recovery and require explicit repair/skip scope if records are inconsistent. Do not quietly restart from zero and claim already-confirmed terms will never rerun.

For multiple old attempts, combine positive proof across all attempts, not only the latest. An earlier attempt may have advanced further than a later attempt that failed during startup. Valid sequential runs should produce a contiguous confirmed prefix. Treat holes as a violated invariant; suffix execution must never bridge a hole by rerunning confirmed later terms.

Batch 8 boundary (information supplied by parent, not independently read): preserve earlier Toutiao `failed`, all completed items, all attempt IDs and results. Continue only its currently paused XHS item from the earliest unconfirmed term. The final batch may truthfully remain `completed_with_failures` because of the old Toutiao failure. The explicit `recover` extension proposed by the main session may then reopen **one selected failed item** only after the batch has ended and no other active/paused batch exists; it must never redirect the currently paused XHS item to Toutiao or auto-requeue old failures.

### 4. Proposed minimal schema and repository contract (next migration: v10)

Keep the current tables/IDs. Add the following metadata; names below are a concrete proposal, not existing fields:

```text
search_runs:
  execution_start_term_position INTEGER NOT NULL DEFAULT 0 CHECK >=0
  search_protocol_version       INTEGER NOT NULL DEFAULT 1 CHECK IN (1,2)

search_run_term_completions:
  run_id                        INTEGER NOT NULL
  term_position                 INTEGER NOT NULL CHECK >=0
  proof                         TEXT NOT NULL CHECK IN (
                                  worker_term_completed,
                                  legacy_next_term_started,
                                  legacy_run_succeeded)
  result_count                  INTEGER NOT NULL CHECK >=0
  completed_at                  TEXT NULL
  recorded_at                   TEXT NOT NULL
  PRIMARY KEY (run_id, term_position)
  FOREIGN KEY (run_id, term_position)
    REFERENCES search_run_terms(run_id, position) ON DELETE RESTRICT

search_batches:
  control_revision              INTEGER NOT NULL DEFAULT 0 CHECK >=0

search_batch_items:
  status adds skipped
  pause_reason                  NULL | attempt_failed | process_interrupted
  completion_basis              NULL | attempt_success | confirmed_terms

search_batch_recovery_entries:   # narrow audit for explicit terminal-item recover
  batch_id, control_revision, item_position, search_run_id
  prior_batch_status, prior_batch_finished_at, prior_item_finished_at, created_at
  PRIMARY KEY (batch_id, control_revision)
  FOREIGN KEY (batch_id, item_position) REFERENCES search_batch_items(batch_id, position)
  FOREIGN KEY (search_run_id) REFERENCES search_runs(id)
```

- Existing runs get protocol version 1; **all new run writers**, including standalone, explicitly set 2. Do not leave a new v2 run indistinguishable from a legacy row by relying on its default.
- `execution_start_term_position` is frozen on creation; for new attempts it is the batch item's first unconfirmed original position. Keep all original terms copied exactly as today. No run is created with start `N`; that case uses the no-work resolution below. Standalone start is always zero.
- Positive completion rows are append-only. For v2, `completed_at` and `recorded_at` mean backend acknowledgement/commit time, not the exact instant the platform finished; `result_count` is the count of distinct persisted attempt/term matches. There is no mutable batch completion counter.
- For legacy evidence, `completed_at=NULL`, `recorded_at=backfill time`, and `proof` states why it is known. Compute result count from that attempt's term matches, including zero. Never assign a fabricated per-term completion time from a later next-term start or run finished time.
- Validate 0..N-1 term positions, original term existence, start offset, run still running, current term identity, prior required completions, and, for child runs, owning batch/item/attempt still active. Back this with foreign keys, closed CHECKs and transaction predicates, not frontend validation alone.
- Idempotency is exact: a repeated repository commit with the same completion evidence may return the existing row; conflicting evidence is an invariant error. Duplicate wire completion frames are still a protocol violation. Do not use `INSERT OR IGNORE` to hide incompatible evidence.
- Derive `completed_term_count`, `next_term_position` (`NULL` when all confirmed), and `remaining_term_count` from the union of completion positions joined through `search_batch_attempts`. Internally represent all complete as `next_position=N`; public `NULL` plus `remaining=0` avoids treating N as an actual term index.
- Terminal runs/attempt links are never reset or reused. New attempts record only their own observations and completions. Global content safe metadata remains mutable under existing behavior; “immutable attempt history” does not mean frozen historical copies of titles or global `last_seen_at`.
- The additional recovery-entry table is needed only for the main session's terminal-item reactivation proposal: it preserves the prior batch/item terminal timestamps before reopening clears them. Bind and validate the selected attempt in the same transaction; make entries append-only with strict positive IDs/revision, closed prior status and non-null prior terminal timestamps. It is not a generalized event-sourcing subsystem. Equivalent immutable transition storage is acceptable, but silently losing the old batch finish time is not history preservation.
- `finish_item(batch_id, position, expected_run_id, ...)` must read that run's durable terminal state and validate the exact latest attempt inside its transaction. A caller-supplied status alone is insufficient to fence late callbacks.

Migration shape:

1. Follow `database.py:93`: `BEGIN IMMEDIATE`, re-read version, require 9, explicit DDL, rollback on failure, set user_version only on success. Keep browser/network work outside the transaction.
2. Add run metadata and batch revision, create completion table, and explicitly backfill coherent **legacy** proof as above. Preserve all old run statuses, timestamps, terms, links and content rows.
3. SQLite's closed item-status CHECK requires rebuilding `search_batch_items` to admit `skipped`. Rebuild its dependent attempt table alongside it: create new item/attempt tables, copy columns explicitly, drop old attempts before old items, rename parent then child, recreate attempt index, and run `foreign_key_check`. Do not drop referenced runs or disable foreign keys casually. New run completion table depends on run terms, not the rebuilt batch tables.
4. No migration automatically continues/skips/cancels batch 8, retroactively requeues old failed items, or starts a worker. Startup reconciliation is separate from schema/backfill.
5. Preserve all pre-v10 data including deleted-ID allocation state. Run tables are ALTERed, not copied, so their `sqlite_sequence` remains intact. Capture row counts/IDs/relations and assert equality in tests.
6. Downgrade is not an in-place version-number edit. Old application code must reject v10 via the existing forward-version guard (`database.py:52`). Recovery from a failed rollout uses an explicitly prepared pre-upgrade backup and matching code; never silently discard new observations.

### 5. Proposed worker v2 and callback ordering

Keep search command structure and prefixes, but require search `version=2`. The worker receives only the immutable selected suffix in `terms`; its positions remain 0-based within that request. It does not need batch IDs or database offsets.

```json
{"version":2,"type":"command","command":"search","request_id":"<uuid4>","platform":"xhs","terms":["<remaining term>","<later term>"],"max_results_per_term":10}
{"version":2,"type":"event","event":"progress","request_id":"<uuid4>","platform":"xhs","phase":"term_started","term_position":0,"term_count":2}
{"version":2,"type":"event","event":"item","request_id":"<uuid4>","platform":"xhs","term_position":0,"item":{"...":"existing normalized model"}}
{"version":2,"type":"event","event":"term_completed","request_id":"<uuid4>","platform":"xhs","term_position":0,"item_count":1}
{"version":2,"type":"event","event":"result","request_id":"<uuid4>","platform":"xhs","outcome":"completed_with_results"}
```

The example shows frame shapes, not a valid complete two-term sequence; a real success must acknowledge both terms. An empty successful term sends `item_count=0` with no item frames. Item data shape, UUID/platform correlation, exact-field/duplicate-key/type/size/privacy checks remain unchanged. Apply the chosen search version consistently to search cancel and open-result frames, parser, serializer, constants and fixtures; auth frames stay v2. Mixed old/new worker versions fail closed with a constant protocol failure, no implicit v1 fallback.

State machine and mapping:

```text
local start(k)
  -> zero or more validated item(k), each DB write awaited
  -> term_completed(k), DB completion commit awaited
  -> start(k+1) or final success

original position = run.execution_start_term_position + local position
```

- Add `on_term_completed(local_position, item_count)` to worker client and emitter boundary. The run service is the single owner of offset mapping for start/item/completion callbacks; preserve original positions in run progress, match relations and completion rows.
- Emit completion after the adapter finishes all required bounded page work, normalization and item emission, including post-loop checks such as XHS `:654`. Never emit from a `finally` block or on partial-page failure/cancel. Completion means the existing bounded search contract succeeded, not exhaustive collection of the whole platform.
- The consumer rejects start before prior completion, item before start/after completion, duplicate/out-of-order completion, incorrect count, missing completion before success, non-integer fields, wrong UUID/platform/version, over-limit items and success/empty mismatch. Track seen content IDs per term so completion count can match distinct persisted matches; cross-term re-emission remains valid.
- Advance in-memory acknowledged cursor only **after** the completion callback succeeds. Persisting a checkpoint cannot be fire-and-forget, and terminal success cannot overtake outstanding writes.
- A completion callback/storage failure immediately fails that request and drains/recycles its worker as needed; it must not advance the batch to another platform. Previously committed content/checkpoints survive; the uncommitted term remains retryable.
- IPC is still one-way events, not a new per-term request/ACK protocol. Awaiting adapter emission means ordered frame writes, not proof that SQLite has committed. A backend crash between emission and commit may therefore reattempt that **unconfirmed** term; this is explicitly within R3. Avoid claiming exactly-once platform requests. If the product later requires the producer to wait for DB acknowledgement before requesting any next term, that is an additional handshake protocol, not provided by callback ordering alone.
- Cancelled `asyncio.to_thread` awaits do not prove the underlying write stopped. Retain/drain in-flight write tasks and use SQL run/attempt fences before allowing terminalization/ownership transfer. A late write must either commit before the terminal barrier or reject without changing a terminal run.

### 6. Results, deduplication and public counts

Reuse existing global/run relationship tables and add a repository-owned batch-item aggregate query, not another write-time content store:

```text
scope = all search_run_contents joined through attempts for one (batch_id,item_position)
group key = search_content_id
total_count = number of grouped contents
kind = earliest attempt relationship's discovery_kind
first_observed_at = min(all scoped observations)
last_observed_at = max(all scoped observations)
matched_terms = distinct original positions across all scoped match relationships, ascending
```

Earliest means `attempt_number`, not a client clock-derived timestamp. A content first discovered during failed attempt 1 remains platform-item `new` even when attempt 2 labels it `repeated`. Content already known before the batch stays `repeated`. Attempt views retain their own true classification. A failed term that once observed A/B and later observes B/C produces three aggregate rows A/B/C, not four, even if the retry's result cap is smaller than the retained union. The cap bounds each request/attempt, not the all-attempt union.

- `new_count + repeated_count = total_count`; filters, pagination total and displayed list use the **same** grouped CTE/query owner. Do not count raw joins after matched-term expansion.
- Preserve existing ordering: new before repeated, aggregate first-observed descending, stable content ID ascending. Bounded pagination remains normal; live offset pagination can move as results arrive, as today, so invalidate on change.
- Include results from failed, skipped and cancelled items/attempts; those statuses never erase provenance. A new successful suffix may be `completed_empty` while the platform aggregate still has results from older attempts: both are truthful with correct labels.
- Return the earliest associated run ID as `source_run_id` if reusing the existing XHS run/result-open endpoint, or add an item-scoped open endpoint that proves aggregate membership and derives the first original matched term. Do not call latest-run open for a result that only exists in an older run. Browser ownership restrictions still apply while a batch is paused.
- Read aggregate detail/counts/latest attempt/completions from one explicit SQLite read transaction/connection, not separated autocommit reads. Current `search_batches.py:463` can mix old item state with a newly finished latest run; stricter new API consistency checks should not see that torn projection. Keep the read transaction free of browser work.

### 7. API and serial state-machine proposal

Existing GETs remain side-effect-free. Extend detail with `control_revision`; extend each item with `completed_term_count`, `remaining_term_count`, `next_term_position`, `checkpoint_basis` (`explicit|legacy_inferred|mixed|unknown`), aggregate `new_count/repeated_count/total_count`, `pause_reason`, and `completion_basis`. Preserve `latest_attempt` as failure/history detail rather than replacing it with a synthetic aggregate run. Expose execution start on attempt/run summaries so a suffix attempt is never presented as having executed every snapshot term.

```http
POST /api/v1/search-batches/{batch_id}/continue
  {"item_position": 4, "expected_run_id": 123, "expected_revision": 7}

POST /api/v1/search-batches/{batch_id}/items/{position}/skip
  {"expected_run_id": 123, "expected_revision": 7}

POST /api/v1/search-batches/{batch_id}/items/{position}/recover
  {"expected_run_id": 123, "expected_revision": 7}

GET /api/v1/search-batches/{batch_id}/items/{position}/results?kind=all|new|repeated&limit=50&offset=0

POST /api/v1/search-batches/{batch_id}/cancel
  existing no-body whole-batch cancellation contract
```

All body keys are required and strict, extras forbidden. `expected_run_id` is explicitly nullable only for a process-interrupted queued item with no attempt. IDs use existing signed-int64 bounds; positions 0..4. Continue/skip return 202 with the durable current detail; reads return 200. Preserve 404/409/422/503 envelopes; add `search_batch_state_changed` (409, refresh required) for stale expectation and a distinct not-recoverable error for inconsistent checkpoints. Missing/invalid payload remains 422, not legacy bodyless fallback.

`recover` is the main session's later **final-review scope extension**, distinct from continue. Accept only a `completed_with_failures` batch and exactly one selected `failed` item with the expected latest terminal run, valid checkpoints and matching revision; require no active/paused batch or competing browser owner. In one repository transaction record the prior terminal timestamps, set only the selected item and its batch to paused, set current item position and `pause_reason=attempt_failed`, clear active lifecycle finished timestamps, and increment revision. Return 202 paused; **no run creation, worker launch, search, rule reload, or automatic scheduling**. Subsequent explicit continue/open/skip uses the normal paused-item flow and frozen snapshots even if the original monitoring rule was edited/deleted. Do not reopen successful/cancelled/internal_error batches, skipped/completed items, or switch away from an existing paused item. All other platform states and all attempt rows remain unchanged. Claim the coordinator before committing the paused transition; on a DB/index/expectation conflict release that exact claim. The partial unique index is the durable race backstop. The old failed run ID remains the latest until continue creates another attempt, so `control_revision` cannot be replaced by expected run ID alone.

Inside one `BEGIN IMMEDIATE`, compare batch paused state, `current_item_position`, item paused state, latest attempt ID (including null), and control revision. No matches means no state change, new attempt, or browser work. Increment revision on accepted control actions/reconciliation and other transitions that replace the recovery decision. The revision closes the small gap where continue requeues but a restart pauses again **before** a new attempt ID exists. Item position plus latest run guards also prevent a delayed skip from targeting another platform after a quick retry/failure.

| Event | Item/batch behavior | Run/history behavior |
| --- | --- | --- |
| Worker success and all requested terms committed | Complete item; advance exactly once to next queued platform | Preserve successful terminal attempt |
| Login/challenge/block/structure/browser/timeout/internal failure | Pause current item and whole batch; later platforms remain queued | Store actual terminal category; preserve partial observations |
| Explicit continue, remaining terms >0 | Requeue same item, then atomically create a new suffix attempt | New monotonically numbered run; previous attempt untouched |
| Explicit continue, remaining terms =0 | Complete item with `completion_basis=confirmed_terms`, then advance/finalize | **No new attempt, no worker call, no empty search, no rewriting failed terminal run** |
| Explicit skip while paused | Mark item skipped with finished timestamp; advance/finalize | Preserve all attempts/results; never synthesize success or cancelled run |
| Explicit recover of one failed item in a completed_with_failures batch | Reopen only that item into paused state; claim owner; no work until another explicit action | Preserve old terminal run, old timestamps in recovery entry, and every other item's state |
| Explicit whole-batch cancel | Cancel current and remaining nonterminal items; never start next platform | Atomically fence any queued/running child, then drain worker; prior terminal runs untouched |
| Service interruption/restart | Reconcile stale work, remain paused with process-interrupted reason; no worker launch on startup/GET | Stale active runs become internal_error; confirmed terms/partial data survive |

All-complete failure example: the final `term_completed(N-1)` commits, then Chrome disconnects during cleanup. Run status remains `browser_unavailable`; item pauses with zero remaining terms. Guarded continue records `completion_basis=confirmed_terms` and item finished time without increasing attempt count. This is not a successful attempt and must not be decoded as “completed item always has a successful latest run.” If that was the final item, batch completes; otherwise only the next platform may perform browser work.

No-work completion is allowed only on explicit continue, not a GET or silent startup inference from a failed run. A crash after the run successfully finalized but before `finish_item` is different: startup may project that durable success onto the item, then pause before starting the next queued item; it need not manufacture a failed attempt. If there is no remaining item, ordinary pure-DB finalization is safe.

`completed_with_failures` remains the least disruptive aggregate terminal status if any item is skipped or retains a legacy failure. Public item status and counts must make skipped distinct from success/failure, even if the existing top-level label remains broad. `terminal_item_count` includes skipped. Completed platform items are never requeued by ordinary continue.

### 8. Cancellation, startup and ownership race requirements

- **Paused ownership:** retain the batch's coordinator claim across manual waiting. Starting an independent account-check/open/search currently conflicts; any in-batch manual helper must execute under the same batch owner and control lock. Releasing ownership for manual waiting would allow another operation to compete with the user's Chrome work.
- **Continue/skip vs runner cleanup:** await settling task outside the service lock, then reacquire and revalidate the durable tuple. Do not deadlock by waiting on a runner that needs the same lock in its `finally` (`services/search_batches.py:375`). Do not expose a manual operation as ready until search cancellation/page cleanup is drained.
- **Cancel during create_attempt:** current create is in `to_thread` (`:337`); cancelling the coroutine can leave the thread committing after the runner exits. Serialize dispatch with cancellation and retain/drain that write. The cancel transaction must also mark a just-created queued/running child and running item, not only queued/paused items as currently at repository `:451`.
- **Cancel vs items/checkpoints/final success:** use durable active-run/current-attempt predicates. Already-committed observations survive; post-terminal callbacks reject. A late `finish_item` must not turn a cancelled/skipped item into completed/paused, and a late old-attempt callback must not change a newer attempt.
- **Double continue / cross-tab skip:** exact paused tuple plus revision is checked inside transaction; one accepted action consumes that revision. A fast re-failure creates a new recovery state, never authorizes a stale request. Status-only checks and a UI-disabled button are insufficient.
- **Restart:** current reconciliation unconditionally marks running items failed (`repositories/search_batches.py:101`) and startup resumes remaining platforms (`services/search_batches.py:150`). Both intentionally change for R4/R5. Every durable active batch must become/recover as paused before scheduling, including pre-first-attempt and between-platform gaps; a queued interruption can have `expected_run_id=null`. Paused/terminal batches never auto-run. Retain existing legacy terminal failures without reactivation.
- **Shutdown:** service shutdown cancellation is not user cancellation of the whole batch. Persist an interruption reason/pause, retain checkpoints, drain the owned worker and release only the in-memory owner on shutdown. Startup can reclaim the durable paused batch without launching the worker. Existing child terminal cancellation recorded during graceful shutdown may remain historical; do not relabel old terminal runs.
- **Storage failure:** do not use current broad `fail_batch` (`repositories/search_batches.py:378`) to mark all queued items failed. Stop scheduling immediately, keep unexecuted items queued and ownership fenced, preserve the actual error, return sanitized 503 when state cannot be saved. If pause persistence itself fails, startup must conservatively pause the leftover active state; never claim a durable pause/complete that was not committed.
- **One process boundary:** existing browser coordinator is in memory. This plan preserves the current single-backend-process architecture; a second simultaneously running backend is not made safe by the active-batch index alone. Multi-process worker/browser leases would be additional scope.

### 9. Tests to add or intentionally change (offline, temp database)

Existing evidence/test anchors:

- `backend/tests/test_search_batches.py:115`, `:158`, `:199`: migration/index/upgrade/idempotence/DDL rollback patterns.
- `backend/tests/test_search_batches.py:230`: attempt transaction rollback, including child terms.
- `backend/tests/test_search_batches.py:402`: immutable repeated manual-challenge attempts.
- `backend/tests/test_search_batches.py:450`, `:492`: cancellation and release-before-runner-start.
- `backend/tests/test_search_batches.py:530`: **old expectation** that restart continues another platform; replace with paused/no-work-until-explicit-action expectations.
- `backend/tests/test_search_batches.py:34`: fake worker currently emits only start(0) even for multi-term successful runs; update it to model all v2 start/item/completion frames, not silently bypass new invariants.
- `backend/tests/test_search_runs.py:109`, `:190`, `:1052`: cross-term/cross-run dedup, transaction rollback, partial-result survival across outcomes.
- `backend/tests/test_search_worker_client.py:389`, `:682`, `:873`: progress/item decoding, correlated cancellation, invalid-sequence recycling.
- Adapter fixtures: `third_party/MediaCrawler/tests/test_product_search.py`, `test_weibo_product_search.py`, `test_kuaishou_product_search.py`, `test_douyin_product_search.py`, `test_xhs_product_search.py`; worker fixtures in `tests/test_auth_worker.py`.

Required new matrix:

1. Migration from exact v9 with all five platform histories, paused legacy batch and earlier failed item: preserve IDs/status/times/results/terms/relations, backfill only valid proof, zero-result prefix, last-term unconfirmed, repeated init, fresh init, FK/index checks, failing-DDL rollback, future-version rejection.
2. Term 7 failure after six complete terms (mix zero/nonzero): continue sends only original positions 6..N-1; saved progress/matches remain original positions; prior platform calls never repeat. Failure again at later term starts from the advanced prefix, while startup failure before any term does not discard older completions.
3. Each platform's empty, capped, exhausted and successful page-loop paths emits exactly one completion; partial page/normalization/signing/login/challenge/timeout/disconnect/cancel failure emits none for the failed term. XHS zero+has_more rejection stays unconfirmed.
4. Delay item callback commit, then completion callback commit: later frames/final success cannot overtake either. Inject callback failure, cancellation while a SQLite thread is blocked, missing/duplicate/wrong-position/wrong-count completion, start before completion, item after completion, mixed versions, wrong UUID/platform and oversized/secret-bearing payloads.
5. Partial failure A/B then retry B/C: global rows and item union equal three, attempt1 keeps new A/B, retry keeps its actual repeated/new classification, item aggregate new/repeated is stable; old-only rows remain openable through a proven source run; matched terms union correctly and no counts are multiplied by joins.
6. Last completion committed then final result lost: paused with remaining=0; continue increases neither run count nor attempt count, makes no current-platform worker call, records confirmed_terms basis, retains failed latest run. Test cancel and skip here too. Conversely lost last completion requires retry of the final term.
7. Ordinary failures all pause exactly like challenge without relabeling their actual cause. No later-platform call until continue/skip; skipped status is not success and results remain readable; legacy terminal failed items do not requeue.
8. Concurrent/replayed continue and skip, stale request after quick refailure, stale request after moving platforms, continue-crash-before-attempt gap with same expected run but changed revision, cancel during attempt creation/progress/completion/finalization, and shutdown with a slow callback. Assert one owner, at most one new attempt, no orphan active run, terminal histories unchanged, no next-platform leak.
9. Restart checkpoints at each boundary (before first attempt, during term, after completion, after child success before item finish, between platforms, paused, cancelled/skipped/terminal) with zero worker calls on startup and GET. Reclaim paused browser owner without CDP launch.
10. API/OpenAPI strict payloads, nullable expected run only for no-attempt paused interruption, sanitized 404/409/422/503, item not-found vs unknown position, aggregate filters/counts and coherent single-snapshot projections. Frontend decoders must accept all failure pause causes and completed-by-checkpoint with failed latest run.
11. Explicit terminal-item recover: batch 8-shaped fixture (old Toutiao failure, other completed platforms), no new run/browser call on recover, only selected item reopens paused, prior timestamps preserved, frozen terms survive rule edits/deletion, stale revision/run rejected, active/paused/foreign-browser-owner conflicts reject without state mutation, duplicate recover creates one audit entry, cancelled/successful/internal_error batch and nonfailed item reject. Recovered item with all terms already confirmed uses the no-work continue path; other completed platforms never rerun.

These tests were identified by source inspection; none were executed in this planning research. Future implementation should use temp on-disk databases/fake worker fixtures first, and follow project Centaurus validation rules for execution-heavy checks.

### 10. Related specs and external/version references

- `.trellis/spec/backend/database-guidelines.md`: repository SQL ownership, explicit immediate transactions, deterministic queries, migration rollback, temp-file tests.
- `.trellis/spec/backend/product-search-guidelines.md`: terminal run immutability, global/run dedup, exact search protocol, bounded adapters, borrowed-browser and privacy contracts.
- `.trellis/spec/backend/batch-search-guidelines.md`: immutable attempts, serial/coordinator ownership, strict UI/API projections. Its ordinary-failure continuation, whole-platform retry and auto-advance-on-restart clauses are the approved behavior changes, not preexisting implementation bugs.
- `.trellis/spec/backend/platform-connection-guidelines.md`: auth protocol isolation and lazy borrowed-browser lifecycle.
- `.trellis/spec/backend/error-handling.md`: strict public input and constant-only errors.
- `.trellis/spec/guides/cross-layer-thinking-guide.md`, `code-reuse-thinking-guide.md`: one event decoder/mapping/projection owner rather than per-consumer casts or duplicated aggregate logic.
- `.trellis/tasks/08-27-collection-manual-recovery/prd.md`: R1/R3/R4/R5/R7 and AC3–AC6/AC8 drive this contract. No design/implementation artifacts existed when research began.
- Versions from local source only: Python >=3.11 in `backend/pyproject.toml:7`; FastAPI 0.141.1 in `backend/uv.lock:104`; Pydantic 2.13.4 in `backend/uv.lock:597`; pytest 9.1.1 in `backend/uv.lock:755`; current search IPC v1 at `third_party/MediaCrawler/tools/search_worker_protocol.py:20`; SQLite schema v9 at `database.py:7`. No dependency upgrade is proposed.
- External documentation was not fetched: the dispatch explicitly forbids network work. Conclusions are code/spec-backed proposals, not claims about newly checked external API behavior. `trellis-before-dev` guided context/spec loading and FastAPI guidance supports strict typed request/response boundaries; neither authorizes implementation or server startup here.

## Caveats / Not Found

- No live SQLite/keys/raw runtime/browser state was opened; no concrete batch 8 cursor, counts, exact term list, or worker build provenance was verified. The old Toutiao/XHS status context comes from the main session and must not be presented as a fresh runtime audit.
- New checkpoints cannot retroactively recover the exact instant/extent of an unconfirmed final term. Retry is at-least-once for unconfirmed terms; committed results are idempotently retained.
- Earlier legacy failed items and terminal batches are not recoverable through current continue APIs. The main session explicitly added the narrow `recover` operation above to final design review after this research began; it remains proposed, not already implemented or independently approved for execution. Automatic reactivation and switching away from an existing pause remain excluded.
- This research owns only this file. Product code, PRD/design, shared specs, services, DB/runtime and Git were not modified. Proposed API/model/schema/protocol changes still require main-session review and implementation approval.
