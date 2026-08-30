# Unified Opinion Automation

## 1. Scope / Trigger

Read this guide before changing automatic task configuration, scheduled or
run-now admission, cross-stage orchestration, failed-stage retry, task-scoped
new-content membership, cancellation, automation history, or the Automation UI.

`AutomationWorkflowService` is the only automatic workflow owner. It always
executes this immutable order:

```text
collection -> initial_analysis -> topic_report
```

The collection, initial-analysis and topic-report services remain child-domain
owners. They expose idempotent adapters to this workflow, but must not advance
the workflow through completion callbacks. Manual collection and explicit
analysis/report APIs remain independent user actions.

## 2. Signatures

All HTTP routes use the `/api/v1` prefix:

| Method / suffix | Contract |
| --- | --- |
| GET `/automation-tasks` | Cursor-paginated task list, limit 1-100. |
| POST `/automation-tasks` | Creates a disabled task; HTTP 201. |
| GET `/automation-tasks/{id}` | Current task configuration and latest run. |
| PUT `/automation-tasks/{id}` | Full replacement with `expected_revision` and explicit `enabled`. |
| GET `/automation-tasks/{id}/occurrences` | Cursor-paginated scheduled admission history. |
| GET `/automation-tasks/{id}/runs` | Cursor-paginated workflow-run history. |
| POST `/automation-tasks/{id}/run-now` | Idempotent manual admission; HTTP 202. |
| GET `/automation-runs/{id}` | Fixed stages, metrics, child links and failure state. |
| POST `/automation-runs/{id}/cancel` | Revision-fenced whole-run cancellation; HTTP 202. |
| POST `/automation-runs/{id}/retry` | Revision-fenced retry from the first failed stage; HTTP 202. |

A task owns a unique name, monitoring-rule reference, ordered platforms,
per-term cap, nonblank `analysis_goal`, and either an interval schedule of
1-43,200 minutes or a daily `HH:MM` schedule with an IANA timezone. Mutations
use canonical UUIDv4 `request_id` values. New tasks are disabled; `run-now` is
allowed without enabling the timer.

Backend owners are `migrations/automation_workflows.py`, the matching schema,
repository, service and API modules, plus explicit child adapters. Frontend
owners are `lib/api/automation-workflows.ts`,
`hooks/use-automation-workflows.ts`, `routes/automation-tasks.tsx`,
`routes/automation-task-editor.tsx` and `routes/automation-run-detail.tsx`.

SQLite v15 appends `automation_tasks`, `automation_task_platforms`,
`automation_occurrences`, `automation_runs`, `automation_stage_attempts`,
`automation_task_contents`, `automation_run_contents` and
`automation_requests`. It also adds the unique workflow operation key to search
batches. Do not rewrite or convert v13 collection-schedule rows during upgrade.

## 3. Contracts

### Admission and frozen intent

- Enabling validates the current rule, effective-term limit and AI
  configuration. Every accepted replacement increments the task revision and
  recalculates its next due time. Disabling affects future admission only.
- Each admitted run freezes the task revision, rule name and terms, platforms,
  result cap, goal and goal hash, AI configuration/provider identity, prompt
  version IDs, template versions and admission time. Later edits affect future
  runs only.
- A task can own at most one active run. Scheduled overlap creates an explicit
  skipped occurrence; manual overlap returns a conflict. Different tasks may
  run independently subject to the existing browser and AI domain leases.
- Scheduled occurrence keys and manual request IDs are durable admission keys.
  Identical mutation replay returns the currently persisted run projection;
  reusing a UUID for a different intent is a conflict.
- Startup reconciliation is storage-only. It records overdue ranges as missed,
  trusts already settled linked children, and marks ambiguous paid/active child
  state interrupted for explicit retry. It never starts a collector, browser or
  model as a side effect of opening the database.

### Fixed execution and task-scoped content

- Stage order is application-owned and cannot be edited, skipped, reordered or
  branched by the user. Every stage attempt has a stable operation key and
  optional child aggregate link.
- Collection calls the batch adapter once for the attempt. It registers only
  content whose membership is new to this task. Global deduplication does not
  make content old for another task; repeated observations within the same task
  do not re-enter later runs.
- Initial analysis receives the current run's exact member IDs and performs the
  reusable generic multimodal understanding. The task goal is frozen as
  orchestration/report intent; it must not mutate the generic evidence model.
- Topic reporting consumes the saved initial-analysis evidence and task goal,
  performs relevance judgment, and synthesizes the report. It must not invoke
  collection or media acquisition.
- Zero new task members is a successful `no_new_sources` run. Initial analysis
  creates no child; report admission persists a readable `no_ready_sources`
  empty report while judgment/composition model calls remain zero.
- Partial analysis/report coverage is visible through stage input, success,
  failure, attempted-request and token metrics. A 10/8/2 run stays inspectable;
  it is never represented as an unexplained Boolean success.

### Retry, cancellation and public state

