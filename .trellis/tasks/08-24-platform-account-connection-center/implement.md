# Implementation Plan

## Phase 0: Preflight and baselines

- [x] Load the curated specs/research and start the task only after the user approved the final
  planning summary.
- [x] Record parent HEAD, MediaCrawler HEAD/gitlink, branch, and worktree status; preserve ignored
  `db_data/`, `logs/`, and any browser runtime data without reading or deleting them.
- [x] Run the current backend and frontend frozen quality gates plus relevant MediaCrawler tests to
  establish a passing baseline.

## Phase A: MediaCrawler authentication contract

- [x] Add the explicit `auth` CLI crawler type and tests proving existing crawler types are
  unchanged.
- [x] Add a versioned, constant-only authentication status emitter and parser tests; ensure no
  free-form or credential-bearing fields are allowed.
- [x] Enforce safe authentication-only config: existing visible Chrome, loopback CDP, no proxy,
  no explicit auth-state persistence, no comments/media/store/wordcloud/database work.
- [x] Refactor the Weibo authentication boundary so a failed post-login online probe exits non-zero
  and `connected` is emitted only after a successful `pong()`.
- [x] Keep the official Weibo SSO page visible but disable the separate QR image viewer in `auth`
  mode.
- [x] Add failing sentinels around search/detail/creator/comment/media paths and prove `auth` reaches
  none of them.

## Phase B: Borrowed Chrome ownership safety

- [x] Open Chrome's remote-debugging settings page when existing-browser CDP is unavailable,
  without taking ownership of that Chrome process.
- [x] Track task-created pages explicitly and close only those pages.
- [x] Change existing-browser cleanup so it never closes the borrowed context/browser and never
  terminates an unowned process; preserve owned-browser cleanup behavior.
- [x] Fail closed in Weibo `auth` mode when existing-browser CDP cannot connect; do not fall back to
  standard or dedicated contexts.
- [x] Bind program-owned CDP debug addresses to loopback and add ownership/cleanup regression tests.

## Phase C: FastAPI platform-connection service

- [x] Add exact Pydantic platform, status, guidance, attempt, list, and safe error models.
- [x] Add application lifespan ownership and an `Annotated` dependency for one
  `PlatformConnectionService`.
- [x] Implement the five-platform catalog with Weibo enabled and four explicit `coming_soon`
  entries.
- [x] Implement `GET /api/v1/platform-connections` and the HTTP 202 start-attempt endpoint.
- [x] Implement the one-at-a-time lock, attempt IDs, in-memory state transitions, bounded polling,
  UTC timestamps, and 409 conflict semantics.
- [x] Launch MediaCrawler through `asyncio.create_subprocess_exec` with fixed arguments and no shell;
  drain/discard ordinary output and validate only prefixed status events.
- [x] Implement timeout, cancellation, process-group termination, and lifespan shutdown without
  touching Chrome.
- [x] Cover exact API payloads, unsupported/unknown platforms, concurrency, event validation,
  success/disconnected/failure, timeout, and shutdown with fake subprocess tests.

## Phase D: React connection center

- [x] Add the runtime-validated platform-connections API boundary and safe error handling.
- [x] Add TanStack Query list/polling and mutation behavior with cancellation and targeted cache
  invalidation.
- [x] Reshape the home route into the approved connection-bus layout while preserving the compact
  local-service health indicator.
- [x] Render five platform rows, accurate status badges, current browser/login guidance, one Weibo
  action, and four honest `coming_soon` states.
- [x] Disable duplicate actions during active work; announce status changes through accessible live
  regions and retain visible focus/reduced-motion behavior.
- [x] Add behavior tests for load, backend failure/retry, all catalog states, start/conflict,
  polling, action guidance, success, disconnected, and technical failure.

## Phase D2: Administration-shell correction

- [x] Add only the shadcn `base-nova` primitives consumed by the shell, reviewing generated files,
  dependencies, aliases, and global token changes before keeping them.
- [x] Add a responsive application shell with the Longtian identity, compact health status, current
  route title, desktop sidebar, and accessible mobile navigation.
- [x] Register truthful `/` workbench and `/platform-accounts` routes; keep future modules disabled
  and labeled `规划中` instead of creating placeholder pages.
