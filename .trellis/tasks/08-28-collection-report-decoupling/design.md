# Decoupled Collection, Initial Analysis and Reports

Status: approved for implementation on 2026-08-29 after final-summary review.
Parent requirement IDs are authoritative. Approval does not activate schedules,
call a real provider or change the production runtime database.

## 1. Boundaries and Ownership

Retain one FastAPI application, SQLite database and React SPA. No queue broker,
new deployment, new crawler or permanent media archive is required.

```text
Monitoring rule (search configuration)
  -> Collection task / fixed-interval occurrence
  -> Existing batch/run collector -> deduplicated results + origin membership
  -> Durable initial-analysis admission (automatic new / explicit history)
  -> Per-record acquisition and understanding -> immutable saved text
  -> Task settles -> durable report intent, once
  -> Text-only relevance -> bounded synthesis -> one report version
```

Each arrow crosses a committed boundary. A downstream failure does not undo an
upstream success. Results and Analysis owns both AI stages; collection pages own
collection history and link to the appropriate saved results/reports.

Keep `SearchBatchService`, `SearchRunService`, `ContentEnrichmentService`,
`BrowserOperationCoordinator`, `AISettingsService.operation()` and `AIClient` as
the existing execution/resource owners. Extract shared validated input, strict
JSON, citation, credential and usage helpers from the old summary path only
where reused; do not copy a second transport or browser launcher.

Proposed new module families under `backend/src/longtian_api/`:

- `analysis_settings`: two business prompt defaults and explicit automation policy.
- `results`: global results/provenance queries, without duplicating stored content.
- `content_analyses`: admission, per-record saved understanding and task progress.
- `collection_schedules`: interval settings, occurrence history and admission.
- `topic_reports`: frozen text sources, relevance, bounded composition and history.

Each family follows `api/v1 -> service -> repository -> database`; model schemas
and public errors have a single owner. Existing `ai_summaries` remains the legacy
reader/compatibility path, not the storage owner for new analyses.

## 2. Data Contracts and Migration

Current schema is v11. Recheck before implementation, then append sequential
migrations owned by A, B and C (planned v12, v13 and v14). Never relabel or rebuild
old tables as a shortcut. Use short, settled, off-event-loop SQLite operations.

| New aggregate | Required persisted contract |
| --- | --- |
| `analysis_prompt_versions` | Stage, immutable version ID, exact instruction text, content hash, application schema version, timestamp. |
| `analysis_settings` | Two current prompt-version IDs; automation enabled flag, approved provider revision, policy revision and activation watermark. No credentials. |
| `content_analysis_claims` | One row per global content ID; eligibility origin, first discovery provenance, initial-attempt/legacy marker, active owner and latest known input fingerprint. Eligibility is not a prompt-cache query. |
| `content_analysis_jobs` | Request UUID or durable automatic origin, frozen selection/count, trigger, both prompt snapshots, provider revision, progress, independent status and settlement time. |
| `content_analysis_attempts` | Job/content identity, deterministic position, source snapshot and valid origin run, acquisition/analysis state, input text/metadata/fingerprint, structured output, errors and usage. Successful terminal output is immutable; a retry creates another attempt. |
| `analysis_completion_events` | Unique initial-analysis job ID, settlement proof and report intent state. Written with normal job settlement, not from frontend polling. |
| `collection_schedules` | Rule reference, platforms, existing per-term result cap, normalized interval, enabled flag, revision, anchor and next due time. |
| `collection_occurrences` | Schedule/revision/due-time unique key, dispatch token, claimed/skipped/missed/interrupted outcome, optional existing batch ID and bounded reason. |
| `topic_report_runs` | Automatic origin or explicit request UUID, immutable prompt/provider/selection snapshots, parent version for retries, status, coverage and usage. |
| `topic_report_sources` | Every selected record, its frozen stage-one attempt ID/text/hash or unavailable reason, origin membership, relevance outcome and reason. Unique report/content identity. |
| `topic_report_nodes` | Bounded judgment/composition work, input hash, stable position/tree membership, saved validated output, errors, usage and reuse reference. Leaf sections remain inspectable. |

Foreign keys, CHECK constraints, unique origin/request keys and guarded writes
back service validation. Positions are nonnegative without the legacy 0–99 cap.
Public IDs/counts must be JS-safe; internal counters must not overflow silently.
Multi-query projections use one read transaction. Paginate large snapshots;
never load a whole library into a request body or hold a transaction while doing
network, browser or model work.

### Compatibility

