# Platform Connection Guidelines

## Scenario: Authentication-only platform connection through borrowed Chrome

### 1. Scope / Trigger

Use this contract when the product adds or changes a platform account readiness flow that starts
in React, is coordinated by FastAPI, and delegates platform-specific authentication to an owned,
lifespan-bounded MediaCrawler worker. It does not authorize collection, credential export,
challenge automation, background browser work, or closing the user's browser.

### 2. Signatures

Product API:

```http
GET  /api/v1/platform-connections
POST /api/v1/platform-connections/{platform}/attempts
```

Persistent worker command shape:

```text
uv run --frozen --project third_party/MediaCrawler python -m tools.auth_worker
```

Strict NDJSON v2 frames:

```text
__MEDIACRAWLER_AUTH_COMMAND__{"version":2,"type":"command","command":"check","request_id":"<uuid4>","platform":"dy"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"progress","request_id":"<uuid4>","platform":"dy","phase":"checking"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"result","request_id":"<uuid4>","platform":"dy","outcome":"connected","reason":"none"}
```

The one-shot `main.py --type auth` command and its strict v1 phase/exit protocol remain available
for direct validation and rollback. The persistent backend path never automatically falls back to
v1 after a v2 failure.

### 3. Contracts

- `GET` returns exactly `{ "platforms": PlatformConnection[] }` in catalog order.
- `POST` returns HTTP 202 as `{ "attempt_id": UUID, "platform": PlatformConnection }` and never
  waits for manual browser work.
- Worker support and product availability are separate trusted allowlists. The supported child
  platforms are exactly `wb | dy | ks | xhs | toutiao`; a known or worker-supported catalog entry
  is not executable until its catalog availability is `enabled`.
- Launch the fixed worker command with `create_subprocess_exec`, inherited stdin/stdout/stderr
  pipes, no shell, and an owned process group. Platform and request correlation travel only in the
  strict v2 frames. Every progress/result event must match the exact active UUID and platform; a
  mismatch fails closed without mutating a foreign row.
- Worker startup is lazy: application lifespan entry, React page load, and `GET` launch no worker
  and create no CDP connection. The first accepted `POST` launches one worker, and `ready` means
  only that its command loop can accept input. Playwright and CDP remain lazy until the first
  `check` command.
- Keep one healthy worker, Playwright runtime, CDP manager, Browser connection, and borrowed
  default BrowserContext for serialized checks. Reuse them across platforms and repeat checks;
  connect only once until Chrome disconnects, the worker is recycled, or FastAPI shuts down.
- The same coordinator also protects product searches and paused manual recovery. A paused batch
  retains ownership; account checks cannot interleave. Search-v2 `manual_page` does not change auth-v2
  frames or call authentication. It shows only a registered current-generation owned page or opens
  one fixed homepage on explicit request. Its outcome is never proof of login. See
  [Batch Search](./batch-search-guidelines.md) for show/close, timeouts and cleanup contracts.
- A disconnect callback captures its own session-generation event. A late callback from an old
  Browser must not set a newer session's disconnected event or invalidate its owned manual page.
- Only one authentication request may be active. Product state remains in memory and is reset by
  a backend restart. A second HTTP request keeps the existing global 409 behavior, and a second
  worker `check` while busy is a protocol violation.
- v2 accepts only exact `ready`, `progress`, `result`, `session/disconnected`, and `stopped` event
  shapes. Frames are UTF-8, prefixed, newline terminated, at most 1,024 bytes, duplicate-key-safe,
  and free of unknown or extra fields. Stdout is protocol-only; stderr is continuously drained and
  is never retained, parsed, logged, or projected into product state.
- Allowed progress phases are `waiting_for_browser`, `waiting_for_approval`, `checking`, and
  `waiting_for_login`. Valid progress is `waiting_for_browser -> waiting_for_approval -> checking`,
  followed by either a terminal result or `waiting_for_login -> checking -> result`. Initial
  waiting phases may be omitted only when the relevant browser/CDP state is already ready; emitted
  phases may not be repeated or skipped.
