# Technical Design

## 1. Architecture and ownership

This task is one vertical slice across the product frontend, product backend, and the pinned
MediaCrawler derivative:

```text
React connection center
  -> versioned FastAPI platform-connection API
  -> in-process PlatformConnectionService (status, lock, timeout)
  -> controlled MediaCrawler subprocess
  -> authentication-only CLI mode
  -> CDP connection to the user's Chrome
  -> official Weibo page + online Weibo probe
```

The product backend does not import MediaCrawler. MediaCrawler keeps ownership of platform and
browser details; FastAPI owns product task state and translates a narrow subprocess protocol into
safe API models. React knows only the API contract.

SQLite is not introduced. Browser authentication remains in the user's Chrome Profile, while the
latest derived connection result lives in memory for the current FastAPI session.

## 2. Platform catalog and state model

The backend owns one ordered catalog: Weibo, Douyin, Kuaishou, Xiaohongshu, Toutiao. Only Weibo
has `availability="enabled"`; the other four have `availability="coming_soon"` and cannot start a
connection attempt.

Each platform returns:

```text
platform          wb | dy | ks | xhs | toutiao
display_name      localized stable label
availability      enabled | coming_soon
status            not_checked | checking | action_required | connected |
                  disconnected | failed | coming_soon
guidance          none | enable_remote_debugging | approve_connection |
                  complete_login | retry
last_checked_at   UTC ISO-8601 timestamp or null
active_attempt_id opaque UUID or null
```

Transitions for Weibo:

```text
not_checked/disconnected/failed
  -> checking
  -> action_required(enable_remote_debugging / approve_connection / complete_login)
  -> checking
  -> connected

active state
  -> disconnected  (online authentication was not completed before the bound)
  -> failed        (browser/process/protocol/unknown technical failure)
```

Only an online `WeiboClient.pong()` can produce `connected`. File presence, process exit without a
valid final event, and Cookie names cannot do so. `last_checked_at` is updated only for a terminal
online result or terminal failed attempt, not for transient phases.

## 3. HTTP contract

Routes live under a platform-connections router with its own prefix and tags:

```http
GET /api/v1/platform-connections
POST /api/v1/platform-connections/{platform}/attempts
```

- `GET` returns `{ "platforms": PlatformConnection[] }` through an exact Pydantic response model,
  with entries in catalog order.
- `POST` returns HTTP 202 as `{ "attempt_id": string, "platform": PlatformConnection }`; it never
  waits for browser authorization or scanning.
- Unknown platform IDs return 404.
- Known `coming_soon` platforms return 409 with a stable `platform_not_available` code.
- Any new request while an authentication subprocess is active returns 409 with
  `connection_attempt_active`; only one borrowed Chrome/CDP session is allowed at a time.
- API errors use FastAPI's `{ "detail": { "code": string, "message": string } }` shape with stable
  product codes and short guidance only. They never expose command lines, child output, paths,
  stack traces, Cookie material, or QR content.

The frontend polls `GET` once per second only while a platform is `checking` or
`action_required`; otherwise it uses the normal TanStack Query cache and explicit retry.

## 4. Backend service lifecycle

`PlatformConnectionService` is created by the FastAPI lifespan and retrieved through an
`Annotated` dependency. It owns:

- the immutable platform catalog;
- current in-memory projections;
- one `asyncio.Lock` and the current `asyncio.Task`;
- the MediaCrawler process handle and a bounded line/event reader;
- shutdown cancellation and child-process termination.

The route only validates input, calls the service, and serializes response models. The service
starts the worker using `asyncio.create_subprocess_exec` with an argument array, never a shell.
The command is resolved from the repository layout and uses the derivative's locked environment:

```text
uv run --frozen --project third_party/MediaCrawler python main.py
  --platform wb --type auth --lt qrcode --headless no
  --get_comment no --get_sub_comment no --save_data_option jsonl
```

Authentication-only mode itself enforces all safety settings, so a mutable base config cannot turn
this command into collection. The backend does not pass a Cookie, password, phone number, keyword,
post ID, or creator ID.

Child stdout/stderr is not written to product logs or returned by the API. The backend drains it to
avoid blocking and recognizes only validated protocol lines. On timeout or application shutdown it
terminates the MediaCrawler process group, waits briefly, then kills only that owned group if
necessary. The user's Chrome is never in that group.

## 5. Versioned subprocess protocol

