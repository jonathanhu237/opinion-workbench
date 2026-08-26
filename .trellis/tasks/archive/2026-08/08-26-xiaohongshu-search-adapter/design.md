# Technical Design

## 1. Architecture and reuse boundary

Extend the existing product-search vertical slice:

```text
React 采集任务 (platform = xhs)
  -> existing FastAPI /api/v1/search-runs
  -> SearchRunService + BrowserOperationCoordinator
  -> SearchRunRepository + SQLite schema v6
  -> existing persistent MediaCrawler worker
  -> strict search protocol v1 (platform = xhs)
  -> XiaohongshuProductSearch adapter
  -> borrowed Chrome context + task-owned page + bounded signed official search requests

React 小红书结果“打开原文”
  -> POST /api/v1/search-runs/{run_id}/results/{result_id}/open
  -> SearchRunService + BrowserOperationCoordinator
  -> repository proves run/result relation and selects first matched term
  -> strict worker open-result command (ID + one stored term; no token/URL)
  -> XiaohongshuProductSearch in-memory token lookup
  -> task-owned page navigates token-bearing official URL and is handed to the user
```

FastAPI continues to own runs, persistence, global identity, source-term provenance and public
errors. MediaCrawler owns only platform interaction and normalized strict events. Neither
`XiaoHongShuCrawler.search()` nor MediaCrawler stores are reachable.

## 2. Platform identity and public API

Extend the exact product `SearchPlatform` set from `toutiao | wb | ks | dy` to
`toutiao | wb | ks | dy | xhs`. HTTP routes, payload fields, statuses, results and deduplication stay
unchanged. Every layer preserves the stored platform and rejects a valid event for another platform.

The canonical Xiaohongshu link is exactly:

```text
https://www.xiaohongshu.com/explore/<lowercase-24-hex-platform-content-id>
```

It allows no credentials, explicit port, query or fragment. Worker, backend and frontend enforce the
same platform-dependent contract. `xsec_token` and `xsec_source` never cross the adapter boundary.

The canonical link is identity metadata, not a directly navigable link in the XHS UI. A synchronous
`POST /search-runs/{run_id}/results/{result_id}/open` accepts no body and returns one strict outcome:

```text
opened | content_not_found | content_unavailable | login_required |
manual_challenge_required | platform_blocked_or_rate_limited |
structure_changed | browser_unavailable | internal_error
```

The repository must prove that the global content row belongs to the requested run, that its platform
is `xhs`, and return its ID plus matched terms in original term-position order. Nonexistent run/result
is 404, non-XHS result is a closed product error, browser contention is the existing 409, and storage
failure is the existing 503. The response never contains a target URL, term, token or raw error.

## 3. SQLite version 6

Migration 6 transactionally rebuilds the five search aggregate tables with
`platform IN ('toutiao', 'wb', 'ks', 'dy', 'xhs')`, copies existing parents and relationships in
dependency order, swaps tables, recreates indexes, advances `user_version`, and commits atomically.

IDs, timestamps, snapshots, observations, foreign keys, autoincrement state and all existing rows
remain equivalent. Identity remains `UNIQUE(platform, platform_content_id)`.

## 4. Strict worker protocol

Keep search protocol version 1 and extend its exact platform allowlist to `xhs`. Existing size, UUID,
ordering, hard-limit, masked-publisher and cancellation rules remain closed. Worker dispatch becomes
exhaustive across all five product platforms. Add a separate strict `open_result` command/event shape
under the same framed transport rather than overloading search item events. Its command contains only
request UUID, platform `xhs`, one stored term and one lowercase 24-hex content ID; its terminal event
contains only the matching fixed outcome. Existing auth/search frames remain byte-for-byte valid.

For `xhs`, item validation requires a lowercase 24-hex content ID and the exact query-free canonical
`/explore/<same-id>` URL.

## 5. Xiaohongshu product adapter

Create `media_platform/xhs/product_search.py` with injected request/signing dependencies for fixtures.
One search operation:

1. closes stale task-owned pages, creates one new page and registers it with the CDP manager;
2. visits the exact domestic official origin and checks known login/challenge evidence;
3. runs the existing authoritative online account probe;
4. refreshes cookies only for the Xiaohongshu origin and never reads LocalStorage;
5. generates one bounded search ID per term, signs the exact compact payload through the existing
   `xhshow` helper, and sends one POST to `/api/sns/web/v1/search/notes` per requested page;
6. advances one-based pages in 20-item steps, requests at most
   `ceil(max_results_per_term / 20)` pages, and stops at the requested limit or recognized
   exhaustion;
7. normalizes unique note cards and re-emits a cross-term match so FastAPI preserves provenance;
8. closes only registered task pages on normal completion, cancellation and non-interactive errors.

The adapter uses no generic retry client, proxy, signature fallback or secondary origin. Cookie,
signature headers, search ID, xsec values, payload, raw response and exceptions stay inside the
adapter and are never logged or emitted.

## 6. Normalization and outcomes

A safe content entry has a recognized note model type, lowercase 24-hex `id`, a `note_card` object
with usable bounded `display_title`, and a recognized note type. Map `normal` to `image` and `video`
to `video`. Use the title as the initial snippet because the search card does not guarantee a full
description. When both user ID and nickname are present, hash and mask them; otherwise emit both
publisher fields empty. Publication text remains empty unless the card exposes an explicit,
validated timestamp in the live contract.

