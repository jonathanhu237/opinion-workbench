# Technical Design

## 1. Architecture and reuse boundary

Extend the existing product-search vertical slice:

```text
React 采集任务 (platform = dy)
  -> existing FastAPI /api/v1/search-runs
  -> SearchRunService + BrowserOperationCoordinator
  -> SearchRunRepository + SQLite schema v5
  -> existing persistent MediaCrawler worker
  -> strict search protocol v1 (platform = dy)
  -> DouyinProductSearch adapter
  -> borrowed Chrome context + task-owned page + bounded official web-search requests
```

FastAPI continues to own runs, persistence, global identity, source-term provenance and public
errors. MediaCrawler owns only platform interaction and normalized strict events. Neither
`DouYinCrawler.search()` nor MediaCrawler stores are reachable.

## 2. Platform identity and public API

Extend the exact product `SearchPlatform` set from `toutiao | wb | ks` to
`toutiao | wb | ks | dy`. HTTP routes, payload fields, statuses, results and deduplication stay
unchanged. Every layer preserves the stored platform and rejects a valid event for another platform.

The canonical Douyin link is exactly:

```text
https://www.douyin.com/video/<numeric-platform-content-id>
```

It allows no credentials, explicit port, query or fragment. Worker, backend and frontend enforce the
same platform-dependent contract.

## 3. SQLite version 5

Migration 5 transactionally rebuilds the five search aggregate tables with
`platform IN ('toutiao', 'wb', 'ks', 'dy')`, copies existing parents and relationships in dependency
order, swaps tables, recreates indexes, advances `user_version`, and commits atomically.

IDs, timestamps, snapshots, observations, foreign keys, autoincrement state and all existing rows
remain equivalent. Identity remains `UNIQUE(platform, platform_content_id)`.

## 4. Strict worker protocol

Keep search protocol version 1 and extend its exact platform allowlist to `dy`. Existing size, UUID,
ordering, hard-limit, masked-publisher and cancellation rules remain closed. Worker dispatch becomes
exhaustive across `toutiao`, `wb`, `ks` and `dy`.

For `dy`, item validation requires a numeric content ID and the exact canonical `/video/<same-id>`
URL.

## 5. Douyin product adapter

Create `media_platform/douyin/product_search.py` with injected request dependencies for fixtures.
One search operation:

1. closes stale task-owned pages, creates one new page and registers it with the CDP manager;
2. visits the exact official origin and checks known login/challenge evidence;
3. runs the existing authoritative online account probe;
4. refreshes cookies only for the Douyin origin and reads only `localStorage.getItem('xmst')` from
   the task page;
5. constructs the audited general-search parameters and sends one GET to
   `/aweme/v1/web/general/search/single/` per requested page;
6. carries a bounded `extra.logid` search ID, advances offsets in 15-item steps, requests at most
   `ceil(limit / 15)` pages, and stops at the requested per-term limit or recognized exhaustion;
7. normalizes unique works and re-emits a cross-term match so FastAPI preserves provenance;
8. closes only registered task pages on normal completion, cancellation and non-interactive errors.

The adapter uses no proxy, retry or `a_bogus` path. Cookie, `xmst`, request parameters, raw response
and exceptions stay inside the adapter and are never logged or emitted.

## 6. Normalization and outcomes

A safe entry contains `aweme_info`, or the first recognized `aweme_mix_info.mix_items` work, with a
numeric bounded `aweme_id` and usable bounded `desc`. Normalize whitespace, construct the canonical
URL from the ID, convert a valid `create_time` to bounded Shanghai display text, hash `author.uid`
and mask `author.nickname`. Do not retain statistics, account IDs, profile fields, covers, playback
URLs, music, images or search metadata.

| Evidence | Worker outcome |
| --- | --- |
| At least one normalized work and all requested pages finish | `completed_with_results` |
| Recognized successful empty list for every term | `completed_empty` |
| Authoritative disconnected account / recognized login response | `login_required` |
| Visible official slider, captcha or safety challenge | `manual_challenge_required` |
| HTTP 403/429 or exact recognized block response | `platform_blocked_or_rate_limited` |
| Unknown status, missing required result shape, or non-empty data with no safe work contract | `structure_changed` |
| Browser/CDP unavailable or disconnected | existing browser terminal outcome |
| Cancellation | `cancelled` |
| Other sanitized transport/runtime failure | `internal_error` |

Partial safe results stay attached to a truthful later failure. No failure becomes empty success.
Login/challenge may leave the one official task page visible for manual handling; the worker closes
it before the next owned operation or shutdown.

## 7. React experience

Add `dy` to the existing Shadcn platform Select and exhaustive presenter map using the reviewed
`assets/platforms/douyin.svg`. History and detail reuse current labels, status guidance, counts and
safe links. Default remains 今日头条. There is no new route, selector, placeholder, fake metric or
theme change.

## 8. Compatibility, delivery and rollback

- Version-4 databases migrate without changing existing rows; older binaries reject version 5.
- Existing Toutiao, Weibo and Kuaishou frames and UI behavior remain valid.
- Commit and push the MediaCrawler derivative first, then update the parent gitlink and product code.
- Stop if live search requires automated challenge work, broader LocalStorage export, context-wide
  scripts, invasive signing or repeated high-frequency requests.
- Rollback code never deletes or downgrades the user's database or browser data.
