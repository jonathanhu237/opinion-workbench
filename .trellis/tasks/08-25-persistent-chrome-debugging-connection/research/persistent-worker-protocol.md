# Research: Persistent MediaCrawler worker protocol and lifecycle

- Query: How should FastAPI own a long-lived MediaCrawler worker that reuses one user-approved
  Chrome CDP connection across serialized platform checks, while preserving the current public API,
  authentication probes, page ownership, and fail-closed behavior?
- Scope: mixed (local code/spec inspection plus primary Chromium, Chrome, and Playwright sources)
- Date: 2026-08-25

## Findings

### Recommendation

Use one **FastAPI-lifespan-owned, lazily launched MediaCrawler subprocess** and communicate over
its inherited `stdin`/`stdout` pipes with a strict, versioned NDJSON protocol. The worker should
own the Playwright runtime, one `Browser` returned by `connect_over_cdp`, and the borrowed default
`BrowserContext` until FastAPI shutdown, worker exit, or Chrome disconnects. Each platform check
is still a bounded request that creates and closes only its own page.

Do not use a TCP or Unix-domain socket for this feature. The parent already owns the subprocess;
inherited pipes are smaller, cross-platform, require no listener or discovery, and cannot be reached
by unrelated local processes through an exposed port. Keep Chrome CDP itself fixed to loopback.

The public API does not need to change. Keep:

```http
GET  /api/v1/platform-connections
POST /api/v1/platform-connections/{platform}/attempts
```

Keep the React batch as five serialized POSTs. Its current reducer waits for one platform to reach a
terminal catalog state before starting the next (`frontend/src/routes/platform-accounts.tsx:317-377`),
and it already disables all row actions while any attempt is active
(`frontend/src/routes/platform-accounts.tsx:248-286`).

### Why the current implementation prompts for every platform

- FastAPI creates exactly one `PlatformConnectionService` for the application lifespan and calls
  `shutdown()` at application shutdown (`backend/src/longtian_api/main.py:18-25`). This is already
  the right owner for a persistent worker.
- The service currently launches a new process inside every `_execute_worker()` call
  (`backend/src/longtian_api/services/platform_connections.py:261-270`) and always terminates a
  still-running process in the attempt `finally` block
  (`backend/src/longtian_api/services/platform_connections.py:220-255`). A second platform therefore
  cannot reuse either the process or Playwright object.
- Each platform currently enters its own `async_playwright()` context and calls its own CDP manager;
  for example Weibo does this at `third_party/MediaCrawler/media_platform/weibo/core.py:84-108`,
  Douyin at `third_party/MediaCrawler/media_platform/douyin/core.py:89-115`, XHS at
  `third_party/MediaCrawler/media_platform/xhs/core.py:194-205`, and Toutiao at
  `third_party/MediaCrawler/media_platform/toutiao/core.py:75-87`.
- Existing-browser mode always emits `waiting_for_approval` before calling `connect_over_cdp`
  (`third_party/MediaCrawler/tools/cdp_browser.py:177-242`). Chromium states that approval mode
  requires every incoming connection to be approved
  ([source, lines 185-188 and 397-405](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/devtools/remote_debugging_server.cc)).
  Therefore process/Playwright/CDP connection reuse, not frontend batching, is the required fix.

### Transport and framing

Recommended worker command (no platform, endpoint, profile path, or credential arguments):

```text
uv run --frozen --project third_party/MediaCrawler python persistent_auth_worker.py
```

Protocol rules:

1. UTF-8, one JSON object per line, newline terminated, maximum 1,024 bytes including prefix and
   newline.
2. Parent-to-child frames use `__MEDIACRAWLER_AUTH_COMMAND__`; child-to-parent frames use the existing
   `__MEDIACRAWLER_AUTH_EVENT__` prefix.
3. Version `2` is a new multi-request protocol. Do not make the same decoder accept legacy v1 and
   v2. The current `main.py --type auth` process retains v1 for rollback and direct tests.