- Preserve all `search_contents`, `search_run_contents`, rule snapshots and old
  `ai_summary_*` IDs/columns/JSON/citations. Existing report URLs remain readable.
- Old item judgments were scoped to monitoring rules, not the new neutral
  understanding schema. Keep them as labelled legacy analysis. Do not certify
  them as new stage-one success or copy old relevance into a new topic verdict.
- Seed only eligibility/history markers: old completed/reused analyses are
  `legacy_completed`; old failed/incomplete/interrupted attempts are
  `legacy_attempted`. Both remain outside “never analysed” bulk admission and
  have explicit new-stage reanalysis/retry actions. Old sources with no attempt
  are historical never-started records, eligible only for explicit selection.
- No migration, prompt seed or history read performs acquisition or model work.
  Retain legacy POST behavior only as a compatibility entry clearly labelled
  “旧版分析”; new UI must not call it. Both paths share resource exclusion, and
  legacy admission/completion participates in the same active claim/history
  guard so bulk cannot duplicate an already admitted legacy item either.
- If any legacy source cannot be proven compatible, preserve its history and
  explain that new-stage analysis requires an explicit operation. Do not backfill
  expensive work merely to make status badges look uniform.

## 3. Prompts, Provider Authorization and Reuse

Two editable shared instruction fields live in Results and Analysis, separate
from provider endpoint/model/key settings. Proposed bound: 1–8,000 Unicode code
points per prompt, valid UTF-8, no NUL; preserve exact accepted text. Empty or
oversized input fails locally/server-side without changing the saved default.

App-owned instructions retain output schemas, source identity, uncertainty,
non-execution of source instructions, citation checks and privacy constraints.
User instructions control business focus; collected text/media remain quoted
untrusted data. No tools, links or instructions found in sources are executed.

Freeze both prompt versions and provider revision when the user/automatic policy
admits an initial-analysis task, so its eventual automatic report uses the
displayed instruction pair. The report job later inherits that intent; editing
defaults during analysis affects subsequent tasks, not this one. Explicit
text-only reports/reports with overrides snapshot their own admission-time
instructions. A one-off override never edits a default.

On first enablement, show the saved provider/model, automatic use of collected
text/media, and possible quota usage. Persist explicit authorization against
the provider revision. Merely upgrading, saving prompts or entering a page does
not enable automatic work. New schedules are initially disabled. This is a
one-time setup boundary, not a confirmation before each automatic report.

Acquire the existing AI lease per executing stage. A queued operation cannot
silently use a changed provider revision; mark it configuration-blocked and
require explicit re-admission. Never persist credentials on jobs or retain old
keys to bypass revision checks. Prompt defaults may change independently while
running work retains its immutable versions. Disabling automation stops new
automatic admissions; already running work has explicit cancellation controls.

Source/input fingerprint, first-stage schema/prompt, extractor and provider
revision determine compatible reuse. Stage-two prompt changes do not invalidate
valid stage-one text. Do not confuse “no cache for newest prompt” with “never
analysed”; known newer input must not resurrect older evidence after a failure.

## 4. Initial Analysis Admission and Execution

### Discovery and frozen scope

Collection deduplication inserts eligibility/provenance in the same transaction
as a newly created global result and its origin membership. Repeated collection
never resets first-seen time or the claim. The activation watermark and legacy
markers prevent an upgrade/repeat observation from sweeping historical data.

After an ordinary collection task settles and releases browser ownership, admit
its eligible newly discovered records as one frozen initial-analysis job. A batch
is one automatic origin; an independent search run is another. A partial failed
collection may still supply saved new results, with its failed collection status
retained. A paused/cancelled collection does not launch a new paid follow-up;
its saved candidates remain visible for explicit analysis.

One-click `一键初步分析` atomically selects all never-started, unclaimed global
records across pages/runs, including history. Freeze membership with a server-side
set operation, using deterministic content-ID order. No array of visible page IDs,
LIMIT 100, implicit time filter or repeated user submissions. A unique active
claim per content serializes automatic/manual races. The response states how
many were admitted and how many already belong to other active tasks; those
continue under their original task/report ownership. Zero eligible records is
a truthful no-op and creates no model request or empty duplicate report.

Later arrivals belong to later jobs. Explicit selection, failed-attempt retry and
completed/legacy reanalysis use separate intents, preserving all old versions.
Every newly admitted retry/reanalysis task follows the same automatic report
rule unless the user cancels it.

### State machines

