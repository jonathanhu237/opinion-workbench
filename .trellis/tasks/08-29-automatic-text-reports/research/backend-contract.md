# C report HTTP contract

Implementation boundary, 2026-08-29. Paths have `/api/v1` prefix. Strict JSON,
positive JS-safe IDs/revisions, nonnegative JS-safe counts, canonical UUIDv4,
UTC ISO timestamps, no-store on every response/error, existing local mutation
Host/Origin/JSON guards. Legacy summary APIs and all A/B payloads remain unchanged.

## Routes and requests

- `GET /topic-reports?limit=50&before_id=N&initial_job_id=N&result_id=N` returns
  `{reports: ReportRun[], next_before_id: number|null}` in descending ID order.
  Limit 1–100; all filters optional. `initial_job_id` finds the automatic report
  and its retry versions for the selected stage-one job. Empty means no report
  admitted yet, not permission for the UI to submit one. GET never consumes events.
- `GET /topic-reports/{id}` returns `ReportRun`.
- `GET /topic-reports/{id}/sources?limit=50&offset=0` returns
  `{items: ReportSource[],total,limit,offset}` in frozen position order.
- `GET /topic-reports/{id}/sections?limit=50&offset=0&kind=leaf|overview` returns
  `{sections: ReportSection[],total,limit,offset}` in `(level,position)` order.
  `kind` is optional; `total` describes the filtered section set. Limits 1–100.
- `GET /topic-reports/{id}/sections/{section_id}` returns `ReportSection`;
  section must belong to this report. This supports bounded root/child navigation.
- `POST /topic-reports` returns **202 ReportRun**, accepting exactly:
  `{request_id,configuration_revision,report_prompt_version_id,
  instructions_override:string|null,selection:{kind:"first_seen_interval",
  first_seen_from:string,first_seen_to:string}}`. Both endpoints are required UTC
  instants with `from < to`, and at most six fractional-second digits; finer
  precision is `422 invalid_request` (C only; A/B timestamps are unchanged).
  Membership is all results first entered in exact `[from,to)` UTC microseconds.
  Select the newest completed initial attempt matching the claim's known input
  fingerprint, independently of today's shared initial prompt. A later failed or
  active attempt does not invalidate that saved text if no newer input is known;
  a known changed fingerprint prevents old-success resurrection. Only when no
  compatible success exists is the latest attempt shown as unavailable. Verify
  claim/attempt/source/first-entry identity before any eligible-success fallback.
  No ID array/source-count cap, publication-time filter or stage-one admission.
- `POST /topic-reports/{id}/retry` returns **202 ReportRun**, accepting exactly
  `{request_id,expected_revision,configuration_revision,
  instructions_override:string|null}`. Requires a terminal parent. A new version
  copies the exact frozen membership/evidence; null preserves its report prompt,
  non-null freezes an override. The explicitly supplied current provider revision
  permits re-admission after provider changes; incompatible nodes are not reused.
- `POST /topic-reports/{id}/cancel` returns **200 ReportRun**, accepting exactly
  `{request_id,expected_revision}`. Requires an active report; settles owned work
  before returning. Cancel does not cancel stage one or any other version.

Every request field above is required, including nullable overrides. One UUID
binds exact action/target/payload, including expected revision. Replay returns its
existing report before checking today's provider/control revision. Changed intent
under the same UUID conflicts. No automatic mutation retries or new UUID after an
ambiguous response. A terminal parent can produce a compatible retry or a new
prompt version; neither overwrites history or saves shared prompt defaults.

Overrides preserve exact accepted nonblank UTF-8 text, 1–8000 Unicode codepoints,
no NUL/surrogates. Creating without override checks the displayed shared prompt
version; creating with override still checks that displayed version as admission
intent. Retry does not read or require the latest shared prompt.

## ReportRun