4. Validate from `unknown` with strict discriminated models, `extra="forbid"`, exact enums, canonical
   UUIDs, and rejection of duplicate JSON keys. Any unknown, missing, extra, wrong-type, oversized,
   non-prefixed, malformed, or out-of-order stdout frame is a protocol failure.
5. Reserve stdout for protocol frames. MediaCrawler logging is already configured through Python
   logging, whose default stream is stderr (`third_party/MediaCrawler/tools/utils.py:29-45`). Drain
   stderr continuously in bounded byte chunks, but never parse, retain, return, or copy it into
   product state. Ordinary stdout is not silently accepted in v2.
6. Use the public FastAPI `attempt_id` as the IPC `request_id`; do not generate a second correlation
   identifier.

Inherited pipes require no authentication secret. If a future design replaces them with a socket,
that socket must bind only to `127.0.0.1`/`::1` and require a fresh high-entropy capability sent over
an inherited pipe, never in argv, environment, a predictable file, URL, logs, or API payload. That
socket design is unnecessary for this task.

### Exact protocol shapes

All field values below are constants/enums except the UUID `request_id`. A platform is exactly one
of `wb | dy | ks | xhs | toutiao`.

Parent to worker:

```json
__MEDIACRAWLER_AUTH_COMMAND__{"version":2,"type":"command","command":"check","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb"}
__MEDIACRAWLER_AUTH_COMMAND__{"version":2,"type":"command","command":"cancel","request_id":"00000000-0000-4000-8000-000000000001"}
__MEDIACRAWLER_AUTH_COMMAND__{"version":2,"type":"command","command":"shutdown"}
```

Worker to parent:

```json
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"ready"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"progress","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb","phase":"waiting_for_browser"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"progress","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb","phase":"waiting_for_approval"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"progress","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb","phase":"checking"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"progress","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb","phase":"waiting_for_login"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"result","request_id":"00000000-0000-4000-8000-000000000001","platform":"wb","outcome":"connected","reason":"none"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"session","state":"disconnected","reason":"browser_disconnected"}
__MEDIACRAWLER_AUTH_EVENT__{"version":2,"type":"event","event":"stopped"}
```

Allowed `result` pairs only:

| outcome | reason | Public projection |
| --- | --- | --- |
| `connected` | `none` | `connected / none` |
| `disconnected` | `login_required` | `disconnected / retry` |
| `failed` | `browser_unavailable` | `failed / enable_remote_debugging` |
| `failed` | `browser_disconnected` | `failed / retry` |
| `failed` | `internal_error` | `failed / retry` |
| `cancelled` | `cancelled` | `failed / retry` (shutdown/timeout cleanup only) |

Do not add dynamic `message`, URL, error, browser, account, page, Cookie, challenge, or diagnostic
fields. Backend guidance remains derived from validated constants and the most recent progress
phase, as it is now at `backend/src/longtian_api/services/platform_connections.py:308-328`.

The `session/disconnected` event is request-independent. It lets FastAPI invalidate stale
`connected` projections even if Chrome closes while the worker is idle. No `session_id`, WebSocket
URL, port selected by input, or browser metadata should cross IPC.

### State machines

Parent/service state:

```text
DORMANT (no child)
  -- first accepted POST --> STARTING
STARTING
  -- ready --> IDLE
  -- timeout / EOF / malformed / exit --> DORMANT + fail active attempt
IDLE
  -- check written --> BUSY(request_id, platform)
BUSY
  -- valid progress --> BUSY (update existing product projection)
  -- valid result --> IDLE
  -- timeout --> CANCELLING
  -- EOF / malformed / exit --> DORMANT + fail active + invalidate stale connected states
CANCELLING
  -- cancelled result --> IDLE
  -- grace expires --> terminate process group --> DORMANT
IDLE or BUSY
  -- session disconnected --> keep/reach IDLE, clear session knowledge,
                              invalidate all stale connected projections
any live state
  -- FastAPI shutdown --> STOPPING --> stopped + exit 0, else TERM/KILL --> STOPPED
```