- Terminal proof is one exact result pair: `connected/none`,
  `disconnected/login_required`, `failed/browser_unavailable`,
  `failed/browser_disconnected`, `failed/internal_error`, or `cancelled/cancelled`. A process exit,
  progress phase, previous result, Cookie, or local marker never proves authentication.
- A request-independent `session/disconnected` invalidates all stale connected projections. If an
  idle-session event was emitted just before a newly queued check, the backend may receive it after
  installing the new request; it invalidates the prior session without cancelling the new request
  only while that request has emitted no progress. After progress begins, busy disconnect is
  strictly the correlated `failed/browser_disconnected` result followed by the session event.
- On timeout, send only the matching `cancel` and wait a bounded interval for
  `cancelled/cancelled`; recycle the worker when acknowledgement is absent or mismatched. On
  FastAPI shutdown, cancel/drain the active request, send `shutdown`, require `stopped` plus exit
  zero, and otherwise use bounded TERM/KILL against only the owned worker group.
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
- For Xiaohongshu, `connected` requires a fresh navigation to the domestic official homepage,
  allowlisted Cookies refreshed from the current borrowed BrowserContext, and the existing signed
  official self-info `pong()`. The response is positive only when `data.result.success` is the JSON
  boolean `true`; truthy strings, numbers, malformed shapes, challenge responses, and network
  failures fail closed. Cookie or visible-UI changes are wake-up hints for another `pong()`, never
  terminal proof.
- Xiaohongshu borrowed-browser manual work may click the ordinary official login entry once when
  the login panel is absent, then waits with a bounded, low-frequency online recheck. It never
  extracts or displays QR material outside Chrome, fills phone/password/code inputs, injects
  Cookies, or detects, manipulates, refreshes, or bypasses a safety challenge.
- Authentication mode must force existing visible Chrome, loopback CDP, no proxy, no explicit
  authentication-state persistence, and no search/detail/creator/comment/media/store/database
  work.
- Borrowed Chrome ownership is narrow: register task-created pages, close only those pages, never
  close a borrowed context/browser, and never terminate a process that this task did not launch.
- Persistent borrowed mode must require an existing default BrowserContext, connect with
  `is_local=True` and `no_defaults=True`, and fail closed instead of creating an incognito context.
  Releasing the worker stops Playwright transport without calling `Browser.close()` or
  `BrowserContext.close()`.
- Persistent Douyin authentication must not install a context-wide stealth script into the user's
  shared context. Kuaishou's signer remains page-local on the task-owned page.
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
| Supported child event names another platform or UUID | Recycle the worker; do not mutate a foreign platform |
| Unknown, oversized, malformed, duplicate-key, extra-field, or out-of-order v2 frame | Recycle the worker; discard raw line |
| Result pair is unknown or does not follow the required progress | `failed`; reject the mismatch |
| Idle worker crash or Chrome session disconnect | Invalidate every stale `connected` projection; reconnect only after a later POST |
| Idle session frame is consumed after a new check is installed but before its first progress | Invalidate the prior session; preserve the new request and worker |
| Session frame arrives after active-request progress without the correlated disconnect result | Recycle the worker; reject the busy ordering violation |
| Login timeout or failed post-login probe | `disconnected`; enter no collection method |
| Chrome/CDP unavailable or approval timeout | `failed` with actionable loopback-debug guidance |
| Backend timeout with exact cancel acknowledgement | Keep the healthy worker/CDP connection for the next explicit check |
| Missing cancel/shutdown acknowledgement, unexpected EOF, or transport failure | Recycle/terminate only the owned worker process group; leave Chrome untouched |
| Borrowed page close fails because Chrome disconnected | Suppress credential-free close noise only |

### 5. Good / Base / Bad Cases

- **Good:** React starts one attempt and polls; FastAPI lazily launches the worker, validates
  constant-only events, and the worker borrows Chrome once. Later platforms reuse that exact CDP
  connection, close only their own pages, and report results without exposing authentication data.
- **Good:** The current five-enabled catalog renders readiness as `0..5 / 5`, exposes five
  connection actions, and contains no unavailable row. A future mixed catalog still excludes each
  `coming_soon` entry from both readiness terms and action controls.