Authentication mode emits a single-line JSON event behind a fixed prefix:

```text
__MEDIACRAWLER_AUTH_EVENT__{"version":1,"platform":"wb","phase":"checking"}
```

Allowed phases are:

- `waiting_for_browser`
- `waiting_for_approval`
- `checking`
- `waiting_for_login`
- `connected`
- `disconnected`

The normal sequences are
`waiting_for_browser -> waiting_for_approval -> checking -> connected` for an existing authenticated
session, or the same prefix followed by
`checking -> waiting_for_login -> checking -> connected|disconnected`. Early waiting phases may be
omitted only when CDP is already available; regressions, duplicate terminal events, and any event
after a terminal phase are invalid.

The event schema permits no free-form message or metadata field. The backend validates version,
platform, phase, line size, and transition order, then maps the event to its own product state and
localized guidance. Unprefixed output is discarded; malformed or unknown prefixed events fail the
attempt without echoing the offending line.

Exit 0 is accepted only after a valid final `connected` event. Exit 20 means authentication was not
completed or confirmed, exit 21 means Chrome/CDP was unavailable or approval timed out, and exit 22
means the authentication runner failed internally. Any unknown exit or event/exit disagreement maps
to `failed`.

## 6. MediaCrawler authentication-only mode

The derivative gains an explicit `auth` crawler type and a small event emitter. For this mode the
runner forcibly sets:

- platform `wb` for this MVP;
- CDP enabled and existing-browser mode enabled;
- headed browser behavior;
- IP proxy, comments, sub-comments, media, wordcloud, database initialization, and content stores
  disabled;
- explicit `BrowserAuthStateStore` persistence disabled, because the borrowed Chrome already owns
  its session.

The Weibo flow is refactored into a testable authentication boundary:

1. connect to the user's Chrome;
2. create and register one task-owned page;
3. navigate to the official Weibo page and run the mobile online probe;
4. if false, keep the official SSO tab visible and let the user scan there;
5. update the mobile-domain client Cookies in memory and run the online probe again;
6. emit `connected` only on success; otherwise exit non-zero;
7. close only the task-owned page in `finally`.

The separate PIL/system QR viewer is disabled in authentication-only mode. Existing crawler modes
retain their behavior. No content method is reachable from `auth`, and tests replace every content
entry point with a failing sentinel.

## 7. Borrowed Chrome lifecycle

When port 9222 is unavailable, the existing-browser path detects Chrome and opens
`chrome://inspect/#remote-debugging` as an unowned ordinary browser URL, then waits for the user to
enable/approve the loopback connection. It does not add a remote-debugging command-line flag to the
user's default profile and does not retain a process handle for later termination.

Ownership rules:

- all debug listeners and probes use `127.0.0.1`/localhost only;
- a borrowed existing `BrowserContext` is never closed;
- `browser.close()` is never called for a borrowed browser;
- only pages explicitly registered by this authentication attempt are closed;
- an existing-browser connection failure in `auth` mode fails closed and never falls back to a
  new standard or dedicated browser;
- program-owned dedicated-browser behavior outside `auth` remains compatible, except its debug
  address is tightened from `0.0.0.0` to `127.0.0.1`.

A real regression keeps a pre-existing sentinel tab open and verifies Chrome remains usable after
success, timeout, and backend cleanup.

## 8. Frontend design

### Subject and job

The subject is a local street-level monitoring desk used by one operator. The page's single job is
to make account readiness and the next human action unmistakable before any collection exists.

### Tokens

The existing civic system remains authoritative:

| Role | Token |
| --- | --- |
| paper background | `#F5F8F7` |
| deep ink | `#102D30` |
| Longtian teal | `#176B67` |
| quiet surface | `#E8F0ED` |
| connected green | `#248B61` |
| attention amber | `#A35F20` |

Display type remains Songti SC, body type PingFang SC/Microsoft YaHei, and compact operational
labels use SFMono/Consolas. No new font or design dependency is added.

### Layout and signature

The product uses an administration shell rather than treating the connection feature as a landing
page. A 240px desktop sidebar owns the product identity and primary navigation; a compact top bar
owns the current page title and local-service status; the content canvas uses normal control-panel
density. On narrow screens the sidebar becomes a shadcn/Base UI navigation sheet.

