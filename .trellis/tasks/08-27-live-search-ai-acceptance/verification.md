# Actual Acceptance Progress — 2026-08-27

## Scope and Status

The user approved the final bounded plan, the scoped local-backend exception and subsequently
resolved the browser authorization blocker with “允许”. The bounded live checks are now finished;
task status remains `in_progress` for review/handoff, without archiving or committing.

**Mixed live results:** all five baseline searches succeeded; four combined searches succeeded,
while Toutiao returned `structure_changed`. Stable-identity deduplication is proven on 15 overlapping
Weibo/Douyin/Xiaohongshu results; Kuaishou returned a different set, so its repeat is inconclusive.
Saved-provider text connectivity passed once. No multimedia or per-post AI analysis was performed.
No product/submodule code changes, commit or push were performed.

## Passed: Backup, Migration and Production Startup

- Created one private local runtime backup using SQLite's backup mechanism before startup. Its
  integrity check was OK and schema version was 8. No credential files or runtime data were sent
  to Centaurus.
- Started the actual production FastAPI application (not a fake service) and its normal migration
  advanced the product schema to 9. Integrity is OK; foreign-key violation count is zero.
- Compared every pre-existing application table with the backup using bidirectional row-set
  differences. All 12 tables had zero missing and zero additional rows immediately after migration.
  Preserved counts: 1 rule, 5 object rows, 23 runs, 115 run terms, 92 contents, 144 run/content
  relations, 150 match relations, 3 batches, 15 batch terms, 9 batch items, 7 attempts, 1 AI row.
- The non-secret AI projection still showed key presence and revision 1 for the saved model.
- Frontend is running from Centaurus with a loopback-only frontend forward and API reverse-forward.
  Existing occupied remote ports were not stopped or reused. A refused occupied-port launch made no
  changes; the successful frontend uses its own dynamically assigned port.
- Product health is OK both directly and through the frontend proxy.

## Passed: Real Rule UI and Saved AI Text Request

- Used the real browser UI to create task-labelled rules **3** (baseline) and **4** (one object plus
  one issue keyword). The composed-query preview showed exactly one expected space-joined query;
  saved API projections preserved the two input groups. Existing rule 1 remained unchanged.
- Used the saved production AI service for exactly one `POST /api/v1/ai-settings/test` with revision
  1. HTTP **200**, `status=connected`, approximately **0.587 seconds**. No retry was made.
- The client sent only its fixed synthetic text prompt, not collected posts, images or video.
  Credentials were consumed by the service and were never read back or included in tool output.
  This proves current text connectivity only, not relevance judgment or multimedia understanding.

## Historical First Attempt: Browser Authorization Blocker

- Started **batch 4** from the real collection UI with the baseline rule, all five platforms and
  a five-result/query cap. The API stored one rule snapshot and executed platforms serially.
- First observed state: Toutiao run **27** running; the other four platforms queued.
- Chrome opened the native **“要允许远程调试吗？”** dialog. A read-only Computer Use accessibility
  inspection confirmed the request for full control of the Chrome session and its Allow/Cancel
  buttons. No permission, login or CAPTCHA was accepted automatically.
- Toutiao run 27 finished as **browser_unavailable**, with zero results. The existing batch state
  machine then advanced to Weibo run **28**, still waiting for the same browser authorization.
- Cancelled only this task's batch to avoid further unattended connection attempts. Final state:
  batch 4 **cancelled**; Toutiao **failed/browser_unavailable**; Weibo **cancelled**; Kuaishou,
  Douyin and Xiaohongshu **cancelled without a child attempt**. All result counts are zero.
- Post-cancellation native inspection still showed the authorization dialog. All **11** original
  Chrome tab IDs remained present. The application displayed truthful connection guidance rather
  than empty-search success, and its captured console had zero warnings/errors.
