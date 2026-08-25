# Research: Current borrowed-Chrome authentication architecture and shared-session refactor

- Query: How does the current borrowed-Chrome authentication path work, and what is the smallest
  feasible MediaCrawler refactor that reuses one Playwright `Browser`/`BrowserContext` for `wb`,
  `dy`, `ks`, `xhs`, and `toutiao` while preserving subprocess isolation and task-page-only cleanup?
- Scope: mixed (repository source/tests/specs plus official Playwright documentation)
- Date: 2026-08-25

## Findings

### Executive recommendation

Use one **lazily started, long-lived MediaCrawler worker subprocess**. The worker should own one
manually started Playwright runtime, one `CDPBrowserManager`, one CDP `Browser`, and the borrowed
default `BrowserContext`. FastAPI should keep a narrow stdin/stdout client for that worker; it
should not import MediaCrawler.

Extract one injection seam in each of the five platform crawlers, conceptually:

```python
async def run_auth_with_context(
    self,
    browser_context: BrowserContext,
    cdp_manager: CDPBrowserManager,
) -> AuthPhase: ...
```

The existing one-shot CLI auth path can start Playwright/CDP and delegate to this method. The new
persistent worker can call the same method with its shared objects. This preserves every existing
platform-specific probe and manual-login routine rather than duplicating them in the worker.

This is the smallest robust option because the Playwright runtime that created a `BrowserContext`
must outlive all uses of that object. Merely caching `CDPBrowserManager` while leaving each crawler's
`async with async_playwright()` wrapper in place would stop the owning Playwright connection at the
end of every attempt (`weibo/core.py:84`, `douyin/core.py:89`, `kuaishou/core.py:94`,
`xhs/core.py:194`, `toutiao/core.py:76`).

Recommended ownership split:

```text
FastAPI lifespan
  owns PlatformConnectionService
    owns PersistentAuthWorkerClient
      owns MediaCrawler OS process
        owns async_playwright().start()
          owns CDPBrowserManager -> Browser -> borrowed default BrowserContext
          owns at most one platform auth coroutine
            owns only the explicitly-created task Page(s)
```

Normal attempt completion closes only the attempt's registered page(s). It does **not** close the
worker, Playwright, `Browser`, `BrowserContext`, or Chrome. Timeout, malformed IPC, worker crash, or
an unrecoverable CDP disconnect invalidates and terminates the worker session; the next explicit
attempt creates a new worker and may require approval again.

### Files found

| File | Role |
| --- | --- |
| `backend/src/longtian_api/services/platform_connections.py` | Current in-memory state machine, one-shot process launch, child event parser, timeout, and process-group cleanup. |
| `backend/src/longtian_api/main.py` | FastAPI lifespan ownership; creates one service and calls `shutdown()`. |
| `backend/src/longtian_api/api/v1/platform_connections.py` | Stable GET and per-platform POST API. |
| `backend/src/longtian_api/schemas/platform_connections.py` | Public status/guidance/error contract. |
| `backend/tests/test_platform_connections.py` | Process, protocol, transition, concurrency, timeout, and shutdown seams. |
| `third_party/MediaCrawler/main.py` | One-shot CLI factory, auth exit-code mapping, and final cleanup. |
| `third_party/MediaCrawler/cmd_arg/arg.py` | Current fail-closed auth configuration override. |
| `third_party/MediaCrawler/tools/auth.py` | Constant-only phase protocol and stable one-shot exit codes. |
| `third_party/MediaCrawler/tools/cdp_browser.py` | Existing-browser CDP connect, default-context selection, page registry, and borrowed cleanup. |
| `third_party/MediaCrawler/tools/browser_launcher.py` | Opens Chrome's remote-debugging settings without taking process ownership. |
| `third_party/MediaCrawler/tools/app_runner.py` | Signal-aware async runner with bounded cleanup. |
| `third_party/MediaCrawler/media_platform/{weibo,douyin,kuaishou,xhs,toutiao}/core.py` | Five auth orchestrations and their current Playwright/CDP creation/cleanup seams. |
| `third_party/MediaCrawler/media_platform/*/{auth,client,login}.py` | Authoritative probes and bounded manual-login behavior that must stay platform-specific. |
| `third_party/MediaCrawler/tests/test_*_auth_mode.py` | Existing per-platform auth, no-collection, timeout, cancellation, and narrow-cleanup regressions. |
| `third_party/MediaCrawler/tests/test_cdp_browser.py` | Direct CDP connection and borrowed-vs-owned cleanup regression tests. |
| `frontend/src/routes/platform-accounts.tsx` | Existing serial five-platform batch queue; no bulk API is needed. |

