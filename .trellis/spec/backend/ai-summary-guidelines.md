# Manual AI Summaries

## 1. Scope / Trigger

This is the legacy combined workflow. New shared results and independent initial
understanding follow [Independent Initial Analysis](./initial-analysis-guidelines.md).
Keep this compatibility contract readable; do not apply its 100-source cap or
topic-specific item object to new analysis jobs.

Use this contract when changing collection-run summaries, saved item analyses, media-to-model
input, usage accounting, or their frontend. This is one explicit operation over one terminal run,
not automatic screening, a cross-platform report, or a daily schedule. A model judgment is an
attributed analysis of a source, not verified proof that an incident occurred.

Owners: `schemas/ai_summaries.py`, `repositories/ai_summaries.py`,
`services/ai_summaries.py`, `services/ai_analysis.py`, `services/summary_errors.py`,
`api/v1/ai_summaries.py`, and the shared `AISettingsService`/`AIClient` transport.
Frontend owners: `lib/api/ai-summaries.ts`, `routes/collection-ai-summary.tsx`,
`routes/collection-summary-confirmation.tsx` and the collection detail integration.

## 2. Signatures

All routes below use `/api/v1` and secret-free strict projections:

- `POST /search-runs/{id}/ai-summaries` accepts exactly
  `{request_id: UUIDv4 string, force_refresh: boolean, configuration_revision: positive integer}`
  and returns `202 SummaryRun`. The caller creates one UUID per confirmed intent.
- `GET /search-runs/{id}/ai-summaries?limit=20&before_id=N` returns
  `{summaries, next_before_id}` in descending summary-ID order; limit 1–50.
- `GET /ai-summaries/{id}` returns `SummaryRun`.
- `GET /ai-summaries/{id}/items?limit=50&offset=0` returns
  `{items,total,limit,offset}` in frozen snapshot order; limit 1–100.
- `POST /ai-summaries/{id}/cancel` accepts exactly `{}` and returns the settled terminal run.
- `SummaryService.create(source_run_id, SummaryCreate)` admits the explicit operation.
  `cancel(summary_id)` and `shutdown()` settle owned work before releasing resources.
- `AIClient.complete(configuration, *, messages, max_tokens, deadline, include_usage=True)`
  returns `AICompletion(text, usage)`. The existing tiny text connection test stays separate.
- Migration **v11** adds `ai_summary_runs` and `ai_summary_items`; it does not rewrite collection
  data. `create_app(content_enrichment_service_factory=...)` supports isolated acceptance without
  replacing the product acquisition or browser ownership model.

## 3. Contracts

### Admission, provenance, and resource ownership

- GET, route entry, refresh, search completion and restart make zero model requests. Only an
  explicit generation does analysis. UI confirmation freezes and displays the saved endpoint,
  model, revision, full source count, media-upload boundary and possible API quota use.
- Acquire the existing AI configuration lease using the displayed revision. A changed revision
  fails before acquisition/model work; never silently send to a new destination. Settings and
  competing AI operations remain excluded while leased.
- Freeze all unique stored results, historical rule/terms, source observations and version fields
  in one short transaction. Do not use the current UI filter/page or reread an edited rule. Reject
  active runs (including active/paused parents), zero sources and more than 100 sources before work.
- UUID replay binds the source run, refresh flag and configuration revision. The same intent
  returns its existing version, including terminal versions; a changed intent conflicts.
- Historical query and per-source matched-term arrays follow `MAX_TERMS_PER_RULE = 100`, with
  order preserved. Do not introduce a smaller model/UI-only limit or truncate either array.
- Use the shared `ContentEnrichmentService.operation()` and its stored-source lookup. Pass the
  frozen `expected_source`; source changes/active collection fail before the worker starts. Keep
  one browser reservation for uncached serial items and release it before text composition.
- Short SQLite operations run off the event loop and settle under cancellation. Never hold a
  database transaction across browser/model work. Startup marks incomplete summaries interrupted;
  it never resumes paid work. Shutdown drains summary, media, AI, batch, search and browser owners.

### One item analysis and compatible reuse

- For complete uncached input, send the acquired full text and validated media once, then save
  `decision`, `reason`, and `evidence_summary`. Valid decisions are `relevant`, `irrelevant`, and
  `uncertain`. Incomplete input, unsupported input and technical failure are not decisions.
- Revalidate the enrichment identity, inventory/coverage, fingerprint, each asset's hash/MIME/size
  and actual in-memory bytes at the model boundary. A cover or first image is not a complete video
  or image set. Never label a truncated body or unverified inventory ready.
- Current media request support is deliberately limited to the reviewed pair
  `https://dashscope.aliyuncs.com/compatible-mode/v1` + `qwen3.5-omni-plus`.
  Other saved configurations can process text-only input; media receives a bounded unsupported
  result, not a silent text-only fallback. This is an implementation support boundary, not a claim
  that other providers cannot accept media.
- Bounds: 20,000 combined title/body characters, 24 images, one video, 6 MiB raw media, and less than 9,000,000
  encoded request bytes. No silent trimming, splitting, repair request or model retry. Inline MP4
  retains its audio track; no page/CDN URL, cookie, local path or browser handle enters the request.
- Cache compatibility includes source observation, historical context, configuration, analysis
  prompt/input version, extractor and acquired content fingerprint. Relative display labels such
  as “刚刚” are not content changes. Once newer acquired content is known, an older completed result
  must not reappear merely because analysis of that newer content failed.
