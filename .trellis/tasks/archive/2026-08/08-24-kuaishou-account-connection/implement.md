# Implementation Plan

## Phase 0: Baseline

- [x] Record parent and MediaCrawler revisions and confirm both worktrees contain no unrelated
  changes.
- [x] Run focused current MediaCrawler auth/Kuaishou tests, backend tests, and frozen frontend gates.

## Phase A: MediaCrawler Kuaishou auth mode

- [x] Generalize the auth CLI allowlist and safety overrides to preserve the selected `wb | ks`.
- [x] Add the Kuaishou auth state machine, constant events, online precheck/recheck, and terminal
  return/exit behavior.
- [x] Add visible-page-only bounded Kuaishou login that never extracts QR bytes and leaves all
  official safety verification to the user.
- [x] Pass auth events through CDP startup, fail closed without standard-browser fallback, and close
  only task-owned pages.
- [x] Add regression tests for CLI safety, success/disconnected/browser failure, event order,
  no-collection sentinels, normal-mode compatibility, and cleanup ownership.

## Phase B: FastAPI multi-platform orchestration

- [x] Replace the Weibo-only command constant with a trusted platform-specific argument builder.
- [x] Validate version-1 events for `wb | ks` and reject events that do not match the active attempt.
- [x] Enable Kuaishou in the ordered catalog while preserving the global lock, state machine,
  timeouts, cancellation, process cleanup, and safe errors.
- [x] Expand service/API tests for exact command values, catalog responses, Kuaishou transitions,
  cross-platform protocol failures, Weibo regressions, and conflicts between platforms.

## Phase C: React Kuaishou connection UX

- [x] Derive the guidance target from the active or most recently checked enabled platform instead
  of hard-coding Weibo.
- [x] Make guidance copy platform-aware and explicitly manual for QR/security verification.
- [x] Update behavior tests for two enabled rows, Kuaishou mutation/polling, correct guidance,
  terminal results, global disablement, and unchanged coming-soon platforms.

## Phase D: Verification

- [x] Run MediaCrawler focused tests, maintained tests, compile/static checks, secret-pattern scan,
  and `git diff --check`.
- [x] Run backend locked sync, Ruff check/format, pytest, import/OpenAPI smoke, and `git diff --check`.
- [x] Run frontend frozen install, format check, Oxlint, TypeScript, Vitest, build, shadcn integrity,
  and loopback browser console/responsive smoke.
- [x] Run cross-layer loopback API/React transitions without starting a real auth task.

## Phase E: Real Chrome/Kuaishou acceptance

- [x] Record only the non-sensitive presence of a pre-existing sentinel tab.
- [x] Run the already-authenticated route when available; otherwise let the user complete the
  official visible login/challenge manually.
- [x] Confirm the online probe and React state reach connected, no collection/store path runs, and
  the sentinel tab/user Chrome survive success and cleanup.
- [x] Record non-sensitive transitions and ownership results in task research.

## Review and delivery

- [x] Run the Trellis full-scope check and update reusable specs if implementation exposes a new
  executable contract.
- [x] Present verification and real-acceptance evidence before requesting commit/push approval.
- [x] After approval, commit/push MediaCrawler first, then update and commit/push the parent gitlink
  with product changes.

## Rollback points

- Auth mode reaches search/detail/creator/comment/media/store code.
- Local Cookie or `passToken` evidence produces product `connected` without online `pong()`.
- CDP failure launches a fallback browser or cleanup closes a borrowed context/browser/tab.
- A child event for one platform changes another platform's state.
- A real run encounters an official challenge that would require automation to continue.
