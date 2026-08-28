# Child A HTTP and handoff contract

Implementation contract, 2026-08-29. All routes below have `/api/v1` prefix.
JSON request objects are strict (unknown fields and coercion rejected); all
responses/errors are `Cache-Control: no-store`. Mutations require the existing
local Host/Origin/JSON guard. IDs, revisions and counts are JS-safe integers.
Dates are UTC ISO strings. GET, prompt save and startup do not start AI work.

## Settings

- `GET /analysis-settings` -> `AnalysisSettings`.
- `PUT /analysis-settings/prompts/{stage}` (`initial|report`) with exactly
  `{expected_version_id, instructions}` -> `AnalysisSettings`.
  Instructions preserve exact accepted text, 1–8000 Unicode code points,
  nonblank, UTF-8, no NUL. A no-op preserves the version ID. Stale IDs conflict.
- `PUT /analysis-settings/automation` with exactly
  `{expected_revision, enabled, configuration_revision}` -> `AnalysisSettings`.
  `configuration_revision` is positive when enabling and null when disabling.
  Enabling binds to the current saved provider revision; no credential is returned.

`PromptVersion = {id, stage, instructions, content_hash, schema_version, created_at}`;
`schema_version` is `initial-understanding-v1` or `topic-report-v1`.
`AnalysisSettings = {initial_prompt: PromptVersion, report_prompt: PromptVersion,
automation: {enabled, revision, approved_configuration_revision: number|null,
activation_content_id: number, available: boolean}}`.
`available` is false in the default child-A application until parent integration
explicitly enables the complete workflow. Saved authorization alone does not
activate incomplete rollout behavior. The UI must label that distinction.

## Shared results

- `GET /results?limit=50&offset=0&platform=...&state=...&first_seen_from=...&first_seen_to=...`
  -> `{items: Result[], total, limit, offset, eligible_count, active_count}`.
  `limit` 1–100; optional half-open UTC first-entry interval. Counts `eligible_count`
  and `active_count` describe the whole library, not the current filters/page.
- `GET /results/{id}` -> `Result`.
- `GET /results/{id}/origins?limit=50&offset=0` ->
  `{items: Origin[], total, limit, offset}`.
- `GET /results/{id}/analyses?limit=50&offset=0` -> attempt page below.
- `GET /results/{id}/legacy-analyses?limit=50&offset=0` ->
  `{items: [{summary_id,source_run_id,item_id,status,decision,reused_from_item_id}],total,limit,offset}`.
  Old summary detail/item endpoints retain their existing JSON contract.

`Result = {id, source: Source, first_seen_at, last_seen_at, origin_count,
analysis_state, latest_attempt_id: number|null, active_job_id: number|null,
legacy_count}`.
`Source` is the existing strict `SummarySource`: `{source_run_id,result_id,
platform,platform_content_id,content_type,title,snippet,content_url,
published_at_text,matched_terms}`. Origin selection is the oldest valid origin
by run ID, with inactive origins preferred; never use a caller-supplied URL.
`Origin = {source_run_id, rule_name, status, discovery_kind, matched_terms,
first_observed_at,last_observed_at}`. `status` uses existing search-run statuses.
`analysis_state` is `never_started|pending_new|queued|acquiring|analysing|completed|
input_incomplete|unsupported|failed|cancelled|interrupted|legacy_completed|legacy_attempted`.
Legacy markers never certify new-stage completion and remain outside bulk.

## Initial analysis

- `POST /content-analysis-jobs` -> HTTP 202
  `{job: Job|null, admitted_count, already_active_count}`.
  Request is exactly `{request_id, configuration_revision,
  initial_prompt_version_id, report_prompt_version_id, force_refresh, selection}`.
  `request_id` is a canonical lowercase UUIDv4. Reusing it with exactly the same
  intent returns the stored admission, including zero-result no-ops; changed
  intent conflicts. `force_refresh` is boolean. `selection` is one of:
  `{kind:"all_never_started"}`, `{kind:"explicit",result_ids:number[]}`,
  `{kind:"retry",result_ids:number[]}`, `{kind:"reanalysis",result_ids:number[]}`.
  Explicit arrays contain 1–1000 unique positive IDs. The all action has NO cap,
  page/interval dependence or request-body ID array. Retry/reanalysis are separate
  intents; explicit is first analysis only. Active sources are left under their
  existing job/legacy owner. New arrivals cannot extend an admitted job.
- `GET /content-analysis-jobs?limit=20&before_id=N` ->
  `{jobs: Job[],next_before_id:number|null}` (limit 1–100).
- `GET /content-analysis-jobs/{id}` -> `Job`.
- `GET /content-analysis-jobs/{id}/items?limit=50&offset=0` ->
  `{items: Attempt[],total,limit,offset}` (limit 1–100).
