# Implementation Plan

## Phase 0: Baseline and online-proof spike

- [x] Record parent and MediaCrawler revisions and classify both worktrees without modifying
      user-owned runtime data.
- [x] Run the current Toutiao parser/crawler/auth-state suite, shared auth/CDP tests, backend tests,
      and frozen frontend gates.
- [x] Validate the current official-page DOM classifier against fresh official-page and synthetic
      anonymous/challenge states, and define exact connected/disconnected/inconclusive shapes
      without returning identity or page text.
- [x] Stop catalog promotion and keep Toutiao `coming_soon` if a stable fail-closed classifier
      cannot be demonstrated.

## Phase A: MediaCrawler Toutiao auth mode

- [x] Extend the typed auth platform and CLI allowlist to exact `wb | dy | ks | toutiao`, preserving
      every auth-only safety override.
- [x] Split Toutiao startup into explicit auth and search paths so auth borrows Chrome/CDP while
      normal search still always launches a fresh standard context and uses `BrowserAuthStateStore`.
- [x] Add the Toutiao constant-event state machine, fresh online precheck/recheck, bounded manual
      official login, terminal return/exit behavior, and credential-free failures.
- [x] Fail closed on CDP startup with no standard-browser fallback and close only the registered
      task Page in every terminal/cancellation path.
- [x] Add no-collection/no-store/no-auth-state sentinels and regressions for CLI overrides, tri-state
      classification, event order, challenge/timeout, browser failure, cleanup ownership, and normal
      search isolation.

## Phase B: FastAPI orchestration

- [x] Extend the trusted auth platform type, mapping, and exact worker command to `toutiao`.
- [x] Keep Toutiao unavailable until real-positive acceptance; then promote only its catalog entry
      to `enabled/not_checked`.
- [x] Expand protocol tests to all four platforms and all 12 ordered foreign-event mismatches,
      asserting no unrelated platform state changes.
- [x] Verify 202 projection, global single-flight conflicts, progress/terminal mapping, timestamp,
      timeout, shutdown cancellation, process-group cleanup, and existing platform compatibility.

## Phase C: React connection UX

- [x] Update default catalog fixtures and account-center behavior to expose Toutiao as the fourth
      enabled action only after the rollout gate passes.
- [x] Verify Toutiao mutation/polling, platform-aware manual-login guidance, terminal result,
      duplicate-action disablement, and safe API errors.
- [x] Verify workbench readiness remains data-derived and renders `0..4 / 4`; preserve Xiaohongshu
      coming-soon behavior and avoid platform-specific UI duplication.
- [x] Preserve shadcn component usage, keyboard/live-region behavior, visible focus, mobile 44 px
      targets, responsive layout, and no-console-error behavior.

## Phase D: Automated verification

- [x] Run MediaCrawler focused and maintained tests, compile/static/pre-commit checks,
      secret/no-collection scans, and `git diff --check`.
- [x] Run backend frozen sync, Ruff format/check, pytest, import/OpenAPI/API smoke, and
      `git diff --check`.
- [x] Run frontend frozen install, Prettier, Oxlint, TypeScript, Vitest, production build, shadcn
      integrity, and desktop/mobile loopback smoke.
- [x] Run cross-layer loopback state transitions without starting a real authentication task.
- [x] Dispatch the Trellis full-scope checks and fix verified findings before and after real
      acceptance.

## Phase E: Real Chrome/Toutiao acceptance

- [x] Record only a non-sensitive baseline count/presence of pre-existing Chrome tabs.
- [x] Run the already-authenticated fast path when available; otherwise let the user complete the
      official visible login, QR/phone flow, or safety challenge manually.
- [x] Confirm the fresh official DOM proof and React state reach `connected`, the worker exits
      normally, and search/store/explicit auth-state paths remain untouched.
- [x] Confirm Chrome and all pre-existing tabs survive, the task-owned Toutiao Page is cleaned up,
      and no credential, identity, Profile path, challenge details, or page content is retained.
- [x] Promote Toutiao to `enabled/not_checked` only after the positive and ownership gates pass;
      otherwise leave it `coming_soon` and record the non-sensitive stop condition.

## Review and delivery

- [x] Update the executable platform-connection spec from `wb | dy | ks` to
      `wb | dy | ks | toutiao`, including the separate normal-search browser contract and Toutiao
      tri-state online proof.
- [x] Present automated and real-acceptance evidence and request commit/push approval.
- [ ] After approval, commit/push MediaCrawler first, then update and commit/push the parent gitlink
      with backend/frontend/spec/task changes; archive the Trellis task and record the journal.

## Rollback points

- The fresh official page cannot reliably distinguish connected, anonymous, and inconclusive DOM
  states.
- Cookie/state-file/old-page evidence or helper completion can produce `connected` without the
  mandatory online recheck.
- Auth mode extracts QR material, injects Cookie, automates a challenge, or reaches
  search/detail/creator/comment/media/store/database/`BrowserAuthStateStore` code.
- Toutiao auth launches a fallback browser, or cleanup closes a borrowed context/browser/user page.
- Adding auth changes the normal Toutiao search path's fresh-context, separate-page, state-store,
  single-navigation, stop-condition, or storage behavior.
- A foreign child event mutates another platform or existing Weibo/Douyin/Kuaishou behavior
  regresses.