```text
{
 id, request_id:string|null,
 trigger:"automatic"|"interval"|"retry",
 initial_job_id:number|null, completion_event_id:number|null,
 parent_report_id:number|null,
 selection:{kind:"initial_job",job_id:number}
          |{kind:"first_seen_interval",first_seen_from:string,first_seen_to:string},
 status:"queued"|"judging"|"composing"|"completed"|"empty"|"failed"
        |"cancelled"|"interrupted"|"configuration_blocked",
 revision:number, configuration_revision:number, base_url:string, model:string,
 prompt:{version_id:number|null,origin:"shared"|"override",instructions:string,
         content_hash:string,schema_version:"topic-report-v1"},
 coverage:Coverage,
 nodes:{judgments:NodeCounts,composition:NodeCounts},
 usage:{judgment:Usage,composition:Usage,total:Usage},
 root_section_id:number|null,
 empty_reason:"no_ready_sources"|"no_relevant_sources"|null,
 queue_reason:"ai_operation_active"|null,
 recovery_reason:"backend_restart"|null,
 error:ReportFailure|null,
 created_at:string,started_at:string|null,finished_at:string|null
}
```

`revision` changes on accepted cancellation/terminal settlement, not every source
progress update. Active states have null finished time; terminal states have a
finished time. Completed has a validated root; empty has no root and one empty
reason. Other states have no root (validated sections remain inspectable drafts).
Terminal runs have zero coverage pending/judging and zero node queued/running.
Unfinished nodes settle as cancelled or interrupted, preserving completed drafts.
Only automatic originals have a completion-event ID and null request ID/parent;
retry inherits selection/initial-job identity but not the unique completion-event
link. Interval and retry carry their explicit request UUID.

`prompt.version_id` is the frozen shared version when `origin=shared`, otherwise
null. It is not a provider revision. Retry with null override preserves the entire
prompt projection. Default application availability becomes usable through C;
saved automation authorization and schedules remain disabled until explicit user
enablement. Report admission after normal explicit stage one does not depend on
collection-auto authorization.

`Coverage = {total,ready,unavailable,pending,judging,relevant,irrelevant,uncertain,
failed,cancelled,interrupted}`. `total=ready+unavailable`; ready equals the sum of
the eight remaining states. These are source counts, not incident counts.
Unavailable is an initial-evidence problem; failed is a technical text-judgment
failure, not irrelevant. Composition failures affect report/node state but do
not replace already saved relevance judgments.

`NodeCounts = {total,queued,running,completed,failed,cancelled,interrupted,reused}`.
Total is the sum of states excluding reused; reused is a subset of completed.
Composition nodes are planned progressively after judgments/child outputs; queued
counts are not a forecast of all future tree nodes.

`Usage` reuses A's uncapped usage shape:
`{attempted_requests,accounted_requests,complete,prompt_tokens:number|null,
completion_tokens:number|null,total_tokens:number|null}`. Validated known partial
usage is summed, unknown is not zero; safe-integer overflow gives null totals and
incomplete accounting. Zero attempts means zero totals/complete=true. No historical
tokens/requests are charged again for reused nodes. These fields cover stage two
only; A's job retains its own separate stage-one usage.

## ReportSource

```text
{position,source:AnalysisSource,first_seen_at:string,
 initial_attempt_id:number|null,initial_status:AttemptStatus|null,
 unavailable_reason:"not_analysed"|"legacy_only"|"in_progress"|"input_incomplete"
  |"unsupported"|"failed"|"cancelled"|"interrupted"|"stale_evidence"|null,
 state:"unavailable"|"pending"|"judging"|"relevant"|"irrelevant"|"uncertain"
      |"failed"|"cancelled"|"interrupted",
 judgment:{decision:"relevant"|"irrelevant"|"uncertain",reason:string}|null,
 judgment_node_id:number|null,error:SummaryFailure|null}
```

`AnalysisSource` is unchanged A's JS-safe source with original result ID, platform,
validated frozen URL and origin run. `AttemptStatus` is A's existing literal set.
Ready sources have a completed initial attempt and null unavailable reason; use
`GET /content-analyses/{initial_attempt_id}` for its immutable saved text/prompts
via the existing A job link. Unavailable sources never have a model judgment.
Semantic states have matching judgments; failures have no fabricated decision.
Relevance reason is nonblank UTF-8, 1–600 codepoints, no NUL.