- Run states are `queued`, `collecting`, `analysing`, `reporting`, `completed`,
  `failed`, `cancelled`, `interrupted` or `configuration_blocked`. The public
  projection always contains exactly the three ordered stages.
- Retry keeps the same run and frozen snapshot. Completed stages and their
  child links are retained; a new attempt is created at the first failed,
  interrupted or configuration-blocked stage. Report-only retry performs no
  collection, media acquisition or initial-analysis call.
- Cancellation first fences the workflow row, then best-effort cancels and
  drains the active child owner. Late child completion cannot advance a
  cancelled run.
- The old `/api/v1/collection-schedules` routes and schedule frontend are not
  registered. Legacy v13 tables/source may remain for historical compatibility,
  but no lifecycle callback or public navigation may admit automatic work.
- Workbench exposes `activity.automation`, the three child-domain activity
  projections, `next_automation`, automation task/run attention, and the latest
  readable report. Frontend server state stays in TanStack Query; run/task IDs
  and pagination stay in route/URL state; mutation UUIDs survive ambiguous
  transport outcomes.
- Public runs expose both the latest fixed three-stage projection and ordered
  append-only attempt history. Every attempt retains its child, coverage, model
  request count, token count, failure and timestamps.
- Run-now, cancel and retry write their request proof in the same SQLite
  transaction as the run admission/state change. A request-proof failure rolls
  back the entire mutation.

## 4. Validation & Error Matrix

Every response uses `Cache-Control: no-store`; mutations retain the existing
local Host/Origin/JSON guards. Persisted rows and frontend decoders must reject
invalid stage order, timestamps, counters, links and revisions rather than
coercing them.

| Condition | Required result |
| --- | --- |
| Unknown task or run | 404 `automation_task_not_found` / `automation_run_not_found` |
| Duplicate normalized task name | 409 `automation_task_name_conflict` |
| Stale task or run revision | 409 `automation_task_changed` / `automation_run_changed` |
| Same task already has active run | 409 `automation_run_active`; scheduled occurrence is skipped |
| UUID reused for changed intent | 409 `automation_request_conflict` |
| Retry has no failed/interrupted stage | 409 `automation_run_not_retryable` |
| Cancel targets terminal run | 409 `automation_run_not_active` |
| Missing/disabled/invalid/oversized rule | Stable rule/automation configuration error; no child work |
| Invalid goal, platforms, schedule or timezone | 422 strict request/configuration error; no write |
| AI configuration unavailable | `configuration_blocked` or stable AI configuration error; no substitution |
| Corrupt storage or closed service | Sanitized 503 automation storage/unavailable error |

Never expose raw SQLite, browser, model or credential-bearing exception text.

## 5. Good / Base / Bad Cases

- Good: task A first sees ten sources, analyses eight and records two failures;
  its report exposes 10/8/2 coverage. Retry begins at the failed stage and
  preserves all previously completed child work.
- Good: task B later sees the same globally deduplicated content. It is still
  new to task B and is processed once for B's goal.
- Base: a scheduled or run-now collection finds no new task content. The run
  completes as `no_new_sources` with zero model calls.
- Bad: report retry launches a browser, a completion callback creates another
  stage, or editing a task rewrites the snapshot of an existing run.
- Bad: polling an empty run list creates work, two active runs overlap for one
  task, or a historical collection schedule is exposed as a live automation.

## 6. Tests Required

- Genuine v14-to-v15 migration, populated v13 preservation, reopen, forward
  version rejection and transactional rollback; assert no schedule conversion
  and no startup browser/model call.
- Interval and daily timing across IANA timezone/DST boundaries, exact due,
  offline/clock-jump recovery, idempotent occurrence admission and same-task
  overlap handling.
- Run-now replay/conflict, frozen snapshots, one active run per task, cancellation
  fencing, restart interruption and retry from collection, analysis and report.
- Per-task new-content membership across repeated task A and independent task B;
  zero-new short circuit with zero model calls; partial 10/8/2 metrics and
  report-only retry with zero upstream work.
- Strict HTTP errors and old-route 404, plus frontend decoder, list/editor/run
  detail, mutation, navigation, workbench and responsive interaction tests.
- Run backend Ruff/pytest and frontend format, lint, type, Vitest and build gates
  locally. Live platform/model validation is separate and must be explicitly
  authorized/configured; fakes prove orchestration rather than provider quality.

## 7. Wrong vs Correct

Wrong: let child completion callbacks choose and start the next stage.

```python
analysis.on_finished = reports.initial_analysis_finished
batch.on_finished = analyses.start_latest_results
```

Correct: the workflow owner admits durable child operations and advances only
after reading their settled state.

```python
for stage in ("collection", "initial_analysis", "topic_report"):
    attempt = repository.start_stage(run_id, stage)
    child = await adapters[stage].admit(operation_key=attempt.operation_key)
    await repository.finish_stage(run_id, stage, project(child))
```

Wrong: retry by creating a new run from today's task configuration.
Correct: retain the original run snapshot and completed attempts, append one
attempt at the first failed stage, and continue the fixed suffix only.
