# Implementation Plan

The task is implemented as one sequential cross-layer change. Do not activate the parent until `prd.md`, `design.md`, this plan and both JSONL manifests pass review. Do not dispatch parallel writers: `database.py`, `main.py`, routers, workbench projections and frontend navigation are shared integration points.

## 0. Preflight and ownership

- [ ] Re-run `python3 ./.trellis/scripts/get_context.py` and `git status --short`.
- [ ] Preserve existing unrelated edits in `.trellis/.template-hashes.json`, `AGENTS.md`, `backend/src/longtian_api/services/enrichment_models.py`, the two existing backend test files and `third_party/MediaCrawler`; inspect overlaps before editing.
- [ ] Recheck the current schema version and route/service registrations instead of assuming v14.
- [ ] Load `trellis-before-dev` and every spec/research entry in `implement.jsonl` before product edits.
- [ ] Use only temporary SQLite databases during automated validation. Do not delete or replace `runtime/longtian.sqlite3` without a later explicit target check and user-visible notice.

## 1. Freeze executable contracts with backend tests

- [ ] Add failing schema/repository tests for automation tasks, interval/daily schedule validation, IANA timezone calculation, occurrence uniqueness, run snapshots, fixed stages, stage-attempt immutability, task-content first membership and UUID intent replay.
- [ ] Add the next migration and `schemas/automation_workflows.py`, `repositories/automation_workflows.py`, `services/automation_workflow_errors.py` and `services/automation_workflows.py` following route→service→repository ownership.
- [ ] Cover fresh/repeated initialization, forward-version rejection, migration rollback and reopen. Do not migrate old collection-schedule rows into new tasks.
- [ ] Add pure schedule functions with injected UTC/monotonic clocks. Test interval, daily Asia/Shanghai, DST gap/overlap zones, offline ranges and forward/backward wall-clock jumps.
- [ ] Gate: run focused migration/repository/service tests plus Ruff on changed backend files.

## 2. Add idempotent stage adapters

- [ ] Extend `SearchBatchService` with workflow-owned admission using a persisted operation key and frozen rule/platform/count snapshot. Preserve serial platforms, manual verification and global result deduplication.
- [ ] After a successful collection attempt, atomically register `(task_id, content_id)` membership from stable batch results; expose inserted new members and repeated counts in deterministic order.
- [ ] Extend `ContentAnalysisService` with workflow admission over server-selected content IDs. Reuse compatible generic understandings, preserve member errors and return a settled job projection without creating a report.
- [ ] Extend `TopicReportService`/repository selection to consume the workflow's frozen content membership and successful initial-analysis attempts across retry jobs, with a frozen task goal and app template version.
- [ ] Add `no_new_sources` as a zero-model workflow outcome; ensure it creates no judgment/composition request.
- [ ] Add child-level operation-key replay tests for crash windows before/after child creation/link persistence.
- [ ] Gate: run collection, initial-analysis and topic-report focused suites, including call-count assertions for no-new and report-only retry.

## 3. Implement the central workflow runner

- [ ] Implement scheduled and manual admission, same-task active-run conflict/skip, deterministic global queue wakeups and the fixed `collection -> initial_analysis -> topic_report` transition table.
- [ ] Persist each attempt before child admission; on callbacks only wake the runner, then reread committed child state before advancing.
- [ ] Implement startup reconciliation with zero browser/model calls. Trust completed linked children; mark ambiguous active work interrupted and require explicit retry.
- [ ] Implement cancellation: fence the run, cancel/drain the current child and suppress later stages while preserving completed outputs.
- [ ] Implement retry from the first failed stage using the original snapshot and new attempt. Test collection, initial-analysis, report, configuration-blocked and ambiguous paid-request cases.
- [ ] Prove the 10/8/2 case: all ten analysis members settle, eight successes feed one report and two unavailable members remain visible.
- [ ] Prove different tasks can be durably admitted while global browser/AI ownership remains exclusive; prove the same task never overlaps.
- [ ] Gate: run workflow lifecycle/restart/concurrency suites and existing resource-owner regressions.

## 4. Switch backend API and lifecycle ownership