- Copy issue observed: the cancelled page also says **“已完成 5 / 5 个平台”**, because that counter
  counts terminal items including failures/cancellations. It is not five successful searches and
  may mislead the operator despite the cancelled header and individual outcomes. Record only;
  this verification task does not authorize a UI fix.
- At that stopping point, no combined search, repeat or original-result inspection had occurred.
  The subsequent authorized attempts are recorded below; batch 4 was not rewritten or continued.

## Authorized Live Search Comparison

- On resumption, no native approval dialog was present. No automatic permission click was needed,
  and no challenge was solved. Captured a fresh baseline of the two Chrome tabs then present;
  both IDs remained present at the end. The prior 11-tab snapshot belongs to the earlier attempt,
  not a claim that user-driven changes between turns were undone.
- Re-enabled only rules 3/4 and created fresh batches. Every run retained at most five results,
  with one query. All 14 new run snapshots match the expected rule query and five-result cap;
  recorded start/finish times confirm serial execution without overlap.

| Platform | Baseline batch 5: run, outcome, new/repeated | Combined batch 6: run, outcome, new/repeated |
| --- | --- | --- |
| Toutiao | 29, completed with 5 results, 4/1 | 34, `structure_changed`, 0/0 |
| Weibo | 30, completed with 5 results, 1/4 | 35, completed with 5 results, 5/0 |
| Kuaishou | 31, completed with 5 results, 2/3 | 36, completed with 5 results, 5/0 |
| Douyin | 32, completed with 5 results, 3/2 | 37, completed with 5 results, 5/0 |
| Xiaohongshu | 33, completed with 5 results, 2/3 | 38, completed with 5 results, 5/0 |

Baseline rule 3 sends `龙田街道`; combined rule 4 sends `龙田街道 投诉`. This is a space-joined
platform query, not guaranteed Boolean AND or a locality filter. Batch 5 completed; batch 6
completed with failures. Toutiao's combined failure was neither retried nor represented as an empty
success. Its exact underlying adapter failure has not been diagnosed by this verification task.

## Observed Search Quality and Public Originals

These are qualitative observations of five retained results per successful search, not recall or
precision measurements. Titles/snippets can be incomplete; no video's spoken or visual content
was analyzed. Allegations in a post are not independently verified facts or proof of an ongoing issue.

| Platform | Baseline observations | Combined observations |
| --- | --- | --- |
| Toutiao | Local football, development, ecology and festival news; mostly neutral/positive | No sample: `structure_changed` |
| Weibo | One local activity plus unrelated or insufficient-location material | Four very similar old local road-access complaints, plus neutral local community news |
| Kuaishou | Scenery, advertising and other locations | General complaint/rights advice; target locality usually unproven |
| Douyin | Some local clips and an old rescue report, mixed with other locations | Complaint-related snippets, but other cities or insufficient locality evidence |
| Xiaohongshu | Maps, schools and rentals | A namesake-town complaint and generic complaint advice; not reliably target-area issues |

Two representative originals were actually opened and checked:

