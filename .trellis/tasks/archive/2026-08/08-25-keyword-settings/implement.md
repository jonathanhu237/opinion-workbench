# Implementation Plan: Monitoring Rules

## Phase A — Freeze shared contracts and first database conventions

- [x] Add the selected SQLite connection, migration, transaction, path, and runtime-data rules to
      `.trellis/spec/backend/database-guidelines.md` before implementing the repository.
- [x] Add the stable product error-envelope and request-validation behavior to the relevant backend
      spec, keeping existing API success/error behavior compatible.
- [x] Freeze the rule limits, normalization algorithm, ordering, public JSON shapes, HTTP statuses,
      error codes, and one-time seed values from `design.md` in backend contract tests.
- [x] Confirm the change boundary remains monitoring-rule configuration only: no platform selector,
      worker launch, browser call, collection action, or MediaCrawler change.

## Phase B — Build the SQLite persistence boundary

- [x] Add the ignored `runtime/longtian.sqlite3` location and WAL/SHM sidecars without touching the
      unrelated `db_data/` directory or existing runtime sessions.
- [x] Implement connection creation, SQLite pragmas, `PRAGMA user_version` migration execution,
      forward-version rejection, and atomic migration 1.
- [x] Create `monitoring_rules` and `monitoring_rule_terms` with constraints, stable positions,
      cascading deletion, timestamps, and the enabled index.
- [x] Seed the one default five-term rule inside migration 1 only.
- [x] Implement repository list/filter/create/replace/delete with per-operation connections, bound
      parameters, short explicit transactions, deterministic row assembly, and atomic replacement.
- [x] Test fresh initialization, repeated initialization, seed deletion persistence, forward-version
      failure, CRUD across reopen, ordering, constraints, rollback, and WAL/runtime isolation.

## Phase C — Add the FastAPI resource

- [x] Add immutable service projections, normalization/validation, configured limits, and domain
      errors without leaking SQLite details or rule values.
- [x] Add strict Pydantic create/replace/response/error models and typed `Annotated` dependencies.
- [x] Add sync GET/POST/PUT/DELETE path operations under `/api/v1/monitoring-rules`, including
      `enabled` filtering, full response models, documented failures, and one operation per function.
- [x] Add the shared `RequestValidationError` product envelope and prove existing API contracts do
      not regress.
- [x] Extend `create_app()` with an injectable monitoring-rule service factory, initialize through
      `run_in_threadpool` before lifespan yield, and preserve async platform-service shutdown.
- [x] Move all backend tests to temporary SQLite files or fakes so no test writes the real runtime
      database.
- [x] Cover 200/201/204, 404/409/422/503, OpenAPI, malformed payloads, normalized conflicts,
      storage sanitization, enabled filtering, and no worker/browser interaction.

## Phase D — Add only the required shadcn primitives

- [x] From `frontend/`, verify the existing `base-nova`/Base UI shadcn configuration.
- [x] Add Dialog, AlertDialog, Field, Textarea, and Switch for the monitoring-rule editor, deletion,
      labels/errors, batch terms, and enabled state.
- [x] Review every generated file and lockfile change; reject unrelated global palette, typography,
      component overwrite, or theme-variable changes.
- [x] Add primitive-level accessibility regressions only where the generated source or project
      integration changes behavior.

## Phase E — Build the typed frontend boundary and route

- [x] Add Zod schemas, API functions, stable API-error mapping, request cancellation, and focused
      decoder tests in `lib/api/monitoring-rules.ts`.
- [x] Add the reusable TanStack Query hook with explicit retry policy and normal cache lifetime.
- [x] Register `/monitoring-rules`, add the third sidebar item, and replace the shell title ternary
      with an explicit pathname mapping while preserving desktop/mobile navigation focus behavior.
- [x] Build the compact semantic rule list with real names, wrapping term badges, textual enabled
      state, row Switch, visible Edit/Delete buttons, and no fake metrics or platform controls.
- [x] Build one controlled create/edit Dialog using React Hook Form + Zod and one-term-per-line
      Textarea parsing. Keep pending and field/form errors visible and close only after success.