The shell's subject-specific signature is a quiet **four-community watch mark** in the sidebar:
four cells orbit one live center, representing the street and its four communities. It is used once
as product identity, not repeated as decoration. The platform page retains a compact signal rail to
explain the one-browser concurrency rule, but it no longer dominates the entire viewport.

```text
+----------------------+---------------------------------------------+
| LT 龙田舆情           | 工作台                         ● 本机服务正常 |
| 四社区 watch mark    +---------------------------------------------+
|                      | 系统准备情况                                |
| ● 工作台             | [服务状态] [已连接平台] [待接入平台]        |
| ○ 平台账号           |                                             |
| · 采集任务  规划中   | 运行准备                                    |
| · 舆情信息  规划中   | [平台账号连接进度 / 进入平台账号]            |
| · 监控关键词 规划中  |                                             |
| · 舆情日报  规划中   | 今日采集                                    |
| · 系统设置  规划中   | 尚未建立采集任务（真实空状态）               |
+----------------------+---------------------------------------------+
```

`/` renders the truthful workbench overview. `/platform-accounts` renders the complete connection
workflow inside the content canvas. The future navigation items are visibly disabled and marked
`规划中`; they are not links and have no placeholder routes. Platform identity uses reviewed text
initials and names, not generic Lucide icons pretending to be brand marks.

### Design critique

The previous connection-bus composition correctly expressed browser concurrency, but its oversized
title, large empty field, and single-feature hierarchy read as a marketing page. The revised shell
keeps that useful model at component scale while giving the product persistent navigation, route
context, denser operational summaries, and honest empty states. It avoids a generic SaaS dashboard
by using the Longtian civic palette, the four-community watch mark, and copy about actual local
monitoring readiness rather than invented growth metrics.

### React ownership

- `lib/api/platform-connections.ts` owns response types, runtime guards, cancellation, and safe API
  errors.
- TanStack Query owns the platform list; a mutation starts the attempt and invalidates the list.
- `app/router.tsx` owns the shell route, `/` workbench index, and `/platform-accounts` child route.
- The shell owns navigation, route metadata, and the shared health indicator; it uses reviewed
  shadcn sidebar/sheet, tooltip, separator, badge, button, and card primitives as appropriate.
- The workbench may reuse the platform query to derive truthful readiness counts; it must not create
  a second API contract or display synthetic trends.
- The platform-accounts route owns connection composition and current guidance selection.
- The existing health boundary retains retry behavior and is presented compactly in the shell.
- Tests query visible names, statuses, live regions, and buttons rather than implementation classes.

## 9. Failure and security matrix

| Condition | Product behavior |
| --- | --- |
| FastAPI unavailable | Existing local-service indicator and platform error state offer retry |
| Chrome absent | Attempt fails with installation guidance; no alternate browser is silently used |
| Chrome closed/debug disabled | Chrome opens the inspect page; UI requests enablement/approval |
| User rejects or misses approval | Bounded attempt becomes failed with retry guidance |
| Weibo not logged in | Official SSO page remains visible; UI requests manual login |
| Login not completed before bound | Terminal disconnected state; no state is exported |
| Online recheck fails | No connected event, no collection, terminal disconnected/failed state |
| Malformed child event | Fail closed and discard raw line |
| Concurrent request | HTTP 409; existing attempt continues unchanged |
| Backend shutdown | Owned MediaCrawler process stops; borrowed Chrome and existing tabs remain |

## 10. Compatibility, delivery, and rollback

- Existing search/detail/creator CLI values and platform behavior remain compatible.
- The MediaCrawler derivative must be reviewed and committed/pushed before the parent gitlink moves;
  those Git operations require the user's later delivery approval.
- The product backend keeps its independent environment and adds no MediaCrawler packages.
- If borrowed-Chrome cleanup cannot be proven safe, stop before the real login test and do not ship
  fallback behavior.
- Rollback is independent by layer: restore the frontend route/API module, remove the FastAPI router
  and service, and restore the derivative revision. Browser/runtime user data is never a rollback
  target.

## 11. Deferred items

- Real connection flows for Douyin, Kuaishou, Xiaohongshu, and Toutiao.
- Cross-restart status history, SQLite, scheduling, and unattended collection.
- Dedicated application Profile and Cookie export/import modes.
- SSE/WebSocket progress; one-second polling is sufficient for one local user and one bounded task.
- Production packaging and automatic installation of Chrome, uv, or MediaCrawler dependencies.
