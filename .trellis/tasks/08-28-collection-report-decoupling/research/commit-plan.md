# Approved commit batch

On 2026-08-29 the user approved this exact two-commit batch and requested an
application start for hands-on use. Feature commit: `61f2b15`.
The second commit records the reviewed design and acceptance evidence below.
No push, task archive or journal commit is included. Conventional Commit
wording follows the repository's recent history.
Recheck dirty paths before executing; include only the explicit paths below.
Do not use `git add .` or include new unrelated work.

## 1. `feat: decouple collection and two-stage analysis`

One coherent feature commit keeps additive schema 12–14, shared lifecycle and
frontend/backend contracts together. Executable specifications travel with the
implementation. Existing migrated data is not part of this commit.

- `.trellis/spec/backend/ai-summary-guidelines.md`
- `.trellis/spec/backend/batch-search-guidelines.md`
- `.trellis/spec/backend/collection-schedule-guidelines.md`
- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/initial-analysis-guidelines.md`
- `.trellis/spec/backend/topic-report-guidelines.md`
- `.trellis/spec/frontend/index.md`
- `.trellis/spec/frontend/state-management.md`
- `backend/src/longtian_api/api/router.py`
- `backend/src/longtian_api/api/v1/analysis_common.py`
- `backend/src/longtian_api/api/v1/analysis_settings.py`
- `backend/src/longtian_api/api/v1/collection_schedules.py`
- `backend/src/longtian_api/api/v1/content_analyses.py`
- `backend/src/longtian_api/api/v1/results.py`
- `backend/src/longtian_api/api/v1/topic_reports.py`
- `backend/src/longtian_api/collection_timing.py`
- `backend/src/longtian_api/database.py`
- `backend/src/longtian_api/main.py`
- `backend/src/longtian_api/migrations/__init__.py`
- `backend/src/longtian_api/migrations/collection_schedules.py`
- `backend/src/longtian_api/migrations/initial_analysis.py`
- `backend/src/longtian_api/migrations/topic_reports.py`
- `backend/src/longtian_api/repositories/ai_summaries.py`
- `backend/src/longtian_api/repositories/analysis_settings.py`
- `backend/src/longtian_api/repositories/analysis_shared.py`
- `backend/src/longtian_api/repositories/collection_schedules.py`
- `backend/src/longtian_api/repositories/content_analyses.py`
- `backend/src/longtian_api/repositories/monitoring_rules.py`
- `backend/src/longtian_api/repositories/results.py`
- `backend/src/longtian_api/repositories/search_batches.py`
- `backend/src/longtian_api/repositories/search_runs.py`
- `backend/src/longtian_api/repositories/topic_reports.py`
- `backend/src/longtian_api/schemas/analysis_evidence.py`
- `backend/src/longtian_api/schemas/analysis_settings.py`
- `backend/src/longtian_api/schemas/collection_schedules.py`
- `backend/src/longtian_api/schemas/content_analyses.py`
- `backend/src/longtian_api/schemas/results.py`
- `backend/src/longtian_api/schemas/topic_report_engine.py`
- `backend/src/longtian_api/schemas/topic_reports.py`
- `backend/src/longtian_api/services/ai_analysis.py`
- `backend/src/longtian_api/services/analysis_errors.py`
- `backend/src/longtian_api/services/analysis_settings.py`
- `backend/src/longtian_api/services/collection_schedule_errors.py`
- `backend/src/longtian_api/services/collection_schedules.py`
- `backend/src/longtian_api/services/content_analyses.py`
- `backend/src/longtian_api/services/content_understanding.py`
- `backend/src/longtian_api/services/media_crawler_auth_worker.py`
- `backend/src/longtian_api/services/results.py`
- `backend/src/longtian_api/services/search_batches.py`
- `backend/src/longtian_api/services/search_runs.py`
- `backend/src/longtian_api/services/topic_report_engine.py`
- `backend/src/longtian_api/services/topic_report_errors.py`
- `backend/src/longtian_api/services/topic_reports.py`
- `backend/tests/collection_schedule_fixtures.py`
- `backend/tests/collection_schedule_smoke.py`
- `backend/tests/initial_analysis_fixtures.py`
- `backend/tests/initial_analysis_smoke.py`
- `backend/tests/schema_fixtures.py`
- `backend/tests/test_ai_summary_repository.py`
- `backend/tests/test_collection_schedule_api.py`
- `backend/tests/test_collection_schedule_repository.py`
- `backend/tests/test_collection_schedule_smoke.py`
- `backend/tests/test_collection_schedules.py`
- `backend/tests/test_content_analyses.py`
- `backend/tests/test_content_analysis_api.py`
- `backend/tests/test_content_analysis_repository.py`
- `backend/tests/test_content_understanding.py`
- `backend/tests/test_initial_analysis_handoff.py`
- `backend/tests/test_initial_analysis_smoke.py`
- `backend/tests/test_monitoring_rule_combinations.py`
- `backend/tests/test_platform_connections.py`
- `backend/tests/test_schedule_browser_availability.py`
- `backend/tests/test_topic_report_api.py`
- `backend/tests/test_topic_report_engine.py`
- `backend/tests/test_topic_report_lifecycle.py`
- `backend/tests/test_topic_report_migrations.py`
- `backend/tests/test_topic_report_review_boundaries.py`
- `backend/tests/test_topic_report_smoke.py`
- `backend/tests/test_topic_reports.py`
- `backend/tests/topic_report_fixtures.py`
- `backend/tests/topic_report_smoke.py`
- `frontend/src/App.test.tsx`
- `frontend/src/app/router.tsx`
- `frontend/src/app/shell.tsx`
- `frontend/src/hooks/use-collection-schedules.ts`
- `frontend/src/hooks/use-topic-reports.ts`
- `frontend/src/lib/api/ai-summaries.ts`
- `frontend/src/lib/api/analysis-fixtures.ts`
- `frontend/src/lib/api/analysis-settings.test.ts`
- `frontend/src/lib/api/analysis-settings.ts`
- `frontend/src/lib/api/analysis-shared.ts`
- `frontend/src/lib/api/collection-schedules.fixtures.ts`
- `frontend/src/lib/api/collection-schedules.test.ts`
- `frontend/src/lib/api/collection-schedules.ts`
- `frontend/src/lib/api/content-analyses.test.ts`
- `frontend/src/lib/api/content-analyses.ts`
- `frontend/src/lib/api/results.test.ts`
- `frontend/src/lib/api/results.ts`
- `frontend/src/lib/api/search-batches.ts`
- `frontend/src/lib/api/topic-reports.fixtures.ts`
- `frontend/src/lib/api/topic-reports.test.ts`
- `frontend/src/lib/api/topic-reports.ts`
- `frontend/src/routes/collection-ai-summary.test.tsx`
- `frontend/src/routes/collection-ai-summary.tsx`
- `frontend/src/routes/collection-run-detail.tsx`
- `frontend/src/routes/collection-runs.test.tsx`
- `frontend/src/routes/collection-runs.tsx`
- `frontend/src/routes/collection-schedule-editor.tsx`
- `frontend/src/routes/collection-schedules.test.tsx`
- `frontend/src/routes/collection-schedules.tsx`
- `frontend/src/routes/results-confirmation.tsx`
- `frontend/src/routes/results-evidence.tsx`
- `frontend/src/routes/results-jobs.tsx`
- `frontend/src/routes/results-presenters.test.tsx`
- `frontend/src/routes/results-presenters.tsx`
- `frontend/src/routes/results-report-actions.tsx`
- `frontend/src/routes/results-report-details.tsx`
- `frontend/src/routes/results-reports.test.tsx`
- `frontend/src/routes/results-reports.tsx`
- `frontend/src/routes/results-settings.tsx`
- `frontend/src/routes/results.test.tsx`
- `frontend/src/routes/results.tsx`

## 2. `docs(trellis): record decoupling design and acceptance`

Approved requirements, child plans, research, manifests and actual isolated
acceptance evidence. These tasks stay unarchived until separately authorized
Trellis bookkeeping; this commit does not activate schedules or deploy code.

- `.trellis/tasks/08-28-collection-report-decoupling/check.jsonl`
- `.trellis/tasks/08-28-collection-report-decoupling/design.md`
- `.trellis/tasks/08-28-collection-report-decoupling/implement.jsonl`
- `.trellis/tasks/08-28-collection-report-decoupling/implement.md`
- `.trellis/tasks/08-28-collection-report-decoupling/prd.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/acceptance-matrix.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/commit-plan.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/coupling-map.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/custom-analysis-prompts.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/implementation-status.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/migration-validation-map.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/planning-review.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/report-admission-boundaries.md`
- `.trellis/tasks/08-28-collection-report-decoupling/research/scheduling-boundaries.md`
- `.trellis/tasks/08-28-collection-report-decoupling/task.json`
- `.trellis/tasks/08-29-automatic-text-reports/check.jsonl`
- `.trellis/tasks/08-29-automatic-text-reports/design.md`
- `.trellis/tasks/08-29-automatic-text-reports/implement.jsonl`
- `.trellis/tasks/08-29-automatic-text-reports/implement.md`
- `.trellis/tasks/08-29-automatic-text-reports/prd.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/backend-contract.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/backend-implementation.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/browser-acceptance.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/checked-dependency-notes.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/engine-implementation.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/engine-review.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/frontend-implementation.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/full-check.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/smoke-fixture.md`
- `.trellis/tasks/08-29-automatic-text-reports/research/text-engine-contract.md`
- `.trellis/tasks/08-29-automatic-text-reports/task.json`
- `.trellis/tasks/08-29-scheduled-rule-collection/check.jsonl`
- `.trellis/tasks/08-29-scheduled-rule-collection/design.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/implement.jsonl`
- `.trellis/tasks/08-29-scheduled-rule-collection/implement.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/prd.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/research/backend-contract.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/research/backend-implementation.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/research/browser-acceptance.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/research/frontend-implementation.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/research/full-check.md`
- `.trellis/tasks/08-29-scheduled-rule-collection/task.json`
- `.trellis/tasks/08-29-shared-results-initial-analysis/check.jsonl`
- `.trellis/tasks/08-29-shared-results-initial-analysis/design.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/implement.jsonl`
- `.trellis/tasks/08-29-shared-results-initial-analysis/implement.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/prd.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/backend-contract.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/backend-implementation.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/browser-acceptance.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/frontend-check.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/frontend-implementation.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/research/full-check.md`
- `.trellis/tasks/08-29-shared-results-initial-analysis/task.json`

## Unrecognized existing edits — excluded

The model-setting changes that predated implementation were independently
committed as `b985e46` before this batch. They are not part of either commit.

- `.codex/agents/trellis-check.toml`
- `.codex/agents/trellis-implement.toml`

The subsequent unrelated edit to `.trellis/.template-hashes.json` is also
excluded and preserved. No push is included. A later archive/journal operation
may create its own bookkeeping commits and is not performed by this batch.
