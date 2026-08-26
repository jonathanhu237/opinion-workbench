# Product Search Guidelines

> Executable contract for product-owned collection runs, borrowed-Chrome search, durable results,
> and cross-run deduplication.

## Scenario: Manual multi-platform product search through the persistent worker

### 1. Scope / Trigger

Use this contract when React starts or reads a product search run, FastAPI persists normalized
discoveries, or the MediaCrawler persistent worker performs a platform search in the user's approved
Chrome session.

This is a product orchestration contract, not a general crawler contract. The standalone adapter
contract in `browser-search-adapter-guidelines.md` continues to require a fresh context. Only this
lifespan-owned product worker may borrow the already approved default Chrome context, and only with
the ownership and serialization rules below. The exact supported search-platform set is
`toutiao | wb | ks | dy`; extending it requires coordinated API, database, worker-protocol, adapter,
frontend, and migration changes.

### 2. Signatures

Database version 5 owns:

```text
search_runs(
  id, monitoring_rule_id, platform, rule_name, max_results_per_term, status,
  current_term_position, created_at, started_at, finished_at
)
search_run_terms(run_id, position, value)
search_contents(
  id, platform, platform_content_id, content_type, title, snippet, creator_hash,
  publisher_name, published_at_text, content_url, first_seen_at, last_seen_at
)
search_run_contents(
  run_id, search_content_id, discovery_kind, first_observed_at, last_observed_at
)
search_run_content_terms(
  run_id, search_content_id, term_position, observed_at
)
```

Required identities are:

```text
UNIQUE search_contents(platform, platform_content_id)
PRIMARY KEY search_run_terms(run_id, position)
PRIMARY KEY search_run_contents(run_id, search_content_id)
PRIMARY KEY search_run_content_terms(run_id, search_content_id, term_position)
```

`monitoring_rule_id` is nullable and uses `ON DELETE SET NULL`; `rule_name` and terms are immutable
run snapshots.

The HTTP boundary is:

```http
POST /api/v1/search-runs
GET  /api/v1/search-runs?limit=20&before_id=<optional-int64>
GET  /api/v1/search-runs/{run_id}
GET  /api/v1/search-runs/{run_id}/results?kind=all|new|repeated&limit=50&offset=0
POST /api/v1/search-runs/{run_id}/cancel
```

Start input is exact and strict:

```json
{"monitoring_rule_id": 1, "platform": "dy", "max_results_per_term": 10}
```

- `monitoring_rule_id`: SQLite signed-int64 integer from 1 upward.
- `platform`: exact literal `toutiao | wb | ks | dy`.
- `max_results_per_term`: strict integer 1–50, default 10.
- The selected enabled rule must contain 1–20 terms.

Public run status is one of:

```text
queued | running | completed_with_results | completed_empty | login_required |
manual_challenge_required | platform_blocked_or_rate_limited | structure_changed |
browser_unavailable | timed_out | cancelled | internal_error
```

The worker keeps the existing auth v2 frames unchanged and adds a separate strict search protocol:

```text
__MEDIACRAWLER_SEARCH_COMMAND__{"version":1,"type":"command","command":"search","request_id":"<uuid4>","platform":"wb","terms":["..."],"max_results_per_term":10}
__MEDIACRAWLER_SEARCH_EVENT__{"version":1,"type":"event","event":"progress","request_id":"<uuid4>","platform":"wb","phase":"term_started","term_position":0,"term_count":5}
__MEDIACRAWLER_SEARCH_EVENT__{"version":1,"type":"event","event":"item","request_id":"<uuid4>","platform":"wb","term_position":0,"item":{...}}
__MEDIACRAWLER_SEARCH_EVENT__{"version":1,"type":"event","event":"result","request_id":"<uuid4>","platform":"wb","outcome":"completed_with_results"}
```

Search cancellation uses the search-command prefix with exact `command="cancel"` and matching
`request_id`. Worker shutdown remains the existing lifecycle command.

### 3. Contracts

#### Product service and API

- `POST` snapshots the current enabled rule and persists `queued` before returning HTTP 202. It
  launches no browser work inside a database transaction.
- A lifespan-owned cross-feature coordinator claims one browser operation before accepting work.
  Platform checks retain their existing product errors; search starts return
  `browser_operation_active` when either feature owns the coordinator.
- Background execution moves `queued -> running -> exactly one terminal status`. Terminal rows are
  immutable except for repository repair of a stale active row during the next startup.
- Startup changes leftover `queued` or `running` rows to `internal_error` with a finished timestamp.
  It does not retry or resume them.
- Run list order is `id DESC` with cursor-style `before_id`; result order is `new` before `repeated`,
  then current-run `first_observed_at DESC`, then stable content ID. Counts are derived from
  `search_run_contents`, not maintained as independent mutable counters.
