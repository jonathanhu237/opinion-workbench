# Automatic Text Reports

## 1. Scope / Trigger

Read this guide when changing automatic report admission, saved-text judgments,
composition, retry/versioning, report history or the Results and Analysis UI.
Read [Initial Analysis](./initial-analysis-guidelines.md) for the upstream job,
evidence and prompt contracts, and
[Unified Opinion Automation](./automation-workflow-guidelines.md) for automatic
admission, task goals, fixed-stage progression and retry ownership.
The legacy [Manual AI Summaries](./ai-summary-guidelines.md) contract remains
readable but is not the new workflow's creation path.

`topic_reports` consumes durable initial-analysis output. Workflow admission
freezes `selection.kind=workflow_run`, a durable operation key and the task goal
as exact report instructions; zero-source workflow admission saves an empty
report without model calls. It must not call a collector, browser,
enrichment/media acquisition or initial-understanding runner.
Topic judgment and synthesis are internal parts of the workflow's report stage.

## 2. Signatures

All routes are under `/api/v1/topic-reports`:

| Method / suffix | Contract |
| --- | --- |
| GET `/` | `limit=1..100` (default 50), optional `before_id`, `initial_job_id`, `result_id`; returns `{reports,next_before_id}` in descending report ID order. |
| GET `/{id}` | Frozen report intent with live progress, coverage and usage. |
| GET `/{id}/sources` | `limit=1..100`, `offset>=0`; `{items,total,limit,offset}`, frozen source-position order. |
| GET `/{id}/sections` | Same pagination, optional `kind=leaf|overview`; `{sections,total,limit,offset}`, level/position order. |
| GET `/{id}/sections/{section_id}` | Section must belong to the selected report version. |
| POST `/` | HTTP 202; explicit first-entry-interval report from saved text. |
| POST `/{id}/retry` | HTTP 202; new version, same frozen source scope. |
| POST `/{id}/cancel` | HTTP 200; settled cancellation, not an optimistic acknowledgement. |

Required create fields:

```json
{
  "request_id": "cb5f9330-ea77-4e24-896d-6ad5c578ee43",
  "configuration_revision": 1,
  "report_prompt_version_id": 2,
  "instructions_override": null,
  "selection": {
    "kind": "first_seen_interval",
    "first_seen_from": "2026-08-28T16:00:00Z",
    "first_seen_to": "2026-08-29T16:00:00Z"
  }
}
```

Retry requires `request_id`, `expected_revision`, `configuration_revision` and
`instructions_override`. Cancel requires `request_id` and `expected_revision`.
Reject extra fields, coerced/unsafe IDs, noncanonical UUIDv4 and invalid UTC time.
Interval endpoints support at most six fractional-second digits (microseconds);
reject greater precision rather than silently truncate it. Frontend interval
validation compares normalized UTC microseconds, not millisecond `Date.parse`
values, including mixed `Z`/`+00:00` and absent/short fractional parts.
An override is exact nonblank UTF-8 text of 1–8,000 characters, without NUL or
surrogates; preserve accepted whitespace. `null` on retry preserves the original
report instructions, not today's shared default.

Core entry points are `TopicReportService.create`, `retry`, `cancel`,
`workflow_admit`, `initialize` and `shutdown`. The historical
`initial_analysis_finished` adapter must not be registered as a live completion
callback. SQLite v14 adds
`topic_report_runs`, `topic_report_sources`, `topic_report_nodes`,
`topic_report_node_sources`, `topic_report_node_children` and
`topic_report_requests`. It preserves v11 legacy and v12/v13 analysis/schedule
rows. Never down-label an upgraded database to run old binaries.
SQLite v16 normalizes historical v15 `topic_report_runs` tables to the
workflow-owned operation-key shape. The repair preserves report/source/node
rows, IDs, JSON, timestamps, foreign keys and AUTOINCREMENT state; it validates
the full table/index/trigger contract rather than trusting only the presence of
`workflow_operation_key`.

The pure engine boundary is `schemas/topic_report_engine.py` plus
`services/topic_report_engine.py`: `prepare_judgment`, `take_leaf`,
`take_overview`, `check_request`, `parse_completion`, `validate_reuse`,
`canonical_hash`, `output_digest` and `ENGINE_VERSION`. Core owns all IO,
provider leases, graph persistence and execution; the engine owns deterministic
strict shapes, partitioning, serialization and output validation.

## 3. Contracts

