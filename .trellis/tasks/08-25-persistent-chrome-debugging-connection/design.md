# Technical Design

## Architecture and ownership

Replace the current one-process-per-check lifecycle with one lazily launched, FastAPI-lifespan-owned
MediaCrawler worker:

```text
React platform row / “一键检测”
  -> existing POST /api/v1/platform-connections/{platform}/attempts
  -> PlatformConnectionService single-flight state machine
  -> inherited stdin/stdout pipes
  -> persistent MediaCrawler authentication worker
       -> one manually started Playwright runtime
       -> one CDPBrowserManager
       -> one approved Browser connection
       -> Chrome's borrowed default BrowserContext
       -> one serialized platform authentication coroutine
       -> only the task-created Page(s)
  -> existing GET polling and row projection
```

The worker is not launched by FastAPI startup, application lifespan entry, `GET`, or React page
load. The first accepted platform `POST` launches it; the worker emits `ready` before touching
Playwright or Chrome, and the first `check` command establishes the CDP connection.

Normal platform completion closes only the pages explicitly registered by that request. The
worker, Playwright runtime, Browser, default BrowserContext, and CDP transport remain alive for the
next request. FastAPI shutdown, worker failure, or Chrome/CDP disconnect ends this reuse window.

## Public compatibility

Keep the existing product contract unchanged:

```http
GET  /api/v1/platform-connections
POST /api/v1/platform-connections/{platform}/attempts
```

- Keep the existing HTTP 202 response, catalog payload, error envelopes, polling behavior, and
  global HTTP 409 `connection_attempt_active` rule.
- Keep the React five-platform batch as serialized per-platform POSTs; do not add a bulk route.
- Add no persistent-worker/session field to the public response and no UI status badge. Browser and
  worker lifecycle details remain behind the service boundary.
- Product state remains in memory and resets on backend restart.

## Persistent worker protocol

### Transport and framing

Launch one fixed command with `create_subprocess_exec`, `stdin`, `stdout`, `stderr`, and the existing
owned POSIX process group. Use inherited pipes rather than a TCP or Unix-domain listener.

Use a strict NDJSON v2 protocol:

- UTF-8, exactly one prefixed JSON object per line;
- maximum 1,024 bytes including prefix and newline;
- parent commands use `__MEDIACRAWLER_AUTH_COMMAND__`;
- child events use `__MEDIACRAWLER_AUTH_EVENT__`;
- reject duplicate JSON keys and every unknown, missing, extra, mistyped, oversized, malformed,
  non-prefixed, or out-of-order frame;
- reserve stdout for protocol only; drain stderr continuously without parsing, retaining, returning,
  or copying it into product state;
- reuse the public attempt UUID as the `request_id` and require an exact UUID/platform match before
  mutating state.

Keep the existing one-shot `main.py --type auth` v1 protocol for direct tests and rollback. Do not
make either decoder accept both protocol versions.

### Exact v2 message families

Parent-to-worker commands are strict discriminated objects:

```json
{"version":2,"type":"command","command":"check","request_id":"<uuid>","platform":"wb"}
{"version":2,"type":"command","command":"cancel","request_id":"<uuid>"}
{"version":2,"type":"command","command":"shutdown"}
```

Worker-to-parent events are:

```json
{"version":2,"type":"event","event":"ready"}
{"version":2,"type":"event","event":"progress","request_id":"<uuid>","platform":"wb","phase":"checking"}
{"version":2,"type":"event","event":"result","request_id":"<uuid>","platform":"wb","outcome":"connected","reason":"none"}
{"version":2,"type":"event","event":"session","state":"disconnected","reason":"browser_disconnected"}
{"version":2,"type":"event","event":"stopped"}
```

The trusted platform enum remains exactly `wb | dy | ks | xhs | toutiao`. Progress phases are the
existing nonterminal phases `waiting_for_browser | waiting_for_approval | checking |
waiting_for_login`. Existing platform code may continue to use its current internal terminal phase
representation, but the worker converts terminal proof into one exact v2 result:

| Outcome | Reason | Product projection |
| --- | --- | --- |
| `connected` | `none` | `connected / none` |
| `disconnected` | `login_required` | `disconnected / retry` |
| `failed` | `browser_unavailable` | `failed / enable_remote_debugging` or the latest actionable browser guidance |
| `failed` | `browser_disconnected` | `failed / retry` |
| `failed` | `internal_error` | `failed / retry` |
| `cancelled` | `cancelled` | cleanup acknowledgement only; public attempt becomes `failed / retry` |