No `design.md` or `implement.md` existed in the task directory at research time.

### Current lifecycle and data flow

```text
React platform row / “一键检测”
  -> POST /api/v1/platform-connections/{platform}/attempts
  -> PlatformConnectionService.start_attempt()
       lock + catalog allowlist + single-active check
       mark platform checking
       create background _run_attempt task
  -> _execute_worker()
       construct fixed `uv run ... python main.py --platform P --type auth ...`
       launch a NEW process group
  -> MediaCrawler main.py
       parse CLI and force auth-safe global config
       instantiate platform crawler
  -> platform crawler.start()
       start a NEW Playwright runtime
       construct a NEW CDPBrowserManager
       call connect_over_cdp  <-- Chrome approval for every attempt
       select borrowed default BrowserContext
       create/register one task Page
       authoritative probe -> optional visible manual login -> authoritative recheck
       close registered task Page
       exit Playwright context and worker process
  -> FastAPI reads phase events until stdout EOF
       validate transition + terminal event + process exit code
       project connected/disconnected/failed
       release active-attempt slot
```

Evidence:

- FastAPI launches a process inside every `_execute_worker` call and stores it as the current
  process (`platform_connections.py:261-275`). After stdout EOF it waits for the process and uses
  the exit code plus terminal event as a two-part proof (`platform_connections.py:279-306`).
- The command is a fixed `uv run --frozen --project ... python main.py --platform ... --type auth`
  tuple (`platform_connections.py:361-373`), and the launcher uses
  `asyncio.create_subprocess_exec`, pipes, and a new POSIX session (`platform_connections.py:470-479`).
- One-at-a-time behavior is enforced before task creation (`platform_connections.py:150-186`).
- FastAPI lifespan already provides the correct high-level owner: one service is stored on
  `application.state`, and shutdown awaits `service.shutdown()` (`main.py:18-25`).
- MediaCrawler parses and forces auth configuration on every process (`cmd_arg/arg.py:356-428`),
  creates the crawler, maps exceptions to stable exit codes, and requires a returned connected
  phase (`main.py:110-137`).
- `CDPBrowserManager._connect_existing_browser` opens the visible settings page only when the
  loopback port is unavailable, waits, emits approval, and then connects (`cdp_browser.py:177-242`).
- The actual approval-causing operation is `playwright.chromium.connect_over_cdp` at
  `cdp_browser.py:360-405`.
- The frontend batch is already a serial queue: it does not advance while the current catalog row
  remains active, then starts the next index (`platform-accounts.tsx:317-377`). The backend API can
  remain unchanged.

### Current browser ownership and cleanup

The current borrowed-browser cleanup boundary is mostly reusable:

- A task explicitly registers pages in `_owned_pages` (`cdp_browser.py:63-67`).
- `close_owned_pages()` clears that list and closes only those exact objects
  (`cdp_browser.py:69-82`).
- Borrowed cleanup closes owned pages, then drops local browser/context references without calling
  `context.close()`, `browser.close()`, or launcher cleanup (`cdp_browser.py:484-505`).
- Owned-browser cleanup retains the old broad behavior (`cdp_browser.py:507-563`).
- Tests place pre-existing and owned pages in the same context and prove only the registered page
  closes, while context/browser/process stay open (`tests/test_cdp_browser.py:163-189`).
- Per-platform cancellation tests already assert page cleanup for Weibo
  (`test_weibo_auth_mode.py:209-229`), Douyin (`test_douyin_auth_mode.py:318-338`), Kuaishou
  (`test_kuaishou_auth_mode.py:399-419`), Xiaohongshu (`test_xhs_auth_mode.py:455-476`), and Toutiao
  (`test_toutiao_auth_mode.py:683-705`).

Because both frontend and backend serialize attempts, the existing manager-wide owned-page list is
safe if and only if the worker also processes exactly one command at a time and does not accept a
new command until `close_owned_pages()` finishes. On a timeout or protocol failure, FastAPI should
terminate the worker before accepting the next command, so stale events/pages cannot cross attempt
boundaries.