- `GET /{id}` returns the rule snapshot, progress, timestamps, and derived new/repeated/total counts.
  The run list may return a smaller summary but uses the same status/count definitions.
- Results contain one row per unique run content with `matched_terms` in original rule position
  order. `kind=new|repeated` filters only the run relationship, never the global content table.
- Platform is never defaulted after validation. The stored run platform must be carried unchanged
  through the service, active worker request, every correlated worker event, repository lookup, and
  response. A valid event for the other supported platform is protocol drift and fails closed.
- `POST /cancel` returns HTTP 202 only for the active run. Cancellation is idempotent inside the
  worker boundary but a second public request after terminal state returns `search_run_not_active`.

#### Persistence and deduplication

- One short `BEGIN IMMEDIATE` transaction processes each normalized item event. Browser/network
  work never occurs while a transaction is open.
- If `(platform, platform_content_id)` does not exist, insert `search_contents` and a `new` run
  relationship. If it already exists before this run, update safe mutable fields and `last_seen_at`,
  then insert a `repeated` relationship.
- If the content was inserted earlier in the same run, later term matches preserve that run
  relationship as `new`; they only add an idempotent term relationship.
- Preserve `first_seen_at`. Update `last_seen_at` monotonically. Do not overwrite a non-empty title,
  snippet, publisher label, or publication text with an empty incoming value.
- `published_at_text` remains bounded display text. Do not parse `刚刚`, `昨天`, or an incomplete
  date into a fabricated exact timestamp.
- The product repository is the only source of truth for run history and cross-run deduplication.
  The worker does not invoke MediaCrawler JSONL/SQLite stores for product search.

#### Worker and borrowed browser

- Extend the existing persistent worker; do not launch `main.py` per term and do not pass terms in
  command-line arguments.
- The command accepts 1–20 non-empty bounded terms as a structured array and a hard result limit of
  1–50. Terms remain on stdin only and are never logged.
- Search reuses the worker's single Playwright/CDP/browser/default-context session. It creates and
  registers only task-owned pages, never closes the borrowed context/browser, and never mutates or
  closes pre-existing tabs.
- Search performs sequential bounded platform searches without context-wide init scripts, signature
  generation, broad pagination, blocked-navigation retry, or fallback to a second browser.
- Toutiao uses the visible official PC search page. Weibo uses the borrowed session to refresh only
  Weibo state, then calls the existing `m.weibo.cn` real-time search endpoint through a
  product-specific single-attempt client. Kuaishou creates one task-owned page, installs the
  existing signer on that page only, proves the account state online, and calls the official
  `/rest/v/search/feed` endpoint through its product-specific single-attempt client. Generic retry
  clients, crawler stores, full-text/detail requests, comments, user profiles, and media helpers are
  forbidden.
- Douyin creates one task-owned official page, reuses the authoritative online account probe, reads
  only `localStorage.getItem('xmst')`, and calls the official
  `/aweme/v1/web/general/search/single/` endpoint through a product-specific single-attempt client.
  It uses the default general sort, requests 15 results per page with offsets 0/15/…, carries
  `extra.logid` as the next `search_id`, and requests at most
  `ceil(max_results_per_term / 15)` pages. It does not call `DouYinCrawler.search`, generate
  `a_bogus`, install context-wide scripts, use a proxy or retry, write crawler stores, or request
  details, comments, profiles, covers or media.
- A disconnected account check is not itself a search failure. The official public search page may
  be used without an authenticated Toutiao account; return `login_required` only when the search
  page itself presents a recognized mandatory login wall.
- The Toutiao PC parser requires exactly one visible `.s-result-list`, scans anchors only inside that
  main column, and never treats `.s-side-list` hot-board entries as keyword results. It groups anchors
  by unwrapped content identity, prefers the human title over image/duration/detail labels, and scopes
  recognized empty text to that same main column. A missing or ambiguous main container fails as
  `structure_changed`.
- The Weibo adapter fixes search type `61`, visits only the allowlisted mobile origin, requests at
  most `ceil(max_results_per_term / 10)` pages per term, and accepts only recognized card type 9
  mblogs with a stable non-empty ID and usable cleaned text. It strips HTML, decodes entities,
  normalizes whitespace, and constructs `https://m.weibo.cn/detail/<id>` itself with no query or
  fragment. Unknown successful response/card shapes fail as `structure_changed`; they never become
  a false empty result.
- The Kuaishou adapter requests at most `ceil(max_results_per_term / 20)` pages per term, sends a
  numeric page `pcursor`, and carries the response `searchSessionId` to later pages. Each page is
  requested once. It accepts only recognized successful feeds containing a stable `photo.id` and
  usable bounded caption, builds the canonical URL itself, and never exposes signing values,
  Cookies, raw response data, author IDs, media URLs, counters, or page-local state. Login,
  challenge, HTTP 403/429, recognized block, signer failure, and unknown response shapes remain
  distinct terminal outcomes and never become empty success.
