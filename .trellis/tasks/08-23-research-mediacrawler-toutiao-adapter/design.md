# MediaCrawler 今日头条最小适配设计

## Scope and Boundary

本任务在 MediaCrawler 派生仓库中新增 `toutiao` search-only 平台。它负责把关键词转换为今日头条公开搜索页导航、从可见 DOM 提取结果、规范化链接并写入 JSONL/SQLite；不负责父项目的定时调度、AI 分析、任务派发或通知。

直接搜索是用户在知悉 2026-08-23 robots 与官方能力调研结论后作出的产品决定。实现必须保留运行时停止条件，但不得把该决定描述为获得平台授权或官方稳定性保证。

## Architecture

```text
CLI/config
  → CrawlerFactory("toutiao")
  → ToutiaoCrawler
      → fresh dedicated standard visible Chrome BrowserContext
      → BrowserAuthStateStore (optional)
      → ToutiaoLogin / DOM live-auth check (optional)
      → ToutiaoWebClient.search(keyword, page_num=0)
          → page.goto(www.toutiao.com/search official entry)
          → platform redirect to so.toutiao.com result page
          → challenge / structure checks
          → visible DOM snapshots
      → help.normalize_result(snapshot)
          → jump URL unwrap
          → Toutiao host allowlist
          → canonical URL + content ID/type
          → minimal privacy-safe result
      → store.toutiao
          → JSONL or SQLite upsert
```

No raw HTTP search client is introduced. `ToutiaoWebClient` wraps the Playwright `Page` boundary only; it must not subscribe to or replay private response payloads.

## Platform Registration and Configuration

- `main.py`: import `ToutiaoCrawler` and register `"toutiao"`.
- `cmd_arg/arg.py`: add `PlatformEnum.TOUTIAO`; update help only. Do not add `specified_id`/`creator_id` routing.
- `config/base_config.py`: include `toutiao` in the supported-platform comment and import `toutiao_config`.
- `config/toutiao_config.py`:
  - `TOUTIAO_REQUIRE_LOGIN = False`
  - `TOUTIAO_LOGIN_WAIT_SEC = 180`
  - `TOUTIAO_MAX_PAGES_PER_KEYWORD = 1`
  - constants for the homepage, official `www.toutiao.com/search/` entry, redirected result origin and allowed target domains

Global `KEYWORDS`, `CRAWLER_MAX_NOTES_COUNT`, `CRAWLER_MAX_SLEEP_SEC`, `SAVE_LOGIN_STATE`, `SAVE_DATA_OPTION`, `HEADLESS` and proxy settings remain authoritative. Toutiao deliberately ignores all CDP settings: every run launches a fresh standard Chrome process and creates a non-persistent `BrowserContext`. The crawler rejects a headless Toutiao run with a clear message because manual verification and observable stop behavior require a visible browser.

## Browser and Authentication Lifecycle

```text
validate search-only + visible-browser config
→ launch fresh standard Chrome and create a non-persistent dedicated BrowserContext
→ restore allowlisted Toutiao cookies when SAVE_LOGIN_STATE=True
→ open Toutiao homepage
→ DOM-based live login check
→ if TOUTIAO_REQUIRE_LOGIN and invalid: open official login UI and wait for user
→ re-run live login check
→ save auth state only after a successful live check
→ create a distinct never-navigated blank search Page
→ close the homepage/auth Page
→ run search regardless of login when TOUTIAO_REQUIRE_LOGIN=False
```

The implementation reuses `BrowserAuthStateStore(platform="toutiao", urls=[official Toutiao URLs])`. It is the only cross-restart authentication persistence boundary and stores only allowlisted Cookies in `browser_data/auth_state/toutiao.json`, atomically and with POSIX mode `0600`. Toutiao never calls `launch_persistent_context`, never enters `CDPBrowserManager`, and therefore does not retain LocalStorage, extensions, browsing history or other profile state between runs.