Do not subscribe to every `BrowserContext.on("page")` event and claim all new tabs: a user can open a
normal tab while an attempt is running. Continue registering only pages explicitly created by
application code. The five current auth paths each create one page themselves and no target login
module creates a second page.

### Per-platform creation, probe, login, and cleanup seams

| Platform | Current creation and page setup | Authoritative terminal proof that must remain | Manual boundary that must remain | Injection/cleanup seam |
| --- | --- | --- | --- | --- |
| Weibo (`wb`) | Starts Playwright/CDP, creates a page, registers it, navigates desktop Weibo (`weibo/core.py:84-110`). | Builds a scoped client from current `.weibo.cn` Cookies and calls `/api/config`; only response `login` is positive (`weibo/core.py:120-123`, `weibo/client.py:118-132`). After manual login it navigates mobile Weibo, refreshes scoped Cookies, and probes again (`weibo/core.py:144-167`). | `WeiboLogin(... visible_page_only=True)`; QR stays in the visible browser (`weibo/core.py:124-142`; test at `test_weibo_auth_mode.py:175-203`). | Extract lines `106-167` into injected-context auth method. Keep `finally: close_owned_pages()` (`weibo/core.py:180-182`). No proxy or auth-state store in auth mode. |
| Douyin (`dy`) | Starts Playwright/CDP, adds a context-level stealth init script, creates/registers page, then navigates (`douyin/core.py:89-116`, `douyin/core.py:410-443`). | `check_douyin_online_auth()` freshly navigates and runs a same-origin no-store `/passport/account/info/v2/` probe; returns only connected/disconnected/inconclusive (`douyin/auth.py:28-111`). | Local marker/UI changes only wake the follow-up online probe; visible login remains manual (`douyin/core.py:118-147`, `douyin/login.py:61-110`). | Extract lines `113-147`; keep page cleanup at `douyin/core.py:175-177`. **Do not keep the context-level stealth injection in persistent borrowed auth mode**; it would affect every future tab in the user's shared context for the worker lifetime. |
| Kuaishou (`ks`) | Starts Playwright/CDP, creates/registers page, installs `KS_SIGN_CAPTURE_SCRIPT` on that owned page, then navigates (`kuaishou/core.py:94-120`). | Client `pong()` calls official `visionProfileUserList` and accepts only result `1` (`kuaishou/core.py:130-134`, `kuaishou/client.py:191-211`). Post-login Cookies are refreshed and `pong()` runs again (`kuaishou/core.py:155-173`). | A new/changed `passToken` is only a wake-up hint; selector drift stays inconclusive (`kuaishou/login.py:69-158`). | Extract lines `115-173`; page-local init script is safe. Keep cleanup at `kuaishou/core.py:190-192`. |
| Xiaohongshu (`xhs`) | Already has a dedicated `_start_auth`; it starts Playwright/CDP, creates/registers one domestic-homepage page, and navigates (`xhs/core.py:189-210`). | Builds signed client from allowlisted current-context Cookies; `pong()` calls official self-info and requires JSON boolean `data.result.success is True` (`xhs/core.py:212-247`, `xhs/client.py:271-307`). | Visible UI/Cookie changes only wake the online recheck; login remains bounded and manual (`xhs/core.py:215-247`, `xhs/login.py:220-369`). | Split `_start_auth` into a Playwright/CDP wrapper plus injected-context body. Keep `close_owned_pages()` at `xhs/core.py:254-256`. |
| Toutiao (`toutiao`) | Already has dedicated `_start_auth`; starts Playwright/CDP and creates/registers one page (`toutiao/core.py:75-88`). | Fresh official navigation plus strict trusted-origin, challenge, header-account, and login-entry DOM classification (`toutiao/core.py:89-121`, `toutiao/auth.py:82-147`). | The visible-only path retains the current official page and polls; it does not automate login/safety work (`toutiao/core.py:92-115`, `toutiao/login.py:52-68,102-146`). | Split `_start_auth` wrapper/body. Keep cleanup at `toutiao/core.py:122-124`. |

### Shared dependencies and what can be injected

#### Can be shared/injected

1. **Playwright runtime**: start once with `await async_playwright().start()` and stop only when the
   worker ends. Official Playwright docs explicitly support manual `start()`/`stop()` for lifetimes
   outside a context manager.
