# Child B HTTP and occurrence contract

Implementation contract, 2026-08-29. All paths have `/api/v1` prefix. Strict
JSON, JS-safe positive IDs/revisions, UTC ISO timestamps, no-store on every
response/error, and the existing local Host/Origin/JSON mutation guard apply.
No new prompt, schedule-name, provider, browser-control or model fields.

## HTTP

- `GET /collection-schedules?limit=50&before_id=N` ->
  `{schedules: Schedule[], next_before_id: number|null}`; limit 1–100, ID descending.
- `POST /collection-schedules` -> 201 `Schedule`. Exact payload:
  `{monitoring_rule_id, platforms, max_results_per_term, interval:{value,unit}}`.
  Result cap defaults to 10, otherwise 1–50. Rule ID is positive. Platforms are
  1–5 unique existing literals, returned in `toutiao,wb,ks,dy,xhs` catalog order.
  `value` is a strict integer 1–43200, `unit` is `minutes|hours`; normalized
  minutes must be 1–43200. New schedules ALWAYS start disabled.
- `GET /collection-schedules/{id}` -> `Schedule`.
- `PUT /collection-schedules/{id}` -> 200 `Schedule`. Full payload is the create
  payload plus required `{expected_revision, enabled}`. All fields required.
  `monitoring_rule_id` may be null only when disabling/retaining a deleted rule
  reference. Existing disabled/invalid rules may be saved while disabled;
  enabling requires a currently enabled rule with 1–20 effective terms.
- `GET /collection-schedules/{id}/occurrences?limit=50&before_id=N` ->
  `{occurrences: Occurrence[], next_before_id: number|null}`; limit 1–100,
  occurrence ID descending. Missing schedule is 404, empty history is 200.

`Schedule = {id, monitoring_rule_id:number|null, rule_name:string,
rule_state:"enabled"|"disabled"|"deleted"|"invalid", platforms:string[],
max_results_per_term:number, interval_minutes:number, enabled:boolean,
revision:number, anchor_at:string|null, next_due_at:string|null,
created_at:string, updated_at:string, latest_occurrence:Occurrence|null,
available:boolean}`.

The saved `rule_name` labels the configuration (no separate schedule name).
`rule_state` reads the current rule; immutable batch snapshots are authoritative
for actual execution. Every successful PUT increments configuration revision,
even a same-value save; timer ticks never increment it. Enabled saves reset
anchor to now and next due to now+interval; disabled saves clear both. Stale PUT
changes nothing. Disabling never cancels an already linked batch. `available`
is the application rollout gate, default false until parent C integration;
saved enabled is distinct from operational availability.

`Occurrence = {id, schedule_id, schedule_revision, due_at:string,
status:"claimed"|"dispatched"|"skipped"|"missed"|"interrupted",
reason:Reason|null, batch_id:number|null, batch_status:SearchBatchStatus|null,
missed_count:number, missed_until:string|null, created_at:string,
dispatched_at:string|null}`.

`Reason = "browser_operation_active"|"browser_unavailable"|
"monitoring_rule_not_found"|"monitoring_rule_disabled"|"invalid_monitoring_rule"|
"too_many_search_terms"|"schedule_changed"|"storage_unavailable"|
"dispatch_interrupted"|"offline"|"clock_jump"`.

- Claimed: no reason/batch/dispatched time. Dispatched: batch + dispatched time,
  no reason. This records admission, not collection success; `batch_status`
  exposes existing queued/running/manual-pause/terminal outcomes. Link directly
  to `/collection-batches/{batch_id}` for unchanged controls and results.
- Skipped: a bounded non-offline/non-clock/non-interrupted reason, no batch.
- Missed: reason offline/clock_jump, count >=1, `due_at` first missed and
  `missed_until` last missed inclusive; one bounded row represents the range.
- Interrupted: reason dispatch_interrupted; a linked but unlaunched batch may
  remain attached with its dispatched time and explicit paused recovery.
- Other statuses have missed_count=0 and missed_until=null. Batch ID/status and
  dispatched_at are either all present or all absent.

## Error pairs and exact messages

| HTTP | Code | Message |
| --- | --- | --- |
| 404 | collection_schedule_not_found | 未找到定时采集计划。 |
| 409 | collection_schedule_changed | 定时采集计划已更新，请刷新后重试。 |
| 422 | invalid_collection_interval | 采集间隔须为 1 至 43200 个整分钟（最多 30 天）。 |
| 422 | invalid_collection_schedule | 定时采集配置不正确，请检查监控规则和平台。 |
| 404 | monitoring_rule_not_found | 未找到该监控规则。 |
| 409 | monitoring_rule_disabled | 该监控规则已停用，请先启用后再采集。 |
| 422 | too_many_search_terms | 一次最多采集 20 个搜索词，请拆分监控规则后重试。 |
| 503 | collection_schedule_storage_unavailable | 定时采集数据暂时无法读取或保存，请稍后重试。 |
| 503 | collection_schedule_unavailable | 定时采集服务暂时不可用，请稍后重试。 |
| 422 | invalid_request | 请求内容不正确。 |
| 403 | ai_request_forbidden | 请从本机应用页面操作 AI 配置。 |
| 415 | ai_json_required | 请使用 JSON 提交 AI 配置。 |

The final two codes/messages reuse the existing mutation guard unchanged;
they do not imply a schedule performs AI work.

## Durable internal handoff

v13 adds schedules, ordered platforms and occurrences. Unique
`(schedule_id,schedule_revision,due_at)` plus a private unique dispatch UUID
protects claims. A short transaction claims/advances to a future anchor-aligned
time. Another short transaction inserts the EXISTING batch, its frozen terms
and platform items AND links its occurrence before any browser work. Replaying
a dispatch token reads the existing link; it never launches a second runner.
The existing batch coordinator is the only lease owner. Busy/manual-paused
owners are neither cancelled nor resumed. A no-I/O known-session flag gates
scheduled admission; unavailable sessions skip without launching the worker.

Startup marks unfinished dispatch claims interrupted and records one offline
range per overdue schedule, advancing next due without replay. Existing linked
batches retain their original restart/manual-recovery contract. A persisted
batch-start marker disambiguates linked-but-unlaunched dispatch from launched
work; either kind is never automatically replayed. A clock-injected UTC timer
uses monotonic waits; backward jumps cannot repeat keys, forward jumps produce
bounded missed ranges. Shutdown stops admissions and drains in-flight dispatch
before downstream and browser owners shut down.

A remains the only discovery and post-release analysis-handoff owner. Scheduler
code never calls initial analysis, an LLM or reports; ordinary batch completion
uses A's existing callback, once, after release, with unchanged suppression for
cancelled/manual-paused collections. No live schedules or model work is enabled.
