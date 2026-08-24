# Platform Connection Guidelines

## Scenario: Authentication-only platform connection through borrowed Chrome

### 1. Scope / Trigger

Use this contract when the product adds or changes a platform account readiness flow that starts
in React, is coordinated by FastAPI, and delegates platform-specific authentication to a bounded
MediaCrawler subprocess. It does not authorize collection, credential export, challenge
automation, or closing the user's browser.

### 2. Signatures

Product API:

```http
GET  /api/v1/platform-connections
POST /api/v1/platform-connections/{platform}/attempts
```

Worker command shape:

```text
uv run --frozen --project third_party/MediaCrawler python main.py
  --platform <wb|dy|ks|toutiao> --type auth --lt qrcode --headless no
  --get_comment no --get_sub_comment no --save_data_option jsonl
```

Versioned child event:

```text
__MEDIACRAWLER_AUTH_EVENT__{"version":1,"platform":"dy","phase":"checking"}
```

### 3. Contracts

- `GET` returns exactly `{ "platforms": PlatformConnection[] }` in catalog order.
- `POST` returns HTTP 202 as `{ "attempt_id": UUID, "platform": PlatformConnection }` and never
  waits for manual browser work.
- Authentication availability is a trusted product allowlist. The current supported child
  platforms are exactly `wb | dy | ks | toutiao`; a known catalog entry is not automatically
  executable.
- Build the worker command from the trusted allowlist with `create_subprocess_exec`. The backend
  must pass the requested platform as one exact argument and require every child event's
  `platform` to equal the active attempt. An event for any other supported platform fails closed.
- Only one authentication worker may be active. Product state remains in memory and is reset by a
  backend restart.
- Allowed worker phases are `waiting_for_browser`, `waiting_for_approval`, `checking`,
  `waiting_for_login`, `connected`, and `disconnected`. The event permits only `version`,
  `platform`, and `phase` fields.
- Valid progress is `waiting_for_browser -> waiting_for_approval -> checking`, followed by either
  `connected` or `waiting_for_login -> checking -> connected|disconnected`. Initial waiting
  phases may be omitted only when Chrome/CDP is already ready; emitted phases may not be skipped.
- Exit `0` is connected only when preceded by a valid terminal `connected` event. Exit `20` is
  disconnected, `21` is browser/CDP unavailable or approval timeout, and `22` is an internal
  worker failure.
- `connected` requires the platform's authoritative online probe. Cookie names, files, or process
  exit alone are never sufficient.
- For Kuaishou, a new or changed `passToken` after the visible login begins is only a wake-up hint
  for the follow-up online probe. Capture the initial token value so stale local evidence cannot
  produce an early success or skip the bounded manual-login wait.
- For Douyin, `connected` requires a fresh official-page, same-origin, no-store account probe with
  the verified success shape. Cookie, LocalStorage, URL, and UI changes are only wake-up hints;
  anonymous, challenge, navigation-failure, and schema-drift results fail closed.
- For Toutiao, `connected` requires a fresh navigation to an exact trusted HTTPS origin and a
  boolean-only visible DOM classification. The positive signal must sit in page chrome and is
  either a visible `data-e2e` account avatar inside an interactive control that is not a
  content-author/profile link, or a visible image inside a banner-scoped account-menu anchor
  (`role="button"`, `aria-haspopup="true"`). The page-chrome boundary, not the link target, is what
  excludes content-author/profile links, because Toutiao's own header account link uses the same
  user route. The positive signal must not coexist with the explicit login entry. Anonymous is
  `disconnected`; challenge, login-entry drift without the positive signal, contradictory signals,
  origin/navigation/browser failure, and schema drift are `inconclusive`. Both non-connected
  results require manual work and the same fresh online recheck before success.
- Toutiao borrowed-browser manual work retains the already opened official page and only polls the
  ordinary login-state classifier. It does not navigate, refresh, click the login entry, inject
  Cookies, extract QR material, read input, or interact with a safety challenge.
- Authentication mode must force existing visible Chrome, loopback CDP, no proxy, no explicit
  authentication-state persistence, and no search/detail/creator/comment/media/store/database
  work.
- Borrowed Chrome ownership is narrow: register task-created pages, close only those pages, never
  close a borrowed context/browser, and never terminate a process that this task did not launch.
- Product logs, API payloads, browser state, fixtures, and evidence must not contain Cookie values,
  authorization headers, QR material, page content, profile paths, or account identity.
- React readiness metrics must derive both numerator and denominator from catalog entries whose
  `availability` is `enabled`. A `coming_soon` entry remains visible as unavailable but never
  inflates the readiness denominator or counts as a failed/not-connected actionable platform.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Unknown platform | HTTP 404 `platform_not_found`; start no process |