2. **`CDPBrowserManager` + `Browser` + borrowed default `BrowserContext`**: connect once and reuse.
   `connect_over_cdp()` returns a `Browser`, and the default context is exposed in
   `browser.contexts`.
3. **Page ownership registry**: serial attempts can reuse the existing explicit register/close list.
4. **Auth-safe configuration helper**: extract the fail-closed overrides at
   `cmd_arg/arg.py:395-428` into one function used by both one-shot CLI auth and persistent-worker
   commands. Call it before every command because `config` is mutable process-global state.
5. **Protocol types/emitters**: extend `tools/auth.py` with strict worker command/result types. Keep
   all fields enum/constant based and all raw platform output outside the protocol.

#### Must stay platform-specific

- Homepage/probe URLs, page initialization, client construction/signing, Cookie-domain allowlists,
  online probes, manual-login polling, challenge boundaries, and final recheck.
- Each `emit_<platform>_auth_event` helper, or an equivalently strict platform-bound emitter. The
  shared CDP manager's connection-phase callback must be rebound to the **current command's**
  platform when a new connection is established.
- The Kuaishou page-local signing capture script.
- Weibo's post-login mobile navigation/Cookie refresh.
- Douyin/Toutiao DOM/network classifiers and Xiaohongshu signed self-info call.

#### Must not be injected/shared

- A saved previous `connected` result as proof of the next check.
- A Cookie string, authorization header, page content, QR material, profile path, or account identity.
- A `BrowserContext` created by FastAPI or passed across an OS-process boundary. Playwright objects
  remain inside the MediaCrawler worker.
- A platform collection client or store operation beyond what the existing auth probe creates.

### Recommended persistent-worker protocol

Keep the public HTTP contract unchanged. Replace per-attempt CLI arguments with a fixed worker
command such as:

```text
uv run --frozen --project third_party/MediaCrawler python -m tools.auth_worker
```

Launch it with stdin/stdout/stderr pipes and the same owned process group. Use bounded, prefixed,
newline-delimited JSON. A minimal strict input union is:

```text
__MEDIACRAWLER_AUTH_COMMAND__{"version":1,"action":"check","platform":"wb"}
__MEDIACRAWLER_AUTH_COMMAND__{"version":1,"action":"shutdown"}
```

Keep the current phase event unchanged so platform code and transition tests survive:

```text
__MEDIACRAWLER_AUTH_EVENT__{"version":1,"platform":"wb","phase":"checking"}
```

A persistent process no longer has a per-attempt exit code, so add an exact result event:

```text
__MEDIACRAWLER_AUTH_RESULT__{"version":1,"platform":"wb","outcome":"connected"}
```

Allowed outcomes should be a fixed enum such as `connected | disconnected | browser_unavailable |
failed`. Success remains a two-part check: a valid terminal phase plus a matching result event. A
`connected` phase without `connected` result, cross-platform result, malformed/oversized line,
unexpected EOF, or result without the required phase fails closed and invalidates the worker.

No attempt UUID is required in worker IPC while there is exactly one in-flight command and every
abnormal attempt terminates the worker before a new attempt. Omitting it keeps the child schema
constant-only and avoids propagating API identifiers. If later concurrency is introduced, add a
strict opaque correlation identifier then; do not infer correlation from timing.

Recommended worker loop:

```text
read and strictly validate one command
  check:
    re-apply safe auth config for the selected enum platform
    if no live browser session:
      start Playwright (if needed)
      connect CDP lazily (may emit browser/approval phases)
      select borrowed default context
      register Browser "disconnected" handler
    instantiate the selected platform crawler
    run_auth_with_context(shared context, shared manager)
    assert browser still connected before emitting successful result
    close only registered pages in finally
    emit exact result
    return to stdin loop
  shutdown:
    close owned pages
    release borrowed manager references
    stop Playwright transport
    exit zero
```

The input loop itself is sequential. It should reject or terminate on a second check if an attempt
task is still active, even though FastAPI already returns the existing 409. Defense in depth prevents
a future backend bug from creating concurrent page operations.

### Reconnect and failure policy

- **Healthy terminal attempt:** keep worker, Playwright, CDP `Browser`, and borrowed context alive.
- **Platform disconnected result:** keep the session alive; only the attempt page closes. A later
  platform check can reuse the same approved connection.
- **Attempt timeout/cancellation:** send SIGTERM to the owned worker group and allow its bounded
  cleanup to close registered pages and stop Playwright; SIGKILL only after grace. Mark the active
  attempt safely, discard the worker client, and reconnect only on the next explicit check.