No message, URL, port, WebSocket endpoint, profile path, account detail, Cookie, authorization
material, QR data, page content, raw exception, or arbitrary configuration may cross this protocol.

### Request and session state machines

The backend separates long-lived worker state from one bounded request:

```text
DORMANT -- first accepted POST --> STARTING -- ready --> IDLE
IDLE -- check written --> BUSY(request_id, platform) -- valid result --> IDLE
BUSY -- timeout --> CANCELLING -- cancelled result --> IDLE
CANCELLING -- grace expires --> recycle worker --> DORMANT
STARTING/BUSY/IDLE -- EOF, crash, malformed frame, writer failure --> recycle --> DORMANT
IDLE/BUSY -- session disconnected --> invalidate session and connected projections
any live state -- FastAPI shutdown --> STOPPING --> stopped + exit 0, else TERM/KILL
```

The worker emits `ready` from `IDLE_NO_CDP`, then processes one request at a time. While a platform
coroutine is running, its command loop may accept only the matching `cancel` or `shutdown`; a second
`check`, mismatched cancel, or malformed command fails closed. The platform task runs in a child
`asyncio.Task` so cancellation and shutdown remain responsive.

Each request validates the current progress order. Skipped initial browser phases are allowed when
CDP is already connected, but repeated/skipped emitted phases, duplicate results, events after a
result, mismatched UUID/platform, or an unknown request recycle the worker.

## MediaCrawler browser session

The worker owns one manually started `async_playwright()` runtime and one `CDPBrowserManager`.

- Start Playwright only on the first valid `check`.
- Call `connect_over_cdp` once for an explicit connection attempt, using the fixed loopback endpoint,
  `is_local=True`, and `no_defaults=True`.
- Borrow an existing default BrowserContext from `browser.contexts`; in borrowed mode, fail closed
  if no context exists instead of creating an incognito context.
- Register `browser.on("disconnected")` and check `browser.is_connected()` before every request.
- Rebind connection-progress emission to the current request/platform only while establishing a new
  CDP session.
- Keep one explicit registry of task-created pages. Close that registry in each request's `finally`;
  never claim pages merely because they appeared in the shared context.
- Never call `BrowserContext.close()`, `Browser.close()`, or terminate the user's Chrome. On worker
  shutdown, close owned pages, release borrowed references, and stop the Playwright transport.
- Keep Chrome's remote-debugging settings helper unowned. It may open the visible settings page only
  when the fixed loopback endpoint is unavailable.

A healthy `disconnected/login_required` platform result does not discard the shared CDP session.
The user can log in during the visible platform flow, or run a later check, without another Chrome
approval while the session remains connected.

## Platform authentication refactor

Extract one injected-context authentication body from each platform crawler, conceptually:

```python
async def authenticate_with_context(
    browser_context: BrowserContext,
    cdp_manager: CDPBrowserManager,
    emit_phase: Callable[[AuthPhase], None],
) -> AuthPhase: ...
```

The current one-shot auth wrapper starts a temporary Playwright/CDP owner and delegates to this
body. The persistent worker delegates with its shared objects. Do not duplicate or move the
platform-specific probes into FastAPI.

- **Weibo:** preserve the scoped `.weibo.cn` Cookie refresh and `/api/config` online proof before
  and after visible login.
- **Douyin:** preserve the fresh official-page same-origin account probe and manual challenge
  boundary. Do not add the current context-wide stealth init script in persistent borrowed auth;
  it would affect future user tabs.
- **Kuaishou:** preserve the official `visionProfileUserList` proof and page-local signing capture
  script; a changed `passToken` remains only a wake-up hint.
- **Xiaohongshu:** preserve signed self-info `pong()`, allowlisted current-context Cookie refresh,
  visible login, and mandatory post-login proof.
- **Toutiao:** preserve fresh trusted-origin DOM classification and the no-click/no-navigation
  manual wait.

Extract the current auth-safe global configuration into one shared function used by both v1 and v2,
and reapply it before every worker command because MediaCrawler configuration is mutable process
state. It must force borrowed visible Chrome, loopback CDP, no proxy, no saved auth state, no data
store, and no search/detail/creator/comment/media work.

## Failure recovery and shutdown

Use one idempotent, generation-aware backend recycle path for ready timeout, write failure,
unexpected EOF/exit, malformed/out-of-order IPC, or unacknowledged cancellation:

1. invalidate the active request future and ignore all late callbacks from the old generation;
2. clear worker/session references before allowing another request;
3. terminate only the owned worker process group with graceful TERM then bounded KILL fallback;
4. fail the active attempt with constant-derived guidance and no raw child output;
5. move every previously `connected` enabled row to a safe non-connected `failed / retry` projection,
   retaining its last checked timestamp;
6. do not reconnect automatically; the next explicit POST launches or reconnects lazily.

Timeout handling first sends `cancel(request_id)` and waits three seconds for the exact cancelled
result so the platform task can close its page. Missing acknowledgement recycles the worker. Worker
readiness has a 30-second sub-limit inside the existing 300-second whole-attempt timeout.

FastAPI shutdown stops accepting attempts, cancels and drains an active request, sends `shutdown`,
waits up to five seconds for `stopped` plus exit code 0, then falls back to the existing three-second
TERM/KILL process-group escalation. Exit code alone never proves a request result. Unexpected worker
EOF is never normal outside a validated shutdown.

Chrome disconnect uses a separate, still fail-closed session-invalidation path because the worker
transport itself may remain healthy. During a request, the worker must prevent a successful terminal
result, emit one `failed/browser_disconnected` result and one session-disconnected event, clean task
pages on a best-effort basis, and return to a no-CDP state. While idle, it emits the session event
directly. FastAPI invalidates every stale connected projection but may keep the worker process; the
next user action reconnects lazily and may create a new native approval prompt. If the worker does
not complete this protocol correctly, the normal recycle path applies.

## Testing strategy

### MediaCrawler derivative

- Strict v2 command/event codec tests: versions, exact shapes, duplicate keys, UUIDs, enums, frame
  size, prefix, malformed UTF-8, ordering, mismatch, duplicate result, and secret sentinels.
- Fake connector proves two different platform checks use one `connect_over_cdp` call and the same
  BrowserContext identity while creating and closing different owned pages.
- Worker lifecycle proves no Playwright/CDP before the first `check`, responsive cancel/shutdown,
  second-check rejection while busy, idle/busy disconnect behavior, and clean borrowed shutdown.
- Borrowed-mode tests prove zero-context failure, `no_defaults=True`, sentinel-tab survival, and no
  context/browser/Chrome close calls.
- Preserve all current five-platform auth, authoritative proof, no-collection, timeout,
  cancellation, and narrow-cleanup tests; add explicit Douyin no-context-wide-stealth coverage.

### Backend

- Extend the fake process seam with writable stdin and scheduled persistent stdout.
- Prove startup/GET launch zero workers; the first POST launches one; later platforms write new
  request IDs to the same process; concurrent POST still returns the exact 409.
- Cover ready/write/EOF/exit/timeout/cancel/shutdown failures, all strict frame failures,
  cross-platform and request mismatches, stale-generation callbacks, idle crashes, and disconnect
  invalidation.
- Prove stderr credential sentinels never reach state, API, errors, logs, or retained evidence.
- Retain exact GET/202/404/409/OpenAPI contract tests.

### Frontend and live acceptance

- Keep existing batch, polling, lock, guidance, error, accessibility, and decoder tests. Add only a
  compatible projection sequence covering first approval guidance, a later direct `checking`, and
  disconnect-driven failure; native prompt count is not a React assertion.
- Live loopback acceptance verifies: no prompt before POST; one approval; at least two different
  platform checks plus a repeat over one worker/CDP generation; serialized page activity; sentinel
  tab survival; Chrome survival after FastAPI stops; stale-state invalidation and a new approval
  after deliberate Chrome/worker disconnect.
- Record only timestamps, loopback address, platform/phase/outcome constants, prompt count, worker
  generation count, page ownership counts, and terminal categories.

## Migration and rollback

1. Extract and test injected-context platform auth bodies while keeping v1 one-shot behavior.
2. Add the v2 worker, protocol, shared browser session, and deterministic MediaCrawler tests.
3. Add a backend persistent-worker client behind the current process-launcher/terminator seams and
   switch only the service's internal strategy.
4. Keep public API/React production behavior unchanged, run all frozen gates, then perform live
   acceptance.
5. Commit and push the MediaCrawler derivative first, then update the parent submodule gitlink and
   parent specs/task artifacts.

Keep v1 for one release. Rollback is an intentional backend switch/revert to the one-shot v1 worker;
v2 protocol failures must never trigger an automatic v1 fallback.
