# Technical Design

## 1. Architecture and explicit split

This task extends the delivered connection pipeline without replacing the existing Toutiao search
browser lifecycle:

```text
React account center
  -> POST /api/v1/platform-connections/toutiao/attempts
  -> FastAPI global single-flight service
  -> MediaCrawler --platform toutiao --type auth
  -> borrowed user Chrome over loopback CDP
  -> task-owned official Toutiao page
  -> fresh fail-closed DOM auth classification
  -> constant-only toutiao events
  -> FastAPI status -> TanStack Query polling

MediaCrawler --platform toutiao --type search
  -> fresh standard visible Chrome context (unchanged)
  -> optional BrowserAuthStateStore (unchanged)
  -> separate Auth Page and Search Page (unchanged)
  -> first-page public search and store (unchanged)
```

The two entry paths share only narrowly reusable official-page login classification and manual
login behavior. Auth mode never restores or saves `BrowserAuthStateStore`; search mode never enters
CDP. This preserves the deliberate browser isolation from the original Toutiao adapter while
honoring the product decision to reuse the user's Chrome for account readiness checks.

## 2. Typed authentication protocol

- Add `AuthPlatform.TOUTIAO = "toutiao"` and include Toutiao in the CLI `auth` allowlist.
- Keep protocol version 1, phases, exit codes, and exact three-field schema unchanged.
- Add `emit_toutiao_auth_event(phase)` so crawler code cannot emit an arbitrary platform string.
- The CLI continues to override credentials, keywords, IDs, proxy, state persistence, storage,
  comments, media, and word cloud before crawler construction.

Normal `search` validation remains strict. `_validate_config()` distinguishes `auth` from `search`:
auth accepts only the CLI-forced boundary; search still rejects headless mode, unsupported stores,
more than one page, empty limits, detail, and creator.

## 3. Toutiao auth-only browser lifecycle

`ToutiaoCrawler.start()` derives `is_auth_mode` before browser startup and delegates to two explicit
private orchestration paths rather than interleaving their invariants.

Auth flow:

1. Create `CDPBrowserManager(auth_event_callback=emit_toutiao_auth_event)` and connect only to the
   existing Chrome requested by the CLI safety overrides.
2. If connection/approval fails, raise `AuthBrowserUnavailableError`; never call the standard
   `launch_browser()` fallback.
3. Create one blank Page, register it immediately as task-owned, and navigate it to the trusted
   Toutiao homepage with a bounded timeout.
4. Emit `checking`; run the tri-state online DOM classification.
5. If connected, emit `connected` and return `AuthPhase.CONNECTED` before any search/store setup.
6. Otherwise emit `waiting_for_login`, keep the official page visible, and use the existing bounded
   manual flow without Cookie injection or QR extraction.
7. Emit `checking` and rerun the same fresh-page classification. Only `connected` emits the terminal
   connected event; disconnected/inconclusive emits `disconnected` and raises
   `AuthDisconnectedError`.
8. In `finally`, close only pages registered by this task. Never close the borrowed context,
   browser, pre-existing pages, or Chrome process.

The outer `main.py` retains its current exit mapping. Normal search continues to own and close its
fresh browser context through the existing non-CDP cleanup behavior.

## 4. Online DOM classification

Refine the current boolean login check into a small internal result contract:

```python
ToutiaoAuthResult = Literal["connected", "disconnected", "inconclusive"]

async def check_toutiao_online_auth(page: Page) -> ToutiaoAuthResult: ...
```

The check runs only after a fresh navigation to an allowlisted official Toutiao origin. The page
evaluates a bounded script that returns booleans only, including an origin decision made in the
same DOM execution context; Python also checks the Page URL before and after evaluation. It never
returns selector text, URLs, or identity.

- `connected`: either the legacy visible `data-e2e="user-avatar"` signal is inside page chrome and
  an interactive non-content-profile control, or the current live-DOM shape is present: a visible
  image inside a banner-scoped anchor with `role="button"` and `aria-haspopup="true"`. In both
  cases the explicit login entry must not exist. The current shape intentionally relies on the
  banner/account-menu boundary because Toutiao's own header account link uses a `/c/user/...`
  route just like content profiles.
