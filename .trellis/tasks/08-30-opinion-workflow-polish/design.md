# Unified Opinion Automation Design

Status: planning review. The PRD is authoritative for product behavior. This design replaces automatic control flow while reusing the existing collector, initial-understanding and topic-report engines.

## 1. Architectural decision

Introduce one fixed-purpose `AutomationWorkflowService`; do not build a generic workflow engine.

```text
Automation task + schedule
          |
          v
 durable occurrence / run snapshot
          |
          v
 AutomationWorkflowService (only automatic progression owner)
          |
          +--> SearchBatchService ---------> saved collection batch/results
          |
          +--> ContentAnalysisService -----> immutable generic understandings
          |
          +--> TopicReportService ----------> task-goal judgments/report
          |
          v
 unified run outcome + workbench/read model
```

The three domain services still own their work, resource leases, errors and saved outputs. They must not call one another. Their terminal notifications only wake the workflow service; the workflow service rereads committed state before advancing. A missed in-memory notification is harmless because startup and periodic reconciliation use durable child IDs and statuses.

This task remains one integrated Trellis implementation rather than parallel backend/frontend child tasks. Database versioning, FastAPI lifespan wiring, API types, frontend decoders and the removal of the old automatic path share the same contracts and must change in a controlled sequence. The implementation plan nevertheless creates explicit backend, integration and frontend review gates.

## 2. Domain model

Use the next schema version after rechecking `Database.LATEST_SCHEMA_VERSION` at implementation time. New tables follow the repository's connection-per-operation and explicit transaction rules.

### `automation_tasks`

Owns editable future intent, not execution history.

- `id`, `name`, `normalized_name`, `monitoring_rule_id`, `analysis_goal`
- schedule discriminator: `interval` or `daily`
- interval shape: `interval_minutes`; daily shape: `daily_time` + IANA `timezone`
- `enabled`, `revision`, `next_due_at`, `created_at`, `updated_at`
- child `automation_task_platforms(task_id, position, platform)`

The row CHECK requires exactly one schedule shape. New rows are disabled. Enabling validates an enabled/executable rule, supported platforms, result cap, saved AI configuration and schedule. Deleting or disabling a referenced rule makes the task visibly blocked; it does not rewrite historical run snapshots.

### `automation_occurrences`

Audits scheduled time decisions independently of accepted runs.

- unique `(task_id, task_revision, due_at)`
- `status`: `claimed | admitted | skipped | missed | interrupted`
- bounded reason including `previous_run_active`, invalid/disabled rule, configuration unavailable, offline, clock jump, storage or dispatch interruption
- optional `run_id`, missed count/range and timestamps

Repeated timer checks cannot admit twice. A claimed occurrence with uncertain dispatch becomes interrupted, never silently retried.

### `automation_runs`

One accepted scheduled or manual intent.

- unique `admission_key`; trigger `scheduled | manual`
- `task_id`, frozen task revision and immutable `snapshot_json`
- state `queued | collecting | analysing | reporting | completed | failed | cancelled | interrupted | configuration_blocked`
- active stage, revision, cancellation flag, final outcome, error and timestamps
- optional linked final `topic_report_id`; `no_new_sources` is a valid zero-model final outcome

`snapshot_json` contains the exact rule name/ordered terms, platforms, result cap, analysis goal/hash, AI configuration identity/revision, application-owned stage-template versions, schedule/timezone context and admitted time. It never contains credentials.

### `automation_stage_attempts`

Append-only attempts for fixed stages `collection | initial_analysis | topic_report`.

- unique `(run_id, stage, attempt_number)` and unique `operation_key`
- state `queued | running | completed | failed | cancelled | interrupted | configuration_blocked`
- child kind/ID, frozen input/output hashes, error and timestamps
- terminal attempts are immutable; a retry appends an attempt

The operation key is persisted before child admission. Each child admission accepts that idempotency key, so a crash between child creation and link persistence can recover the same child instead of duplicating browser/model work.

### `automation_task_contents`

Defines “new to this task,” independent of global content identity.

- unique `(task_id, content_id)`
- `first_run_id`, first collection run/result provenance and `first_seen_at`

After a successful collection stage, one transaction reads its stable batch membership and inserts task/content rows. Rows actually inserted by this run are its fixed initial-analysis membership. Existing rows are repeated for this task. Task A and task B may each own a first-membership row for the same global content.

### Idempotent mutation requests

Persist UUIDv4 intent hashes for `run-now`, `cancel` and `retry`. Identical replay returns the original result; reuse with changed action, target, observed revision or payload is a 409 conflict. Frontend ambiguous network failures retain the UUID and confirmed intent.

## 3. State and progression contracts

The stage order is an application constant, not stored as a user-editable graph.

```text
queued -> collecting -> analysing -> reporting -> completed
                    \             \            \
                     failed / interrupted / configuration_blocked

active state --cancel--> cancelled
terminal retryable state --retry--> append failed-stage attempt, resume same run
```

### Admission and global queue