- Default reuse does not reopen a remote post to check for unseen edits. Force-refresh explicitly
  reacquires and reanalyses. Reuse points to a canonical completed item, not a reuse chain; old
  versions and original collection results remain intact. Private cost-probe results are not cache.
- Persist text analyses and bounded input metadata, not temporary media bytes, download locators,
  cookies, credentials, or raw provider responses. Normal per-item completion/cancellation cleans
  owned staging. Existing media-worker quarantine limitations remain explicit, not false success.

### Text composition, parsing, and token accounting

- Only completed relevant evidence enters final composition. It is text-only, using the same
  configuration; media is not uploaded again. Coverage comes from application counts, not LLM
  claims. No relevant items produces an explicit empty report without a composition request.
- Final evidence is limited to 120,000 characters. Preserve item analyses if final input/output
  fails. Output budgets are 2,048 tokens per analysis and 4,096 for composition, deadline 180s.
- Accept strict plain JSON or one exact whole-response JSON fence. Reject duplicate keys, NaN,
  extra prose, unknown fields, invalid enums and unknown/empty/repeated citations. Do not extract
  a plausible substring, repair semantics or make a hidden second call.
- Source IDs are original stored result IDs, never AI item IDs. Resolve them through frozen item
  sources; the model cannot supply links. XHS keeps the existing stored-result reopening action.
- Prompt content is untrusted source material. Do not execute its instructions, tools or links.
  Secret-bearing output is rejected with a constant code and is not retained or exposed.
- Usage is optional validated numeric metadata from a successfully completed stream. Preserve it
  when local JSON/schema validation subsequently fails. Unknown usage is not zero. Keep counts for
  attempted versus accounted requests; reused items contribute no historical tokens to new usage.
- Token integers are nonnegative JS-safe integers with input + output = total. Invalid usage
  metadata becomes unknown without weakening transport success checks. Sum known usage and mark
  partial accounting incomplete. If aggregation overflows the safe range, return null totals and
  `complete=false`, even if every individual request was accounted. Do not invent currency costs.

## 4. Validation & Error Matrix

| Boundary | Public result | Required behavior |
| --- | --- | --- |
| Bad request, UUID, query or extra field | `invalid_request` | No work; no echoed payload |
| Unknown run/version | `search_run_not_found` / `ai_summary_not_found` | No fallback to another run |
| Active source / empty / >100 sources | `ai_summary_source_active` / `ai_summary_empty_source` / `ai_summary_source_limit` | Reject before media/model |
| Stale configuration / different replay intent | Existing configuration error / `ai_summary_request_conflict` | Reconfirm; do not create a new intent automatically |
| Changed, partial, unavailable or unsupported input | Bounded acquisition/input failure on item | No fabricated unrelated judgment |
| Provider/JSON/schema/citation failure | Bounded stage/code/message | Preserve completed analyses and validated usage |
| Cancel / restart | `cancelled` / `interrupted` | Retain history; settle work; no automatic resumption |
| SQLite failure | `ai_summary_storage_unavailable` or saved storage failure | Transaction rollback, no partial accepted snapshot |

All declared summary success/error responses use `Cache-Control: no-store`, including local guard,
HTTP and request-validation errors; preserve other error headers. Mutations use the existing local
Host/Origin/JSON guard. Never return raw exception text, remote response bodies, secret references
or request headers.

## 5. Good / Base / Bad Cases

- Good: a second generation reuses relevant/irrelevant/uncertain analyses and only sends text for
  the new report. Incomplete items remain explicitly unresolved and can be acquired again.
- Base: one complete item is analysed once, then cited in a text report; both versions survive reload.
- Bad: analyse only the visible results page, classify unread media as irrelevant, let refresh start
  paid work, reuse stale evidence after known content changes, or treat a model claim as verified fact.

## 6. Tests Required

- Transport/analysis: complete SSE, strict and fenced JSON, credential redaction, media-byte bounds,
  citation membership, valid uncertainty, usage retention, and historical 21/100/101-term boundaries.
- Repository/service: additive v10→v11 migration, real transactional abort after the first child,
  full-run snapshots beyond one page and new/repeat filters, canonical reuse and known-change
  invalidation, stale source detection, force-refresh, cancellation at each stage, startup no-op
  requests, composition without browser ownership, and unknown/overflow usage.
- API: strict/local guards, revision-bound UUID replay, source limits, pagination and injected
  lifespan services. Frontend: independent strict decoder, code-point string bounds, 100 matched
  terms, immutable confirmation, pending/ambiguous retry states, history, cancellation, full-set
  citation resolution and XHS source opening.
- Isolated browser acceptance: no calls before confirmation/on reload, filtered view still uses
  the full run, mixed outcomes, reuse, old-version display, cancel, keyboard dismissal and console.
- Real acquired-media/provider acceptance is a separate explicit gate. Mock tests and tiny
  synthetic images do not establish model quality or complete five-platform media support.

## 7. Wrong vs Correct

```python
# Wrong: silently downgrade unread media and turn a failure into a semantic verdict.
return {"decision": "irrelevant", "reason": str(error)}

# Correct: keep failure separate; completed uncertain is a legitimate model judgment.
repository.finish_item(summary_id, item_id, "input_incomplete", error=bounded_failure)
```

```typescript
// Wrong: current pagination and freshly changed settings alter a confirmed operation.
startAISummary(runId, { result_ids: visibleRows, revision: currentSettings.revision })

// Correct: the server freezes the full run, bound to the displayed configuration/intent.
startAISummary(runId, {
  request_id: confirmedRequestId,
  force_refresh: confirmedRefresh,
  configuration_revision: confirmedSettings.revision,
})
```
