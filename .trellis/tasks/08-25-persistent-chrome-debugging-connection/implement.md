# Implementation Plan

## Phase A — Preserve platform behavior behind an injected browser boundary

- [x] Extract the current authentication-safe global configuration into one shared MediaCrawler
      function and use it from the existing v1 CLI path without changing its exact overrides.
- [x] Extract an injected `BrowserContext`/`CDPBrowserManager` auth body for Weibo, Douyin,
      Kuaishou, Xiaohongshu, and Toutiao; keep each existing one-shot wrapper and its v1 event/exit
      behavior intact.
- [x] Preserve each platform's authoritative online proof, visible manual-login boundaries,
      timeouts, post-login recheck, no-collection guarantees, and task-page-only `finally` cleanup.
- [x] In persistent borrowed auth, remove Douyin's context-wide stealth injection while retaining
      Kuaishou's page-local signing script; add targeted regressions for both boundaries.
- [x] Run the existing five-platform auth suites after the extraction before adding the persistent
      worker, so any behavior drift is isolated to this phase.

## Phase B — Build the MediaCrawler v2 persistent worker

- [x] Add strict protocol-v2 command/event models, duplicate-key-safe and size-bounded NDJSON
      parsing, constant-only emitters, and exact request UUID/platform correlation. Keep v1 decoding
      separate and unchanged.
- [x] Add the fixed persistent-worker entry point and a responsive sequential command dispatcher
      supporting `ready`, `check`, matching `cancel`, `shutdown`, `progress`, `result`,
      `session/disconnected`, and `stopped`.
- [x] Add a worker-scoped browser session that manually starts Playwright only on the first check,
      connects once with `is_local=True` and `no_defaults=True`, borrows the existing default
      BrowserContext, and registers disconnect handling.
- [x] Make borrowed zero-context behavior fail closed; do not create an incognito context. Reapply
      auth-safe configuration before every serialized request.
- [x] Close only explicitly registered request pages on terminal, error, timeout, cancellation, and
      shutdown paths. Release the shared browser references and stop Playwright without closing the
      default context, Browser, or Chrome.
- [x] Add worker/protocol/fake-browser tests for lazy startup, two-platform identity reuse,
      one-connect behavior, request ordering, busy rejection, cancellation, graceful/forced
      shutdown, idle/busy disconnect, malformed input, and credential-free output.
- [x] Run the full maintained MediaCrawler test suite and diff/secret checks before changing the
      parent backend.

## Phase C — Switch FastAPI to a lifespan-owned persistent worker client

- [x] Separate long-lived worker transport/process state from the existing bounded active-attempt
      state, preferably in a focused service module while keeping `PlatformConnectionService` as
      the product-state owner.
- [x] Extend the injected fake process/launcher seam with stdin, a persistent stdout reader,
      stderr drain, process waiter, ready future, active-result future, and monotonically increasing
      worker generation.
- [x] Launch the worker only inside the first accepted background attempt; wait for `ready`, send
      one exact v2 `check`, and map validated progress/results back to the unchanged public catalog.
- [x] Retain global single-flight locking and exact HTTP 404/409/202 behavior. Match every event to
      the active request UUID and platform before changing any row.
- [x] Implement the single idempotent recycle path for malformed/oversized/out-of-order IPC,
      writer failure, unexpected EOF/exit, stale callbacks, and worker crash. Implement the healthy
      Chrome session-disconnect event as a separate invalidation path; in both cases invalidate all
      stale connected projections and reconnect only after a later POST.
- [x] Implement bounded attempt timeout through `cancel`, worker shutdown through `shutdown`, and
      existing TERM/KILL process-group fallback without ever signalling the user's Chrome.
- [x] Adapt and extend backend tests for zero-launch startup/GET, same-process multi-platform reuse,
      conflict behavior, exact result proof, cancellation/shutdown, disconnect invalidation,
      generation races, protocol failure matrix, and credential-sentinel non-disclosure.
- [x] Keep the existing public schemas, route signatures, OpenAPI shapes, and product error messages
      unchanged; add no bulk route or worker/session response field.

## Phase D — Compatibility and user-facing verification

- [x] Retain current React production code unless a compatibility defect is discovered. Keep the
      serialized five-platform queue, row polling, active-action locking, and existing browser/login
      guidance.
- [x] Add or adapt frontend fixtures/tests for first approval guidance, subsequent direct checking,
      disconnect-driven failure, unchanged exact response decoding, batch sequencing, and safe
      error rendering.
- [x] Update `.trellis/spec/backend/platform-connection-guidelines.md` from the v1-per-attempt
      lifecycle to the lifespan-owned v2 worker contract while preserving v1 rollback, platform
      proof rules, page ownership, loopback, and secret boundaries.