- The scheduler may admit runs for different tasks durably. The workflow runner advances them in deterministic ID order and relies on existing browser/AI ownership for actual exclusivity.
- The same task cannot admit another run while one is queued or active. A scheduled collision becomes a skipped occurrence; `run-now` returns a conflict.
- Reads, polling, startup and route entry never admit work.

### Reconciliation

- Before launching a child, persist the stage attempt and operation key.
- After receiving a callback/wakeup, reread the linked child in one consistent database snapshot and only then settle/advance the stage.
- Startup does no browser or model work. It reconciles uncertain active attempts to `interrupted` unless a linked child has a trustworthy committed terminal result. The user then explicitly retries.
- Never hold a SQLite transaction across browser, network or model work. Cancellation drains owned database writes before releasing a resource.

### Retry

Find the first fixed stage without a successful attempt.

- Collection failed: admit a new batch using the original snapshot. Previously saved global results remain; task membership is frozen only from a successful attempt, so repeated global results can still become new-to-task inputs.
- Initial analysis failed at the job level: reuse the successful collection and previously successful compatible item understandings; admit only unresolved members. The stage output is the union of valid successes across its attempts plus the final unavailable set.
- Report failed: create a new report version from the workflow's frozen source/evidence snapshot. It performs no collection, acquisition, media upload or initial-understanding call.
- A changed/unavailable frozen provider revision is not silently substituted. The run remains configuration-blocked; a new run is required if the original provider intent cannot be restored.

Member-level incomplete/unsupported/failed results do not make an otherwise settled initial-analysis job a failed workflow stage. They remain unavailable coverage and reporting proceeds after all members are terminal.

### Cancellation

Set the workflow cancellation flag first, then call the linked child owner's existing cancel boundary. Do not launch downstream stages after cancellation. Preserve all child history and task-content membership already committed by successful stages.

## 4. Scheduling

Reuse the injected UTC clock and monotonic timer pattern from `CollectionScheduleService`, moving it under the workflow owner.

- Interval plans compute a future due time from the explicit enable/edit anchor.
- Daily plans store `HH:MM` and an IANA zone, then materialize `next_due_at` in UTC. For a DST gap, use the first valid instant after the requested local time; for a repeated wall time, execute once at the earlier occurrence. Tests use zones with both transitions even though the default product zone is Asia/Shanghai.
- Startup and forward clock jumps summarize missed due times and advance to one future due time; they do not create catch-up runs.
- A backward clock jump cannot repeat the unique occurrence key.
- `run-now` uses a separate request key and does not change the anchor or `next_due_at`.

## 5. Stage adapters and reuse

### Collection

Add a workflow admission method to `SearchBatchService` using the saved operation key and frozen rule/platform/count snapshot. Preserve serial platform execution, manual verification pauses, batch recovery, source deduplication and collection status. Remove the old schedule occurrence ownership from the product API after workflow acceptance.

### Initial analysis

Remove automatic admission from `SearchRunService`/`SearchBatchService` completion callbacks. Add an internal workflow admission that accepts server-selected content membership and a stable operation key. It reuses the existing acquisition, media validation, content-understanding parser, claims, attempts and usage accounting.

Automatic workflow stage one uses an application-owned generic-understanding template version. Existing independent manual analysis/history may remain available, but it cannot auto-create a report. Compatibility depends on input fingerprint, generic template/schema, extractor and provider intent; task analysis goal is deliberately excluded from stage-one cache identity.

### Topic report

Remove `ContentAnalysisService.on_job_finished = TopicReportService.initial_analysis_finished`. Add explicit workflow report admission from the workflow's frozen membership and the union of successful initial-analysis attempts. Extend the report selection/provenance model to link a report version to one workflow run and frozen task goal.

The existing report engine still owns one judgment per ready source, relevant-only bounded leaf/overview composition, citation validation, usage and retryable versions. Extend the empty outcome with `no_new_sources`, which creates no judgment or composition nodes. A task goal is stored as immutable goal text/hash plus an app template version; it is not a raw system-prompt editor.

Old `analysis_completion_events` and collection handoff rows may remain as inert historical storage if removing them would require destructive unrelated rewrites. No runtime service consumes them to advance automatic work. Replacement is proven by router/lifespan/callback tests, not by requiring every obsolete table to disappear.

## 6. API contracts

All routes live under `/api/v1`, use strict Pydantic models, local mutation guards, no-store responses, stable Chinese errors and positive JS-safe IDs.

```text
GET    /automation-tasks
POST   /automation-tasks
GET    /automation-tasks/{id}
PUT    /automation-tasks/{id}
GET    /automation-tasks/{id}/occurrences
GET    /automation-tasks/{id}/runs
POST   /automation-tasks/{id}/run-now

GET    /automation-runs/{id}
POST   /automation-runs/{id}/cancel
POST   /automation-runs/{id}/retry
```

Task PUT is full replacement with `expected_revision`. Mutations require UUIDv4 request IDs where replay ambiguity matters. Run projections contain a fixed three-stage array generated by the backend, never accepted from clients. Child links are typed deep links, not raw database payloads.