- Deduplicate repeated anchors within one term, but emit the same content again for another
  `term_position`; FastAPI owns cross-term merging and provenance.
- Item frames use `term_position`, not a copied source-term string. They contain only the bounded
  normalized platform model: content ID/type, title, snippet, masked publisher fields, visible
  publication text, platform-allowlisted canonical URL, and a 13-digit Unix-millisecond discovery
  timestamp.
- Search command frames are at most 32 KiB and search event lines at most 64 KiB. Decode UTF-8,
  reject duplicate JSON keys/unknown fields/wrong types, correlate exact UUID/platform, and fail the
  request on protocol drift. Never retain or log raw stdout/stderr.
- Progress positions are exactly sequential from zero, item events belong only to the current term
  and cannot exceed its requested hard limit, and successful completion follows progress for every
  term. `completed_empty` carries no items, `completed_with_results` carries at least one item, and
  `cancelled` is accepted only after the matching request was cancelled.
- A non-empty creator hash is exactly the lowercase 16-hex anonymous digest produced by the adapter;
  its publisher label must be present and match the fixed masked nickname forms. Empty publisher
  fields remain paired. Raw publisher identifiers or labels fail the protocol boundary.
- Canonical content URLs remove fragments, known search/tracking parameters, and empty query
  parameters, sort any remaining meaningful query pairs, and never retain redirect/session tokens.
  Weibo is stricter: only `https://m.weibo.cn/detail/<matching-platform-content-id>` with no query,
  fragment, credentials, or non-default port is valid.
  Kuaishou is equally strict: only
  `https://www.kuaishou.com/short-video/<matching-platform-content-id>` is valid; hostname case
  variants, explicit ports, queries, fragments, credentials, and mismatched IDs are rejected.
  Douyin is equally strict: only
  `https://www.douyin.com/video/<matching-numeric-platform-content-id>` is valid; hostname case
  variants, explicit ports, queries, fragments, credentials, non-numeric IDs and mismatched IDs are
  rejected.
- Normal completion and cancellation close the task-owned search page. Login/challenge outcomes may
  leave that one official page visible for manual action; it remains registered and is closed before
  the next task-owned operation or worker shutdown. Pre-existing pages are never cleanup targets.

#### UI contract

- Add the real sidebar label `采集任务` and routes `/collection-runs` and
  `/collection-runs/:runId`; the sidebar item is active for both.
- The start view uses enabled monitoring rules, a Shadcn platform Select containing exactly the
  executable `今日头条`、`微博`、`快手` and `抖音` targets, and a labeled 1–50 number field with default 10. It does
  not show unavailable platforms as executable controls or add a sort selector.
- Poll once per second only while the selected/latest run is active. Terminal/history queries use
  ordinary TanStack Query caching and explicit invalidation.
- The run detail displays real counts and labels every item `新增` or `历史内容再次命中`. Original
  links open safely with `target="_blank"` and `rel="noreferrer"`.
- Use the existing Shadcn/Base UI primitives and semantic tokens. Do not replace global colors or
  fonts, create fake telemetry, or use color as the only status signal.

#### Privacy and delivery

- API models, logs, tests, and task evidence exclude Cookies, LocalStorage, auth headers, QR data,
  raw HTML/body/child lines, browser-profile paths, SQL, database paths, and raw exceptions.
- Commit and push the MediaCrawler derivative before moving the parent gitlink, and move the gitlink
  only to a reachable clean derivative revision.

### 4. Validation & Error Matrix

All expected HTTP failures use `{"detail":{"code":"...","message":"..."}}` with constant
Chinese guidance.

| Condition | Status / outcome | Required behavior |
| --- | --- | --- |
| Malformed body/query/path, unknown field, wrong strict type | HTTP 422 `invalid_request` | No run or browser work |
| Rule missing | HTTP 404 `monitoring_rule_not_found` | No run |
| Rule disabled | HTTP 409 `monitoring_rule_disabled` | Direct operator to enable it |
| Rule has more than 20 terms | HTTP 422 `too_many_search_terms` | Direct operator to split it |
| Another search/account operation active | HTTP 409 `browser_operation_active` | Existing operation continues |
| Run missing | HTTP 404 `search_run_not_found` | No child action |
| Cancel requested for terminal/non-active run | HTTP 409 `search_run_not_active` | Preserve terminal row |
| Product SQLite unavailable | HTTP 503 `search_storage_unavailable` | Constant message, no path/SQL |
| Unknown search platform or platform-dependent URL mismatch | HTTP 422 / worker protocol failure | No default substitution; fail closed |
| Recognized results | `completed_with_results` | Persist items/matches and counts |
| Recognized empty page for every term | `completed_empty` | Persist truthful zero-result run |
| Account check is disconnected but public search is available | Continue search | Do not invent a login prerequisite |
| Mandatory login wall on the search page | `login_required` | No false empty; point to account flow |
| Official safety challenge | `manual_challenge_required` | No retry/bypass; keep official page visible |
| HTTP 403/429 or recognized block | `platform_blocked_or_rate_limited` | Stop immediately, no retry/fallback |
| Neither result nor recognized empty structure | `structure_changed` | Stop; do not parse arbitrary page text |
| CDP unavailable/disconnected | `browser_unavailable` | Preserve borrowed-browser ownership |
| Service timeout | `timed_out` | Correlated cancel, recycle worker if no ack |
| Operator cancellation | `cancelled` | Retain already persisted partial observations with terminal status |
| Malformed/mismatched/oversized child frame | `internal_error` | Fail closed; discard raw frame |
| Backend restarts with active rows | `internal_error` | Reconcile stale rows, do not resume |