| Known unavailable platform | HTTP 409 `platform_not_available`; start no process |
| Readiness catalog contains `coming_soon` entries | Exclude them from `connected / enabled`; keep them visible and non-actionable |
| Another attempt is active | HTTP 409 `connection_attempt_active`; preserve current attempt |
| Supported child event names any other platform | Fail closed; do not mutate either platform |
| Unknown, oversized, malformed, extra-field, or out-of-order child event | Fail closed; discard raw line |
| Exit 0 without terminal `connected` | `failed`; never infer authentication |
| Exit 20 without an explicit terminal `disconnected` event | `failed`; reject the mismatch |
| Login timeout or failed post-login probe | `disconnected`; enter no collection method |
| Chrome/CDP unavailable or approval timeout | `failed` with actionable loopback-debug guidance |
| Backend timeout/shutdown | Terminate the owned worker process group; leave Chrome untouched |
| Borrowed page close fails because Chrome disconnected | Suppress credential-free close noise only |

### 5. Good / Base / Bad Cases

- **Good:** React starts one attempt and polls; FastAPI validates constant-only events; the worker
  borrows Chrome, runs the online probe, closes its own page, and reports connected without
  exposing authentication data.
- **Good:** A catalog with four enabled entries plus one `coming_soon` entry renders readiness as
  `0..4 / 4`, exposes four connection actions, and keeps the unavailable entry visible.
- **Base:** Chrome remote debugging is disabled. The worker opens
  `chrome://inspect/#remote-debugging`, reports the required user action, times out safely, and
  leaves every existing Chrome tab open.
- **Bad:** FastAPI imports MediaCrawler runtime globals, accepts arbitrary child JSON, passes
  credentials on the command line, accepts a `wb` event for an active `ks` attempt, trusts Cookie
  presence, falls back to a dedicated browser, or calls `context.close()` / `browser.close()` on a
  borrowed Chrome instance.
- **Bad:** React divides connected accounts by the total catalog length, producing `0 / 5` when
  only four platforms are executable.

### 6. Tests Required

1. Exact API catalog, 202 response, safe 404/409 envelopes, and OpenAPI response models.
2. One-at-a-time concurrency, UTC terminal timestamp, bounded timeout, shutdown cancellation, and
   owned process-group TERM/KILL behavior.
3. Exact worker command with `create_subprocess_exec`, no shell, and no credential-bearing args.
4. Protocol version/platform/phase/extra-field/line-size/transition/exit mismatch cases; assert raw
   child text never reaches product state or errors. Cover every mismatch pair among
   `wb | dy | ks | toutiao` and assert all 12 ordered mismatches mutate no foreign platform.
5. Authentication config sentinels that fail if any search, detail, creator, comment, media,
   persistence, or store entry point is reached.
6. Borrowed cleanup regression: one pre-existing sentinel page remains, only registered pages
   close, context/browser/process cleanup is not called, and owned-browser behavior remains intact.
7. Frontend runtime validation, active polling, duplicate-action disabling, safe error mapping,
   live-region guidance, responsive overflow, and console checks. Assert the workbench numerator
   and denominator both use only enabled entries (`0..4 / 4` for the current catalog), while the
   `coming_soon` row remains visible and has no connection action.
8. Real loopback acceptance records only phases, terminal category, timestamps, counts, listener
   address, and ownership results.
9. Kuaishou stale-token regression: an initially present `passToken` after a failed online probe
   must not finish visible login; only token appearance/change may trigger the early recheck, and
   only a successful online probe may emit `connected`.
10. Douyin online-probe regression: cover connected, anonymous, challenge, navigation failure,
    malformed/unknown response shapes, stale local markers, QR non-extraction, manual-only
    challenges, and the mandatory post-login online recheck.
11. Toutiao DOM-probe regression: cover both scoped visible positive shapes (legacy `data-e2e`
    avatar and banner account-menu anchor), content-profile exclusion, login-entry drift,
    anonymous, challenge, contradictory/malformed shapes, trusted origin before and after
    evaluation, browser failure, manual no-click/no-navigation behavior, and the mandatory
    post-login online recheck.

### 7. Wrong vs Correct

#### Wrong

```python
process = await asyncio.create_subprocess_shell(command_with_cookie)
if await process.wait() == 0:
    status = "connected"
await borrowed_context.close()
```

#### Correct

```python
platform = AUTH_PLATFORM_BY_ID[requested_platform]  # trusted `wb | dy | ks | toutiao`
process = await asyncio.create_subprocess_exec(
    *fixed_auth_args(platform), start_new_session=True
)
event = _parse_auth_event(
    await process.stdout.readline(), expected_platform=platform
)
_validate_transition(previous_phase, event.phase)
status = "connected" if event.phase == "connected" and await process.wait() == 0 else "failed"
await cdp_manager.close_owned_pages()
```

For React readiness, the same allowlist boundary applies:

```typescript
// Wrong: includes visible but unavailable catalog entries in the denominator.
const value = `${connected.length} / ${platforms.length}`

// Correct: readiness describes only actionable platforms.
const enabled = platforms.filter((item) => item.availability === 'enabled')
const connected = enabled.filter((item) => item.status === 'connected')
const value = `${connected.length} / ${enabled.length}`
```