## ReportSection

```text
{id,report_id,kind:"leaf"|"overview",position,level,
 status:"queued"|"running"|"completed"|"failed"|"cancelled"|"interrupted",
 source_count:number,
 document:{overview:string,items:[{text:string,source_ids:number[]}]}|null,
 overview_document:{overview:string,items:[{text:string,section_ids:number[]}]}|null,
 sources:[{position:number,source:AnalysisSource}],
 children:[{id:number,kind:"leaf"|"overview",position:number,level:number,
            source_count:number,overview:string}],
 attempted:boolean,usage:TokenUsage|null,reused_from_node_id:number|null,
 error:SummaryFailure|null}
```

Leaf level is zero; it has 1–8 frozen relevant sources and no children. A completed
leaf has document only: overview 1–2000, 1–16 items of text 1–2000; each citation
list has 1–8 distinct source IDs from this section; their union covers its sources.
Sources are present even in a failed/queued leaf, independent of current result
page. Original result ID is the citation identity; position+1 is its display number.

Overview level is positive, sources is empty, and children has 2–8 completed saved
child projections (a final singleton is carried without another node). A completed
overview has overview_document only, with the same prose/item bounds and 1–8
distinct supplied section IDs per paragraph. Children retain all leaf evidence;
root responses do not expand unbounded descendant sources. Follow child detail
links or paginated leaves. Model prose is rendered as text, never as HTML/URLs.

Only completed nodes have documents; other nodes may have a bounded error. Reused
nodes are completed, attempted=false, usage=null and reference a canonical original
node. New completed nodes are attempted=true, usage may be unknown. TokenUsage
reuses existing validated AIUsage. XHS opens only the frozen origin/result tuple;
other original links use the frozen validated URL. Engine logical keys never leak.

## Errors and saved failures

All errors have exactly `{detail:{code,message}}`:

| HTTP | Code | Message |
| --- | --- | --- |
| 404 | topic_report_not_found | 未找到该文本报告。 |
| 404 | topic_report_section_not_found | 未找到该报告章节。 |
| 409 | topic_report_changed | 报告状态已更新，请刷新后重试。 |
| 409 | topic_report_request_conflict | 请求标识已用于其他报告操作，请重新确认。 |
| 409 | topic_report_not_terminal | 报告仍在处理中，请先等待或取消。 |
| 409 | topic_report_not_active | 报告已结束，无需取消。 |
| 422 | invalid_report_interval | 请选择有效的首次入库时间范围。 |
| 422 | invalid_analysis_prompt | 提示词须为 1 至 8000 字的有效非空文本。 |
| 409 | analysis_prompt_changed | 提示词已更新，请刷新后重试。 |
| 503 | topic_report_storage_unavailable | 文本报告数据暂时无法读取或保存，请稍后重试。 |
| 503 | topic_report_unavailable | 文本报告服务暂时不可用，请稍后重试。 |

Reuse existing exact `invalid_request`422, `ai_request_forbidden`403,
`ai_json_required`415 and AI configuration/credential errors from A. Unexpected
storage/projection failures are constant503, not raw validation/SQLite details.
Source/node saved errors reuse `SummaryFailure` stage/code/message constants.
Run `ReportFailure` additionally allows exactly the existing AI codes
`ai_configuration_required`, `ai_configuration_changed`, `ai_credentials_unavailable`
and `ai_settings_storage_unavailable`, only with stage=`execution` and their exact
`AI_ERROR_CONTRACTS` messages. A/legacy failure schemas are unchanged. Runtime provider
changes produce configuration_blocked; startup recovery produces interrupted with
recovery_reason=backend_restart, never secretly runnable queued metadata. Explicit
retry is required after recovery. Busy AI lease stays queued with no paid attempt.
