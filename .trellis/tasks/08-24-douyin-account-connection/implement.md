# Implementation Plan

## Phase 0: Baseline and online-probe spike

- [x] Record parent and MediaCrawler revisions and classify both worktrees.
- [x] Run the current auth/CDP/manual-slider, backend, and frozen frontend baseline gates.
- [x] Identify and test a read-only fresh Douyin official-page signal for connected, anonymous, and
      inconclusive states without reading account identity or credentials.
- [x] Stop planning execution and keep Douyin unavailable if no fail-closed online proof can be
      demonstrated.

## Phase A: MediaCrawler Douyin auth mode

- [x] Extend the typed auth platform/CLI allowlist to exact `wb | dy | ks` while preserving all
      auth-only safety overrides.
- [x] Add the Douyin auth state machine, constant platform events, online precheck/recheck, bounded
      terminal behavior, and stable exit mapping.
- [x] Add visible-page-only manual login that opens the official UI but never extracts QR bytes,
      fills credentials, or automates slider/CAPTCHA handling.
- [x] Pass auth events through CDP startup, fail closed without standard-browser fallback, and close
      only task-owned pages.
- [x] Add regression tests for online proof vs stale local state, CLI safety, event order, browser
      failure, timeouts/cancellation, no-collection sentinels, cleanup ownership, and normal-mode
      compatibility.

## Phase B: FastAPI orchestration

- [x] Extend the trusted auth platform type/mapping and exact worker command to `dy`.
- [x] Enable Douyin in the ordered catalog only after the worker readiness gate passes.
- [x] Expand protocol tests across all three supported platforms, including every relevant
      cross-platform event mismatch and state-isolation assertion.
- [x] Verify the global lock, progress mapping, terminal timestamps, timeout, cancellation,
      process-group cleanup, and Weibo/Kuaishou compatibility.

## Phase C: React connection UX

- [x] Make the catalog fixture and account-center behavior treat Douyin as the third enabled row.
- [x] Verify Douyin mutation/polling, platform-aware manual-login guidance, terminal result, and
      duplicate-action disablement.
- [x] Derive workbench enabled-platform names and `0..3 / 3` readiness copy from API data rather
      than hard-coded platform pairs.
- [x] Preserve Xiaohongshu/Toutiao coming-soon behavior, accessibility, responsive layout, and
      shadcn component usage.

## Phase D: Automated verification

- [x] Run MediaCrawler focused and maintained tests, compile/static/pre-commit checks,
      secret/no-collection scans, and `git diff --check`.
- [x] Run backend frozen sync, Ruff format/check, pytest, import/OpenAPI/API smoke, and
      `git diff --check`.
- [x] Run frontend frozen install, Prettier, Oxlint, TypeScript, Vitest, build, shadcn integrity,
      desktop/mobile loopback smoke, and console inspection.
- [x] Run cross-layer loopback transitions without starting a real authentication task.
- [x] Dispatch the Trellis full-scope check and fix verified findings.

## Phase E: Real Chrome/Douyin acceptance

- [x] Record only the non-sensitive presence/count of pre-existing Chrome tabs.
- [x] Run the already-authenticated fast path when available; otherwise let the user complete the
      official visible login, QR/SMS, or safety challenge manually.
- [x] Confirm the fresh online probe and React state reach `connected`; verify no collection/store
      path runs.
- [x] Confirm user Chrome and pre-existing tabs survive, the task-owned Douyin page is cleaned up,
      and no secret/page-content evidence is retained.

## Review and delivery

- [x] Update the platform-connection executable spec from `wb | ks` to `wb | dy | ks`, including
      the fail-closed online-proof and cross-platform event contract.
- [x] Present automated and real-acceptance evidence and request commit/push approval.
- [ ] After approval, commit/push MediaCrawler first, then the parent product changes and gitlink;
      archive the task and record the journal.

## Rollback points

- The online probe cannot reliably distinguish connected, anonymous, and inconclusive official
  page states.
- Local Cookie/LocalStorage/UI hints or exit code alone can produce product `connected`.
- Auth mode extracts QR material, fills credential fields, automates a slider/CAPTCHA, or reaches
  search/detail/creator/comment/media/store/database code.
- CDP failure launches fallback Chrome, or cleanup closes borrowed context/browser/user pages.
- A child event for one platform mutates another platform, or existing Weibo/Kuaishou behavior
  regresses.
