# Shared Results and Independent Initial Analysis

## 1. Scope / Trigger

Use this contract for the global result library, two business prompt defaults,
initial-understanding admission/execution, and the `/results` frontend. These
resources are independent of legacy per-run summaries and of report generation.
Monitoring rules remain collection configuration; neither rules nor collection
records own prompt defaults or report success.

Owners: `migrations/initial_analysis.py`, `repositories/{analysis_settings,
analysis_shared,content_analyses,results}.py`, corresponding schemas/services/API
modules, `services/content_understanding.py`, and the collection terminal hooks.
Frontend owners are `lib/api/{analysis-shared,analysis-settings,content-analyses,
results}.ts` and `routes/results*.tsx`.

The shared transport, media, privacy and usage requirements in
[Manual AI Summaries](./ai-summary-guidelines.md) still apply. Its 100-source cap,
topic-specific first-stage object and manual combined trigger do not apply here.

## 2. Signatures

All HTTP paths have `/api/v1` prefix:

- `GET /analysis-settings` returns separate immutable `initial_prompt` and
  `report_prompt` versions and revision-bound `automation` authorization.
- `PUT /analysis-settings/prompts/{initial|report}` accepts exactly
  `{expected_version_id, instructions}` and returns settings.
- `PUT /analysis-settings/automation` accepts exactly
  `{expected_revision, enabled, configuration_revision}`.
- `GET /results` accepts `limit` (1–100), `offset`, optional `platform`, `state`,
  `first_seen_from`, `first_seen_to`; response is
  `{items,total,limit,offset,eligible_count,active_count}`.
- `GET /results/{id}` and paginated `/{id}/origins`, `/{id}/analyses`,
  `/{id}/legacy-analyses` expose saved provenance and separate histories.
- `POST /content-analysis-jobs` accepts exactly `{request_id,
  configuration_revision,initial_prompt_version_id,report_prompt_version_id,
  force_refresh,selection}`; returns 202
  `{job: AnalysisJob|null,admitted_count,already_active_count}`.
- Selection is `{kind:"all_never_started"}` or
  `{kind:"explicit"|"retry"|"reanalysis",result_ids:[...]}`. Explicit lists contain
  1–1000 unique positive IDs; all-never-started has no page/source cap or ID array.
- `GET /content-analysis-jobs?limit=20&before_id=N`, `/{id}`, `/{id}/items` and
  `GET /content-analyses/{id}` read frozen state. `POST /content-analysis-jobs/{id}/cancel`
  accepts exactly `{}` and returns settled state.
- `ContentAnalysisRepository.completion_events(after_id=0, limit=100)` reads
  immutable normal-settlement events with the job and successful attempt IDs.

Migration v12 appends `analysis_prompt_versions`, `analysis_settings`,
`content_analysis_jobs`, `content_analysis_attempts`, `content_analysis_claims`,
`content_analysis_requests`, `analysis_completion_events` and
`collection_analysis_handoffs`. Do not relabel a modern schema as an old fixture.

## 3. Contracts

### Discovery, membership and versions

- Keep one global `(platform,platform_content_id)` result in the existing content
  store. Register its discovery/claim in the same transaction as content and
  origin membership. Repeat observation preserves first-entry time and eligibility.
- `eligible_count`/`active_count` describe the whole library, not current filters.
  Interval filters use UTC `[from,to)` first-entry time. UI date ranges convert
  inclusive Asia/Shanghai dates to that interval; publication text stays separate.
- Atomically freeze all never-started unclaimed results in deterministic ID order.
  Include unattempted history for explicit bulk; exclude failed, interrupted,
  completed, legacy-attempted and legacy-completed records. Retry and reanalysis
  are separate explicit intents. Later arrivals cannot extend an admitted job.
- A shared per-content claim excludes simultaneous new-stage or legacy owners.
  Legacy successes remain `legacy_completed`, not valid new understanding;
  legacy failed/incomplete attempts remain `legacy_attempted`. Keep old JSON,
  IDs, citations and usage readable. Do not migrate topic judgments into neutral
  understanding or reinterpret missing evidence as success.
- Canonical lowercase UUIDv4 replay binds the exact admission payload, including
  zero-result no-ops. A lost response must not cause a new UUID automatically.
- Freeze both prompt versions and the provider revision/endpoint/model. Prompts
  preserve exact accepted nonblank UTF-8 text, 1–8000 Unicode code points, no NUL.
  No-op saves preserve IDs; stale saves conflict. Changed defaults affect future
  admissions only. Rule edits do not mutate frozen source or prompt history.

### Lifecycle and evidence

- Job states: `queued`, `running`, `completed`, `cancelled`, `interrupted`,
  `configuration_blocked`. Completed means every member settled, not all succeeded.
- Attempt states: `queued`, `acquiring`, `analysing`, `completed`,
  `input_incomplete`, `unsupported`, `failed`, `cancelled`, `interrupted`.
  Counts reconcile to frozen membership; reused is a subset of completed.
- Use existing exclusive AI/browser owners. Busy resources leave work queued,
  without marking a model request attempted. Release browser ownership between
  records and before report work. SQLite operations use settled thread calls;
  no acquisition/network work belongs inside a transaction.
- Coordinate admission with the runner's empty-queue exit. A persisted new job
  must not remain stranded behind a runner that already decided to stop.
- Save accepted full text and bounded media metadata using `SavedInput`; never
  persist temporary media bytes, locators, credentials or raw provider responses.
  Revalidate actual media through the existing acquisition/model boundary.
