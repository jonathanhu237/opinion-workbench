# Independent Fixed-Interval Collection

## 1. Scope / Trigger

Use this contract when changing rule-referenced collection schedules, occurrence
history, scheduled batch admission, timer lifecycle or the schedule section of
`/collection-runs`. Monitoring rules contain search configuration only. Schedules
contain no prompts, provider credentials or report-generation conditions.

Owners: `collection_timing.py`, `migrations/collection_schedules.py`, the matching
schema/repository/service/API modules, scheduled admission in `search_batches`,
and the existing worker's no-I/O browser-session evidence. Frontend owners are
`lib/api/collection-schedules.ts`, `hooks/use-collection-schedules.ts` and
`routes/collection-schedule*.tsx`.

Reuse [Batch Search](./batch-search-guidelines.md) for execution/manual recovery
and [Independent Initial Analysis](./initial-analysis-guidelines.md) for the
post-release new-result handoff. The timer is not another collector or AI owner.

## 2. Signatures

All routes have the `/api/v1` prefix:

- `GET /collection-schedules?limit=50&before_id=N` returns
  `{schedules,next_before_id}` in descending ID order; limit 1-100.
- `POST /collection-schedules` accepts `{monitoring_rule_id,platforms,
  max_results_per_term,interval:{value,unit}}` and returns 201 with a disabled
  schedule. Result cap defaults to 10, otherwise 1-50. Units are minutes/hours.
- `GET /collection-schedules/{id}` returns the current configuration projection.
- `PUT /collection-schedules/{id}` accepts the full create payload plus
  `{expected_revision,enabled}`; all fields are required. A null rule ID is only
  valid when retaining/disabling an already deleted rule reference.
- `GET /collection-schedules/{id}/occurrences?limit=50&before_id=N` returns
  `{occurrences,next_before_id}`. A missing schedule is 404; empty history is 200.
- `CollectionScheduleService.start/tick/shutdown` own timer admission.
  Clock and monotonic time are injected; deterministic tests call `tick`.
- `SearchBatchService.start_scheduled_batch(claim, timestamp,
  admission_allowed)` uses a private dispatch token to link an existing batch
  atomically before launching its runner. It is not a separate public endpoint.

Migration v13 appends `collection_schedules`, ordered
`collection_schedule_platforms` and `collection_occurrences`. Keep all prior
run/content/analysis rows and additive migrations intact.

## 3. Contracts

### Configuration and timing

- Accept positive whole minutes/hours normalized to 1-43,200 minutes (30 days).
  Do not add cron/calendar semantics. Platforms are unique and follow the
  existing `toutiao,wb,ks,dy,xhs` catalog order.
- New schedules are disabled. Every accepted PUT increments revision, including
  a same-value save. Enabled saves set anchor to now and due to now+interval;
  disabled saves clear both. Timer ticks never increment configuration revision.
- Stale revisions change nothing. Enabling requires an existing enabled rule
  with valid effective terms within the existing 20-term limit. Disabled
  configurations can retain a disabled/deleted rule; the UI exposes that state.
- Read current rule state for configuration display, but freeze actual rule
  terms/name/platform settings on each admitted batch. Rule edits affect future
  work, not historical batches, result provenance or reports.
- Persist UTC due times and calculate the first future anchor-aligned time.
  Use monotonic waits, not wall-clock sleeps or execution duration accumulation.
- Startup reconciles unfinished dispatch claims, records one bounded missed
  range per overdue schedule, advances due time and makes no collection call.
  Forward clock jumps use the same bounded missed-range policy; drain every
  storage page under that classification, not just the first 100 schedules.
  Backward jumps cannot repeat an already claimed unique key.

### Durable dispatch and browser ownership

- Claim and advance due time in one short transaction. The key is unique on
  `(schedule_id,schedule_revision,due_at)`; dispatch UUIDs are private and unique.
- Insert existing batch/terms/platform items and its occurrence link in one
  transaction. Recheck schedule revision/enabled state and current rule before
  committing. Browser work starts only after the durable link exists.
- Replaying a dispatch token returns its existing batch, never launches another
  runner. A persisted launch marker distinguishes linked-but-unlaunched history;
  restart never automatically replays either kind of interrupted execution.
- Validate persisted platform membership/order through the same canonical
  boundary used by output projection. Empty/reversed child rows must fail closed
  before claim/link or worker launch; internal timer admission cannot rely on
  validation that only public POST requests receive.
- The existing batch coordinator is the only browser owner. Busy collection,
  initial analysis or a paused manual-verification batch causes an explicit
  skipped occurrence, without cancelling, stealing or resuming that owner.
- Scheduled admission requires the existing worker's conservative no-I/O
  browser-session evidence. A fresh backend needs an explicit manual connection
  check/search first; worker process readiness alone is insufficient. This is
  evidence of a usable browser, not proof that every platform is authenticated.
  Browser/process failure clears availability; a later authentication challenge
  still follows the normal explicit manual-recovery path.
- Disabling affects future admissions only. Already linked work keeps its own
  batch cancellation/pause/continue controls and saved source provenance.
- Shutdown stops timer admissions first and drains in-flight dispatch before
  downstream owners and the browser close. Check shutdown between missed pages
  and after asynchronous rule reads. Run remaining cleanup even if one fails.