Worker state:

```text
BOOTING -- protocol loop ready --> IDLE_NO_CDP (emit ready)
IDLE_NO_CDP -- check --> CONNECTING
CONNECTING -- approved connect --> RUNNING
CONNECTING -- unavailable/declined/timeout --> IDLE_NO_CDP (failed/browser_unavailable)
IDLE_WITH_CDP -- check --> RUNNING
RUNNING -- result + owned-page cleanup --> IDLE_WITH_CDP
RUNNING -- cancel --> cancelling task + owned-page cleanup --> IDLE_WITH_CDP
RUNNING -- browser disconnected --> cancel task, close-owned-page best effort,
                                    result failed/browser_disconnected,
                                    session disconnected, IDLE_NO_CDP
IDLE_WITH_CDP -- browser disconnected --> session disconnected, IDLE_NO_CDP
any state -- shutdown --> STOPPING --> close owned pages, stop Playwright transport,
                          release references, emit stopped, exit 0
```

Each request has its own phase validator. Allowed progress is the current contract:

```text
start -> waiting_for_browser -> waiting_for_approval -> checking
start ------------------------> waiting_for_approval -> checking
start -----------------------------------------------> checking
checking -> connected-result
checking -> disconnected-result
checking -> waiting_for_login -> checking -> connected-result|disconnected-result
```

`failed` or `cancelled` may terminate from any nonterminal phase. A repeated phase, skipped emitted
phase, duplicate result, event after result, unknown request ID, wrong platform, or a second check
while busy fails closed and recycles the worker. The 20 ordered cross-platform mismatch regression
in the current suite (`backend/tests/test_platform_connections.py:601-649`) should be retained for
v2 request frames.

### Lazy startup and browser ownership

- Do not launch the worker at FastAPI startup or on `GET`. The first accepted POST schedules the
  existing non-blocking background attempt; that background task calls `ensure_worker()`.
- `ensure_worker()` launches exactly one child, starts stdout/stderr/process-wait monitor tasks,
  waits for `ready`, then writes the first `check` command. Launch and readiness are part of the
  existing overall attempt timeout.
- Worker `ready` means only “IPC command loop ready.” It must not connect to Chrome. The first
  `check` starts Playwright and calls `connect_over_cdp`, ensuring app startup and page load cause no
  prompt.
- Keep the Playwright object alive. Playwright documents that `connect_over_cdp` attaches to an
  existing Chromium browser and exposes its default context through `browser.contexts`
  ([BrowserType docs](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)).
  The repository resolves Playwright 1.61.0 (`third_party/MediaCrawler/uv.lock:1261-1275`). Use
  `is_local=True` and `no_defaults=True`; the latter is explicitly intended to avoid Playwright
  default overrides when attaching to a user's daily browser (same primary documentation).