### 5. Good / Base / Bad Cases

- **Good:** A five-term Kuaishou rule starts one durable run, searches each term sequentially through
  the task-owned signer page, stores one global content row for a cross-term match, records both
  matching terms, and reports consistent new/repeated counts on a later run.
- **Base:** A one-term run reaches a recognized empty state and persists `completed_empty` with zero
  results; no store or private endpoint is invoked.
- **Bad:** Terms appear in process arguments/logs, a generic retry client or crawler
  store is used, repeated content is inserted again, a cross-term match loses provenance, an unknown
  response becomes empty success, one layer silently substitutes Toutiao, or cleanup closes the
  user's context/tab.

### 6. Tests Required

1. Migration: version 1→2→3→4→5, direct version 4→5, fresh version 5, repeated initialization,
   forward-version rejection, foreign keys/indexes, active-row reconciliation, preservation of all
   Toutiao IDs/relations/timestamps, and same content ID isolation across platforms.
2. Repository: run snapshots, stable history pagination, state transitions, transactional item
   upsert, same-run cross-term provenance, cross-run new/repeated classification, monotonic times,
   non-empty field preservation, counts, filters, and rollback on failure.
3. API/service: exact 202/200 payloads, rule enabled/size checks, 1–50 limit, int64 bounds, global
   operation conflicts, cancellation, all terminal mappings, timeout, shutdown, OpenAPI models, and
   sanitized 404/409/422/503 responses.
4. Worker protocol: strict command/item/progress/result/cancel frames, duplicate-key/extra-field/
   size/UUID/platform rejection, structured term array, term-position correlation, stderr drain, and
   no raw-frame logging.
5. Borrowed Chrome: reuse one CDP/default context, task-page registration, no context-wide scripts,
   no close of browser/context/pre-existing pages, challenge-page lifecycle, cancellation, disconnect,
   and worker recycle.
6. Platform adapters: retain all Toutiao, Weibo and Kuaishou fixtures, plus Douyin exact request
   parameters, scoped-cookie and single-key LocalStorage access, 15-result pagination/logid
   propagation, single attempt, bounded pages, canonical URL construction, publisher masking,
   within-term deduplication, cross-term re-emission, hard limit, and every recognized terminal
   outcome. Kuaishou retains its exact signed request parameters, task-local signer isolation and
   numeric pagination/session propagation.
7. Frontend: runtime decoders, exact status/code pairs, start validation, active polling, cancel,
   history/deep link, new/repeated filters and counts, matched terms, safe original links, empty/error/
   login guidance, keyboard/focus/live-region behavior, mobile layout, and no fake data.
8. Cross-layer and real browser: for each newly supported platform, one approved borrowed-browser
   search plus the exact repeated run, new/repeated classification, preserved first-seen and advanced
   last-seen times, account/search mutual exclusion, truthful login/challenge outcomes, restart
   persistence, pre-existing-tab sentinel, no credential leakage, and clean submodule/gitlink
   delivery.

### 7. Wrong vs Correct

#### Wrong

```python
# Terms leak through argv, each invocation owns a different browser, generic stores lose run context.
await create_subprocess_exec(
    "python", "main.py", "--platform", "toutiao", "--keywords", ",".join(terms)
)
```

```sql
-- Repeated observations create repeated content rows and cannot retain per-term provenance.
INSERT INTO search_contents(platform, platform_content_id, title)
VALUES (?, ?, ?);
```

#### Correct

```python
# One lifespan-owned worker receives a bounded structured command over stdin.
await worker.search(
    request_id=run_uuid,
    platform=stored_run.platform,
    terms=rule_snapshot.terms,
    max_results_per_term=limit,
    on_item=persist_normalized_item,
)
```

```text
upsert unique search_contents(platform, platform_content_id)
  -> upsert one search_run_contents(run_id, content_id, new|repeated)
  -> insert one search_run_content_terms(run_id, content_id, term_position)
```