### Admission, snapshots and lifecycle

- The central automation workflow explicitly admits one report child for its
  settled initial-analysis stage. The operation key and frozen member snapshots,
  including unavailable members, make admission idempotent. No per-record
  report, all-history accumulation, later-arrival expansion or callback-owned
  progression.
- Freeze exact successful attempt IDs, full accepted input text, structured
  understanding, `EvidenceCoverage`, source identity/origin, first-entry time,
  initial prompt/provider provenance and the report prompt/provider intent.
  Current source fields cannot replace this evidence when reading, retrying or
  citing the report. Coverage is part of the frozen source hash and model request.
- Explicit interval selection uses global `first_seen_at` in `[from,to)`, not
  publication or last-observation time. Freeze unavailable coverage too. Never
  resurrect older evidence behind a known newer acquired-input fingerprint whose
  analysis failed. Select the newest completed evidence matching the known
  fingerprint even when a later failed/active attempt has not proved an input
  change; a changed shared prompt alone does not invalidate that saved text.
  With no eligible success, retain the latest unavailable state. Validate claim/
  attempt content identity before selection rather than hiding broken references
  with a fallback. Compare UTC instants exactly: SQLite `julianday` loses
  sub-millisecond precision and cannot alone enforce this half-open interval.
  Retry copies the original scope, including unavailable
  members; newly prepared material requires a new explicit scope.
- Manual initial-analysis intent does not automatically produce a report.
  Prompt saves, GET, polling and route entry admit no work. New automation tasks
  remain disabled until explicitly enabled; run-now is a separate explicit
  mutation and does not enable the timer.
- Workflow admission only admits/enqueues report intent and must not wait for
  an upstream AI lease. A downstream exception must not undo or strand saved
  initial analysis. The report queue rechecks emptiness under its admission lock
  so concurrent admission cannot be left without a runner.
- Pending legacy analysis-completion events are inert on startup. Manual initial
  analysis cannot create a report during restart. Startup is storage-only;
  recovered active reports become explicitly interrupted, non-runnable records with
  `recovery_reason=backend_restart`. A later unrelated wake cannot resume them.
  Existing historical event links remain readable but do not admit work.
  Explicit retry creates a new version. Stop the automation owner before
  draining child analysis/report owners; clean up all owners even when an
  earlier cleanup fails.

### Bounded saved-text execution

1. Every analysis-eligible source receives one text-only judgment with the frozen report
   instructions: `relevant | irrelevant | uncertain`, with a nonblank reason of
   at most 600 characters. Its serialized input includes the coverage manifest;
   preview and partial sources cannot claim unseen detail or media. A technical
   error is not an unrelated judgment.
2. Partition relevant evidence in frozen order into leaves of at most eight
   sources. Use full accepted text and all saved understanding fields, not only
   a short abstract. Leaf output is an overview plus 1–16 cited paragraphs,
   each nonblank and at most 2,000 characters. Each paragraph cites 1–8 unique
   admitted result IDs; the citation union must equal all leaf members.
3. Keep every leaf. A tree of at most eight completed children per overview
   reduces them to one root. A one-leaf report needs no extra request. Only the
   actual final singleton is carried unchanged; fill buffers across database
   pages. Each overview call consumes at least two children. Overview paragraphs
   cite supplied logical child keys, not model-created database IDs or URLs.

Each exact system-plus-serialized-user input is at most 120,000 characters,
including business instructions and JSON escaping. The existing transport must
remain strictly below 9,000,000 bytes. Reuse the existing 2,048 judgment / 4,096
composition output-token budgets and 180-second deadline. These are local bounds,
not a promise of provider context capacity. Oversize input fails visibly, with
no clipping, billed repair call or media/stage-one fallback.

Plan all leaves before leaf execution and each overview level before that level
executes. Persist the plan and compare execution-time fresh requests with it;
do not repartition after an ambiguous paid call. Persist application-owned graph
membership separately from model citations. Parent members must equal the
disjoint union of real child members, not just have the same total count.

### Fresh requests, reuse and usage

- Reconstruct a fresh engine request from frozen evidence and verified graph
  rows. Stored `PreparedCall` messages are audit data, never executable authority.
  The object intentionally does not contain the full dependency/context manifest;
  checking its shape alone cannot prove its stored `input_hash`.