| Owner | States and terminal meaning |
| --- | --- |
| Job | `queued -> running -> completed` after every member has a terminal attempt; completed means settled, not all successful. Separate `cancelled`, `interrupted`, `configuration_blocked` states. |
| Attempt | `queued -> acquiring -> analysing -> completed`; alternatives `input_incomplete`, `unsupported`, `failed`, `cancelled`, `interrupted`. Semantic uncertainty inside successful text is not a technical failure. |
| Report intent | Created exactly once with normal completed-job settlement; consumed idempotently into a separate report job. No report is rebuilt per item. |

Process records serially using existing owners; release the browser between
items, and never hold it during text reporting. A busy resource leaves work
queued, with reason visible; it is not a failed paid attempt. Never starve manual
verification recovery by stealing its owner. No network call occurs inside a
claim/settlement transaction. Each committed success is readable immediately.

On restart, previously admitted unfinished jobs/attempts become interrupted and
need explicit recovery; no automatic replay of possibly billed work. Unadmitted
new-result markers remain persisted and visible. Startup reconciliation is
storage-only; do not turn it into a historical admission/model loop. A subsequent
ordinary collection completion can admit only proved never-attempted eligible
new-result backlog with valid policy/provenance, not interrupted jobs. Cancellation
drains owned writes/calls, preserves successes, and suppresses that task's automatic
report intent. An already separately admitted report has its own cancel control.

### Saved evidence

Revalidate real media inventory/bytes at the model boundary. Keep current input
bounds: combined title/body 20,000 characters, at most 24 images/one video, 6 MiB
media, encoded request under 9,000,000 bytes. Preserve the current reviewed-media
provider boundary; unsupported/incomplete input is not silently downgraded.

Save the full accepted extracted text and bounded media metadata plus a strict
stage-one object: `summary` (1–1,500 chars), `location_clues` (up to 12 brief
attributed excerpts, each <=200 chars, text/image/video/audio modality),
`time_context` (<=500 chars), `media_observations` (up to 12, each <=400 chars),
and `uncertainties` (<=500 chars). Limit combined generated prose to 6,000 chars.
The model's output budget remains 2,048 tokens; overrun/missing fields fail, not
repair or silent clipping. The bounds are maxima, not a promise to exhaust every
field. Retaining accepted source text prevents a short abstract becoming the
only downstream evidence. Store app-owned coverage, source IDs and fingerprints
alongside output, not as model assertions.

Geography can remain unknown. Claims remain attributed, times retain uncertainty,
and media observations do not assert that an event was verified. No stage-one
topic-relevance gate. Cleanup temporary media using existing staging ownership;
only saved text/metadata is durable. Reanalysis may reacquire media explicitly.

## 5. Automatic Text-only Report

### Handoff and scope

The transaction that normally settles an initial-analysis job writes its unique
completion event. The consumer creates a report exactly once, freezing successful
attempt IDs/text/source snapshots and the unsuccessful remainder. A crash between
event and report creation cannot lose or duplicate the report. Reconciliation
may materialize missing queued metadata, but startup does not resume a partially
executed model call; interrupted reports require explicit retry.

For ten attempts with eight successes, all eight enter topic evaluation after
the ten attempts settle. Only the subset judged relevant enters substantive
report prose; do not claim all eight are Shenzhen Longtian sources. The other two
remain uncovered initial-analysis outcomes. No additional confirmation, per-item
regeneration, whole-history accumulation or waiting for failures to succeed.

Optional explicit report creation selects existing valid saved analyses by
`first_seen_at` in a half-open UTC interval `[from, to)`, with UI dates converted
from Asia/Shanghai. It can cross runs/platforms/rules. It never launches stage one.
Membership and latest eligible evidence versions are frozen on admission; an
old report remains readable even when the current source/prompt later changes.

### Bounded aggregation for more than 100 records

Do not carry the legacy report's total-source cap into this data model. Use one
logical report with bounded text requests and paginated persisted sections:

1. **Judgment:** one text-only request per saved initial analysis, with the same
   saved stage-two instructions. It returns `relevant | irrelevant | uncertain`
   and a reason <=600 chars. All successful initial analyses are evaluated;
   failed input/model parsing is not an irrelevant judgment. Budget 2,048 output
   tokens and 180 seconds per request, no hidden retry.
2. **Leaf sections:** partition relevant saved evidence in stable source order,
   at most eight sources per request and at most 120,000 characters including
   system instructions, custom prompt and exact serialized input. Generate the
   existing overview plus cited paragraphs shape, with at most 16 paragraphs per
   leaf and a 4,096-token/180-second bound. Validate citations against that leaf;
   their union must cover its relevant sources. Save every validated leaf.
