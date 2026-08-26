# Technical Design

## 1. Architecture and reuse boundary

Extend the current product-search vertical slice rather than creating another collector:

```text
React 采集任务 (platform = ks)
  -> existing FastAPI /api/v1/search-runs
  -> SearchRunService + BrowserOperationCoordinator
  -> SearchRunRepository + SQLite schema v4
  -> existing persistent MediaCrawler worker
  -> strict search protocol v1 (platform = ks)
  -> KuaishouProductSearch adapter
  -> borrowed Chrome context + task-owned signer page + bounded official search requests
```

FastAPI continues to own runs, product persistence, global identity, source-term provenance and
public errors. MediaCrawler only owns browser/platform interaction and normalized strict events.
Neither the generic `KuaishouCrawler.search()` nor MediaCrawler stores are reachable.

## 2. Platform identity and public API

Extend the exact product `SearchPlatform` set from `toutiao | wb` to `toutiao | wb | ks`. The HTTP
routes, payload fields, status vocabulary, result model and deduplication semantics stay unchanged.
Every layer carries the stored platform unchanged and rejects a valid event for another platform.

The canonical Kuaishou link is exactly:

```text
https://www.kuaishou.com/short-video/<platform_content_id>
```

It allows no credentials, non-default port, query or fragment. Backend and frontend runtime
validators enforce the same platform-dependent contract.

## 3. SQLite version 4

SQLite version 3 restricts search platforms to `toutiao | wb`. Migration 4 transactionally rebuilds
the five search aggregate tables with `platform IN ('toutiao', 'wb', 'ks')`, copies existing parents
and relationships in dependency order, swaps tables, recreates indexes, advances `user_version`,
and commits atomically.

IDs, timestamps, rule snapshots, observations, term relationships, foreign keys and existing
Toutiao/Weibo rows remain equivalent. Identity remains `UNIQUE(platform, platform_content_id)`, so
equal IDs on different platforms stay isolated.

## 4. Strict worker protocol

Keep search protocol version 1 and extend its exact platform allowlist to `ks`. Command, progress,
item, result, cancel, size, UUID, ordering, hard-limit and masked-publisher validation stay closed.
The backend active request correlates the exact requested platform. Worker dispatch becomes:

```text
toutiao -> existing adapter
wb      -> existing adapter
ks      -> new Kuaishou product adapter
other   -> protocol/internal failure
```

For `ks`, item URL validation requires the exact canonical `/short-video/<matching-id>` link.

## 5. Kuaishou product adapter

Create `media_platform/kuaishou/product_search.py` with injected request/signing dependencies for
fixtures. One search request:

1. creates and registers one task-owned page in the borrowed default context;
2. installs the existing `KS_SIGN_CAPTURE_SCRIPT` on that page only, then navigates to the exact
   official Kuaishou origin;
3. refreshes only Kuaishou cookies and performs the authoritative online login probe;
4. emits sequential term progress;
5. for each page body, generates `__NS_hxfalcon` through the task page and sends one POST to
   `/rest/v/search/feed?__NS_hxfalcon=<ephemeral>&caver=2`;
6. carries `searchSessionId`, requests at most `ceil(limit / 20)` pages, and stops at the requested
   per-term limit;
7. normalizes unique safe feeds and re-emits the same work for another term so FastAPI can preserve
   cross-term provenance;
8. closes only the registered task page on completion or cancellation.

The product request client uses no proxy and no automatic retry. Signing values, headers, Cookies,
body contents, raw responses and exceptions never cross the adapter boundary or enter logs.

## 6. Normalization and outcomes

A safe feed requires a dictionary `photo` with a stable bounded ID and usable bounded
`caption`/`originCaption`. Normalize whitespace, construct the canonical URL from the ID, convert a
valid platform timestamp to bounded display text, and retain only the existing anonymous creator
hash plus fixed masked nickname. Do not retain counts, cover URLs, playback URLs or author IDs.

| Evidence | Worker outcome |
| --- | --- |
| At least one normalized work and all requested pages finish | `completed_with_results` |
| Recognized successful empty response for every term | `completed_empty` |
| Failed authoritative login proof / recognized login response | `login_required` |
| Recognized official verification page/response | `manual_challenge_required` |
| HTTP 403/429 or recognized `result=2` | `platform_blocked_or_rate_limited` |
| Signer unavailable, unknown result code/shape, or non-empty feeds with no safe contract | `structure_changed` |
| Browser/CDP unavailable or disconnected | existing browser terminal outcome |
| Cancellation | `cancelled` |
| Other sanitized transport/runtime failure | `internal_error` |

Partial safe items stay attached to a truthful later failure. No failure is converted to empty
success. A login or challenge may leave only the official task page visible for manual handling;
the worker cleans it before the next owned operation or shutdown.

## 7. React experience

Add `ks` to the existing Shadcn platform Select and exhaustive presenter map using
`assets/platforms/kuaishou.svg`. History and detail render the correct logo/label and reuse current
status guidance. The default remains 今日头条 for compatibility. There is no sort/filter control,
placeholder platform, fake metric, new route, global theme change or separate Kuaishou page.

## 8. Compatibility, delivery and rollback

- Existing version-3 databases migrate without changing their rows; older binaries reject version
  4 rather than silently writing it.
- Existing Toutiao/Weibo protocol frames, API payloads and UI behavior remain valid.
- Commit and push the MediaCrawler derivative first, then update the parent gitlink and product code.
- Stop and return to planning if the real endpoint now requires broader state extraction, more
  invasive signing, automated challenge work or repeated high-frequency requests.
- Rollback code must never delete or downgrade the user's database or browser data.