- **Malformed/cross-platform IPC:** terminate worker immediately; do not attempt to resynchronize a
  long-lived stdout stream.
- **Worker crash/EOF:** fail only the active attempt, clear the worker reference, preserve Chrome and
  pre-existing tabs, and lazy-start a replacement on the next POST.
- **Chrome disconnect:** use Playwright's `Browser.on("disconnected")` event to mark the shared
  session invalid. If an attempt is active, it must not complete as connected. An idle disconnect
  can be observed by a background worker monitor or detected before the next command; either way,
  the next explicit command starts a fresh CDP connection.
- **FastAPI shutdown:** ask the worker to shut down, wait a short grace, then terminate the owned
  worker process group if needed. Never call `Browser.close()` or `BrowserContext.close()` on the
  borrowed objects.

`tools/app_runner.py:32-109` is reusable for signal-aware bounded cleanup, but the worker cleanup
must explicitly call `await playwright.stop()` after releasing borrowed manager references.

### Important `CDPBrowserManager` changes

1. In borrowed mode, `_create_browser_context` currently creates a new context when
   `browser.contexts` is empty (`cdp_browser.py:416-445`). For this feature it should fail closed
   instead. A new incognito context would not be the user's authenticated daily profile and, under
   borrowed cleanup, would also be left open.
2. The installed Playwright version is 1.61.0 (`third_party/MediaCrawler/uv.lock:1261-1262`). Its
   `connect_over_cdp` supports `no_defaults=True`; use it for the user's daily browser so Playwright
   does not apply default focus/media/download overrides to the existing default context. This is a
   small safety improvement directly aligned with long-lived attachment.
3. Register `Browser.on("disconnected")` and expose an internal invalid-session signal to the worker.
   `is_connected()` already delegates to `browser.is_connected()` (`cdp_browser.py:568-572`).
4. Keep `cleanup()`'s borrowed branch and ensure worker shutdown stops Playwright rather than calling
   `browser.close()`.
5. Do not apply Douyin's context-wide `add_init_script` to the shared daily context. Kuaishou's
   page-local script is acceptable because the page is owned and closed.

### Architecture option comparison

| Option | Isolation | Change size | Lifecycle correctness | Main risks | Verdict |
| --- | --- | --- | --- | --- | --- |
| Persistent MediaCrawler worker with injected shared context | Preserves current OS-process/environment boundary | Moderate: worker/IPC + five small auth-body extractions + backend client | Strong: the Playwright owner and context live in one process/event loop; pages remain attempt-scoped | Must add result protocol, crash recovery, and strict worker cleanup | **Recommended; smallest robust solution** |
| Import MediaCrawler directly into FastAPI | None | Superficially smaller, but dependency/package cleanup becomes large | One FastAPI-owned Playwright runtime is possible | Violates task requirement and current spec; MediaCrawler uses un-namespaced absolute imports (`main.py:35-56`), process-global mutable config (`cmd_arg/arg.py:356-428`), a full heavy dependency graph, and pins FastAPI 0.110.2 while backend requests FastAPI >=0.116 (`MediaCrawler/pyproject.toml:8-43`, `backend/pyproject.toml:7-9`) | Reject |
| CDP WebSocket proxy that keeps one Chrome upstream while one-shot Playwright subprocesses reconnect downstream | Keeps platform processes | Very large/new network component | Unsupported handoff: each Playwright client expects its own initialized CDP transport and Browser object | Must remap command IDs/session IDs, route browser-wide events, handle target ownership and disconnect semantics; adds listener/attack surface; `connect_over_cdp` is already documented as lower fidelity | Reject |

The CDP proxy is effectively a more complicated browser daemon. Once a daemon is required, it is
safer to put the existing Python/Playwright platform logic inside it—that is the persistent-worker
option—rather than trying to virtualize raw CDP for independent Playwright drivers.

### Likely affected files

#### Parent repository

- `backend/src/longtian_api/services/platform_connections.py`
  - replace per-attempt launch/EOF logic with lazy persistent-worker acquisition and per-command
    result reading;
  - retain catalog/state/409/timeout projection;
  - retain process-group TERM/KILL fallback;
  - add stdin to the managed process surface and keep worker state separate from active-attempt state.