- [x] Build controlled delete confirmation with failure recovery and canonical cache invalidation.
- [x] Implement loading, empty, initial error/retry, cached refetch error, row pending, and polite
      success states without a toast dependency.
- [x] Keep rule mutations pessimistic, action-specific, keyboard accessible, and at least 44 px on
      mobile; prevent horizontal overflow for long terms.

## Phase F — Cross-layer verification and delivery review

- [x] Prove a create/edit/toggle/delete round trip preserves the exact public rule shape and term
      order across SQLite, FastAPI, frontend decoder, TanStack Query, and rendered UI.
- [x] Prove a backend normalization or storage failure reaches the correct Chinese recovery path and
      never becomes a false success or client-only validation error.
- [x] Run the complete backend and frontend frozen gates plus `git diff --check` and submodule status.
- [x] Run loopback browser smoke tests at desktop, 375 px, and the exact 48 rem shell boundary;
      inspect focus, dialogs, responsive wrapping, console errors, and horizontal overflow.
- [x] Verify rule actions do not touch platform connection state, start the persistent worker, open
      the browser, or expose collection controls.
- [x] Perform Trellis full-scope review and fix every verified finding.
- [x] Update task acceptance evidence, then request explicit delivery approval before committing,
      pushing, archiving, or starting the separate collection-task work.

### Acceptance evidence

- SQLite migration, CRUD persistence, enabled filtering, normalization, rollback, storage
  sanitization, OpenAPI, and no-worker boundaries are covered by the passing backend suite
  (`114 passed`).
- Frontend loading, error/retry, create/edit/toggle/delete, strict API decoding, navigation, focus,
  and dialog behavior are covered by the passing frontend suite (`52 passed`).
- Frozen install, Prettier, Oxlint, TypeScript, Vite production build, Ruff format/lint, pytest,
  compileall, `git diff --check`, and recursive submodule checks passed on 2026-08-25.
- Live loopback acceptance created, edited, disabled, and then removed an exact temporary rule. The
  final API and refreshed UI contain only the five-term default rule.
- Browser checks at 375 px, the exact 768 px boundary, and 1280 px showed no horizontal overflow;
  the mobile editor remained inside the viewport and the console contained no warnings or errors.
- The task did not change MediaCrawler, platform connection behavior, the global theme, existing
  Button/Separator primitives, frontend dependencies, or lockfiles.
- Final independent review added regressions for SQLite-int64 path IDs, HTTP-status/error-code
  pairing, and backend-only Unicode `casefold` duplicate feedback; all now fail closed at the
  correct boundary.
- Vite still reports the pre-existing-style entry chunk warning at 506.59 kB; the new route is lazy
  loaded as a separate 127.76 kB chunk and all build gates pass.

## Validation commands

```bash
backend/.venv/bin/ruff format --check backend/src backend/tests
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pytest -q backend/tests
backend/.venv/bin/python -m compileall -q backend/src backend/tests

mise x node@24 -- pnpm --dir frontend install --frozen-lockfile
mise x node@24 -- pnpm --dir frontend format:check
mise x node@24 -- pnpm --dir frontend lint
mise x node@24 -- pnpm --dir frontend typecheck
mise x node@24 -- pnpm --dir frontend test:run
mise x node@24 -- pnpm --dir frontend build

git diff --check
git submodule status --recursive
git -C third_party/MediaCrawler status --short
```

## Risk and rollback points

- If startup migration or service injection causes existing tests to write the real runtime DB,
  stop and restore explicit temporary-path/factory injection before continuing.
- If an update can replace the parent but lose some terms, stop at the repository layer and make the
  full replacement one explicit transaction before exposing PUT.
- If generated shadcn source rewrites the established theme, discard only those generated theme
  hunks and re-add the named primitives without changing project tokens.
- If mobile requires a separate editor component mode, first simplify the single Dialog layout;
  do not duplicate form state or introduce a breakpoint race without separate approval.
- If implementation needs platform IDs, browser state, scheduling, or result semantics, stop: the
  scope has expanded into the future collection-task feature.
- Rollback never deletes `runtime/longtian.sqlite3`; preserve or back it up before any manual reset.
