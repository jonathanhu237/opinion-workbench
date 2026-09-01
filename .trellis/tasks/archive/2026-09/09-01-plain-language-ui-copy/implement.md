# Implementation Plan — Plain-Language UI Copy

## 1. Inventory and Baseline

- [x] Build a route-by-route inventory of visible helper, status, error, confirmation, and empty
  copy, excluding tests/fixtures/prompts/generated content.
- [x] Record representative current tests and the exact internal-language phrases they assert.
- [x] Confirm the existing loopback frontend/backend remain available for later browser QA without
  triggering collection or model work.

## 2. High-Visibility Copy

- [x] Clean the workbench duty banner, attention cards, latest-report panel, activity summary, and
  empty/error states.
- [x] Clean application-shell health copy and route-level error fallback copy.
- [x] Add/update workbench and shell tests for removed redundancy and retained actionable states.

## 3. Automation Copy

- [x] Clean task editor descriptions and confirmations while retaining schedule/model-call effects.
- [x] Clean task lists, run history, and run detail terminology (`冻结`, `修订`, `运行快照`,
  `已保存产物`, `固定工作流`).
- [x] Update automation tests for the new visible language and unchanged actions/links.

## 4. Results, Reports, and Collection Copy

- [x] Clean results, analysis job/evidence, report history/detail/action, and confirmation copy.
- [x] Replace internal progress terms with plain evidence/report language without merging states.
- [x] Clean collection batch/run/recovery/summary text and platform-account guidance.
- [x] Update representative tests across results/report, collection, and platform surfaces.

## 5. Monitoring and Settings Copy

- [x] Remove redundant monitoring-rule help while preserving search-term composition guidance.
- [x] Simplify AI/prompt settings copy while preserving credential, provider-call, quota, and
  authorization consequences.
- [x] Update form tests where visible behavior changed.

## 6. Consistency Review

- [x] Search product source for the PRD's internal-language phrases and review every remaining hit.
- [x] Verify buttons and headings do not depend on deleted paragraphs for accessible context.
- [x] Verify errors state the outcome and a concrete next step when one exists.

## 7. Quality and Browser Gate

- [x] Run `mise x node@24 -- pnpm format` from `frontend/`.
- [x] Run frozen install, format check, lint, type-check, full Vitest, and production build.
- [x] Browser-check workbench, automation run detail, and results/report detail at desktop and
  narrow widths; verify no console warning/error, overflow, accidental mutation, platform request,
  or model call.
- [x] Run `git diff --check` and Trellis task validation.

## Rollback Points

- Commit only frontend source/tests plus this task's Trellis artifacts.
- Leave unrelated dirty backend/spec/submodule work untouched.
- Copy changes are reversible independently because no API, storage, or workflow contract changes.
