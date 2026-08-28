# Manual summary API — frozen coordination contract

2026-08-28. Backend/public owner: `schemas/ai_summaries.py`. All routes below use
`/api/v1`; reads never initiate work. Model prose is escaped text, not HTML/links.

## Routes

- `POST /search-runs/{source_run_id}/ai-summaries` → 202 `SummaryRun`.
  Exact JSON `{request_id: UUID-v4 string, force_refresh: boolean,
  configuration_revision: positive integer}`. Bind the revision to the saved
  destination/model shown in the confirmation. Same UUID+run+force+revision replays
  the existing version (even terminal); any mismatch is 409. No silent config refresh.
- `GET /search-runs/{source_run_id}/ai-summaries?limit=20&before_id=N` →
  `{summaries: SummaryRun[], next_before_id: integer|null}` descending ID; limit1..50.
- `GET /ai-summaries/{id}` → `SummaryRun`.
- `GET /ai-summaries/{id}/items?limit=50&offset=0` →
  `{items: SummaryItem[], total: integer, limit: integer, offset: integer}` ordered
  source snapshot position; limit1..100. All items may be read, not just relevant.
- `POST /ai-summaries/{id}/cancel`, exact JSON `{}` → 200 `SummaryRun` after owned
  work settles. Terminal cancellation is idempotent and returns unchanged state.

POSTs reuse the local Host/Origin/JSON mutation gate. All responses are no-store.
IDs fit signed64; counts are nonnegative integers; timestamps are UTC ISO8601.

## SummaryRun (exact fields)

```
id, request_id, source_run_id, platform, source_run_status,
rule_name, terms: string[], configuration_revision, base_url, model, force_refresh,
status: queued|running|completed|failed|cancelled|interrupted,
phase: analysing|summarising,
counts: SummaryCounts, usage: SummaryUsage,
document: {overview: string, items: {text: string, source_ids: integer[]}[]}|null,
error: SummaryFailure|null,
created_at, started_at: timestamp|null, finished_at: timestamp|null
```

`source_run_status` is the existing SearchRunStatus frozen at admission; queued and
running sources are rejected. `platform` uses the existing five-platform union.
`terms` and `rule_name` are historical run values, not today's edited rule. `total`
is the entire unique stored run (1..100), independent of UI pagination/new filter.
Active/paused parent batches reject admission. Each version remains immutable in
scope after collection recovery. `completed` has a document (possibly empty items
and an explicit no-relevant-content overview); other states have document null.
Only queued/running have null finished_at; queued has null started_at. A failed
version can retain many successful item analyses. Phase records the last stage.

SummaryCounts exact fields:
`total, pending, analysing, relevant, irrelevant, uncertain, input_incomplete,
failed, cancelled, interrupted, reused`.
Total equals pending+analysing+the seven terminal categories. Reused is a subset of
relevant+irrelevant+uncertain, never an additional category. Terminal runs have zero
pending/analysing. No result is reclassified as irrelevant because input/API failed.

SummaryUsage exact fields:
`attempted_requests, accounted_requests, complete, prompt_tokens, completion_tokens,
total_tokens`. Only **new attempts in this version**, including composition, count.
Normally complete = accounted_requests == attempted_requests. If the summed token
total exceeds JavaScript's safe integer limit (2**53-1), all aggregate token fields
are null and complete=false even when every individual attempt is accounted; exact
bounded individual usage remains readable. Token values sum validated
known accounting only. They are null if attempts exist but none have valid usage;
partial sums have complete=false. With zero attempts all three token totals are0
and complete=true (known no requests). No currency estimate. A reused item makes
no attempt and contributes no historical token counts.

## SummaryItem (exact fields)

```
id, summary_run_id, position,
source: {
  source_run_id, result_id, platform, platform_content_id, content_type,
  title, snippet, content_url, published_at_text, matched_terms: string[]
},
status: pending|analysing|completed|input_incomplete|failed|cancelled|interrupted,
decision: relevant|irrelevant|uncertain|null,
reason: string|null, evidence_summary: string|null,
reused_from_item_id: integer|null,
attempted: boolean, usage: TokenUsage|null,
input_status: ready|partial|unavailable|unsupported|null,
input_issues: string[],
error: SummaryFailure|null,
started_at: timestamp|null, finished_at: timestamp|null
```

`completed` has all three analysis fields; other states have all three null. Reuse
points directly to one canonical completed prior item, never chains; attempted=false
and usage=null. Other completed items have attempted=true. Source fields are the
immutable admission observation, not subsequently enriched text or global-row changes.
Text/full media metadata are stored internally, no file handles/paths or bytes exposed.
`input_issues` are closed normalized media issue codes (schema literal, not arbitrary
provider text). `input_status=null` means no normalized acquisition result yet.

TokenUsage exact standard fields: `prompt_tokens, completion_tokens, total_tokens`
and nullable `prompt_tokens_details, completion_tokens_details`. Each detail object
contains only optional integer `text_tokens,image_tokens,video_tokens,audio_tokens,
cached_tokens`; missing details are not inferred. Total=input+output. A new request
without usable accounting has attempted=true, usage=null, not zero usage.

Summary citation `source_ids` are **result_id**, not summary item IDs. Every citation
belongs to a relevant completed item in this frozen version. Resolve titles/links
from SummaryItem.source; XHS uses the existing `/search-runs/{source_run_id}/results/
{result_id}/open` mutation. Never navigate model-produced URLs. Page through items
if necessary; max100 makes one limit100 request sufficient for citation resolution.

## Public errors

Envelope is exactly `{detail:{code,message}}`. Structural failures are422
`invalid_request` / `请求内容不正确。`. Existing AI errors retain their exact
status+message from `services/ai_errors.py`, including409 configuration_required,
configuration_changed,operation_active and503 credential/settings failures;
local gate errors remain403 ai_request_forbidden /415 ai_json_required.

New exact errors:

| HTTP | Code | Message |
| --- | --- | --- |
|404|search_run_not_found|采集任务不存在。|
|404|ai_summary_not_found|汇总记录不存在。|
|409|ai_summary_source_active|采集任务尚未结束，请结束后再生成汇总。|
|409|ai_summary_request_conflict|此请求已用于其他汇总，请刷新后重试。|
|409|browser_operation_active|浏览器正在执行其他操作，请结束后再试。|
|422|ai_summary_empty_source|采集任务没有结果，暂时无法生成汇总。|
|422|ai_summary_source_limit|一次最多汇总 100 条内容，请缩小采集范围。|
|503|ai_summary_storage_unavailable|汇总记录暂时无法读取或保存，请稍后重试。|
|503|ai_summary_unavailable|汇总服务暂时不可用，请稍后重试。|

Operational failures appear in the durable item/run, not as a polling HTTP failure.
SummaryFailure exact `{stage,code,message}` uses stage
`acquisition|input|analysis|composition|execution`. Codes/messages are centralized in
backend schema/service; UI can display the validated constant message. Closed codes:
`input_incomplete,source_changed,source_active,browser_operation_active,
acquisition_failed,invalid_enrichment,unsupported_model,request_too_large,
invalid_json,invalid_schema,invalid_citations,credential_leakage,
ai_destination_forbidden,ai_authentication_failed,ai_model_not_found,ai_rate_limited,
ai_provider_unavailable,ai_timeout,ai_invalid_response,ai_unsupported_input,
ai_request_too_large,cancelled,interrupted,internal_error,storage_unavailable`.
No raw exceptions/model answers, browser credentials or file paths are public/stored.