- [x] Update other project specs only where implementation establishes a reusable new contract;
      avoid documenting task-specific internals as general policy.

## Phase E — Quality gates and live Chrome acceptance

- [x] Run MediaCrawler formatting/lint/type-appropriate checks, targeted worker/auth tests, full
      maintained tests, compile checks, and secret/protocol scans.
- [x] Run backend frozen-environment Ruff format/lint, full pytest suite, OpenAPI/headers checks, and
      `git diff --check`.
- [x] Run frontend frozen install, formatter, ESLint, TypeScript, Vitest, production build, and a
      loopback browser smoke check with no new console errors or responsive overflow.
- [x] Verify live that starting FastAPI and opening React causes no worker/CDP connection or native
      prompt before the first platform POST.
- [x] Approve one real Chrome connection, check at least two different platforms and repeat one
      check, then run the full serialized batch; verify one worker generation, one
      `connect_over_cdp` call, and no further native approval while the session stays alive.
- [x] Keep a pre-existing sentinel tab open and verify each attempt closes only its own pages;
      stopping FastAPI must leave Chrome and the sentinel tab open.
- [x] Deliberately disconnect Chrome or the worker, verify active/stale connected state fails closed,
      and verify the next explicit check lazily creates a new approval flow.
- [x] Record only non-sensitive counters, constants, timestamps, loopback address, and ownership
      results; record no URLs beyond a fixed sentinel, account identity, Cookies, headers, QR data,
      page content, profile paths, WebSocket endpoints, or raw stderr.

## Phase F — Review and delivery

- [x] Perform a Trellis full-scope check across MediaCrawler, backend lifecycle/IPC, frontend
      compatibility, shutdown and failure recovery, specs, tests, and live evidence; address all
      verified findings.
- [x] Commit and push the MediaCrawler derivative first, verify the revision is reachable on its
      configured remote, and leave the submodule clean.
- [x] Update the parent gitlink only after the derivative push; validate mode `160000`, recursive
      submodule status, parent frozen gates, and `git diff --check`.
- [ ] After explicit delivery approval, create Conventional Commits directly on `main`, push the
      parent repository, archive the Trellis task, and record the developer journal. Do not create a
      PR or Codex branch.

## Verification Evidence

- Automated gates: MediaCrawler `412 passed` with one pre-existing SQLAlchemy deprecation warning;
  backend Ruff/compileall and `87 passed`; frontend frozen install, format, lint, typecheck,
  `33 passed`, and production build succeeded with the existing 500 kB advisory chunk warning.
- Lazy-start live check: FastAPI startup, React availability, and the initial platform `GET`
  produced no `tools.auth_worker` process and no Chrome approval prompt.
- Reuse live check: one approval established worker generation PID `72156`; `wb`, `dy`, `ks`, `xhs`,
  and `toutiao` all reached their authoritative `connected` result serially, and a repeated `wb`
  check completed on the same PID without another approval.
- Reconnect live check: after an intentional FastAPI reload ended the first connection, the next
  explicit `wb` check entered `approve_connection`, a new approved worker PID `73733` connected,
  and no automatic reconnect occurred before that user action.
- Ownership live check: with the second CDP connection active, a fixed `https://example.com`
  sentinel tab existed. Stopping FastAPI removed the worker while Chrome PID `33919` and the
  sentinel remained. FastAPI was restarted on `127.0.0.1:8000`, the frontend remained on
  `127.0.0.1:5173`, and the temporary sentinel was then removed.
- Evidence contains only fixed loopback addresses, process IDs, platform/result constants, counts,
  and ownership outcomes; no account identity, Cookie, header, QR, page-content, profile, WebSocket,
  or raw child-output material was recorded.

## Validation commands

Exact changed-file lists may be narrowed during implementation. The final gate includes:

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
git -C third_party/MediaCrawler status --short
```

## Rollback points

- If injected-context extraction changes a platform's authoritative proof, visible manual-login
  boundary, v1 protocol, or ordinary crawler behavior, restore the wrapper and isolate the shared
  body before continuing.
- If a persistent worker cannot deterministically correlate requests, close only owned pages, or
  prevent overlapping platform tasks, do not switch the backend from v1.
- If Chrome/worker disconnect can leave a false connected projection, or shutdown can close Chrome
  or a pre-existing tab, block delivery and recycle the ownership design.
- If the live run produces another approval without a real CDP disconnect, treat it as a failed
  acceptance gate; do not claim the prompt problem is solved from unit tests alone.
- Keep the one-shot v1 path for one release so operational rollback changes only the backend worker
  strategy and requires no public API or React rollback.