3. **Overview:** if several leaves exist, synthesize their bounded overviews
   through a tree of at most eight children per node under the same input/output
   bounds. Internal references must belong to the supplied child IDs; persist
   application-owned descendant source membership. Each level reduces node count.
   Keep every detailed leaf in the final report rather than replacing evidence
   with the compressed top-level overview. One leaf needs no extra overview call.

The report is not a promise to fit an arbitrary library in one model context or
one response payload. Character and encoded-byte checks are local safeguards,
not a model token-capacity guarantee. A single source/prompt that cannot fit is
a visible failure; no stage-two reacquisition, silent cut, semantic repair call
or hidden manual narrowing. Partition before sending, never split in response
to an ambiguous already-billed call.

This uses N judgment requests plus bounded relevant-section/overview requests,
in addition to stage one's own work. Display attempted/accounted requests and
known/unknown usage separately by stage. Large tasks may be slow/cost more; no
currency estimate without actual pricing data. Preserve usage even when local
schema validation fails and exclude reused historical tokens from new totals.

### Outcomes and independent recovery

Report states are `queued -> judging -> composing -> completed`, or `empty`
when the validated input/judgment set has no report material. `failed`,
`cancelled`, `interrupted` and `configuration_blocked` retain their causes;
only explicit re-admission creates a retry version from those states.

- No successful stage-one evidence: bounded `empty` outcome with initial failure
  counts, zero model calls. This does not mean no relevant events exist.
- No relevant evidence after successful judgments: bounded `empty` report with
  unrelated/uncertain counts, no composition call; all stage-one texts remain.
- Technical judgment/composition failure: report `failed`, validated intermediate
  results and stage-one successes preserved. Partial sections may be inspected
  as a clearly labelled draft, not a successful complete report.
- Explicit retry creates a new report version with the same frozen scope/prompt,
  reusing compatible completed nodes and retrying failed/unfinished text work.
  New instructions create a new version and invalidate only downstream nodes.
  Neither action calls the browser, sends media or redoes stage one.
- Cancellation/interruption are terminal attempts with separate explicit retry.
  Saving a prompt, later collection, GET or a cache miss cannot cause retries.

Coverage is calculated from stored outcomes: original task total, successful
initial analyses, unavailable/failed remainder, relevant/irrelevant/uncertain
judgments and technical report failures. These are content counts, not incident
counts. Invariant: every input has exactly one state; every substantive citation
resolves to frozen relevant evidence. Render model prose as text, not executable
HTML/Markdown links. The model never supplies source URLs.

## 6. Periodic Collection

Store a positive whole-minute interval, accepting minutes or hours in the form;
proposed maximum 43,200 minutes (30 days), normalized to minutes server-side.
This is not cron/calendar scheduling. On enable/edit, next due is now plus the
interval. Show the actual next due time; a rule edit changes only future runs.

Run one lifespan-owned timer for the existing single backend process. Use an
injectable UTC clock and monotonic timer waits; calculate due times from the
saved anchor, not by accumulating task execution duration. For an overdue time,
advance to the first future anchor-aligned occurrence. Clock rollback does not
repeat an already claimed key; forward jumps create a missed-range record, not
an unbounded row per missed minute.

At due time, claim `(schedule_id, revision, due_at)` once. Validate the current
rule exists/is enabled and snapshots still match its collection settings.
Disabled/deleted rules and unavailable browser sessions produce explicit skipped
reasons. A busy current collection or shared-browser owner also skips this
occurrence without cancelling current work or queuing catch-up jobs.

Extend existing batch admission with an internal idempotent occurrence token;
the batch row and occurrence link must be durably associated before launching
browser work. Recovery of a claimed-but-unlaunched occurrence marks it
interrupted, never dispatches a second collection. Disabling a schedule stops
future occurrences only; cancellation of its active batch remains explicit.
Manual-verification pauses keep existing recovery/ownership controls. On restart,
record missed periods, move to a future due time and do no catch-up collection.

Completed collection publishes the same durable new-result handoff as a manual
collection. No report is needed for collection to succeed. Stop timer admission
first during shutdown, then settle analysis/report owners before existing
media/client/batch/search/browser teardown; run all cleanup even if one fails.

## 7. API and UI Contracts