- Input compatibility covers engine/schema version, logical node key, provider
  revision/endpoint/model, exact prompt, exact messages, ordered evidence/output/
  membership hashes and request budgets. Source hashes include immutable initial
  attempt IDs and provenance, not current report IDs or credentials.
- Revalidate nested models even when the outer Pydantic model is frozen. Use
  canonical sorted compact strict JSON; reject NaN, duplicate keys, unsupported
  values and invalid UTF-8 rather than stringify/repair them.
- `output_digest(kind, output)` verifies shape and hashes the existing output
  manifest. It does not prove citation membership, graph identity or credential
  safety. Projection and reuse separately verify those constraints. Corrupt
  matching reuse candidates fail closed; incompatible candidates are not reused.
- Reused nodes point to a canonical completed node, have `attempted=false` and
  `usage=null`, and contribute no historical requests/tokens to the new version.
  Retry parents and canonical reused nodes must have older IDs than their new
  versions; reject self/cyclic ancestry before walking it. Enforce strict `<`
  order in both backend projections and frontend decoders, not only inequality
  with the current ID; a future-ID reference is invalid even without a self-loop.
  Mark each fresh attempt durably immediately before its single transport call.
  Retain observed usage even when JSON/schema/citation validation subsequently
  fails. Unknown usage is not zero; safe-integer overflow yields unknown totals.
  Reconstruct `AIUsage` at C transport receipt and again before persistence.
  Invalid optional usage (including mutations inside a frozen model's details)
  becomes `None`, preserving attempted counts; never fall back from the parser's
  unknown value to the original invalid object and poison report history.
- Report-only retry or changed instructions may do new text work, but must add
  zero collector, media-acquisition, media-upload and initial-analysis calls.

### Public state and interface

Report status is `queued`, `judging`, `composing`, `completed`, `empty`, `failed`,
`cancelled`, `interrupted` or `configuration_blocked`. `completed` has a root;
`empty` has `no_ready_sources` or `no_relevant_sources` and no root. No ready
sources means zero model calls; the historical `ready` count now means frozen
analysis-eligible saved inputs, not only strict full-source acquisition. No
relevant judgments means zero composition calls. Failed reports retain
inspectable validated draft sections.

Coverage reconciles `total = ready + unavailable`; ready reconciles pending,
judging, relevant, irrelevant, uncertain, failed, cancelled and interrupted.
Initial failures remain unavailable, not report judgments. Report usage separates
judgment, composition and total attempted/accounted requests and known tokens.
Counts describe source records, not verified incidents.

Public leaf sections contain bounded frozen sources and `source_ids`. Public
overview sections have no expanded source array; they contain bounded children
and `section_ids` mapped to this report version's actual child rows. Never expose
the old version's child IDs after reuse. Resolve links only from validated frozen
source URLs/XHS origin tuples; model prose is text, not executable HTML or links.

Source projections expose `evidence_coverage`; report UI labels preview, detail,
validated-media and full-source evidence and shows modality counts. It may not
flatten preview evidence to the same coverage presentation as a full source.

Keep selected report/version and source/section pagination in URL state, separate
from result filters and initial-job selection. One-click initial analysis stays
the primary action. Show workflow-owned report status beside its originating run;
retry/cancel and optional interval/one-off override remain distinct secondary
actions. Preserve ambiguous mutation intent/UUID; do not auto-retry a mutation or
turn an empty report-list response into authorization to create one.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Unknown report / section outside selected version | 404 `topic_report_not_found` / `topic_report_section_not_found`. |
| Stale observed report revision | 409 `topic_report_changed`. |
| UUID reused for a changed action, target or payload | 409 `topic_report_request_conflict`; identical replay returns the original intent result before current configuration checks. |
| Retry active report / cancel terminal report | 409 `topic_report_not_terminal` / `topic_report_not_active`. |
| Reversed/empty first-entry interval | 422 `invalid_report_interval`. |
| Interval endpoint with more than six fractional-second digits | 422 `invalid_request`; no truncated interval or report admission. |
| Blank, oversized, NUL or invalid UTF-8 override | 422 `invalid_analysis_prompt`; no admission. |
| Shared prompt changed before explicit create | 409 `analysis_prompt_changed`; override does not bypass the displayed-default revision check. |
| Incompatible/unavailable provider lease | Configuration blocked; report-only execution failures retain `ai_configuration_required`, `ai_configuration_changed`, `ai_credentials_unavailable` or `ai_settings_storage_unavailable` with existing constant AI messages. Do not widen the legacy/A failure union or silently substitute a provider. |
| Corrupt stored prompt, source, node, graph, usage or state | Sanitized 503 `topic_report_storage_unavailable`, not fabricated success or raw SQLite/source text. |
| Eligible preview/partial saved input | Freeze coverage, judge available evidence, and retain its limits in citations/UI. |
| No analysis-eligible saved input | Empty `no_ready_sources`; zero report model calls. |
| Coverage conflicts with frozen saved input | Storage failure; do not judge or silently repair it. |
| Closed/unavailable service | 503 `topic_report_unavailable`. |
| Invalid/omitted citation, invalid JSON/schema or leaked credential | Visible node/report failure, saved upstream evidence retained, observed usage preserved. |

Use existing strict local mutation guards, no-store responses, secret-safe
provider errors and fixed public messages. Do not return raw provider output or
exception detail to make a report error more descriptive.

## 5. Good / Base / Bad Cases

- Good: a ten-member job settles with eight successes and two input failures;
  exactly one report judges all eight, retains the two unavailable rows and
  composes only the relevant subset. Retrying it preserves those ten snapshots.
- Base: all ready sources are unrelated/uncertain. The report is empty without
  composition, while each initial summary and relevance reason remains readable.
- Base: a preview-only source may be judged and cited, but its report source keeps
  `search_preview`, partial text and unknown media coverage visibly attached.
- Bad: a 1,001-member job silently stops after the first 100, or the UI sends a
  second generation request when polling sees no report yet.
- Bad: omit coverage from the report hash/request or present a preview citation as
  a detail/full-source reading.
- Bad: changing the report instructions reruns image/video understanding or
  overwrites the old report's evidence/prompt version.

## 6. Tests Required

- Populated v11→v14 migration, v13→v14 preservation, reopen, forward-version
  rejection and transactional rollback after an actual child insert; no startup
  provider/collector work and no changed legacy JSON, usage, IDs or source links.
- 10/8/2 workflow admission, duplicate operation-key replay, later arrivals,
  zero-ready and cancelled/interrupted upstream suppression.
- 1/8/9/101/1,001 sources, strict exact 120,000-character boundary with escaped
  Unicode/custom prompts, oversize input, multi-level tree and final singleton.
- Missing/unknown/duplicate citations; nested model mutation; Boolean IDs;
  graph member substitution, digest mismatch and persisted-message tampering.
- Fresh/compatible/incompatible/corrupt reuse, current-version child-ID mapping,
  unknown/overflow usage, parse failure after usage and zero report-only media.
- Preview, partial detail, validated-media and full-source frozen inputs. Assert
  coverage survives repository round-trip, request serialization, source hashing,
  API decoding and visible report source labels; conflicting coverage fails closed.
- Settled cancellation/shutdown, queue-exit admission race, configuration changes
  and recovered metadata remaining non-runnable after a later unrelated wake.
- Strict HTTP/decoder errors, UUID replay and ambiguous transport retry, saved
  default versus one-off override, interval timezone/first-entry semantics,
  frozen cross-run citations, self/future retry and canonical-node references,
  and legacy read-only navigation.
- Full backend and frozen frontend gates locally; isolated fake-service
  browser QA for automatic reporting, text-only retry, keyboard focus, narrow
  layout, reload/pagination and console. Mocks do not establish live-model quality.

## 7. Wrong vs Correct

Wrong: execute a saved request envelope after checking only its stored hash.

```python
call = PreparedCall.model_validate_json(row["prepared_json"])
await client.complete(configuration, messages=stored_messages(call))
```

Correct: regenerate from immutable evidence and verified dependencies, verify
the frozen provider intent and plan, then preflight the exact fresh request.

```python
call = prepare_judgment(context, frozen_source)
proof = check_request(call, configuration)
# Core verifies the graph/plan, persists attempt ownership, invokes transport once
# with these exact fresh messages, then validates output and settles usage.
```

Wrong: retry by selecting today's successful evidence for the old time range.
Correct: copy the parent report's frozen source/evidence rows into a new version;
an explicit new interval report is how the user chooses today's eligible scope.

Wrong: report a preview source using only its understanding and omit input limits.

```python
payload = {"text": source.input.text, "understanding": source.understanding}
```

Correct: freeze and serialize the evidence limits with the source.

```python
payload = {
    "text": source.input.text,
    "understanding": source.understanding,
    "evidence_coverage": source.input.evidence_coverage,
}
```