- Understanding has only `summary` (1–1500 code points), `location_clues` (0–12
  excerpt/modality pairs, excerpt 1–200), `time_context` (1–500),
  `media_observations` (0–12 strings, each 1–400), `uncertainties` (1–500).
  Combined prose is at most 6000. There is no relevance verdict in stage one.
  Preserve source attribution, unknown geography/time, and unverified claims.
- Reuse only canonical compatible completed evidence, respecting the latest known
  acquired fingerprint. A newer failed analysis cannot revive older stale input.
  Reused history adds no new attempted requests or historical token usage.
- Normal job settlement writes exactly one completion event transactionally.
  Failed members do not block that event once all members settle. Cancellation,
  interruption and configuration-blocked settlement preserve prior successes but
  suppress their job's automatic report event and release all active claims.
- Startup reconciles unfinished work to interrupted without model calls. Explicit
  retries create new versions; GET, prompt save and cache misses do not retry work.
- New-content automation requires explicit saved authorization tied to provider
  revision. Collection completion hands off only after browser release; batch
  children do not individually trigger jobs. Cancelled/paused collections do not
  trigger follow-up. Only proved new, unattempted backlog is auto-eligible.
  Rollout availability and saved authorization are distinct; availability must
  not accidentally enable automatic work or sweep history.

### Frontend ownership

- Query owns resources, URL owns filters/selection/pagination, RHF owns prompt
  drafts. Confirmation owns the UUID, provider and both exact prompt snapshots.
  Disable automatic mutation retries; retain ambiguous intent for explicit replay.
- Conflicting prompt saves preserve drafts. Adopting the latest version is an
  explicit action followed by a separate save, never an automatic overwrite.
- Independent settings writes may return out of order. Merge prompt versions and
  policy revision monotonically, fence late settings GETs, and make page Refresh
  retry selected-source/evidence/history reads as well as the list.
- Independently decode strict status/count/source/usage contracts. Display
  incomplete input and technical failure separately from successful uncertainty.
- Read history without submitting work. Keep cancellation accessible for active
  jobs while viewing old jobs. Focus selected evidence; restore focus on close.
- Source links use frozen application-owned data; XHS uses the stored source-run
  and result tuple. Model output never supplies a navigation URL.

## 4. Validation & Error Matrix

| Condition | Public result / invariant |
| --- | --- |
| Invalid payload/UUID/extra field | Existing `invalid_request`; no work |
| Invalid business prompt | 422 `invalid_analysis_prompt` |
| Stale prompt / automation revision | 409 `analysis_prompt_changed` / `analysis_policy_changed` |
| Replayed UUID with changed intent | 409 `content_analysis_request_conflict` |
| Wrong selection intent for saved state | 409 `content_analysis_selection_conflict` |
| Missing result / attempt or job | 404 `result_not_found` / `content_analysis_not_found` |
| Invalid first-entry interval | 422 `invalid_result_interval` |
| SQLite failure / closed execution service | 503 `analysis_storage_unavailable` / `content_analysis_unavailable` |
| Changed provider configuration | Existing AI error before model work; never redirect intent |
| Model/input failure | Constant bounded saved failure; no fabricated relevance verdict |

All success/error responses are `Cache-Control: no-store`; mutations retain local
Host/Origin/JSON guards. Never echo database errors, credentials or provider bodies.

## 5. Good / Base / Bad Cases

- Good: 1001 unattempted records across runs are admitted once from any page;
  concurrent automatic/manual admission cannot process the same content twice.
- Base: one saved source becomes neutral understanding and a completion event,
  independently readable before a downstream report succeeds.
- Bad: use visible IDs as bulk scope, mark legacy judgment as new understanding,
  clear failure history when a prompt changes, or start paid work from a GET.

## 6. Tests Required

- Genuine v11 fixtures preserve old rows/JSON/IDs; v12 rollback after actual DDL
  or a later child insertion leaves no partial job, claim, UUID or version update.
- 0/1/101/1001 bulk boundaries, cross-run/page membership, simultaneous claims,
  no-op replay after new arrivals, repeat discovery, historical/legacy exclusion.
- Neutral output/media bounds, malformed JSON, usage after validation failure,
  forced refresh, canonical reuse and latest-known-input invalidation.
- Busy leases, queue-exit/admission barriers, provider revision change, cancelled
  writes/calls, shutdown/reopen, exactly-once normal completion and suppressed events.
- Strict frontend decoding; prompt CAS/draft recovery; ambiguous UUID replay;
  polling refresh, history/focus/cancel controls and synthetic HTTP browser checks.
- Run backend/frontend gates on isolated Centaurus source snapshots. Browser
  acceptance uses a temporary database and fake acquisition/provider, forwarding
  both frontend and API ports. Mocks do not establish real model quality.

## 7. Wrong vs Correct

```typescript
// Wrong: page state silently limits a supposedly all-library operation.
startContentAnalysis({ selection: { kind: 'explicit', result_ids: visibleIds } })

// Correct: server freezes the full eligible set under the confirmed intent.
startContentAnalysis({
  ...confirmedRequest,
  selection: { kind: 'all_never_started' },
})
```

```python
# Wrong: report failure makes successfully saved source understanding disappear.
if not report_succeeded:
    discard_initial_analysis()

# Correct: settle independent evidence, then expose a durable downstream event.
repository.finish(job_id, "completed")
events = repository.completion_events(after_id=last_event_id)
```