Representative stable errors include task/run not found, task changed, task name conflict, invalid schedule/timezone/goal, disabled or invalid rule, run already active, run not retryable, run not active, request conflict, AI configuration unavailable/changed, storage unavailable and workflow unavailable.

## 7. Frontend experience

Replace the “定时采集” primary route with “自动任务”; do not add another competing navigation item.

### Task list and editor

- Each card shows enabled state, rule, platforms, concise analysis goal, plan, next run and latest outcome.
- Primary actions are `立即运行`, `查看运行`; enable/disable and edit are secondary explicit mutations.
- The editor exposes business fields only. The fixed pipeline is shown as read-only explanatory text, not disabled controls that imply future editability.
- Schedule uses an explicit `固定间隔 / 每天固定时间` choice with visible timezone and a computed next-run preview.
- Submit, enable, run-now, cancel and retry show pending and terminal feedback; ambiguous requests keep their request ID and confirmation state.

### Run detail

- A semantic ordered timeline shows `采集`, `初步分析`, `相关性判断与报告` with text/icon/status; color is supplementary.
- The current transition uses one contextual `role=status` update; errors use `role=alert`. Polling must not move focus or cause layout jumps.
- Each stage exposes start/end, counts, saved child link, usage and bounded failure guidance. Only the first failed stage exposes `从失败阶段重试`; active runs expose `取消整次运行`.
- The final panel links to the frozen report or renders the zero-model “本轮无新增舆情” outcome. It never claims that an empty result proves no relevant event exists.
- Preserve deep links and URL-owned selected run/pagination. Support keyboard operation, visible focus, 44px touch targets, 4.5:1 text contrast, narrow layouts and reduced motion.

The UI follows the existing shadcn/Base UI tokens and typography. The UI/UX design search supports an operations-dashboard pattern with explicit freshness, visible stale/error states and no decorative charts; it does not justify replacing the project's current palette or typography.

### Workbench and Results

The workbench reads one projection derived from automation tasks/runs and the latest readable report. Results and Analysis continues to expose saved content and manual operations, but removes copy/actions that imply every manual initial-analysis job automatically creates a report. Existing report/source deep links remain valid.

## 8. Replacement, rollout and rollback

- Add the new schema and backend contracts behind application-factory availability flags used only by tests during construction.
- Build and verify workflow orchestration before exposing the new frontend route.
- Switch lifespan/router/workbench ownership atomically: register `AutomationWorkflowService`, unregister `CollectionScheduleService`, remove collection-finished automatic-analysis callbacks and remove analysis-finished automatic-report callbacks.
- Remove the old collection-schedule frontend route/client/hooks after new task UI tests pass. Do not keep both user-facing schedulers.
- Do not migrate old schedule rows. Use temporary databases for tests. Any reset of `runtime/longtian.sqlite3` for hands-on validation is a separate explicit destructive step with a backup/target check.
- Rollback disables new admissions first, drains workflow and child owners, then restores the prior code version. Additive workflow rows and existing domain outputs remain readable or inert; rollback never deletes collected content or model results.

## 9. Main risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Duplicate child work after a crash | Persist unique operation key before admission; child admission is idempotent; reconcile from committed child status. |
| Two automatic mechanisms both advance | Remove old callbacks/routes and assert only workflow-owned admissions in lifecycle/integration tests. |
| Report retry repeats expensive media work | Report stage consumes frozen saved text; cross-stage call-count tests require zero browser/media/stage-one calls. |
| Per-task “new” confused with global dedup | Dedicated `(task_id, content_id)` membership and A/B cross-task tests. |
| Slow runs create backlog | Same-task due occurrences skip visibly; different tasks remain durable and resource-serialized. |
| Task edit changes history | Immutable run snapshot and version-guarded task writes. |
| DST/offline causes duplicate runs | UTC materialized due time, IANA zone rules, unique occurrence key, injected clock tests. |
| Dirty worktree loses unrelated edits | Recheck status before every implementation batch; do not overwrite existing edits in enrichment/spec/tests or the MediaCrawler submodule. |

## 10. Validation strategy

- Repository/migration tests: fresh/repeated initialization, forward-version rejection, transactional rollback, task schedule checks, occurrence uniqueness, task-content membership, frozen snapshots, stage attempt immutability and request replay.
- Service tests: scheduled/manual admission, fixed-stage order, wakeup loss/restart, same-task skip, different-task queueing, cancellation at each boundary, retry from each stage, partial-member success and no-new zero-call result.
- Integration call-count tests: exactly one child per stage operation key; report retry has zero collector/media/stage-one calls; GET/startup has zero browser/model calls; old callbacks create no automatic child.
- API tests: strict payloads, revision/request conflicts, timezone/goal bounds, stable envelopes and no-store/local guards.
- Frontend tests: strict decoders, editor validation, next-time preview, run-now ambiguity, timeline polling, cancel/retry confirmation, empty/failure/report states, keyboard/focus/narrow layout and deep links.
- Full backend Ruff/pytest and frontend format/lint/typecheck/test/build gates run locally per project policy, followed by an isolated local-browser acceptance with fake collector/model services. Real platform/model acceptance remains an explicit later operation because it uses login state and may incur cost.