- Optional new `backend/src/longtian_api/services/media_crawler_auth_worker.py`
  - isolate process/IPC lifecycle from product status projection; this is preferable if the existing
    service would otherwise combine two state machines.
- `backend/tests/test_platform_connections.py`
  - replace one-shot fake process assumptions and add multi-command/same-process/restart tests.
- `backend/src/longtian_api/main.py`
  - probably no semantic change; its existing lifespan shutdown call is already correct.
- No schema/API/frontend production file should need a contract change.

#### MediaCrawler derivative submodule

- New `tools/auth_worker.py`: strict sequential command loop and shared Playwright/CDP lifecycle.
- `tools/auth.py`: command/result enums, prefixes, strict emitters/parsers (or a neighboring
  `tools/auth_protocol.py` if keeping the file focused is clearer).
- New `tools/auth_mode.py` or extracted helper used by both `cmd_arg/arg.py` and the worker to apply
  the exact safe auth configuration on every command.
- `tools/cdp_browser.py`: borrowed-context fail-closed rule, `no_defaults=True`, disconnect signal,
  and explicit reusable-session hooks.
- `media_platform/weibo/core.py`, `douyin/core.py`, `kuaishou/core.py`, `xhs/core.py`,
  `toutiao/core.py`: extract injected-context auth bodies; do not rewrite probes/login classes.
- `tests/test_auth_protocol.py`, `tests/test_cdp_browser.py`, five `test_*_auth_mode.py` files, and a
  new `tests/test_auth_worker.py`.
- `pyproject.toml`/`uv.lock`: no new dependency is required.

### Test seams and required regressions

#### Backend unit/integration

1. GET/app startup does not launch a worker or write a command.
2. First POST launches exactly one fixed worker command and writes one strict platform command.
3. Two sequential different-platform attempts reuse the same fake process/stdin/stdout session.
4. The existing frontend-style five-platform sequence causes one process launch and five serial
   commands; no bulk route is added.
5. Existing 409 conflict behavior remains while a command is active.
6. Terminal phase + result matrix replaces terminal phase + exit matrix; mismatch fails closed.
7. Cross-platform, extra-field, malformed, oversized, partial, and out-of-order events terminate and
   discard the worker without mutating foreign platform state.
8. Worker EOF/crash during an attempt marks it failed, and the next explicit attempt launches a new
   worker.
9. Timeout/shutdown sends graceful shutdown/TERM, then KILL after grace, without touching Chrome.
10. Secret sentinels never appear in API state/errors or retained child output.

The current fakes at `backend/tests/test_platform_connections.py:62-167` are good seams but need a
writable stdin and persistent output scheduling. Existing transition/error tests at lines `605-850`
should be retained and adapted rather than deleted.

#### MediaCrawler unit/integration

1. Exact command/result schemas: versions, actions, platforms, outcomes, extra fields, line limits,
   and constant-only emission.
2. Worker starts no Playwright/CDP before the first valid `check` command.
3. Two different platform commands receive the same `Browser` and `BrowserContext` object identity;
   only the first connection emits approval phases.
4. Worker command loop never overlaps auth coroutines.
5. Every attempt creates/registers/closes only its own page; a pre-existing sentinel page survives
   two platform checks and worker shutdown.
6. Graceful shutdown calls borrowed cleanup + Playwright stop, never context/browser/Chrome close.
7. Browser disconnect during a probe cannot emit a successful result; the next command reconnects
   or the worker exits for backend restart.
8. Borrowed mode with zero existing contexts fails instead of creating an incognito context.
9. Douyin persistent auth does not add a context-wide init script; Kuaishou still adds its owned-page
   script.
10. Preserve all five existing phase sequences, authoritative online rechecks, manual timeouts,
    challenge restrictions, and no-collection sentinels. Existing tests already establish these
    expectations, for example Weibo `test_weibo_auth_mode.py:94-158`, Douyin
    `test_douyin_auth_mode.py:160-220`, Kuaishou `test_kuaishou_auth_mode.py:125-190`, Xiaohongshu
    `test_xhs_auth_mode.py:184-262`, and Toutiao `test_toutiao_auth_mode.py:478-558`.

#### Live acceptance

- Start FastAPI and verify no approval appears before a POST.
- Approve one first platform check, then check at least one different platform and run the full
  frontend batch without another approval.
