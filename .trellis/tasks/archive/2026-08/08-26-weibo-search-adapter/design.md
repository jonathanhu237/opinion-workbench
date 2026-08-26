# Technical Design

## 1. Architecture and reuse boundary

The feature extends the existing product-search vertical slice instead of introducing a second
collection system:

```text
React 采集任务 (platform = wb)
  -> existing FastAPI /api/v1/search-runs
  -> SearchRunService + BrowserOperationCoordinator
  -> SearchRunRepository + SQLite schema v3
  -> existing persistent MediaCrawler worker
  -> strict search protocol v1 (platform = wb)
  -> WeiboProductSearch adapter
  -> borrowed Chrome context + bounded m.weibo.cn request
```

FastAPI remains authoritative for runs, global content identity, source-term provenance, public
errors, and durable SQLite. MediaCrawler remains the browser/platform adapter. The generic
`WeiboCrawler.search()` and MediaCrawler stores are not called because their global configuration,
five-attempt retry, extra collection flows, and file/database outputs violate the product boundary.

## 2. Platform identity and public API

Use `wb` as the canonical search-platform identifier because it is already the strict worker and
platform-account identifier. Introduce one shared backend `SearchPlatform = Literal["toutiao",
"wb"]` and reuse it in create, run, and result models. The HTTP routes and status/error vocabulary
remain unchanged.

`POST /api/v1/search-runs` continues to accept the selected platform and returns 202 after the run
snapshot is durable. The service passes the stored platform through to the worker and repository;
no downstream layer substitutes a default. URL validation is platform-dependent:

- `toutiao`: retain the current Toutiao official-domain contract.
- `wb`: accept only canonical `https://m.weibo.cn/detail/<platform_content_id>` URLs with no
  credentials, non-default port, query, or fragment.

Frontend runtime decoders validate both platform values and the same platform-dependent original
link contract. Known status/code pairs remain exact.

## 3. SQLite version 3

SQLite version 2 hard-codes `platform = 'toutiao'` in `search_runs` and `search_contents`. Migration
3 transactionally rebuilds all five search tables so foreign keys never point at a dropped parent:

1. create v3 parent and relationship tables with `platform IN ('toutiao', 'wb')`;
2. copy existing rows in dependency order;
3. drop old relationship tables in reverse dependency order, then old parents;
4. rename v3 parents and children to the stable table names;
5. recreate indexes, set `user_version = 3`, and commit.

All existing columns, IDs, timestamps, rule references, relationship keys, and Toutiao data are
preserved. The repository changes hard-coded Toutiao SQL into bound platform parameters. The global
identity remains `UNIQUE(platform, platform_content_id)`, so equal IDs on Weibo and Toutiao are
distinct while repeat Weibo observations deduplicate.

## 4. Strict worker protocol

Search protocol version 1 keeps the same frame shapes and adds `wb` to the exact search-platform
allowlist. Command, progress, item, result, cancel, UUID, size, duplicate-key, ordering, and
per-term-count checks remain unchanged.

Both serializers and parsers validate item URLs against the correlated platform. The backend active
request stores the requested platform and rejects a validly shaped event for the other search
platform. The worker dispatches through an exhaustive platform branch:

```text
toutiao -> search_toutiao_with_context(...)
wb      -> search_weibo_with_context(...)
other   -> protocol/internal failure
```

Terms stay only in bounded stdin frames and platform request parameters; they are never printed or
logged. Stdout remains strict protocol-only and stderr remains drained/discarded.

## 5. Weibo product adapter

Create a narrow `media_platform/weibo/product_search.py` adapter with dependencies injectable for
fixture tests. For one run it:

1. creates and registers one task-owned page in the borrowed default context;
2. navigates only to an allowlisted `https://m.weibo.cn/` origin and refreshes only Weibo cookies;
3. creates a product-specific request client with fixed ordinary headers and no proxy;
4. for every term, emits progress and requests real-time search type `61` sequentially;
5. reads up to the requested hard limit, using at most `ceil(limit / 10)` pages and no retry for a
   page request;
6. normalizes unique card-type-9 mblogs and emits the same content again for a different term so
   FastAPI can preserve cross-term provenance;
7. closes only the task-owned page on ordinary completion/cancellation.

The normalizer accepts only a dictionary with a stable non-empty mblog ID and usable cleaned text.
It strips HTML, decodes entities, normalizes whitespace, bounds all text, constructs the canonical
mobile detail URL from the ID rather than trusting a response URL, formats the existing platform
creation value as bounded display text, and retains only the existing anonymous creator hash and
masked nickname. If no safe title exists, the first bounded portion of cleaned content is used as
the required title and the full bounded content becomes the snippet.

No full-text request, comment request, image helper, store, database, proxy, signature generation,
context-wide script, or fallback browser is reachable from this adapter.

## 6. Outcome classification

The adapter maps only recognized evidence:

| Evidence | Worker outcome |
| --- | --- |
| At least one normalized item and all requested pages finish | `completed_with_results` |
| Valid response/card structure for every term, no valid result cards | `completed_empty` |
| Recognized official login-required response/page | `login_required` |
| Recognized official verification/challenge response/page | `manual_challenge_required` |
| HTTP 403/429 or recognized access/rate rejection | `platform_blocked_or_rate_limited` |
| Successful transport but unknown/malformed response/card contract | `structure_changed` |
| CDP/Chrome unavailable or disconnected | existing browser outcomes |
| Cancellation | `cancelled` |
| Other sanitized transport/runtime failure | `internal_error` |

Partial safe items emitted before a terminal failure remain attached to the truthful terminal run.
Raw HTTP bodies, dynamic platform messages, and exceptions are never used as public error text.
Challenge or login may leave the official task-owned page visible for manual action; it remains
registered and is cleaned before the next browser operation or worker shutdown.

## 7. Frontend experience

The current collection page gains a Shadcn Select with exactly the two executable platforms:
今日头条 and 微博, using the existing reviewed platform logo assets. The initial selection remains
今日头条 for compatibility; changing it sends `wb` without changing the selected monitoring rule or
per-term limit.

History and detail render platform name/logo from one exhaustive presenter map. Result links and
runtime payloads are validated by platform. There are no placeholder entries for 快手、抖音 or
小红书 and no new dashboard metrics, colors, routes, or search-sort control. Existing responsive,
keyboard, focus, live-region, polling, cancel, and deep-link behavior remains intact.

## 8. Compatibility, delivery, and rollback

- Existing version-2 databases migrate forward without changing Toutiao rows or public IDs. An
  older binary will reject schema version 3 rather than silently corrupting it.
- Existing Toutiao commands/events and API payloads remain valid under protocol version 1.
- Implement and commit the MediaCrawler derivative first, push its reachable revision, then update
  the clean parent gitlink and commit backend/frontend changes.
- Rollback code must not delete or downgrade the user database. If real Weibo validation affects a
  pre-existing page, browser context, or current Toutiao behavior, stop and redesign before delivery.