1. [Weibo original](https://m.weibo.cn/detail/5008729703713273), global content **112**, run **35**:
   the rendered original explicitly names Shenzhen/Pingshan/Longtian/Laokeng and alleges blocked
   road and emergency-vehicle access. Its visible date is **2024-03-06**, not a new incident from
   this collection date. Three other similar complaint posts have distinct platform post IDs;
   record-level deduplication does not merge them into one event.
2. [Xiaohongshu canonical original](https://www.xiaohongshu.com/explore/68a926c7000000001d01a8c4),
   global content **126**, run **38**: the rendered complaint explicitly names **福清市龙田镇**,
   not Shenzhen's Longtian Street. The product's no-body original-open endpoint returned `opened`;
   no signed navigation URL or token is reproduced here. It is a concrete namesake false match.

Additional title/snippet evidence includes a Douyin local rescue post dated **2025-08-05**,
[canonical video](https://www.douyin.com/video/7534996258398768393); the video itself was not watched
or sent to a model. The time evidence illustrates that **newly inserted is not newly published**.

Adding `投诉` surfaces more complaint-related material in this small sample, but does not eliminate
wrong locations, generic tutorials, neutral posts or stale incidents. A simple complaint-keyword
search cannot by itself identify current, target-area public-opinion information.

## Live Repeat and Stable-Identity Deduplication

Batch **7** repeated only the four successful combined searches once, with the same query/cap.

| Platform | Repeat run | New / repeated | Stable-ID overlap with combined run | Conclusion |
| --- | --- | --- | --- | --- |
| Weibo | 39 | 0 / 5 | 5 with run 35 | Proven for these five contents |
| Kuaishou | 40 | 5 / 0 | 0 with run 36 | Inconclusive: returned a different set |
| Douyin | 41 | 0 / 5 | 5 with run 37 | Proven for these five contents |
| Xiaohongshu | 42 | 0 / 5 | 5 with run 38 | Proven for these five contents |

All 15 intersecting identities reused the same global content row, were marked `repeated`, retained
the original `first_seen_at`, and strictly advanced `last_seen_at`. No duplicate global
`(platform, platform_content_id)` exists. No third Kuaishou search was made to manufacture overlap.
Toutiao was ineligible for this repeat because its combined run failed.

The three finished batches stored **65 run/content observations** and added **37 global contents**
(92 before, 129 after). This is not 65 unique posts or 37 newly published events. Per-run first-pass
counts can already include repeats from earlier history.

## Final UI, Preservation and Handoff

- In the real Weibo repeat page `/collection-runs/39`, selecting **新增 0** showed the proper empty
  state; selecting **再次命中 5** showed five articles. Counts, dates, snapshot query and original
  links were visible. Captured application console: zero warnings/errors.
- Final database integrity: **OK**; foreign-key violations: **0**; active runs/batches: **0**.
  Every original row in the 11 non-content tables remains unchanged. Original content identities
  and first-seen timestamps remain intact; content metadata/last-seen can update on a rediscovery.
- Rules 3/4 were disabled again through normal full replacement with both input groups preserved;
  rule 1 remains enabled and unchanged. AI revision remains 1. The real AI test was not repeated.
- Keep the owned app/tunnel and result tabs available. Comparison: `/collection-batches/6`;
  repeat/deduplication: `/collection-batches/7`; baseline: `/collection-batches/5`. Failed/cancelled
  batch 4 is preserved. No database rollback or deletion was performed.
- Product gaps remain: Toutiao combined-search failure; misleading terminal-progress wording;
  namesake/neutral/stale-result filtering; no event-level merging. Media acquisition, per-result
  AI analysis and final summary generation remain unimplemented, so there is no full AI pipeline
  acceptance. Any fixes or new provider calls require separate direction.

## Owned Runtime Handles (For Narrow Cleanup/Resume)

- Local backend: process **66821**, exec session **17086**, loopback port **18000**.
- Centaurus frontend: exec session **8977**, loopback port **35985**.
- SSH forward: process **66922**, exec session **79203**; local **5173** to remote frontend, remote
  loopback **18000** to local backend. An earlier obsolete forward process was terminated by exact ID.
- In-app browser: owned tab **6**, showing the batch result. Two task-owned original-inspection
  tabs (Weibo and Xiaohongshu) are retained as deliverables; the latter was opened through the
  product and then claimed for rendered-page inspection. Neither was a pre-existing user tab.
- Backup remains in the task-owned ignored local runtime directory, not synchronized or committed.
- The system SQLite CLI also rejected a read-only post-run check; Python's `sqlite3` read-only
  connection completed the integrity/count/foreign-key checks successfully. Use that established
  read-only path for follow-up checks rather than changing database permissions or assuming damage.

## Later User-Approved Rule Cleanup — 2026-08-27

The earlier handoff above describes the pre-cleanup state. The user subsequently requested one
remaining rule group. Only acceptance rules 3/4 have now been deleted through the product API,
after a fresh private local backup. Original rule 1 and all 39 runs, 7 batches and 129 contents
remain. Full row comparisons of the nine search tables allow only the expected nulling of
deleted-rule references; snapshots, results and attempts did not change. Integrity is OK and
there are no foreign-key violations. No new platform/model request or product fix occurred.
Details and the still-unresolved Toutiao follow-up: `research/rule-cleanup-verification.md`.

## Authorized Clean-Slate Reset — 2026-08-31

This reset was explicitly authorized before any new acceptance run. The API and frontend were
stopped, no platform/model request was made, and the existing source/uncommitted edits were left
untouched. A second private backup was validated at
`runtime/e2e-reset.NjshhB/before-reset.sqlite3` (directory `0700`, database and sidecars `0600`;
the earlier backup was not overwritten).

The backup and live database were schema **15**, with `quick_check=ok`, `integrity_check=ok`, and
`foreign_key_check=0`. The live database was cleaned in one `BEGIN IMMEDIATE` transaction with
`PRAGMA foreign_keys=ON`, using child-before-parent deletion order. The exact pre-reset counts and
deleted counts were:

| Domain | Exact rows cleared by table | Total |
| --- | --- | ---: |
| Legacy AI summaries | `ai_summary_runs=6`, `ai_summary_items=30` | 36 |
| Collection/search | `search_batches=9`, `search_batch_terms=59`, `search_batch_items=38`, `search_batch_attempts=33`, `search_batch_recoveries=0`, `search_runs=54`, `search_run_terms=336`, `search_run_contents=763`, `search_run_content_terms=892`, `search_run_term_completions=237`, `search_contents=574` | 2,995 |
| Independent analysis | `content_analysis_jobs=0`, `content_analysis_requests=0`, `content_analysis_attempts=0`, `content_analysis_claims=574`, `analysis_completion_events=0`, `collection_analysis_handoffs=0` | 574 |
| Legacy schedules | `collection_schedules=0`, `collection_schedule_platforms=0`, `collection_occurrences=0` | 0 |
| Topic reports | `topic_report_runs=0`, `topic_report_requests=0`, `topic_report_sources=0`, `topic_report_nodes=0`, `topic_report_node_sources=0`, `topic_report_node_children=0` | 0 |
| Automation | `automation_tasks=0`, `automation_task_platforms=0`, `automation_task_contents=0`, `automation_runs=0`, `automation_run_contents=0`, `automation_stage_attempts=0`, `automation_occurrences=0`, `automation_requests=0` | 0 |

Only cleared-table sequence rows were reset: `ai_summary_items`, `ai_summary_runs`,
`search_batches`, `search_contents`, and `search_runs` (5 rows). Preserved-table sequence rows
and IDs were not touched.

The following preserved configuration projections were captured before reset and matched after
the committed transaction. Full-row SHA-256 values are included so secret material is not exposed:

- `monitoring_rules`: id **1**, name `龙田街道及四个社区`, enabled **1**;
  object terms in position order: `龙田街道`, `龙田社区`, `老坑社区`, `竹坑社区`, `南布社区`;
  issue terms in position order: `投诉`, `噪音扰民`, `环境污染`, `安全隐患`.
- `ai_settings`: id **1**, base URL `https://dashscope.aliyuncs.com/compatible-mode/v1`,
  model `qwen3.5-omni-plus`, revision **1**, credential present (reference value omitted).
- `analysis_settings`: id **1**, initial prompt version **1**, report prompt version **2**,
  enabled **0**, approved configuration revision `null`, revision **1**, activation content id
  **492**.
- `analysis_prompt_versions`: id **1** `initial` / `initial-understanding-v1` and id **2**
  `report` / `topic-report-v1`; raw instructions omitted, lengths **76/73**, content hashes
  retained in the row comparison.

| Preserved table | Rows | Full-row SHA-256 |
| --- | ---: | --- |
| `monitoring_rules` | 1 | `68c412e73b1837e057cf49dfe13382672dedecee520afc57045aa828740296ba` |
| `monitoring_rule_terms` | 5 | `ee3e056373f0d111ae7b9ed0956e7dae6fee8fb7f0242208ddf57e7d45e4d69e` |
| `monitoring_rule_issue_terms` | 4 | `d59027a60ea2d6fb14b4404eab36ec969d51e034fdc25c630d1524cb1c9f5200` |
| `ai_settings` | 1 | `4e93880625355da7a3076fdc63149490acc3ffcc443354dd3755326da3383e81` |
| `analysis_settings` | 1 | `1e0c7a104296508aba0484362573f726a6147c81ec596e032960cfa831f4732e` |
| `analysis_prompt_versions` | 2 | `3aa787593f31b3083b3551434612119ce9c033f24141794fa1060608716fdc2a` |

Post-reset validation reopened the committed database read-only and found schema **15**,
`quick_check=ok`, `integrity_check=ok`, `foreign_key_check=0`, zero rows in every listed
operational table, and byte/field-identical preserved rows. The AI credential store remained
present with one `0600` file; runtime platform-session and media directories were not deleted or
modified (media inventory was 0 files / 0 bytes). No product source file was changed by this
reset; pre-existing uncommitted product and submodule changes were preserved and are not
attributed to this acceptance.

## Current E2E Acceptance — 2026-08-31 (Blocked at Browser Authorization)

This is the first post-reset live acceptance attempt. The local API returned health **200** at
`http://127.0.0.1:18000/api/v1/health`; the frontend is available at
`http://127.0.0.1:5174/` and is served through a temporary loopback-only proxy on port 8000 because
the product Vite proxy defaults to 8000 while the API was intentionally started on 18000. The
unrelated process on port 5173 was not stopped or reused. Chrome CDP was listening on 127.0.0.1:9222.
No product source file was changed by this acceptance; pre-existing uncommitted product and
submodule changes were preserved and are not attributed to it.

### Bounded intent and durable IDs

- Created task-labelled monitoring rule **7**, enabled, with exactly one object term
  `深圳坪山龙田街道` and exactly two issue terms `投诉`, `安全隐患`. The two stored effective
  queries are `深圳坪山龙田街道 投诉` and `深圳坪山龙田街道 安全隐患`.
- Created automation task **1**, initially disabled, named `2026-08-31验收·龙田自动链路`, with
  catalog-order platforms `wb`, `ks`, `xhs`, `max_results_per_term=2`, and a dormant interval
  schedule of **43,200 minutes**. Its analysis goal was the user-approved text: “识别与深圳市坪山区龙田街道直接相关的公共服务投诉、安全隐患和居民诉求；排除其他地区同名龙田、广告和泛化教程；报告必须引用已采集来源，并区分事实陈述与网民主张。”
- One and only one manual admission was accepted: automation run **1**, request UUID
  `81fb1f75-a3a2-45f0-91fa-4dca09dc0a0c`, trigger `manual`, task revision **1**, snapshot AI
  revision **1**, prompt versions **1/2**. The bounded collection intent was at most 12
  platform-term observations.

### Stage evidence and blocker

| Stage / action | Result | Durable evidence |
| --- | --- | --- |
| Collection admission in run 1 | **Failed** | Run status `failed`; stage `collection=failed`, generic product error `stage_failed`; child kind/id `null`; input/success/failure `0/0/0`; elapsed about **11 ms**. No search batch, search run, or content row was created. |
| Initial analysis | **Cancelled** | Stage cancelled by workflow after collection failure; no child job, model usage, or analysis rows. |
| Topic report | **Cancelled** | Stage cancelled by workflow after collection failure; no report, source, citation, or model usage rows. |
| First automation external activity | **Stopped before platform search** | The fresh worker conservatively starts with `browser_session_available=false`; the API exposed CDP availability but no validated worker session. No LLM request occurred. |
| Authorized recovery check: `wb` | **Blocked** | Product connection attempt `6221cd00-8911-4f5b-b198-a761bd4896df` first reported `action_required` / `approve_connection`; the UI subsequently rendered “检查失败” and requested login in the current Google Chrome session. No approval, login, CAPTCHA, or manual action was performed. |
| `ks`, `xhs` checks and run retry | **Not run** | Stopped immediately at the first browser authorization blocker; no failed-stage retry was issued. |

The backend terminal emitted no traceback: `AutomationWorkflowService._execute_run` catches the
underlying exception and persists the fixed generic `stage_failed` message. The strongest
code-backed explanation is that `SearchBatchService._start_workflow_batch` refuses to create a
batch while `SearchRunService.browser_session_available` is false; the worker only changes that
flag after an explicit auth/search/manual-page/open-result event. Thus a fresh backend cannot
bootstrap the workflow from a bare CDP listener. This is an observed cold-start admission defect
plus a later observed browser authorization blocker, not a forced retry or a provider result.

### Acceptance matrix

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Local API and frontend startup | **PASS** | API 18000 healthy; UI 5174 healthy; temporary 8000→18000 loopback proxy; 5173 untouched. |
| Reset cleanliness and saved configuration | **PASS** | Post-reset operational lists were empty; saved AI/analysis projections were available (AI revision 1, prompt versions 1/2). |
| Query/rule/task snapshot fidelity | **PASS** | Rule 7 has the exact one-object/two-issue design; task 1 snapshot preserves both effective queries, platform order, cap 2, goal, and saved AI/prompt revisions. |
| Real social-media collection | **BLOCKED** | Run 1 stopped before batch creation because worker session evidence was cold; the only authorized `wb` recovery check then required browser approval/login. |
| Initial LLM analysis | **NOT REACHED** | No collected content and no content-analysis job/model usage. |
| Topic report and citations | **NOT REACHED** | No report/source/citation graph exists for run 1. |
| UI inspection | **PARTIAL** | `/platform-accounts` visibly shows the微博检查失败/login guidance; console snapshot had no warning/error entries. Automation-run detail/report UI cannot show downstream artifacts because none exist. |
| Cleanup/preservation after blocker | **DEFERRED** | Per explicit instruction, task 1, run 1, rule 7, and the worker/browser state are preserved for user action; rule 7 was not disabled and no retry was issued. |

Owned local handles remain available for user-directed continuation: backend exec session **17019**
(`127.0.0.1:18000`), frontend exec session **39284** (`127.0.0.1:5174`), temporary loopback
proxy exec session **29927** (`127.0.0.1:8000`), and the marked in-app browser page
`http://127.0.0.1:5174/platform-accounts`. No credential, cookie, raw provider payload, or model
response was recorded.

## Current E2E Continuation — 2026-08-31 (Login Confirmed; Terminal Partial)

The user subsequently confirmed that all five platform accounts were logged in and that Chrome
remote debugging was allowed. I reused the owned local services and did not create a new task,
rule, or run. The selected task remained bounded to wb -> ks -> xhs, two effective queries,
two results per query, and the saved AI configuration. Toutiao and Douyin were not checked.

### Runtime and connection recovery

- Backend: local API 127.0.0.1:18000, exec session 95704, reloader/server PIDs 37311/37376;
  /api/v1/health returned 200.
- Frontend: local Vite 127.0.0.1:5174, exec session 34085, PID 37476; the page returned 200.
  The unrelated process on 5173 remained untouched.
- Temporary local-only API proxy: 127.0.0.1:8000, exec session 54294, PID 37438. Its root
  path is not an application route (404); the frontend API requests through it succeeded.
  Chrome CDP remained on 127.0.0.1:9222, PID 33919.
- The product connection checks were performed once each, in task order:

| Platform | Check attempt | Result | Guidance / active attempt |
| --- | --- | --- | --- |
| Weibo | c962b7aa-12a8-4cf1-91ad-9e00fc093932 | connected | none / null |
| Kuaishou | aa3f0a4a-c9a5-4f85-9aa6-126a008920d9 | connected | none / null |
| Xiaohongshu | 944dc8a8-51ae-4ca1-a66e-c69a29dbefd4 | connected | none / null |

There was no login, permission, CAPTCHA, rate-limit, or manual-action blocker after the user's
confirmation. No platform connection check or provider call was issued after this table.

### One authorized recovery retry and stage outcome

The original failed run was reused exactly once. The failed-collection recovery request was
4679fdb3-ebfb-46cc-b7fc-ce8e0be50c10 with expected run revision 3; it returned HTTP 202 and did
not create another run. Run 1 then reached terminal failed, revision 7.

| Stage | Attempt / child | Result and durable counts |
| --- | --- | --- |
| Collection | attempt 2 / search_batch #1 | completed; input 10, success 10, failure 0 |
| Initial analysis | attempt 2 / content_analysis_job #1 | automation stage failed; input 10, success 0, failure 0; stage ended at 06:38:32.367714Z |
| Topic report | attempt 2 / no child | cancelled; no report was admitted |

Batch 1 completed in 06:38:22.525653Z–06:38:32.285882Z. Its three catalog-order search
children all completed with results: Weibo run 1 (2 new, 2/2 terms), Kuaishou run 2 (4 new,
2/2 terms), and Xiaohongshu run 3 (4 new, 2/2 terms). The retained set is 10 observations
(at most 12), with no failed batch item and no repeat on this fresh database.

The analysis job was created at 06:38:32.358005Z, started at 06:38:32.378187Z, and completed
at 06:38:53.533210Z, about 20 seconds after the automation stage had already marked itself
failed. Its final API counts were total=10, completed=0, input_incomplete=10, all other terminal
buckets 0; completion_event_id=1; usage was attempted_requests=0, accounted_requests=0,
prompt_tokens=0, completion_tokens=0, total_tokens=0. All ten items were attempted=false;
nine had the incomplete/unsafe media inventory error and one had an acquisition-failed error.
Consequently no LLM/provider model request occurred and no report was created.

### Code-backed automation timing defect

The persisted product error is the fixed generic stage_failed; no traceback was emitted because
the workflow catches and stores that generic error. The more specific cause is directly visible
in the current source:

1. services/content_analyses.py:48-81 has workflow_admit() return await self.create(payload).
2. schemas/content_analyses.py:214-217 defines that return as an AnalysisAdmission wrapper
   containing job, admitted_count, and already_active_count; the job status is nested.
3. services/automation_workflows.py:862-899 extracts child.job.id but passes the original
   wrapper as initial to _wait_child.
4. services/automation_workflows.py:1001-1025 enters its polling loop only while the top-level
   child.status is a live status. The wrapper has no top-level status, so the loop is skipped,
   status becomes None, and the automation stage is persisted as failed immediately.

The timestamps above match this sequence exactly: the automation initial-analysis attempt ended
at 06:38:32.367714Z, while job 1 finished at 06:38:53.533210Z. This is an observed generic
failure with a code-backed root cause, not a speculative provider failure. No source patch was
made during acceptance.

### Source quality and graph checks

The API returned 2, 4, and 4 stored results for search runs 1, 2, and 3. Representative
inspection found one directly relevant but stale Weibo road/blocked-emergency-access complaint
(https://m.weibo.cn/detail/5008729703713273, published 2024-03-06) and one neutral local
Pingshan/Longtian community article (https://m.weibo.cn/detail/5246622608918588, published
2025-12-22). Kuaishou samples included generic Shenzhen salary/marketing material
(https://www.kuaishou.com/short-video/3xk5p4d78xsws2q), a complaint from an unspecified
Shenzhen street (https://www.kuaishou.com/short-video/3x5w8yphewtmrt2), and other-locality
Pingshan/Maluan or Talent Park material. Xiaohongshu samples were generic complaint/tutorial or
insufficient-context posts, including
https://www.xiaohongshu.com/explore/6a4b59ca000000001702f46e. These are relevance observations
only; allegations were not treated as verified facts.

Read-only API/DB graph checks found:

- automation_task_contents and automation_run_contents each contain exactly 10 rows for task/run
  1; their content-ID sets are equal, positions are 0–9, and every ID resolves to one of the
  10 search_contents rows from batch 1.
- All 10 stored source rows retain one of the two frozen effective queries as matched_terms;
  search-run result counts, batch item counts, and run-content membership agree.
- The topic-report tables are all empty (topic_report_runs/sources/nodes/node_sources/
  node_children/requests=0), and topic_report_id is null. Therefore there are no report source
  IDs or citations to validate, and no report was manually created or bypassed.
- Post-reset acceptance-history counts are limited to the single task/run: three search runs,
  one batch, ten search contents, one analysis job, ten analysis attempts/claims, six stage
  attempts, and two automation request rows (run-now plus the one retry). No active workflow
  owner remains.

### UI, cleanup, and preservation

Using the in-app browser skill, I inspected:

- /automation-runs/1: collection attempt 2 and batch 1 show 10/10 success; initial analysis
  shows job 1, 0 saved, 10 unsuccessful, and model requests 0; report is cancelled.
- /results?job=1: all 10 task members are visibly marked content-incomplete, the first-analysis
  task shows processed 10/10 and saved 0, and the page says the task did not call the model.
- /platform-accounts: Weibo, Kuaishou, and Xiaohongshu visibly show logged in; unselected
  Douyin/Toutiao remain not checked. Browser console error/warning logs were empty on the
  inspected pages.

After all checks, rule 7 was disabled through the normal full-replacement API
PUT /api/v1/monitoring-rules/7; its name, one object term, two issue terms, and two effective
queries are unchanged, and the response reports enabled=false. Automation task 1 remains
disabled (revision=1); the task, run, batch, search results, analysis job, and failure history
were preserved for review. The original monitoring rule 1, its five object terms/four issue
terms, and saved AI/analysis/prompt configuration remain byte/field-identical to the reset
backup. Read-only post-cleanup reopen reported schema 15, quick_check=ok, integrity_check=ok,
and foreign_key_check=0.

### Final acceptance matrix

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Local API/frontend/CDP startup | **PASS** | API 18000, UI 5174, local proxy 8000, CDP 9222 healthy; 5173 untouched |
| Saved config and exact bounded intent | **PASS** | Rule/task snapshot has the requested terms, platforms, cap, goal, AI revision, and prompt versions |
| Connection readiness | **PASS** | wb/ks/xhs checks each connected, guidance none, no active attempt |
| Real social-media collection | **PASS** | One retry of run 1 produced batch 1 and 10/10 successful retained observations |
| Initial LLM analysis | **PARTIAL/FAIL** | Job 1 settled but all 10 inputs were incomplete/acquisition-failed; model requests/tokens 0; automation wrapper also failed before child completion |
| Topic report and citations | **NOT REACHED** | Report stage cancelled; report/source/citation graph is empty |
| UI and API consistency | **PASS/PARTIAL** | Run, batch, result, platform pages and graph agree; no console errors; final report view unavailable because report stage was not reached |
| Post-run cleanup and preservation | **PASS** | Rule 7 disabled only after checks; task/history preserved; schema/integrity/FK/config checks pass |

The complete current path is therefore collection-successful but not a valid end-to-end
LLM/report acceptance. The remaining blockers are the code-backed automation wait/admission bug
and the provider-side incomplete media acquisition observed on this run. No further retry,
provider/model test, login action, or report bypass was performed.