- Register `browser.on("disconnected")`. Playwright defines that event for browser application
  close/crash or browser closure
  ([Browser docs](https://playwright.dev/python/docs/api/class-browser#browser-event-disconnected)).
  Also check `browser.is_connected()` before every request to cover event-loop races.
- Do not call `browser.close()` or `context.close()` for the borrowed default context. Playwright
  notes the default context cannot be closed
  ([BrowserContext docs](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-close)),
  and project ownership rules already prohibit closing borrowed context/browser
  (`.trellis/spec/backend/platform-connection-guidelines.md:88-94`).
- On individual completion, call only the existing owned-page cleanup
  (`third_party/MediaCrawler/tools/cdp_browser.py:63-82`). On worker shutdown, close owned pages,
  suppress only credential-free already-closed/disconnected cleanup noise, release borrowed
  references, and stop the Playwright runtime. Never send `Browser.close`, close the default
  context, or signal the user's Chrome process.
- Open `chrome://inspect/#remote-debugging` only when the loopback port is unavailable. The existing
  helper deliberately launches this as an unowned, separate session
  (`third_party/MediaCrawler/tools/browser_launcher.py:191-218`), so terminating the worker process
  group cannot terminate Chrome.
- Make exactly one `connect_over_cdp` attempt per explicit reconnection. Chromium approves each
  incoming connection; silently falling back to a second connection after an approval timeout can
  produce another prompt. In approval mode the direct fixed loopback endpoint is the supported
  path in current code (`third_party/MediaCrawler/tools/cdp_browser.py:360-388`). A failed attempt
  should return `browser_unavailable`; retry only after the next user action.

Chrome's command-line `--remote-debugging-port` behavior on the default data directory changed in
Chrome 136; Chrome recommends a separate user-data directory for that command-line automation
path ([Chrome for Developers, 2025-03-17](https://developer.chrome.com/blog/remote-debugging-port)).
This project deliberately does not work around that restriction: it uses the visible
`chrome://inspect` approval path, borrows the current profile, and keeps the endpoint loopback-only.

### Minimal MediaCrawler refactor boundary

The current platform-specific online probes and login behavior should not move into FastAPI. Add a
worker-scoped browser session and extract one context-injected authentication function per crawler:

```python
async def authenticate_with_context(
    browser_context: BrowserContext,
    page_owner: OwnedPageRegistry,
    emit_phase: Callable[[AuthPhase], None],
) -> AuthPhase: ...
```

The existing one-shot `start()` path should create its temporary manager and call the same function;
the persistent worker calls it with the shared borrowed context. This avoids duplicating the
authoritative probes described in the platform spec
(`.trellis/spec/backend/platform-connection-guidelines.md:57-87`) and preserves current direct
MediaCrawler tests.

The persistent worker entry point must hard-code the same safe auth configuration currently forced
by the CLI (`third_party/MediaCrawler/cmd_arg/arg.py:377-428`): visible borrowed Chrome, no proxy,
no Cookies input, no saved login state, no storage, and no search/detail/creator/comment/media work.
Only the trusted platform enum may change between serialized requests. Never accept arbitrary
configuration through IPC.

### Serialization and request ownership

- Retain the FastAPI service lock and current HTTP 409 `connection_attempt_active` behavior
  (`backend/src/longtian_api/services/platform_connections.py:150-186`). Split current fields into
  `_worker_process`/reader monitors (long-lived) and `_current_attempt_task` (bounded).
- Maintain one pending result future keyed by the active UUID. A progress/result event must match
  both UUID and platform before any product state changes.
- The worker command reader must stay responsive while an auth coroutine runs: execute the auth
  request in a child `asyncio.Task`; the command loop may accept only matching `cancel` or
  `shutdown`. It must never start a second page operation.
- The frontend's `AbortController` currently cancels only the POST request
  (`frontend/src/routes/platform-accounts.tsx:209-245`). Preserve this behavior: after HTTP 202,
  navigation or polling cancellation does not cancel the accepted backend attempt. There is no
  public cancellation endpoint in this task.

### Timeouts and cancellation

Recommended defaults, all injectable in tests:

| Boundary | Default | Behavior |
| --- | ---: | --- |
| Whole platform attempt | existing 300 s | Includes lazy worker start, CDP approval, probe, and manual login |
| Worker `ready` within whole attempt | 30 s | On expiry terminate worker group and fail request |
| Cancel acknowledgement | 3 s | Then terminate worker group; never signal Chrome |
| Graceful shutdown (`stopped` + exit) | 5 s | Then existing TERM/KILL process-group escalation |
| TERM grace | existing 3 s | Then SIGKILL/process.kill fallback |

On attempt timeout, parent sends `cancel(request_id)` and waits for the exact cancelled result.
The worker cancels the active platform task, awaits its `finally` cleanup, and emits one result. If
the worker does not acknowledge, terminate and forget it. A future explicit POST starts a new
worker/CDP connection and may require Chrome approval.

FastAPI shutdown should:

1. Stop accepting new attempts.
2. Cancel the active request and allow task-owned page cleanup.
3. Send `shutdown` after the active request is terminal (or immediately after cancel timeout).
4. Await `stopped` and exit 0 for up to five seconds.
5. Fall back to existing owned process-group TERM/KILL logic
   (`backend/src/longtian_api/services/platform_connections.py:482-522`).
6. Mark any active product attempt failed, clear all active IDs and worker references, and return
   without closing Chrome or its pre-existing tabs.

### Crash, EOF, malformed frame, and disconnect recovery

Use one idempotent `recycle_worker(reason_constant)` path for all transport failures:

- Cancel the stdout reader, stderr drainer, process waiter, and active result future without
  including exception or raw child text in product state.
- Terminate only the owned worker process group if it is still alive.
- Clear stdin/stdout/process/session references before releasing the service lock.
- Complete the active attempt as `failed / retry` (or the existing actionable browser guidance if
  the last valid phase was browser/approval waiting).
- Change every previously `connected` enabled catalog entry to a non-connected safe state
  (`failed / retry`, retaining its last checked timestamp) because the session that supported that
  observation no longer exists. This satisfies the requirement that disconnect cannot leave a
  false connected projection without extending the public API.
- Ignore late callbacks from the old generation. Capture a monotonically increasing in-memory
  worker generation in every monitor callback; only the current generation may mutate state.
- Do not auto-restart. The next explicit platform POST lazily launches a new worker.

EOF is normal only after a valid `stopped` event during service shutdown and exit code 0. Exit code
alone never proves a platform result. EOF at any other time, any nonzero exit, malformed frame,
unknown request, or writer failure invokes the same recovery path. A worker crash after a valid
`connected` result still invalidates that status when the process monitor observes the crash.

### What the UI should observe

No new API fields or frontend protocol are necessary:

1. App/FastAPI startup and initial GET: all rows stay at their stored in-memory projection; no
   Chrome dialog appears.
2. First check with remote debugging disabled: row becomes `需要操作` with
   `enable_remote_debugging`; Chrome opens the visible settings page.
3. First incoming CDP connection: row becomes `需要操作` with `approve_connection`; exactly one
   Chrome approval dialog appears.
4. After approval: row becomes `检查中`. If the account is not logged in, it becomes `需要操作` with
   `complete_login`, and the user logs in on the task-created page in the current Chrome. Only the
   authoritative post-login probe can produce `已登录`.
5. Later platform checks while the same Browser remains connected start at `检查中`; they must not
   show approval guidance or another Chrome approval dialog.
6. An unsuccessful authentication probe ends `未登录` and uses the existing row prompt to log in
   in the current Chrome. A technical worker/browser failure ends `检查失败`; no raw details appear.
7. Idle worker/Chrome disconnect invalidates prior `已登录` rows to `检查失败`. The next explicit
   check re-enters browser/approval guidance and may show a new Chrome dialog.

Another Chrome prompt is unavoidable after any event that destroys the incoming debugging
connection: FastAPI restart, persistent-worker restart/crash/forced recycle, Playwright transport
stop, Chrome close/crash/restart, disabling and re-enabling remote debugging, or a CDP connection
drop. It is also unavoidable mid-batch if the shared connection dies before the next platform. It
is **not** expected merely because the platform changes or the user repeats a check while the same
worker, Playwright runtime, Browser, and Chrome connection remain alive.

### Deterministic validation plan

#### MediaCrawler unit tests

1. Exact v2 command/event round trips for every platform/phase/result pair; reject wrong version,
   duplicate keys, extra fields, noncanonical UUID, unknown enum, wrong platform, malformed UTF-8,
   non-prefixed stdout, and 1,025-byte frames.
2. Fake connector: two sequential checks for different platforms call `connect_over_cdp` exactly
   once, reuse the identical BrowserContext object, and create two different owned pages.
3. `browser.on("disconnected")` while idle emits one session event and clears references; while busy
   it cancels the request, emits exactly one failed result, then one session event.
4. Cancellation and shutdown close only registered pages. A pre-existing sentinel page remains;
   borrowed `context.close`, `browser.close`, and Chrome process cleanup are never called.
5. Worker remains responsive to cancel/shutdown while the platform coroutine blocks. A second
   check, mismatched cancel, and malformed parent command fail closed.
6. Preserve all existing platform probe/login regressions and auth configuration sentinels,
   especially `third_party/MediaCrawler/tests/test_auth_mode.py:39-126` and the platform-specific
   tests enumerated in `.trellis/spec/backend/platform-connection-guidelines.md:155-168`.

#### Backend unit/integration tests

Extend the existing `FakeProcess` seam (`backend/tests/test_platform_connections.py:62-137`) into a
duplex fake with a captured stdin writer and queued stdout frames:

1. Creating the FastAPI app, entering lifespan, GET, and opening the React page launch zero workers.
2. First POST launches one worker; a second platform after a terminal result uses the same process,
   writes a second request ID, and launch count stays one.
3. Concurrent POST still returns exact 409 and writes no second check.
4. `ready` timeout, write failure, EOF before/after ready, exit before result, nonzero idle exit,
   oversized/malformed/extra-field frame, wrong UUID/platform, duplicate result, result-before-check,
   and stale-generation callbacks all recycle the worker without cross-platform mutation.
5. Timeout sends cancel; missing cancel result triggers TERM/KILL. Shutdown sends cancel then
   shutdown, accepts only `stopped` + exit 0, and leaves catalog with no active IDs.
6. Idle session disconnect and idle worker crash invalidate every connected projection. The next
   POST launches a new worker and projects `approve_connection` when that phase arrives.
7. stderr containing credential sentinels is drained but absent from API responses, state, captured
   product logs, and assertion evidence.
8. Existing exact GET/202/404/409/OpenAPI tests remain byte-for-shape compatible.

#### Frontend tests

The existing API decoder requires exact keys (`frontend/src/lib/api/platform-connections.ts:108-175`),
so unchanged schemas prove compatibility. Retain current one-click batch, polling, active-action,
error, and login-guidance tests. Add only a projection scenario showing first request
`approve_connection`, subsequent request direct `checking`, and a disconnect-driven `failed` state;
do not model or count the native Chrome dialog in React tests.

#### Live loopback acceptance

1. Start FastAPI and React with Chrome running; verify no worker/CDP connection and no prompt before
   a POST.
2. Start one platform check, approve once, then run at least one different platform check and a
   repeated check. Verify one worker generation, one `connect_over_cdp` call (through test-safe
   instrumentation), one native approval, serialized page activity, and terminal authoritative
   results.
3. Keep a pre-existing sentinel tab open. Verify only task-created pages close after each attempt.
4. Stop FastAPI while Chrome remains open; verify Chrome and sentinel tab remain.
5. Separately close/restart Chrome or kill the worker, verify stale connected states clear, and
   verify the next explicit check requires a new approval.
6. Record only timestamps, listener address `127.0.0.1`, phase/outcome constants, prompt count,
   worker-generation count, page ownership counts, and terminal categories. Record no URLs beyond a
   fixed non-sensitive sentinel, Cookies, headers, QR material, page content, profile paths, account
   identity, WebSocket URL, or raw stderr.

### Migration and rollback

1. First extract context-injected platform auth functions and keep all current one-shot v1 tests
   passing.
2. Add the v2 worker entry point and deterministic fake-browser/IPC tests without changing FastAPI.
3. Add the backend persistent-worker manager behind the existing `ProcessLauncher`/terminator
   injection seam and switch only the service's internal worker strategy.
4. Run MediaCrawler-derived, backend, and frontend frozen gates, then the live loopback acceptance.
5. Keep `main.py --type auth` and the v1 parser untouched for one release. Operational rollback is
   a narrow backend default switch/revert to the existing per-attempt command; public API and React
   require no rollback.
6. Do not make v2 fall back automatically to v1 after a malformed frame. Protocol drift must fail
   closed; an intentional code rollback selects the v1 launcher before process start.

## Files Found

- `.trellis/tasks/08-25-persistent-chrome-debugging-connection/prd.md` — source requirements and
  acceptance boundaries.
- `.trellis/spec/backend/platform-connection-guidelines.md` — current API, child protocol,
  authentication authority, ownership, error matrix, and test contract.
- `backend/src/longtian_api/main.py` — FastAPI lifespan ownership point.
- `backend/src/longtian_api/services/platform_connections.py` — current one-process-per-attempt
  lifecycle, phase decoder, timeout, and process-group termination.
- `backend/tests/test_platform_connections.py` — current fake process/reader/launcher/terminator
  seams and failure matrix.
- `third_party/MediaCrawler/tools/auth.py` — v1 constant-only auth phases and events.
- `third_party/MediaCrawler/tools/cdp_browser.py` — existing borrowed-browser connection,
  task-owned page registry, and cleanup behavior.
- `third_party/MediaCrawler/tools/browser_launcher.py` — loopback owned-browser flags and unowned
  visible settings-page launch.
- `third_party/MediaCrawler/cmd_arg/arg.py` — authentication-only safe configuration override.
- `third_party/MediaCrawler/media_platform/{weibo,douyin,kuaishou,xhs,toutiao}/core.py` — five
  platform-specific authentication flows and authoritative probe boundaries.
- `frontend/src/routes/platform-accounts.tsx` — current serialized batch queue and UI guidance.
- `frontend/src/lib/api/platform-connections.ts` — exact public response decoder.

## External References

- Chromium source, `remote_debugging_server.cc` — approval mode and per-incoming-connection user
  approval:
  https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/devtools/remote_debugging_server.cc
- Chrome for Developers, “Changes to remote debugging switches to improve security,” 2025-03-17 —
  Chrome 136 default-profile command-line restriction and custom-profile recommendation:
  https://developer.chrome.com/blog/remote-debugging-port
- Playwright Python `BrowserType.connect_over_cdp` — attaching to an existing Chromium browser,
  default context, CDP fidelity warning, `is_local`, and `no_defaults`:
  https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp
- Playwright Python `Browser` — `is_connected` and `disconnected` event:
  https://playwright.dev/python/docs/api/class-browser#browser-event-disconnected
- Playwright Python `BrowserContext` — default-context and close semantics:
  https://playwright.dev/python/docs/api/class-browsercontext#browser-context-close

## Related Specs

- `.trellis/spec/backend/platform-connection-guidelines.md`
- `.trellis/spec/backend/auth-state-guidelines.md`
- `.trellis/spec/backend/error-handling.md`
- `.trellis/spec/backend/logging-guidelines.md`
- `.trellis/spec/backend/quality-guidelines.md`
- `.trellis/spec/frontend/state-management.md`
- `.trellis/spec/frontend/type-safety.md`
- `.trellis/spec/guides/cross-layer-thinking-guide.md`
- `.trellis/spec/guides/code-reuse-thinking-guide.md`

## Caveats / Not Found

- Chrome approval dialogs are native browser UI and cannot be deterministically asserted by unit or
  React tests. The “one approval” acceptance requires a manual/live Chrome run; code-level tests
  prove one process and one `connect_over_cdp` call.
- Playwright documents CDP connections as lower fidelity than its native protocol. Existing
  platform flows already use CDP, so this task does not introduce that limitation, but the full
  five-platform live gate remains necessary.
- There is no safe requirement or implementation path for “never prompt again.” The design removes
  prompts between checks only while the exact incoming CDP connection remains alive.
- Stopping the Playwright runtime without `browser.close()` is the intended borrowed-browser
  shutdown path in current code, but Chrome/tab preservation must remain a live acceptance item
  because Playwright's public API does not expose a dedicated `disconnect()` method for this object.
- The current frontend renders every generic `failed` row as a prompt to log in. This matches the
  latest product request for failed checks but is imprecise for worker crashes. The recommended
  protocol preserves compatibility; a future product-copy task could distinguish technical retry
  without exposing details by adding a new constant guidance value.