- [x] Move the existing connection workflow into the platform-accounts route without changing the
  platform API, polling, mutation, cancellation, or safe error behavior.
- [x] Build the workbench from real health/platform status plus explicit empty states only; do not
  fabricate collection totals, sentiment trends, alerts, or tasks.
- [x] Update behavior tests for route navigation, active state, disabled future items, mobile menu,
  workbench truthfulness, and the preserved connection workflow.
- [x] Run the full frozen frontend gate and loopback desktop/mobile browser smoke check with no
  console warnings, focus loss, or overflow.

## Phase D3: Project-skill design pass

- [x] Apply the project-local `ui-ux-pro-max` design-system, shadcn, React, navigation, and focus
  searches; record which evidence is accepted and which generic output is rejected.
- [x] Replace the custom desktop-aside/mobile-Sheet split with the reviewed shadcn Sidebar,
  SidebarProvider, and SidebarTrigger composition while preserving route semantics.
- [x] Refine the workbench into the ruled duty-ledger hierarchy using only truthful health and
  platform data; remove generic SaaS-card and English-eyebrow cues that do not help the operator.
- [x] Preserve the four-community watch mark, civic palette, Chinese typography, platform
  connection behavior, honest planned modules, and no-external-font constraint.
- [x] Enforce 44px narrow-screen targets, sticky-header focus clearance, visible focus, reduced
  motion, and responsive behavior at 375/768/1024/1440 widths.
- [x] Update behavior tests, run the frozen frontend gate, run shadcn integrity checks, and perform
  a fresh loopback desktop/mobile visual and console review without triggering authentication.

## Phase E: Automated verification

- [x] MediaCrawler: run focused auth/CDP/Weibo tests, the maintained `tests/` suite, compile/static
  checks, secret-pattern scan, and `git diff --check`; record any unrelated legacy failures.
- [x] Backend: run `uv sync --locked`, Ruff check, Ruff format check, pytest, and import/OpenAPI
  smoke checks.
- [x] Frontend under mise Node 24: frozen install, format, format check, Oxlint, TypeScript, Vitest,
  and Vite production build.
- [x] Cross-layer: run FastAPI and Vite on loopback, validate GET/POST/poll transitions with the
  browser console free of warnings or errors.
- [x] Visual: inspect desktop and narrow layouts for every terminal and active state, keyboard focus,
  reduced motion, and overflow.

## Phase F: Real Chrome/Weibo acceptance

- [x] Before connecting, open a harmless sentinel tab in the user's Chrome and record only its
  non-sensitive presence.
- [x] Run an already-logged-in path when available and verify the first online probe reaches
  `connected` without a QR prompt.
- [x] If the account is not logged in, let the user complete the official visible login manually;
  do not automate any challenge.
- [x] Verify the React page progresses through real states and ends at `connected` only after the
  online probe succeeds.
- [x] Stop/cancel the backend worker and prove the sentinel tab and user's Chrome remain open and
  usable, task-created pages are closed, ports are loopback-only, and no crawler content was stored.
- [x] Record only timestamps, state transitions, exit category, page/process counts, and ownership
  results; never record credential or QR material.

## Review, knowledge capture, and delivery

- [x] Run the Trellis full-scope check against the curated check manifest and fix in-scope findings.
- [x] Use `trellis-update-spec` if the subprocess protocol or borrowed-browser ownership establishes
  a reusable executable contract.
- [x] Re-run every affected gate after review/spec changes and present the result before Git delivery.
- [x] After separate user approval to commit/push, commit and push the MediaCrawler derivative first,
  verify the revision is reachable and clean, update the parent gitlink, then commit/push the parent
  with Conventional Commits.

## Rollback points

- Borrowed Chrome closes or mutates a pre-existing tab/context: stop immediately; do not continue
  real login testing until ownership cleanup is corrected.
- Authentication-only mode reaches a collection/store path: fail the task and restore the pre-task
  derivative revision before redesigning the boundary.
- Child protocol leaks or permits arbitrary text/metadata: stop API integration and narrow the
  protocol before continuing.
- Parent/backend environment imports MediaCrawler: stop and restore subprocess isolation.
- MediaCrawler submodule or user runtime data contains unrelated changes: report the exact overlap;
  never reset or delete user-owned data automatically.
