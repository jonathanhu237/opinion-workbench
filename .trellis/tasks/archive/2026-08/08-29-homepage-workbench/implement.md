# Homepage Workbench Implementation Plan

## 1. Backend read contract

- [x] Add strict workbench response/error models in `backend/src/longtian_api/schemas/workbench.py`.
- [x] Add `WorkbenchRepository` with one explicit SQLite read transaction, deterministic full-dataset queries, latest-owner supersession, global next-due selection, and validated latest report overview.
- [x] Add `WorkbenchService` with injected UTC clock and constant sanitized storage failure.
- [x] Add `GET /api/v1/workbench`, no-store behavior, dependency registration, lifespan construction, and router inclusion.
- [x] Confirm the GET path performs no writes and reaches no browser, collector, enrichment, AI, report-admission, or schedule-admission entry point.

## 2. Backend verification

- [x] Add repository/service/API tests covering empty data, all latest-state rules, later-success clearing, disabled/cancelled exclusions, global next schedule, active progress, completed/empty report summaries, newer failed report coexistence, invalid persisted output, and constant 503 responses.
- [x] Add read-only sentinels/call-count assertions proving repeated GET and polling create no work.
- [x] Run targeted workbench tests, then the full backend Ruff/pytest gates.

## 3. Frontend API and query ownership

- [x] Add `frontend/src/lib/api/workbench.ts` with exact Zod validation, error mapping, query key, and abortable fetch.
- [x] Add `frontend/src/hooks/use-workbench.ts` with 5-second active and 30-second idle refresh; preserve validated cached data on later errors and expose stale state.
- [x] Extend `usePlatformConnections` with an optional homepage idle interval while preserving existing Platform Accounts behavior and query identity.
- [x] Map typed workbench/platform status to existing deep links only; introduce no mutation hook.

## 4. Workbench UI

- [x] Replace the deliberate `null` route with the approved hierarchy: duty signal, conditional attention, dominant latest-report card, and secondary collection-analysis-report signal rail with next schedule and platform readiness.
- [x] Use existing Card/Badge/Button-link primitives, civic tokens, display/body typography, Lucide icons, and reduced-motion behavior. Add only narrowly scoped global CSS if Tailwind cannot express the signal rail cleanly.
- [x] Implement loading, empty, unknown, partial error, full error, stale, active, readable-report, and empty-report states with semantic headings/live regions.
- [x] Keep all controls as refresh or navigation; do not render daily metrics, charts, raw results, risk labels, or handling state.

## 5. Frontend verification

- [x] Add route behavior tests for every state and deep link, adaptive refresh, cached-stale behavior, keyboard semantics, and absence of mutation requests/speculative content.
- [x] Update application-shell tests that intentionally asserted the prior empty route, retaining navigation and main-focus coverage.
- [x] Run Prettier, Oxlint, TypeScript, Vitest, and production build through mise Node 24.

## 6. Integration and review gates

- [x] Run the cross-layer contract tests against a temporary on-disk database and fake platform/worker/model boundaries.
- [x] Start the local fake/isolated backend and Vite frontend; inspect desktop and narrow layouts, keyboard navigation, focus, live-region behavior, refresh/stale states, horizontal overflow, and browser console.
- [x] Verify by instrumentation/database snapshot that homepage entry, refresh, polling, and navigation created no tasks or persistent writes.
- [x] Review the final diff for unrelated dirty-worktree changes, forbidden dependencies, duplicate domain logic, and spec drift.

## Validation Commands

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd ../frontend
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```

Final validation note: all frontend gates passed (602 tests). Backend Ruff and
format gates passed; 1027 tests passed and the single failing topic-report smoke
test reproduces through the pre-existing enrichment staging changes outside this
task. The focused workbench suite passed all 10 tests.

## Risk and Rollback Points

- After backend contract tests: if current-state SQL cannot preserve domain invariants without duplicating unsafe projection logic, stop and refactor shared read helpers before UI work.
- After frontend API tests: if the composite contract cannot distinguish stale/partial state truthfully, revise the response rather than coercing unknown values to normal/zero.
- Before browser QA: the feature remains removable by unregistering the additive endpoint and restoring `Workbench` to `null`; no data rollback is required.
