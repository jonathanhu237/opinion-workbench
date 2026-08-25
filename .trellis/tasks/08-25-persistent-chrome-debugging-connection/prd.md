# 常驻 Chrome 调试连接

## Goal

Reuse one user-approved Chrome DevTools Protocol connection across platform-account checks so the
single-user application does not request remote-debugging approval for every platform or every
repeat check, while continuing to borrow the user's normal visible Chrome profile.

## Background

- Current platform checks start one bounded MediaCrawler subprocess per platform. Each subprocess
  calls Playwright `connect_over_cdp`, so current Chrome approval mode treats every check as a new
  incoming debugging connection.
- Chromium's approval-mode implementation requires user approval for each incoming connection. It
  intentionally has no application allowlist or permanent `always allow` action.
- The user accepts that the local application will retain full debugging control of the daily
  Chrome session while the backend is running, in exchange for authorizing only once per runtime.
- The existing frontend already serializes individual and batch checks; the backend also rejects a
  second active authentication attempt.

## Requirements

- Establish the borrowed-Chrome CDP connection lazily on the first platform check. Do not display
  the Chrome permission dialog merely because FastAPI or the React application starts.
- Keep one MediaCrawler-owned CDP connection alive and reuse it for all subsequent individual and
  batch platform checks until Chrome disconnects, the persistent worker exits, or FastAPI shuts
  down.
- Preserve one-at-a-time platform authentication. A persistent connection must not permit
  concurrent page operations or overlapping platform attempts.
- Keep MediaCrawler execution isolated from the FastAPI Python environment through an owned worker
  process and a narrow, versioned, constant-only IPC protocol.
- Preserve the existing public `GET /platform-connections` and per-platform `POST .../attempts`
  contracts unless research proves a compatible extension is required. The React batch queue must
  not need a new bulk API.
- Retain authoritative platform-specific online probes and the existing manual login/safety
  challenge boundaries. Reusing a browser connection must never turn Cookie presence, URL state,
  or a previous result into proof of authentication.
- Track and close only pages created for application checks. Never close a pre-existing tab,
  borrowed BrowserContext, the user's Chrome process, or the shared browser connection as part of
  an individual platform attempt.
- On FastAPI shutdown, terminate the owned worker cleanly and release the CDP connection without
  closing Chrome. On worker crash or Chrome disconnect, fail the active attempt safely, clear the
  stale worker state, and reconnect lazily on the next user action; that reconnection may require a
  new Chrome approval.
- Keep commands, events, errors, logs, tests, and stored state free of Cookies, authorization
  headers, page content, QR material, profile paths, and account identity.
- Keep all CDP and application control endpoints loopback-only. Do not add a remote listener,
  authentication bypass, Chrome policy, hidden browser, or dedicated application Profile.

## Acceptance Criteria

- [x] During one uninterrupted FastAPI + persistent-worker + Chrome runtime, approving the first
      platform check permits later individual checks and a full five-platform batch without another
      Chrome remote-debugging approval dialog.
- [x] Starting FastAPI and opening the React application causes no CDP connection and no Chrome
      approval dialog before the user requests a platform check.
- [x] Every platform attempt remains serialized and uses the same live worker/CDP session; a second
      attempt still receives the existing safe conflict behavior.
- [x] The five platform authentication flows retain their existing progress events, authoritative
      terminal checks, manual login boundaries, timeouts, and task-page-only cleanup.
- [x] FastAPI shutdown, worker crash, malformed IPC, Chrome disconnect, and request cancellation do
      not close the user's Chrome or pre-existing tabs and cannot leave a false `connected` result.
- [x] After a worker or Chrome disconnect, the next explicit check starts a fresh lazy connection
      and clearly enters the existing browser-approval guidance when Chrome asks again.
- [x] Existing platform connection API and frontend behavior tests continue to pass without a new
      batch endpoint or credential-bearing payload.
- [x] Backend, MediaCrawler-derived, and frontend frozen quality gates pass; live loopback acceptance
      demonstrates one approval followed by at least two different platform checks over one CDP
      connection, with only non-sensitive evidence recorded.

## Key Product Decisions

- The user explicitly accepts that, after approving the first CDP connection, the application can
  control the normal daily Chrome session for as long as the backend-owned worker and Chrome remain
  connected.
- The connection lifetime is bounded by the current FastAPI/worker/Chrome runtime. Restarting any
  of them, or losing the CDP transport, may require a new approval on the next explicit check.
- FastAPI must not import the MediaCrawler runtime. One persistent MediaCrawler subprocess owns
  Playwright, the borrowed default BrowserContext, and all platform-specific authentication code.
- The worker is started lazily and remains serial. Long-lived browser access does not broaden the
  product into concurrent automation, collection, or background surveillance.
- No new worker/session indicator or control is required in the UI. Existing row states and
  guidance remain the product surface, and the existing public API remains compatible.

## Out of Scope

- Eliminating the first approval after Chrome, FastAPI, or the persistent worker restarts.
- Switching to an application-specific Chrome Profile, Chrome for Testing, or a hidden browser.
- Concurrent platform checks, collection/search tasks, scheduled crawling, or multi-user support.
- Automating Chrome's approval dialog, platform login, CAPTCHA, slider, SMS, or safety verification.
- Persisting a Playwright/CDP object across operating-system restarts.

## Constraints and Accepted Risks

- Chrome approval mode authorizes every new incoming CDP connection. The application can avoid
  repeated prompts only while the exact Playwright/CDP connection remains alive; it cannot offer a
  safe or supported “always allow” guarantee.
- A long-lived CDP connection has full debugging authority over the user's normal Chrome profile.
  The accepted mitigations are loopback-only transport, a user-triggered lazy connection, strict
  process ownership, no credential transport, serialized checks, and clean shutdown.
- A forced worker kill may leave a task-created platform tab open if its cleanup cannot run. It must
  still never close Chrome or a pre-existing user tab.
- Native Chrome prompt count cannot be proven by mocks. Automated tests must prove one worker and
  one `connect_over_cdp` call; a live two-platform run must verify the real approval behavior.
- Borrowed mode must fail when Chrome exposes no existing default BrowserContext. It must not create
  an incognito context that lacks the user's login state.
- Persistent borrowed authentication must not install context-wide scripts or defaults that affect
  the user's future tabs. In particular, Douyin authentication must not add its current
  context-wide stealth script, and CDP attachment should use Playwright's `no_defaults` mode.
