# Implementation worker brief

Implement the approved Toutiao account-connection task through the offline-ready gate.

## Ownership

You own the implementation and automated tests in:

- `third_party/MediaCrawler` for the typed `toutiao` auth platform, CLI safety boundary, explicit
  auth-only borrowed-Chrome path, tri-state official DOM proof, manual login reuse, cleanup, and
  normal Toutiao search regressions.
- `backend/` for the trusted Toutiao worker command/protocol and tests.
- Task evidence needed to describe automated verification, if useful.

Do not change the React product catalog or promote the backend Toutiao catalog entry to `enabled`
yet. The main session owns the real borrowed-Chrome positive gate and the final catalog/UI rollout.

## Non-negotiable boundaries

- Normal Toutiao `search` must still ignore CDP, use a fresh standard visible context, use optional
  `BrowserAuthStateStore`, separate Auth/Search Pages, and retain all existing stop/storage rules.
- Toutiao `auth` must borrow existing Chrome over loopback CDP, fail closed without a browser
  fallback, create/register one task-owned page, and close only that page.
- Auth mode must not touch search/detail/creator/comment/media/store/database or
  `BrowserAuthStateStore`.
- Connected requires a fresh official-page tri-state DOM result. Cookie, state-file, old-page, URL,
  helper completion, or exit status cannot decide success.
- Login/challenges are manual only. No QR extraction, Cookie injection, credential input, challenge
  inspection, retry/bypass, or secret-bearing output.
- Preserve `wb`, `dy`, and `ks` behavior. Cover all 12 ordered foreign-event directions after the
  supported auth union becomes four platforms.
- No real browser/login run, no commit, no push, and no unrelated refactor.

You are not alone in this repository. Preserve the active Trellis task files and any user-owned or
other-agent changes; accommodate them and do not revert them.

Run focused and maintained automated gates proportionate to your changes, then report exact files,
results, remaining external/baseline failures, and the real-positive rollout step left to main.
