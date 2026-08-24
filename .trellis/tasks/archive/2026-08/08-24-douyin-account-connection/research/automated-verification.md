# Automated verification

Date: 2026-08-24 (Asia/Shanghai)

## Baseline and rollout state

- Parent baseline revision: `02dee9516fb5ddc13fe66bf09a8042f11bd289c0`.
- MediaCrawler baseline revision: `18083e5d7dd70e0ced6bad536e7cd1cc4b577a89`.
- The parent initially contained only the untracked active task artifacts; MediaCrawler was clean.
- The worker CLI, typed event protocol, and backend trusted command mapping now accept exact
  `wb | dy | ks`.
- The initial automated stage kept Douyin `coming_soon` and did not start a real authentication
  POST. After the separate real logged-in positive acceptance succeeded, the rollout-only change
  enabled Douyin in the backend catalog and default React fixture.

## Online probe

- A fresh, anonymous system-Chrome context ran the production probe against the official Douyin
  page and returned only `disconnected`.
- Unit coverage verifies `connected`, `disconnected`, `inconclusive`, unknown return values, and
  navigation failure. The probe navigates a fresh official page, performs a no-store same-origin
  account request, and returns only one constant result.
- Official account identity and raw response data remain in the page and are discarded. The probe
  contains no Cookie or LocalStorage read. Local markers exist only in the visible-login helper as
  changed-since-start wake-up hints for a mandatory online recheck.

## MediaCrawler derivative

- Final focused auth/CDP/manual-slider suite: `85 passed`.
- Final maintained `tests/` suite: `277 passed`.
- Full repository pytest after independent review: `286 passed`, `8 skipped`, `6 failed`, and
  `4 subtests passed`. The six failures are the same Redis-dependent proxy/cache integration tests;
  local Redis at `127.0.0.1:6379` was unavailable and was not started for this auth-only task.
- Compileall and scoped pre-commit hooks passed.
- Regression tests cover exact `dy` events, auth-only CLI overrides, no API-client/collection path,
  online recheck, stale local evidence, QR non-extraction, bounded visible login, fail-closed CDP,
  cancellation, and task-owned page cleanup.

## Backend

- `uv sync --frozen --group dev`, Ruff format/check, and pytest passed.
- Pytest after rollout and independent isolation review: `59 passed`.
- Import, exact OpenAPI route, and TestClient API catalog smoke passed.
- The fixed `dy` worker command is credential-free. Every cross-platform pair among
  `wb | dy | ks` is rejected by the event parser; the enabled catalog now returns HTTP 202 with the
  exact fixed command and maps a valid `dy` connected event to the connected product state.

## Frontend

- Frozen install, Prettier, Oxlint, TypeScript, Vitest, and Vite build passed.
- Vitest: `26 passed`.
- The build retained the existing non-blocking warning for a minified JavaScript chunk over 500 kB.
- Shadcn `base-nova` info and component diff were clean.
- The default fixture now exposes the third action. Tests start `dy`, render platform-specific
  guidance, poll a Douyin attempt to connected, and derive three-platform readiness copy from API
  data.

## Loopback browser smoke

- Read-only loopback smoke used the already-running FastAPI `127.0.0.1:8001` and Vite
  `127.0.0.1:5173` services; the unrelated SSH listener on `127.0.0.1:8000` was untouched.
- The desktop and 375 x 812 checks rendered five rows without horizontal overflow and with 44 px
  mobile action targets. The final post-rollout desktop read showed three enabled actions, two
  unavailable rows, and console warning/error count `0` against the restarted current services.
- An earlier pre-rollout smoke saw only the existing Vite development request for missing
  `/favicon.ico`; it was absent from the final post-rollout console read. No React, FastAPI,
  API-contract, or runtime exception was emitted.

## Completed acceptance gate

- The main session subsequently completed the real borrowed, logged-in Chrome positive probe; see
  `real-chrome-acceptance.md`.
- The accepted `checking -> connected` result and browser-ownership counts satisfied the rollout
  gate, so the backend catalog and default frontend fixture now expose Douyin as
  `enabled/not_checked`.

## Independent Trellis check

- The full-scope review synchronized the executable platform-connection spec to exact
  `wb | dy | ks` and added the Douyin fail-closed online-probe contract.
- The review corrected the React manual-action guidance to explicitly name QR-code, SMS, and
  safety-verification work; no authentication or collection behavior changed.
- MediaCrawler focused cross-platform authentication tests passed (`85 passed`), the maintained
  suite passed (`277 passed`), and the full repository produced `286 passed`, `8 skipped`, and the
  same six Redis-only failures while `127.0.0.1:6379` rejected connections.
- Backend Ruff/format, OpenAPI/catalog smoke, and `59` tests passed after expanding full worker
  state-isolation coverage to all six cross-platform event directions. Frontend frozen install,
  Prettier, Oxlint, TypeScript, `26` tests, production build, and shadcn integrity passed. The
  existing non-blocking >500 kB JavaScript chunk warning remains.
- The in-app browser connection was unavailable during the independent repeat smoke. No real
  authentication POST was started; the recorded real Chrome acceptance remained the rollout
  authority.