- `GET /content-analyses/{id}` -> `Attempt`.
- `POST /content-analysis-jobs/{id}/cancel` with exactly `{}` -> settled `Job`.

`Job = {id,request_id:string|null,trigger:"manual"|"automatic",
status:"queued"|"running"|"completed"|"cancelled"|"interrupted"|"configuration_blocked",
configuration_revision,base_url,model,initial_prompt:PromptVersion,
report_prompt:PromptVersion,force_refresh,counts:Counts,usage:Usage,
queue_reason:"ai_operation_active"|"browser_operation_active"|null,
completion_event_id:number|null,created_at,started_at:string|null,finished_at:string|null}`.
`Counts = {total,queued,acquiring,analysing,completed,input_incomplete,
unsupported,failed,cancelled,interrupted,reused}`. Status counts sum to total;
reused is a subset of completed. Completed means all members settled, not all
succeeded. Cancelled/interrupted/configuration-blocked jobs have no completion event.

`Attempt = {id,job_id,position,source:Source,first_seen_at,status,
output:Understanding|null,input:SavedInput|null,input_fingerprint:string|null,
reused_from_attempt_id:number|null,attempted:boolean,usage:TokenUsage|null,
error:SummaryFailure|null,created_at,started_at:string|null,finished_at:string|null}`.
The shared saved-input schema owner is `backend/src/longtian_api/schemas/analysis_evidence.py`.
Attempt statuses are `queued|acquiring|analysing|completed|input_incomplete|
unsupported|failed|cancelled|interrupted`. `SavedInput`, `TokenUsage` and bounded
`SummaryFailure` retain the existing backend schema; saved input contains full
accepted text/coverage/media metadata, never blobs, locators or credentials.
`Understanding = {summary,location_clues:[{excerpt,modality}],time_context,
media_observations:[string],uncertainties}`. Summary 1–1500 code points;
0–12 clues with 1–200 excerpt and `text|image|video|audio` modality; time_context
1–500; 0–12 media observations of 1–400; uncertainties 1–500; combined prose <=6000.
There is deliberately no stage-one relevance verdict.
`Usage = {attempted_requests,accounted_requests,complete,prompt_tokens:number|null,
completion_tokens:number|null,total_tokens:number|null}`. Unknown is not zero;
reuse adds no requests or historical tokens. Counts have no legacy 101 cap.

## Errors

Constant `{detail:{code,message}}` envelopes. Existing AI codes/statuses stay
unchanged. Child A adds:

| HTTP | Code | Message |
| --- | --- | --- |
| 404 | result_not_found | 未找到采集内容。 |
| 404 | content_analysis_not_found | 未找到初步分析记录。 |
| 409 | analysis_prompt_changed | 提示词已更新，请刷新后重试。 |
| 409 | analysis_policy_changed | 自动分析设置已更新，请刷新后重试。 |
| 409 | content_analysis_request_conflict | 此请求标识已用于其他分析操作。 |
| 409 | content_analysis_selection_conflict | 所选内容状态已变化，请刷新并使用对应的重试或重新分析操作。 |
| 422 | invalid_analysis_prompt | 提示词须为 1 至 8000 字的有效非空文本。 |
| 422 | invalid_result_interval | 首次采集时间范围不正确。 |
| 503 | analysis_storage_unavailable | 暂时无法读取或保存分析数据，请稍后重试。 |
| 503 | content_analysis_unavailable | 初步分析服务暂时不可用，请稍后重试。 |

## B/C durable handoff

Discovery claim registration is part of the new global result + origin transaction.
Collection terminal handoff runs only after the existing browser owner releases;
batch children do not independently trigger jobs. Cancelled/paused collections
do not trigger automatic admissions. Default feature activation stays off.
Only proved new, never-attempted markers enter automatic backlog; history and
interrupted/failed attempts are never swept. Normally settled jobs write a
unique `analysis_completion_events.job_id` event in the settlement transaction.
C consumes immutable attempt membership/output and job prompt/provider intent;
it must not join mutable current content or make report success a stage-one gate.
Repository `completion_events(after_id=0, limit=100)` exposes paginated immutable
event records for C; successful IDs and unsuccessful coverage are derived from
the already terminal frozen attempts in the same read snapshot.

Internal event shape is `{id, job: AnalysisJob, settled_at: datetime,
state: "pending"|"consumed", successful_attempt_ids: list[int]}`. C owns its
independent report admission/consumption transaction; A never runs report work.
An ordinary later collection completion can recover a new candidate whose
collector committed its terminal state before a process crash skipped the
handoff. This recovery still excludes cancelled/paused origins, old history and
already attempted content. Startup performs only interruption reconciliation.
A queued provider-revision mismatch settles remaining members as interrupted,
releases all job claims, retains any successes, and sets the job to
`configuration_blocked` without a completion event. Explicit recovery is required.
