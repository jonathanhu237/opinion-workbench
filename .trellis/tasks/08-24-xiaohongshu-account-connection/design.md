# Technical Design

## Architecture and boundaries

The feature extends the existing catalog-driven connection pipeline:

```text
React account center
  -> POST /api/v1/platform-connections/xhs/attempts
  -> FastAPI global single-flight service
  -> fixed MediaCrawler --platform xhs --type auth subprocess
  -> borrowed user Chrome / task-owned Xiaohongshu Page
  -> fresh official self-info check
  -> manual visible-page login when needed
  -> refreshed browser cookies + repeated official self-info check
  -> constant-only xhs events
  -> FastAPI terminal state
  -> TanStack Query polling and catalog-derived 0..5 / 5 readiness
```

The boundary ends at authentication readiness. Search, detail, creator, comments, downloads,
stores, databases, explicit auth-state persistence, and account identity remain unreachable.

## MediaCrawler design

### Shared authentication protocol

- Add `AuthPlatform.XIAOHONGSHU = "xhs"` and include XHS in the CLI `auth` allowlist.
- Keep protocol version, phases, exit codes, and the exact three-field event schema unchanged.
- Add an XHS event wrapper that always supplies `AuthPlatform.XIAOHONGSHU`; arbitrary strings never
  reach `emit_auth_event`.
- Auth CLI overrides continue to force existing visible Chrome, loopback CDP, no proxy, no state
  store, no data path, and all collection toggles off.

### Auth-only orchestration

`XiaoHongShuCrawler.start()` gains an early authentication branch while leaving ordinary crawler
ordering intact:

1. detect exact `CRAWLER_TYPE == "auth"` before proxy or state-store setup;
2. connect only to the approved existing Chrome through the shared CDP manager;
3. create and register one task-owned Page, then navigate freshly to the domestic XHS homepage;
4. create the existing signed XHS HTTP client from allowlisted BrowserContext cookies;
5. emit `checking` and call the existing official `pong()`;
6. if connected, emit `connected` and return before all collection/storage code;
7. otherwise emit `waiting_for_login`, expose the official visible login panel without extracting
   QR material, and wait boundedly for user-driven state change;
8. update the client from current allowlisted browser cookies, emit `checking`, and rerun `pong()`;
9. emit `connected` only for the affirmative server result, otherwise emit `disconnected`;
10. close only the registered task Page in terminal, error, timeout, and cancellation paths.

Authentication-mode CDP failure raises the shared browser-unavailable error and never executes the
standard-browser fallback. `BrowserAuthStateStore` is structurally unreachable because the auth
branch returns before normal setup and the CLI also forces `SAVE_LOGIN_STATE=False`.

### Visible-page-only login helper

The current `login_by_qrcode()` cannot be reused because it calls `find_login_qrcode()` and
`show_qrcode()`. Add a narrow `visible_page_only` helper or an equivalent auth-only method:

- if the official login panel is already visible, leave it untouched;
- otherwise it may click a stable ordinary “登录” entry once to expose the official panel;
- never read the QR image source or pixels and never call QR display helpers;
- never fill phone, verification-code, or password inputs;
- never inspect challenge images, calculate tracks, move the mouse, refresh, or navigate around a
  challenge;
- use UI/Cookie changes only as low-cost wake-up hints and periodically invoke a callback that
  refreshes client cookies and performs the authoritative online check;
- enforce one overall bounded wait; selector drift and inconclusive state are non-success.

Normal qrcode/mobile/cookie login methods remain unchanged for ordinary crawler runs.

### Authoritative XHS check

Reuse `XiaoHongShuClient.pong()` rather than creating a DOM-only login heuristic. It signs and sends
the existing official self-info request and returns a boolean from `data.result.success`.

- The auth orchestrator consumes only the boolean and never logs, returns, or persists the response.
- Browser Cookie/UI state can trigger a repeat call but cannot become terminal proof.
- Network errors, challenge state, response drift, and any exception remain `disconnected` or an
  internal failure; they never downgrade to a Cookie-based success.
- Automated tests mock positive and negative results; real acceptance validates current official
  behavior from the user's Chrome.

## FastAPI design

- Extend `AuthPlatformId` and `_AUTH_PLATFORM_BY_ID` to exact `wb | dy | ks | xhs | toutiao`.
- Mark XHS `enabled/not_checked` only after worker tests and real Chrome acceptance pass.
- Reuse the fixed command builder, one global task slot, timeout/cancellation/process-group ownership,
  strict event parser, transition table, status mapping, and safe error envelopes.
- Require `event.platform == active_attempt_platform`; parameterize all 20 directed mismatches among
  five platforms without exposing child output.
- Do not add a database, MediaCrawler runtime import, XHS-specific service, or new response fields.

## React design

- Keep the existing five-row API schema and generic `PlatformRow`; change XHS catalog fixtures from
  `coming_soon` to `enabled` only after rollout gate success.
- Reuse the existing mutation, polling, guidance, live-region, duplicate-action locking, and error UI.
- Validate that XHS `action_required` copy directs the operator to the visible Chrome page.
- Workbench readiness already derives numerator and denominator from enabled catalog entries; its
  expected final state becomes `0..5 / 5`, with no remaining unavailable row.
- No new route, component family, design tokens, or non-shadcn primitive is required.

## Compatibility and migration

- No persisted schema or migration.
- Backend restart still resets every enabled connection to `not_checked`.
- Protocol version and exit codes do not change; only the trusted platform enum expands.
- Ordinary XHS BrowserAuthStateStore ordering, profile behavior, qrcode/mobile/cookie methods,
  search/detail/creator branches, and other four platform commands/events remain compatible.

## Operational, delivery, and rollback considerations

- Keep XHS `coming_soon` until automated tests and a real positive borrowed-Chrome check both pass.
- Roll back if auth mode reaches collection/store code, extracts QR material, automates a challenge,
  trusts local state as terminal proof, starts fallback Chrome, persists auth state, or closes a
  user-owned page.
- Record only phases, terminal state, timestamps, and page/tab counts during live acceptance.
- Deliver and push the MediaCrawler derivative commit before updating the parent submodule gitlink.
- If the real positive probe cannot be established reliably, retain the implementation behind the
  unavailable catalog state or revert it; never ship a false “connected” status.