Homepage authentication and keyword search deliberately use two different Pages in the same temporary context. The homepage Page owns the live authentication check and optional manual login. Only after any confirmed state is saved does the crawler create a fresh blank search Page, close the authentication Page, and bind a new `ToutiaoWebClient` to the search Page. The search Page receives exactly one navigation: the official `www.toutiao.com/search/?keyword=...` entry.

`ToutiaoLogin` supports visible, manual QR/phone/safety handling through the official UI. The automation may open the login entry and wait for an observable signed-in state; it does not fill SMS codes, extract credential values, inspect challenge details, or act on sliders/CAPTCHAs. During this explicit login wait only, a DOM check that reports an official challenge is treated as not-yet-authenticated: one non-sensitive manual instruction is logged, then the normal one-second polling continues until live authentication succeeds or the configured timeout fails. This exception does not apply to search. `LOGIN_TYPE=cookie` may reuse the existing explicit Cookie input only if domain-scoped injection can be implemented without logging values; unsupported login modes fail explicitly.

If login UI selectors cannot be validated reliably, the fallback is to leave the visible page open for the configured wait interval and poll the same DOM live-auth check. Timeout ends the login attempt without saving state.

## Search Flow

For each trimmed, non-empty keyword:

1. Set `source_keyword_var`.
2. Construct the official desktop entry URL `https://www.toutiao.com/search/?keyword=...` with `urllib.parse.urlencode`; page number remains logically fixed to zero and is not supplied as a redirect-session parameter.
3. Navigate through one `Page.goto()` call, allow the platform's normal redirect to the `so.toutiao.com` result page, then inspect the final top-level response status and DOM when available. Navigation errors propagate unchanged; there is no `ERR_ABORTED` swallowing, retry or direct-result-origin fallback.
4. Stop on 403/429 or visible challenge phrases such as safety verification, CAPTCHA, slider, abnormal traffic or mandatory login.
5. Wait for either a recognized result anchor or a recognized empty-result state.
6. Collect a DOM snapshot per candidate anchor: resolved `href`, visible anchor text, and bounded nearby visible text. Do not persist raw HTML.
7. Normalize and deduplicate in memory by `content_id` before store writes.
8. Stop after the configured note-count limit, then sleep the fixed configured interval before the next keyword.

The first version does not click page numbers, results, cards, tabs or time filters and does not scroll for more results.

## DOM Contract and Structure Drift

Selectors should prefer semantic facts over generated class names:

- candidate anchor has an HTTP(S) URL or `/search/jump` URL;
- jump URL contains a `url` query parameter;
- anchor is visible and has non-empty text;
- normalized target is an allowlisted Toutiao host.

Nearby card text is only used to fill optional `snippet`, `publisher_name` and `published_at_text`. Extraction is bounded by ancestor depth and text length so a selector failure cannot capture the whole page. Missing optional fields are empty strings.

Three page outcomes are distinct:

- recognized results: return normalized records;
- recognized “no results”: return an empty list;
- neither result nor empty state: raise `ToutiaoStructureChangedError` and stop.

## URL Normalization

`help.py` owns pure, offline-testable functions:

- recursively decode `search/jump?url=` up to two layers;
- accept only `http` and `https`;
- reject missing host and non-Toutiao targets;
- lowercase host, remove fragments and known tracking parameters;
- recognize new article paths, legacy `/a<id>/`, video/micro-post/trending paths when present;
- derive `content_id` from a stable numeric path ID, otherwise from a deterministic SHA-256 digest of the canonical URL;
- classify `content_type` conservatively as `article`, `video`, `micro_post`, `trending` or `unknown`.

Nested jump tokens, `jtoken`, search-session IDs and other redirect metadata never enter the stored URL or logs. Normalization performs no network request.

## Data Contract and Privacy

`model/m_toutiao.py` defines a Pydantic model matching the persisted contract:

| Field | Required | Notes |
| --- | --- | --- |
| `content_id` | yes | path ID or canonical-URL digest |
| `content_type` | yes | conservative enum-like string |
| `title` | yes | visible result title |
| `snippet` | no | visible bounded result excerpt only |
| `creator_hash` | yes | deterministic hash of the visible publisher label when available, otherwise empty |
| `publisher_name` | no | visible publisher label passed through the existing nickname mask |
| `published_at_text` | no | original visible date text; no guessed timestamp |
| `content_url` | yes | normalized allowlisted Toutiao URL |
| `source_keyword` | yes | current configured keyword |
| `discovered_at` | yes | local timestamp |

No original account identifier, avatar, profile link, IP location, cookie, request header, QR payload or raw page content is represented in the model.

## Store and Database

`store/toutiao/__init__.py` converts the Pydantic result into the minimal dict and creates a store for `jsonl` or `sqlite` only. `store_comment()` and `store_creator()` are no-ops because those data types are out of scope.

`database.models.ToutiaoContent` contains the contract plus `add_ts` and `last_modify_ts`. SQLite store behavior:

```text
select by content_id
→ found: update mutable visible fields + last_modify_ts
→ absent: set add_ts/last_modify_ts and insert
→ commit
```

JSONL remains append-only but the crawler deduplicates within one run. Cross-run deduplication is guaranteed only by SQLite in this task.

## Error Model and Stop Conditions

Introduce typed platform errors for invalid configuration, challenge/block, structure drift and unsupported mode. Search challenge/block errors are logged without page HTML, query tokens or credential values, then propagated so the run is visibly unsuccessful instead of silently returning zero results. The sole context-specific exception is `ToutiaoLogin`'s explicit manual wait: its live-state polling may keep the visible browser open for a user to handle an official challenge, but timeout still raises an authentication error and unconfirmed state is never saved.

No automatic navigation retry is used for 403/429, challenges or structure drift. Ordinary DOM wait timing may use one bounded Playwright wait. Repeating the DOM-only live-auth check during an explicit manual login wait is allowed; it never refreshes or navigates the page.

## Tests

- Registration/CLI: `toutiao` resolves and detail/creator are rejected.
- URL table tests: one/two jump layers, legacy/current URLs, query/fragment removal, external host, invalid scheme, malformed encoding and hash fallback.
- Parser fixtures: normal card, missing optional fields, duplicate, station-wide external result, recognized empty page, challenge page and structure drift.
- Crawler orchestration: one page per keyword, fixed delay, note limit, no detail/comment calls, stop propagation and no network-response hooks.
- Authentication: restore order, optional anonymous flow, required manual flow, post-login online check, save only on success, disabled state I/O, timeout/challenge behavior and secret-safe logs.
- Store: JSONL contract, SQLite insert/update idempotency and prohibited-field filtering.
- Privacy: add Toutiao model/extractor to `test_no_user_info.py`; raw publisher label is not persisted.

## Real Regression

After offline checks pass:

1. Use the adapter's fresh non-persistent standard Chrome `BrowserContext`; confirm that no CDP port or user-data/profile directory is created and that the submodule is otherwise clean.
2. Run one visible anonymous search for `龙田街道`, one page, maximum ten results, no comments/media/detail.
3. Record only result count, required-field completeness, canonical target hosts and any non-sensitive stop condition.
4. Enable required login, let the user complete official UI manually, then fully stop Chrome and verify a second start can pass the first live login check without another prompt.
5. Remove only the task-created temporary validation directories and the auth-state file inside them after validation; do not touch the project's existing `browser_data/`, `db_data/` or `logs/`.

If search presents a challenge, 403/429 or structure drift, stop and report the observed boundary. During explicit login, leave the visible browser available for the user to handle an official challenge until success or the configured timeout; stop without saving if it times out. Offline-complete code may not be claimed as live-verified until the single-page regression succeeds.

## Delivery and Rollback

- Commit and push the MediaCrawler fork first using Conventional Commits.
- Verify the pushed commit is reachable and the submodule working tree is clean.
- Update and commit the parent gitlink plus Trellis evidence afterward.
- Rollback is the parent gitlink reverting to the previous reachable fork commit; no database migration downgrade is needed during development because the new table is additive.
- Runtime disablement is achieved by not selecting `platform=toutiao`; no existing platform behavior changes.