- [ ] Add strict `/api/v1/automation-tasks` and `/api/v1/automation-runs` routes, typed errors, local mutation guards, `Cache-Control: no-store`, OpenAPI responses and pagination.
- [ ] Add application-state wiring for the workflow service. Shutdown stops timer/admission first, then workflow, report, analysis, media, AI, batch, run and platform owners in dependency order.
- [ ] Remove runtime registration of `CollectionScheduleService` and its router.
- [ ] Remove `search_* -> content_analysis_service.collection_finished` and `content_analysis_service.on_job_finished -> topic_report_service` automatic callbacks. Manual domain endpoints remain callable but cannot auto-advance.
- [ ] Update the workbench repository/service/API to derive next task, attention state, current fixed stage and latest readable result from automation runs.
- [ ] Add negative integration tests showing old completion callbacks/events do not create work and only the workflow service can admit the next automatic stage.
- [ ] Gate: full backend Ruff format/check and pytest before frontend work.

## 5. Replace the frontend scheduler with automatic tasks

- [ ] Add strict Zod/TypeScript API owners and TanStack Query hooks for tasks, occurrences, runs, run-now, cancel and retry. Keep mutation request IDs stable across ambiguous failures.
- [ ] Replace the “定时采集” navigation/route with “自动任务”; remove old schedule client/hooks/components/tests after the replacement route passes.
- [ ] Build the task list/editor with business-only fields, explicit disabled-by-default creation, interval/daily schedule choice, timezone, next-run preview, goal helper text and enabled-rule validation.
- [ ] Build run history/detail with a semantic three-stage timeline, contextual live status, text/icon state labels, progress/coverage/usage, deep links and zero-new/failure/cancelled/completed outcomes.
- [ ] Implement run-now, cancel and retry confirmations with observed revision/request intent. Expose retry only for the first failed stage; do not expose stage skip/order controls.
- [ ] Update Results and Analysis copy so manual jobs do not imply automatic report creation. Preserve independent manual operations and historical evidence/report navigation.
- [ ] Update the workbench to link unified runs/results and show explicit freshness/stale/error states.
- [ ] Verify keyboard/focus, 44px targets, contrast, reduced motion, narrow layouts, polling without focus movement and no color-only status.
- [ ] Gate: run focused API/route tests, then format, lint, typecheck, full tests and build.

## 6. Cleanup, specs and final integration

- [ ] Search for every `collection_schedule`, `collection_finished`, `on_job_finished`, `analysis_completion_events` consumer and old frontend route. Classify remaining references as manual/history/inert schema or remove them; no live competing automatic path may remain.
- [ ] Update backend and frontend spec indexes. Replace the old fixed-interval collection guideline with the fixed workflow contract or mark it historical; update initial-analysis, topic-report, workbench, batch-search and state-management contracts.
- [ ] Run a fake-service end-to-end local acceptance covering scheduled trigger, run-now, zero-new, relevant/unrelated/uncertain, 10/8/2, overlap skip, cancellation, all three retry boundaries, reload/restart and old-callback non-admission.
- [ ] Run local browser QA at 375/768/1024/1440 widths and inspect console; provide the local URL rather than opening a Codex sidebar preview.
- [ ] Do not run real platform collection or model calls without an explicit later authorization. Record that mock/fake acceptance does not establish live provider or crawler quality.
- [ ] Run `trellis-check`, fix verified findings, perform the PRD acceptance matrix review and update specs before commit.

## Validation commands

Backend, from `backend/`:

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests --tb=short
```

Frontend, from `frontend/`:

```bash
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

Focused commands should target new automation tests first, but they do not replace the full gates.

## Risky owners and rollback points

| Owner | Risk | Rollback point |
| --- | --- | --- |
| `backend/src/longtian_api/database.py`, migrations | schema/check/FK drift | Stop after migration tests; do not touch real runtime DB. |
| batch/analysis/report repositories and services | duplicate or paid replay | Require operation-key and exact call-count tests before lifecycle wiring. |
| `backend/src/longtian_api/main.py`, API router | two active automatic owners or unsafe shutdown | Switch only after workflow integration tests pass; availability flags can disable new admission during construction. |
| workbench projections | contradictory/stale status | Keep projection read-only and prove cross-aggregate snapshots before route switch. |
| frontend router/shell/routes | broken navigation or ambiguous mutations | Keep replacement behind its tested route until API decoders and mutation recovery pass. |
| local runtime data | irreversible development-data loss | Use temporary DBs; any real reset requires a separate explicit checked action. |

No rollback step may use destructive Git commands or delete collected/model data. If an implementation phase fails, disable new admission and retain committed child outputs for diagnosis.
