# Implementation Plan

## Phase A — MediaCrawler authentication boundary

- [x] Extend the shared auth platform enum and CLI allowlist to exact `wb | dy | ks | xhs | toutiao`;
      update error text and configuration tests while preserving all auth safety overrides.
- [x] Add the constant-only XHS auth-event wrapper and early auth-only branch in
      `XiaoHongShuCrawler`, using only borrowed visible Chrome and one registered task Page.
- [x] Add the visible-page-only XHS login wait path that never extracts QR material, fills inputs, or
      manipulates challenges; keep ordinary qrcode/mobile/cookie paths unchanged.
- [x] Make the existing official `pong()` the sole terminal success proof before and after manual
      login, refreshing allowlisted browser cookies before the second check.
- [x] Add independent event-sequence, cleanup, CDP-failure, timeout/cancellation, negative-proof,
      no-QR-extraction, no-state-store, and no-collection tests.
- [x] Regress ordinary XHS authentication-state ordering and search/detail/creator behavior.

## Phase B — FastAPI and React rollout

- [x] Extend the trusted FastAPI auth platform type/mapping/parser to XHS and parameterize all 20
      directed cross-platform event mismatches.
- [x] Keep XHS unavailable while worker behavior is under test; after the positive rollout gate,
      change only its catalog entry to `enabled/not_checked`.
- [x] Update backend catalog, command, lifecycle, timeout/cancellation, restart-reset, and protocol
      tests for five enabled platforms without adding persistence.
- [x] Update React fixtures and behavior tests so XHS has the generic detection action, polling,
      manual guidance, disabled-while-active behavior, and accessible terminal status.
- [x] Update workbench expectations to catalog-derived `0..5 / 5` and verify that no platform remains
      “暂不可用”; do not introduce XHS-specific UI components.

## Phase C — Quality and real acceptance

- [x] Run MediaCrawler formatting/lint/type-appropriate checks, auth/XHS targeted tests, maintained
      full tests, compileall, diff check, and secret/QR-material scan.
- [x] Run backend frozen environment setup, Ruff format/lint, all pytest tests, header hook, and
      cross-platform protocol checks.
- [x] Run frontend frozen install, formatter, ESLint, TypeScript, Vitest, production build, and a
      loopback browser smoke check with zero new console errors/warnings.
- [x] Start a real attempt through React/FastAPI using the user's approved Chrome; if needed, have the
      user complete login/challenge in the official page, then verify worker/API/UI all reach
      `connected` from a fresh `pong()`.
- [x] Confirm sentinel tabs and Chrome survive, only the task Page closes, loopback ownership remains
      intact, no collection/state-store calls occur, and evidence contains no credential, QR, identity,
      page-content, or Profile-path material.
- [x] Promote XHS to enabled only after the real positive gate and rerun all affected
      catalog/readiness automated tests after promotion.
- [x] Run a fresh loopback UI smoke check after promotion with five actions, `0..5 / 5` readiness,
      no unavailable platform, and zero new console errors or warnings.

## Phase D — Review and delivery

- [x] Perform Trellis full-scope implementation review across MediaCrawler, FastAPI, React, ordinary
      XHS compatibility, security boundaries, and real-browser evidence; address verified findings.
- [x] Update project platform-connection specs if the fifth-platform rollout establishes a reusable
      contract or new XHS-specific gotcha.
- [x] After explicit delivery approval, commit and push the MediaCrawler derivative `main`, verify the
      remote revision, then commit the parent gitlink, application changes, specs, and task artifacts
      directly to parent `main`.
- [ ] Archive this Trellis task and record the developer journal; do not create a PR or Codex branch.

## Validation commands

Exact file lists may be narrowed during implementation, but the final gate includes:

```text
third_party/MediaCrawler/.venv/bin/ruff format --check <changed Python files>
third_party/MediaCrawler/.venv/bin/ruff check <changed Python files>
third_party/MediaCrawler/.venv/bin/pytest -q tests
backend/.venv/bin/ruff format --check backend/src backend/tests
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pytest -q backend/tests
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend format:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
git diff --check
git submodule status --recursive
```

## Rollback points

- If no stable real positive `pong()` exists from borrowed Chrome, keep XHS `coming_soon` and do not
  claim delivery.
- If visible login requires QR extraction or challenge automation, stop at the official page and keep
  the platform unavailable rather than widening automation.
- If auth mode reaches storage/collection, launches fallback Chrome, persists state, or closes a
  user-owned resource, revert the auth branch before further testing.
- If ordinary XHS crawler regression fails, restore its original lifecycle and separate the auth path
  more strictly before rollout.