- The timer never calls initial analysis, reports or a model. Normal batch
  completion uses the existing single post-browser-release A handoff. Child runs
  and paused/cancelled collections do not create duplicate automatic jobs.

### History and UI

- Occurrence states are `claimed`, `dispatched`, `skipped`, `missed`,
  `interrupted`. Dispatched means batch admission, not successful collection;
  expose the linked batch status and its existing detail route.
- Missed rows contain inclusive first/last due times and a positive bounded
  count. Other statuses have zero missed count and null missed-until.
- Batch ID/status/dispatched time are all present or all absent. Interrupted
  prelaunch dispatch can retain its link and explicit paused recovery.
- Keep rollout `available` separate from persisted `enabled`, current rule
  state and browser readiness. Saving a schedule does not grant AI authorization.
- Query owns server state; URL owns `schedule`, `schedulesBefore` and
  `occurrencesBefore`; form state owns drafts. Page limits never limit execution
  history. GET, route entry and polling do not create or enable schedules.
- Fence late reads around saves and preserve newer revisions in list/detail
  caches. Conflicts retain the draft and require explicit recovery. Pending
  operations disable duplicate submission; enable/disable labels explain scope.
- A referenced rule can be deleted/disabled without changing the schedule's
  revision. Compare that dependency projection as well as revision when deciding
  whether a draft/confirmation is stale; require explicit adoption followed by
  a separate save/confirm. New occurrence progress alone must not invalidate a
  draft. Older reads cannot silently rebase the saved intent.

## 4. Validation & Error Matrix

Every response/error has `Cache-Control: no-store`. Mutations reuse existing
local Host/Origin/JSON guards. Strict request schemas reject extra prompt/model
fields, coercions, duplicate/unknown platforms, unsafe IDs and invalid intervals.
Stored output projections and frontend decoders independently validate UTC
timestamps, revisions, platform order and status/reason/link/count consistency.
Malformed persisted projections return a constant 503 storage error, not a 200
that only the frontend rejects. Frontend error status/code pairs remain exact.

| Situation | Public outcome |
| --- | --- |
| Unknown schedule | 404 `collection_schedule_not_found` |
| Stale schedule or rule changed during save | 409 `collection_schedule_changed` |
| Normalized interval exceeds range | 422 `invalid_collection_interval` |
| Invalid configuration | 422 `invalid_collection_schedule` |
| Missing/disabled/too-large rule | Existing `monitoring_rule_not_found` / `monitoring_rule_disabled` / `too_many_search_terms` |
| Storage failure | 503 `collection_schedule_storage_unavailable`, constant safe message |
| Closed service | 503 `collection_schedule_unavailable` |
| Invalid JSON shape/ID/query | 422 `invalid_request` |
| Forbidden origin/non-JSON mutation | Existing `ai_request_forbidden` / `ai_json_required`; no schedule write |

Occurrence reasons are bounded application codes: browser busy/unavailable,
missing/disabled/invalid/too-large rule, schedule changed, storage unavailable,
dispatch interrupted, offline and clock jump. Never persist raw browser errors.

## 5. Good / Base / Bad Cases

- Base: save a disabled one-hour plan; enabling sets a future due time; one
  exact due produces one linked batch using the current valid rule snapshot.
- Good: concurrent polls/token replay still produce one batch; a later rule
  edit leaves its snapshot intact; manual pause survives the next skipped round.
- Bad: unavailable browser produces a successful empty run, disabling cancels
  active work, restart catches up missed rounds, or a second page escapes the
  forward-jump missed-range classification. These are regressions, not fallback.

## 6. Tests Required

Use disposable SQLite, fake UTC/monotonic clocks and fake workers. Cover genuine
v12 migration/preservation/reopen, actual DDL and multi-row rollback, forward
schema rejection, exact normalized interval limits, stale CAS, deletion/history,
same-due concurrent claims and atomic token/batch linkage. Exercise exact due,
duplicate polls, busy owners, manual pause, unavailable browser, current rule
changes, backward/forward jumps, >100 schedules in a jump, long offline gaps,
crash before/after link and launch marker, disable of linked work and shutdown
during admission. Assert one A handoff after release, no direct scheduler AI call.
Corrupt timestamp/platform projections must fail reads without work; malformed
platform membership before claim or between claim/link must never launch a batch.

Frontend tests cover strict decoders, forms, unit conversion, enable/disable,
revision/read races, URL pagination, linked history, no mutation from reads and
unchanged manual collection. Include same-revision rule deletion/disable recovery
and occurrence-only draft preservation. Main-owned browser acceptance uses the isolated
fake app, keyboard/narrow layout and console inspection. Mocks do not prove
live browser/account availability or platform collection quality.

## 7. Wrong vs Correct

```text
Wrong: due -> launch browser -> save batch/occurrence -> auto-retry on restart
Correct: claim+advance -> validate+lease -> atomically link existing batch
         -> launch once -> normal batch state/provenance -> post-release handoff

Wrong: disable schedule -> cancel active batch; clock jump -> replay backlog
Correct: disable future admission only; clock jump -> bounded missed history
         across every storage page -> next future anchor-aligned due
```