- `disconnected`: the explicit login entry exists and no account signal exists.
- `inconclusive`: challenge terms, both signals, neither signal, unexpected origin, navigation or
  evaluation failure, or any schema drift.

The existing `ToutiaoWebClient.is_logged_in()` used by normal search may wrap this result as a
boolean/typed challenge according to its existing contract, or both paths may share a pure parser.
Normal search must preserve its current manual-challenge and `BrowserAuthStateStore` ordering.

The DOM result is authoritative only because it is read from the currently loaded official page.
Cookie presence, prior state-file contents, URL history, and process status are excluded. If the
current site cannot expose stable positive and anonymous signals, implementation stops before
catalog promotion.

## 5. Manual login behavior

Reuse `ToutiaoLogin`'s bounded polling with an explicit auth-only guard while preserving the
separate normal-search behavior:

- the CLI-selected auth mode is QR/manual only, so `login_by_cookies()` is unreachable;
- borrowed-browser auth retains the already freshly navigated official page and never navigates,
  refreshes, or clicks it; the existing normal-search helper may still navigate and click the exact
  visible login entry before its manual wait;
- it never extracts QR bytes, fills phone/SMS/password fields, returns account data, or interacts
  with a challenge;
- repeated official challenges log one credential-free instruction and continue ordinary
  low-frequency checks within the existing overall timeout;
- only the canonical evaluate-during-navigation race is inconclusive; other failures propagate
  through a credential-free error boundary.

Completion of the helper is only a wake-up for the mandatory post-login online recheck.

## 6. FastAPI and protocol validation

Extend `AuthPlatformId` and `_AUTH_PLATFORM_BY_ID` to exact `wb | dy | ks | toutiao`. The worker
command remains a fixed argument tuple executed by `create_subprocess_exec`; the only variable is a
member of the trusted mapping.

The event model accepts four supported platform tags, while `_parse_auth_event()` still receives
the current expected platform. Parameterized tests cover all 12 ordered mismatches. Existing phase
transition, line-size, extra-field, exit-code, timeout, cancellation, process-group, and safe-error
contracts remain unchanged.

The ordered catalog is promoted only after the real-positive gate:

```text
wb enabled
dy enabled
ks enabled
xhs coming_soon
toutiao enabled
```

If the gate fails, the trusted worker may remain implemented for further diagnostics while the
product catalog stays unavailable, matching the Douyin rollout precedent.

## 7. React behavior

No Toutiao-specific route or row is added. The existing generic row exposes an action for every
enabled catalog entry, and platform-aware guidance already interpolates `display_name`.

Tests update the default catalog and assert:

- four enabled actions and only Xiaohongshu unavailable;
- a Toutiao POST starts exactly once and polling reaches action-required/terminal states;
- manual guidance names 今日头条 and describes only user-operated login/security work;
- the workbench derives enabled names and readiness as `0..4 / 4` from API data;
- global single-flight disablement, keyboard/live-region behavior, 44 px mobile targets, no
  horizontal overflow, and no console errors remain intact.

## 8. Verification and rollout

Automated verification first covers CLI overrides, protocol constants, tri-state DOM parsing,
auth-only early return, no-collection/state-store sentinels, CDP fail-closed behavior, task-page
ownership, normal search isolation regression, backend cross-platform isolation, and generic React
behavior.

Real acceptance then uses a harmless pre-existing Chrome sentinel tab. Prefer an already-logged-in
path; otherwise the user handles official login/challenges. Promote the catalog only when the
worker emits a valid terminal connected event, React reaches connected, no search/store/state-file
path runs, all pre-existing tabs survive, and the task-owned page is gone. Evidence is restricted
to phases, timestamps, terminal category, tab counts, listener address class, and ownership result.

## 9. Delivery and rollback

Commit and push the MediaCrawler derivative first. Only after its revision is reachable and clean
may the parent update the submodule gitlink together with FastAPI, React, specs, and Trellis
evidence.

Rollback or keep the catalog gated if the online check is ambiguous, auth reaches search/store,
auth restores/saves explicit state, CDP falls back to a new browser, a challenge is automated, or
cleanup touches a user-owned page/context/browser/process. Normal Toutiao search behavior is a
separate regression gate and must remain available at its prior revision contract.