A sanitized live first page contained safe notes, both recognized auxiliary card types, and several
otherwise-valid note cards whose `display_title` normalized empty. Ignore only an absent, null or
blank-string title after proving the lowercase ID, `note_card` object and recognized `normal` or
`video` type. Do not synthesize a title or mark the ID seen before a later safe card is emitted.
Missing/invalid IDs, missing cards, unknown model/note types and other malformed non-null title
shapes remain `structure_changed`.

Known `rec_query` and `hot_query` entries are auxiliary search suggestions, not content. Covers,
counters, raw author fields, xsec values and other metadata are ignored.

| Evidence | Worker outcome |
| --- | --- |
| At least one normalized note and all requested pages finish | `completed_with_results` |
| Recognized successful empty list, or only valid untitled/auxiliary cards with coherent exhaustion, for every term | `completed_empty` |
| Authoritative disconnected account / HTTP 401 / recognized login response | `login_required` |
| HTTP 461/471 or recognized official captcha/safety challenge | `manual_challenge_required` |
| HTTP 403/429, code 300011/300012 or recognized block response | `platform_blocked_or_rate_limited` |
| Unknown status, contradictory pagination or malformed non-empty data outside the narrow valid-untitled/auxiliary shapes | `structure_changed` |
| Browser/CDP unavailable or disconnected | existing browser terminal outcome |
| Cancellation | `cancelled` |
| Other sanitized transport/runtime failure | `internal_error` |

Partial safe results stay attached to a truthful later failure. No failure becomes empty success.
Login/challenge may leave the one official task page visible for manual handling; the worker closes
it before the next owned operation or shutdown.

## 7. On-demand original opening

The direct query-free gate failed with Xiaohongshu business error 300031, so the product uses this
bounded flow only when the user clicks an XHS result:

1. FastAPI proves `(run_id, result_id)` exists, is XHS and has at least one stored matched term.
2. The global `BrowserOperationCoordinator` admits one operation; the endpoint awaits it with a
   bounded timeout and returns a fixed outcome instead of creating another durable aggregate.
3. The worker opens one owned official home page, proves login and reads only XHS-origin cookies.
4. It signs and sends exactly one first-page request for the first stored matched term. No alternate
   term, second page, retry, proxy or detail request is allowed.
5. It searches the in-memory cards for the exact stored ID. Unknown/malformed non-target shapes keep
   the same fail-closed rules; a coherent page without the target returns `content_not_found`.
6. A matching card must provide a bounded nonempty `xsec_token`. The worker does not read or trust a
   response `xsec_source`; because this is the one approved search-origin operation, one private
   worker constant derives the fixed channel identifier `pc_search`. Token and derived channel are
   used only to construct an official `/explore/<same-id>` navigation inside the worker.
7. The worker validates the resulting page. Login/challenge/block evidence maps normally; known
   unavailable-note evidence including business error 300031 maps to `content_unavailable`; unknown
   redirects or contradictory DOM/URL evidence map to `structure_changed`.
8. On `opened`, the manager unregisters the page without closing it, transferring the visible tab to
   the user. Login/challenge pages may likewise be handed off. All other failures close the owned page.

`xsec_token`, `xsec_source`, Cookie, signed headers, term, payload and raw response never enter a worker
event, backend object, HTTP response, frontend state, SQLite row or log. The destination URL is allowed
to exist in the user's visible Chrome address bar/history because that is the official navigation the
user explicitly requested.

The sanitized live correction gate proved that the exact target card can be present once with a
bounded nonempty token while omitting `xsec_source`. The operation-owned source derivation is therefore
part of the adapter contract, not a permissive fallback or an externally supplied field.

## 8. React experience

Add `xhs` to the existing Shadcn platform Select and exhaustive presenter map using the reviewed
`assets/platforms/xiaohongshu.svg`. History and detail reuse current labels, status guidance and
counts. Default remains 今日头条.

For non-XHS rows, retain the current anchor. For XHS rows, render the existing Shadcn `Button` with
`ExternalLink`; one page-level mutation owns the active result ID so every XHS open button is disabled
during the exclusive operation. The button says `正在打开…` while pending. A nearby `aria-live` region
reports `已在谷歌浏览器打开` only for `opened`; every other fixed outcome gets actionable Chinese text,
and transport/protocol errors keep their technical product message. No new route, placeholder, fake
metric, toast dependency or theme change is introduced.

## 9. Compatibility, delivery and rollback

- Version-5 databases migrate without changing existing rows; older binaries reject version 6.
- On-demand opening adds no database migration and never rewrites existing canonical XHS content URLs.
- Existing Toutiao, Weibo, Kuaishou and Douyin frames and UI behavior remain valid.
- Commit and push the MediaCrawler derivative first, then update the parent gitlink and product code.
- Stop if live opening requires xsec persistence or exposure, more than the approved single search
  page, automated challenge work, broader browser-state export, context-wide scripts, alternate
  signing or repeated high-frequency requests.
- Rollback code never deletes or downgrades the user's database or browser data.