- **Base:** Chrome remote debugging is disabled. The worker opens
  `chrome://inspect/#remote-debugging`, reports the required user action, times out safely, and
  leaves every existing Chrome tab open.
- **Base:** Chrome disconnects while the worker is idle. The worker emits a constant session event,
  FastAPI invalidates stale connected rows, and only the next user-triggered check reconnects.
- **Bad:** FastAPI imports MediaCrawler runtime globals, accepts arbitrary child JSON, passes
  credentials on the command line, accepts a `wb` event for an active `ks` attempt, trusts Cookie
  presence, falls back to a dedicated browser, or calls `context.close()` / `browser.close()` on a
  borrowed Chrome instance.
- **Bad:** FastAPI launches the worker on startup, creates one process/CDP connection per platform,
  treats `ready` as authentication, retains stderr, automatically falls back to v1, or leaves a
  stale row connected after the worker/browser session ends.
- **Bad:** React divides connected accounts by the total catalog length. In a synthetic catalog
  with four enabled entries and one future `coming_soon` entry, it incorrectly produces `0 / 5`
  instead of `0 / 4`.

### 6. Tests Required

1. Exact API catalog, 202 response, safe 404/409 envelopes, and OpenAPI response models.
2. Zero launch on lifespan/GET; one-at-a-time concurrency; one lazy worker reused across multiple
   platforms and repeats; UTC terminal timestamp; bounded cancel/shutdown; owned TERM/KILL fallback.
3. Exact fixed worker command with duplex pipes, `create_subprocess_exec`, no shell, and no
   credential-bearing args or platform CLI arguments.
4. v2 version/UUID/platform/phase/result/extra-field/duplicate-key/line-size/transition mismatch
   cases; assert raw child text and drained stderr never reach product state or errors. Cover every
   mismatch pair among
   `wb | dy | ks | xhs | toutiao` and assert all 20 ordered mismatches mutate no foreign platform.
5. Authentication config sentinels that fail if any search, detail, creator, comment, media,
   persistence, or store entry point is reached.
6. Borrowed cleanup regression: one pre-existing sentinel page remains, only registered pages
   close, context/browser/process cleanup is not called, and owned-browser behavior remains intact.
   Prove zero-context failure, `is_local=True`, `no_defaults=True`, lazy Playwright startup, one
   `connect_over_cdp` for sequential checks, and no context-wide Douyin script.
7. Frontend runtime validation, active polling, duplicate-action disabling, safe error mapping,
   live-region guidance, responsive overflow, and console checks. Assert the current catalog renders
   `0..5 / 5` with five actions and no unavailable row. Retain a synthetic mixed-catalog regression
   proving any future `coming_soon` row remains visible/non-actionable and is excluded from both
   readiness terms.
8. Real loopback acceptance records only phases, terminal category, timestamps, counts, listener
   address, and ownership results. It must show no prompt before POST, one approval followed by at
   least two platforms plus a repeat/full batch on one connection, sentinel-tab survival, and a
   new lazy approval only after deliberate worker/Chrome disconnect.
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
12. Xiaohongshu online-probe regression: cover strict boolean success, false and malformed response
    shapes, network failure, stale Cookie/UI hints, QR non-extraction, manual-only challenges,
    bounded wait/cancellation, task-page-only cleanup, and the mandatory post-login online recheck.

### 7. Wrong vs Correct

#### Wrong

```python
process = await asyncio.create_subprocess_shell(command_with_cookie)
await process.stdin.write(unbounded_json_with_cookie)
status = "connected" if process.returncode == 0 else "failed"
await borrowed_context.close()
```

#### Correct

```python
platform = AUTH_PLATFORM_BY_ID[requested_platform]
process = await asyncio.create_subprocess_exec(
    *FIXED_PERSISTENT_WORKER_COMMAND,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,
)
await write_exact_v2_check(process.stdin, request_id, platform)
result = await read_correlated_constant_result(process.stdout, request_id, platform)
status = project_allowed_result_pair(result)
# The MediaCrawler request `finally` closes only its registered pages.
# FastAPI keeps the healthy worker alive and sends shutdown during lifespan exit.
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
