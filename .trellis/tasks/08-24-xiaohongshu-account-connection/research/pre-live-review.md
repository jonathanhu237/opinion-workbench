# XHS account connection pre-live review

Date: 2026-08-24

> Historical checkpoint: this document records the state before real acceptance. The positive
> rollout gate and final enabled-catalog results are recorded in `implementation-results.md`.

## Scope and rollout state

This review covered the MediaCrawler authentication boundary, FastAPI protocol and gated catalog,
React rollout behavior, ordinary XHS compatibility, and non-sensitive loopback UI state. It did not
start a real XHS attempt or interact with the user's Chrome. XHS remains `coming_soon`, and the live
positive gate, borrowed-browser ownership evidence, and catalog promotion remain pending.

## Finding fixed

`XiaoHongShuClient.pong()` previously used Python truthiness for
`data.result.success`. A drifted response such as the string `"false"` or integer `1` could therefore
be misclassified as authenticated. The check now accepts only the JSON boolean `true` (`is True`),
with regressions for false, string, numeric, object, missing, and null response shapes. Exception
details also remain absent from the online-probe log path.

The platform-connection code-spec was synchronized to distinguish the five-platform trusted worker
allowlist from catalog availability, and now records the XHS online-proof/manual-login contract and
all 20 directed cross-platform mismatch cases.

## Verified boundaries

- Auth CLI forces visible borrowed Chrome, loopback CDP, QR-code login mode, no proxy, no explicit
  auth-state persistence, no IDs/keywords, and every collection/storage toggle off for XHS.
- The XHS auth branch returns before proxy-pool, `BrowserAuthStateStore`, collection, and storage
  paths. CDP failure does not fall back to a standard or dedicated browser.
- One task-created Page is registered immediately and only `close_owned_pages()` is called on
  success, failure, timeout, and cancellation; borrowed context/browser/process cleanup is not
  called by the auth branch.
- The task Page freshly navigates to the domestic official homepage. The first and post-login
  decisions use the existing signed official self-info `pong()`; current allowlisted browser
  Cookies are refreshed before follow-up checks.
- Cookie/UI changes only wake another online check. The visible-page helper does not call QR
  extraction/display, fill inputs, inject Cookies, or automate a challenge. It clicks the ordinary
  login entry at most once and waits with a bounded, low-frequency loop.
- Ordinary XHS state restore/save ordering, QR viewer behavior, search/detail/creator guards, and
  standard-browser fallback remain covered by the maintained tests.
- FastAPI trusts exactly `wb | dy | ks | xhs | toutiao`, builds the fixed argv vector, rejects all 20
  directed cross-platform event mismatches, and still returns HTTP 409 for XHS while its catalog row
  is unavailable.
- React accepts the post-rollout XHS shape and covers generic start, polling, manual guidance, and
  `5 / 5` readiness without an XHS-specific component. The current gated catalog still renders
  `0 / 4`, four detection actions, and XHS as the only unavailable platform.

## Verification

- MediaCrawler Ruff format/lint on changed Python files: passed.
- MediaCrawler targeted auth/XHS/CDP tests: 103 passed.
- MediaCrawler maintained test suite: 367 passed; one existing SQLAlchemy deprecation warning.
- MediaCrawler compileall and Python file-header hook: passed.
- FastAPI Ruff format/lint: passed; backend tests: 94 passed.
- Frontend frozen install, Prettier, Oxlint, TypeScript, Vitest, and production build: passed; 33
  tests passed. The build retained the existing chunk-size advisory.
- Loopback smoke: Workbench rendered `0 / 4`; the account page rendered five rows, four detection
  actions, one unavailable row, and no horizontal overflow. No application JavaScript warning or
  error was observed. The Playwright browser made an existing `/favicon.ico` request that returned
  404; this is unrelated to the XHS path and was not widened into this task.
- Parent and submodule `git diff --check`, submodule metadata, and changed-content sensitive-pattern
  review: passed. No credential, QR, account-identity, page-content, or Profile-path evidence was
  recorded.
- Temporary loopback ports 8000 and 5176 and the smoke browser were closed after validation.

## Remaining gate

Run the real React/FastAPI/MediaCrawler attempt with the user's approved Chrome. Require a fresh
positive XHS `pong()`, then verify Chrome and all pre-existing tabs survive, only the task Page is
closed, loopback ownership remains intact, and no collection or auth-state persistence occurs. Only
after that gate may XHS change to `enabled/not_checked`, followed by the five-enabled catalog tests
and a fresh UI smoke check.