- Record only worker PID continuity, platform/phase/outcome enums, timestamps, page counts, and
  sentinel-tab survival. Do not record screenshots, page text, account names, Cookie data, QR data,
  or profile paths.
- Close Chrome mid-attempt and prove the attempt cannot become connected; then prove the next
  explicit attempt asks for/re-establishes a fresh connection.
- Stop FastAPI and prove Chrome plus pre-existing tabs remain open.

### Risks and mitigations

| Risk | Why it exists | Mitigation |
| --- | --- | --- |
| Long-lived full control of the user's daily Chrome | Accepted product tradeoff in the PRD; one approved CDP connection remains powerful | Loopback only, lazy start, visible browser, clear shutdown, no remote API, no policy bypass, no credential transport. |
| Context-wide Playwright side effects | Existing `connect_over_cdp` can apply defaults, and Douyin adds stealth to the borrowed context | `no_defaults=True`; skip context-wide stealth in persistent auth; use page-local setup only. |
| Mutable `config` leaks between platforms | One process now handles five platforms | Reapply one shared fail-closed auth configuration function before every command; serial worker only. |
| Stale output corrupts next attempt | Worker stdout persists across commands | One command at a time; exact terminal result boundary; any timeout/malformed event kills worker before reuse. |
| Browser dies while idle/active | `Browser`/context handles become stale | `Browser.on("disconnected")`, pre-command live check, fail active attempt closed, lazy reconnect on next action. |
| Graceful cleanup is interrupted | Backend may need to KILL worker | SIGTERM first with bounded worker cleanup; owned page closure in `finally`; Chrome is unowned so socket loss does not terminate it. A SIGKILL may leave the task page visible, but must never close a user tab or Chrome. |
| First browser context is not the user's intended profile | Current code blindly takes `browser.contexts[0]` | In borrowed mode require an existing default context; do not create one. Verify real Chrome behavior on supported OS/browser version. |
| Platform flow refactor drifts behavior | Weibo/Douyin/Kuaishou auth is mixed into `start()` | Extract, do not rewrite; keep one-shot wrapper and all current auth-mode/no-collection tests. |
| Submodule/parent revisions become inconsistent | MediaCrawler is a git submodule | Commit/push the derivative first, then update the parent gitlink per submodule spec. |

### External references

- [Playwright Python `BrowserType.connect_over_cdp`](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp): attaches to an existing Chromium browser; its default context is exposed through `browser.contexts`; CDP mode is lower fidelity than Playwright protocol. Current docs also document `no_defaults` for avoiding overrides on a daily-driver context.
- [Playwright Python `Playwright.stop`](https://playwright.dev/python/docs/api/class-playwright#playwright-stop): manual Playwright lifetime when created outside a context manager.
- [Playwright Python library, async REPL example](https://playwright.dev/python/docs/library#interactive-mode-repl): official async `await async_playwright().start()` / `await playwright.stop()` example.
- [Playwright Python `Browser`](https://playwright.dev/python/docs/api/class-browser): `is_connected()`, `contexts`, and the `disconnected` event used for worker invalidation.

The repository locks Playwright 1.61.0 (`third_party/MediaCrawler/uv.lock:1261-1262`), so the
documented `no_defaults` and disconnect event surfaces are available without a dependency change.

## Caveats / Not Found

- A true “one Chrome approval for the runtime” guarantee depends on live Chrome behavior and cannot
  be proven by mocks alone. Unit tests can prove one `connect_over_cdp` call; a live two-platform
  acceptance run is still required.
- Playwright documents CDP attachment as lower fidelity. Existing platform flows already depend on
  it, but long-lived use increases the importance of disconnect and browser-version regressions.
- There is no supported way to serialize or transfer a Playwright `BrowserContext` across OS
  processes. Reuse therefore has to happen inside one persistent owner process.
- The current task has no `design.md`/`implement.md` yet. Only `implement.jsonl` and `check.jsonl`
  manifests were present; they were intentionally not read because Trellis research roles are
  isolated from implement/check context manifests.
- No existing persistent stdin worker, worker command protocol, or CDP proxy implementation was
  found in the parent or MediaCrawler source.
- If a worker is forcibly SIGKILLed before its `finally` runs, its task page may remain open in
  Chrome. The safe invariant is that the application never closes a pre-existing page or Chrome;
  graceful TERM-first cleanup minimizes orphaned task pages but cannot make SIGKILL cleanup
  deterministic.
