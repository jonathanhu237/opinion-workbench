# Technical Design

## 1. Scope and architecture

This task extends the existing platform-neutral connection center by one enabled platform. It does
not introduce a second service or a Kuaishou-specific HTTP endpoint:

```text
React platform account route
  -> POST /api/v1/platform-connections/ks/attempts
  -> PlatformConnectionService (one global attempt)
  -> MediaCrawler --platform ks --type auth
  -> borrowed user Chrome over loopback CDP
  -> official visible Kuaishou page
  -> KuaiShouClient.pong() online result
```

The browser holds authentication state. FastAPI holds only the latest derived status for its
current process. No database, Cookie export, or QR transport is added.

## 2. Authentication-only platform contract

`cmd_arg` permits `auth` only for the explicit set `{wb, ks}`. It retains the requested member of
that set instead of forcing Weibo, then applies the existing fail-closed safety overrides: headed
borrowed Chrome, loopback CDP, no proxy, no state-file persistence, no keyword/IDs, no comments,
media, store, database, or word cloud.

Kuaishou follows the existing version-1 phases:

```text
waiting_for_browser -> waiting_for_approval -> checking -> connected
waiting_for_browser -> waiting_for_approval -> checking
                    -> waiting_for_login -> checking -> connected|disconnected
```

The early browser phases may be omitted when CDP is already available. No new `slider` phase is
introduced: the product cannot reliably classify every official challenge, and all of them require
the same user action on the visible page.

## 3. Kuaishou crawler lifecycle

`KuaishouCrawler.start()` derives `is_auth_mode` before browser startup.

1. CDP creation receives `emit_auth_event` in auth mode.
2. A CDP failure raises `AuthBrowserUnavailableError`; normal crawler modes retain their fallback.
3. The crawler creates and registers one owned page, loads the official Kuaishou home page, creates
   the existing signed client, emits `checking`, and calls `pong()`.
4. If false, it emits `waiting_for_login` and calls the login helper in visible-page-only mode.
5. The helper opens the official login UI but does not extract or display QR image bytes. It waits
   for bounded local evidence that the user may have completed login; selector drift or timeout is
   treated as inconclusive rather than authenticated.
6. The crawler updates Cookies in memory, emits `checking`, and calls `pong()` again. Only
   `visionProfileUserList.result == 1` emits `connected` and returns `AuthPhase.CONNECTED`.
7. Otherwise it emits `disconnected` and raises `AuthDisconnectedError`.
8. `finally` closes only pages registered by this task. The shared borrowed context and browser are
   never closed.

Search/detail/creator branches are structurally unreachable from auth and guarded by failing test
sentinels. Existing non-auth login and persistence behavior remain unchanged.

## 4. FastAPI command and protocol validation

Replace the constant command tuple with a command builder whose only variable is a validated
enabled `PlatformId`. The argument vector remains fixed and is still executed without a shell.

`_AuthEvent.platform` accepts the exact supported auth-platform union, while the parser receives
the current attempt's expected platform. A valid event for the wrong supported platform is still a
protocol failure. State transitions, line bounds, exit codes, output disposal, timeouts, process
groups, and safe API errors remain unchanged.

The initial catalog enables `ks` with `not_checked`; `dy`, `xhs`, and `toutiao` remain
`coming_soon`. One global task lock continues to cover both Weibo and Kuaishou.

## 5. React guidance ownership

The existing row rendering automatically exposes a button for any `enabled` platform, so product
logic should remain catalog-driven. The guidance panel must no longer select Weibo unconditionally.
It derives the relevant connection in this order:

1. an active `checking` or `action_required` connection;
2. the connection with the newest non-null `last_checked_at`;
3. the first enabled connection.

Guidance copy interpolates `display_name`. For `complete_login`, it tells the user to finish QR scan
or official safety verification in that platform's visible Chrome page. The API type and runtime
decoder remain unchanged.

## 6. Verification and real acceptance

Automated tests cover CLI allowlisting and safe overrides, event sequences, no-collection sentinels,
post-login online recheck, timeout/failure, CDP fail-closed behavior, owned-page cleanup, dynamic
backend commands, cross-platform event rejection, global conflicts, catalog payloads, correct
frontend guidance, polling, and regression of the Weibo path.

The real acceptance uses a harmless pre-existing Chrome sentinel tab and performs an already-logged
in path when available. If login is required, the user handles the official QR/challenge manually.
Acceptance succeeds only when the online probe returns connected, the React state reaches
`connected`, no auth POST is repeated, no content is stored, and the sentinel tab/Chrome remain
usable after cleanup.

## 7. Delivery and rollback

MediaCrawler changes are committed and pushed in the derivative first. The parent then updates its
gitlink together with backend/frontend changes. If auth reaches collection, closes borrowed Chrome,
accepts local Cookie evidence as connected, or falls back to a new browser after CDP failure, stop
and roll back before real login testing.