All routes below are proposed under `/api/v1`. Pydantic strict schemas and narrow
frontend decoders own shapes; use constant `{detail:{code,message}}` errors,
`Cache-Control: no-store`, existing local Host/Origin/JSON guards, and no raw
exceptions/provider payloads. New request UUIDs mean new user intent, not retry.

| Resource | Proposed endpoints / behavior |
| --- | --- |
| Shared results | `GET /results` with platform, stage-one state, first-entry interval and cursor filters; `GET /results/{id}` with paginated origin/history links. Reads are side-effect free. |
| Prompts/policy | `GET /analysis-settings`; revision-guarded `PUT /analysis-settings/prompts/{stage}` and explicit `PUT /analysis-settings/automation`. Provider credentials remain in existing settings. |
| Initial analysis | `POST /content-analysis-jobs` with UUID, provider/prompt revisions and discriminated selection: all-never-started, explicit IDs, failed retry or reanalysis. `202` returns frozen counts/job; GET list/detail/items; POST cancel. |
| Schedules | GET/list and POST/create, revision-guarded PUT/update, GET occurrence history. Reference existing rule/platform/result-cap schema; do not embed prompt fields. |
| Reports | GET/list/detail/sources/sections; internal event creates automatic reports. Explicit POST for saved-text interval/override reports; POST retry/cancel with observed revision and UUID. No report mutation admits stage one. |

List/page limits bound responses only (default 50, max 100), not whole-task
membership. Every paginated report section includes the validated frozen source
projections needed by its citations; the UI must not fetch the whole library or
validate a citation against only the currently visible result page. Preserve
`(source_run_id, content_id)` proof for XHS stored-result opening; use existing
validated source links for other platforms.

Keep existing civic theme, shadcn/Base UI primitives and React Router shell. This
is an interaction/data-flow change, not a visual rebrand or a new design system.

- Collection: schedule settings/history alongside existing manual runs.
- Results and Analysis: shared result list, `一键初步分析`, separate prompt editors,
  per-record saved-text detail, task progress and reports/history.
- Main action states its entire-library scope and current eligible count; no
  misleading page-only selection. Display saved provider/usage boundary next to
  it without making a report-generation dialog mandatory. Disable duplicate
  submission and retain the same UUID after an ambiguous transport response.
- Show `初步分析：已处理 8/10` separately from `报告：等待初步分析结束` /
  `正在生成` / `已生成` / `生成失败`. Failure is not a red-coloured “unrelated” row.
- Prompt editors use explicit `保存初步分析提示词` and `保存报告提示词` actions,
  dirty/pending states and local errors. Optional `用其他提示词重新生成` operates
  on saved text and does not change defaults unless separately saved.
- Retry failures and reanalyse completed/legacy sources are visibly separate
  from the all-never-started action. Cancelling an analysis task stops its
  automatic follow-up; saved successful texts remain available.
- TanStack Query owns server state, URL owns filters/version selection, RHF/Zod
  owns editors, and React owns disclosure/focus only. GET polling never submits.
  Keep keyboard labels, focus, live status feedback and useful empty/error states.

UX evidence: local `ui-ux-pro-max` search `batch processing progress feedback`
returned Feedback / Progress Indicators for all platforms. Apply separate stage
indicators; the unrelated mobile haptic and feedback-rating suggestions are not
part of this task. Existing frontend specs override generic visual suggestions.

## 8. Delivery, Risks and Rollback

A establishes shared results/stage-one storage and UI; B adds schedules against
that handoff; C adds reports and the complete feature. Migration and shared
`main.py`/router edits are serialized, not concurrent multi-writer work. Parent
integration verifies the full experience before enabling automation.

During rollout keep automatic admission disabled and use isolated DB/fake-client
acceptance first. Back up the real database consistently only with the approved
deployment workflow; do not copy a live WAL database naively. Recheck real data
compatibility before enabling any automatic paid work.

Rollback first disables new admissions and settles owners. Leave additive data
and old reports intact. Old binaries reject newer schemas, so rollback is a
forward-compatible code disable or an explicitly approved restore of a matched
backup, never `user_version` relabelling/table deletion. A restore can lose later
data and needs a concrete recovery/merge decision; do not automate it.

Remaining risks are execution time/usage for large batches, model mistakes or
lost clues despite structured summaries, browser contention, and source edits
after discovery. Mock tests prove contracts, not real Shenzhen Longtian accuracy
or five-platform media support. Representative acquired-media/provider evaluation
requires separate explicit live authorization. No unresolved product question
blocks review of this proposal.
