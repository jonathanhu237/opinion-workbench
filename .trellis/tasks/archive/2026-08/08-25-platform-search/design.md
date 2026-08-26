# Technical Design

## 1. Architecture and ownership

This task is one vertical slice across the React product, FastAPI product backend, product SQLite,
and the pinned MediaCrawler derivative:

```text
React 采集任务
  -> versioned FastAPI search-run API
  -> SearchRunService + shared BrowserOperationCoordinator
  -> SearchRunRepository -> runtime/longtian.sqlite3
  -> lifespan-owned persistent MediaCrawler worker
  -> strict search NDJSON protocol over stdin/stdout
  -> context-injected Toutiao visible-page search
  -> user's approved Chrome default context
```

FastAPI remains the product owner. MediaCrawler owns browser/platform details and emits only bounded
normalized observations. React consumes only versioned product models. The generic MediaCrawler
CLI/store path is not the product source of truth.

The current `PersistentAuthWorkerClient` becomes a persistent MediaCrawler worker client capable of
both unchanged authentication checks and the new search request type. Worker process lifecycle moves
to FastAPI lifespan ownership so platform connection and search services share one worker. A small
`BrowserOperationCoordinator` provides atomic cross-feature admission; the worker request lock remains
the second-line protocol guard.

## 2. Run lifecycle

One accepted start request follows:

```text
validate request + read enabled rule
  -> reject >20 terms / invalid limit / shared-operation conflict
  -> claim shared browser operation
  -> transaction: insert queued run + immutable name/term snapshot
  -> HTTP 202
  -> background task: queued -> running
  -> worker.search(terms[], limit)
  -> progress/item events -> short product SQLite transactions
  -> one terminal run status
  -> release shared browser operation
```

The run status is the public state machine defined in
`.trellis/spec/backend/product-search-guidelines.md`. `queued` and `running` are active; every other
value is terminal. Service cancellation sends one correlated worker cancel. Timeout sends the same
cancel and recycles the worker only when acknowledgement is absent or invalid.

Partial observations already received before cancellation, timeout, or platform failure remain
attached to that terminal run. This is not false success: the terminal status remains the reason the
run stopped, while the detail page may still show the evidence safely persisted before termination.

Startup migration also reconciles stale active rows to `internal_error` with a finish timestamp. It
does not resume, retry, or create a replacement run.

## 3. SQLite model and deduplication

Database migration 2 adds five tables described by the product-search code-spec:

```text
search_runs 1---* search_run_terms
search_runs 1---* search_run_contents *---1 search_contents
search_run_contents 1---* search_run_content_terms *---1 search_run_terms
```

`search_runs` stores a nullable source-rule reference plus immutable rule-name and term snapshots.
Deleting or editing a monitoring rule never rewrites history. `search_contents` is the global unique
content catalog. The two relationship tables preserve run-relative freshness and every source term.

For each item event, one short transaction:

1. looks up `(platform, platform_content_id)`;
2. inserts a new content row or updates safe non-empty mutable fields and `last_seen_at`;
3. creates the run relationship once as `new` if the row was created by this run, otherwise
   `repeated`;
4. creates the `(run, content, term_position)` relationship idempotently;
5. commits before any next browser operation.

The run relationship never flips from `new` to `repeated` merely because another term finds the same
item. Counts are SQL-derived from those unique run relationships, preventing stored counter drift.

History uses descending run IDs with `before_id`. Results use bounded offset pagination and default
to new items first, then current-run observation time. Toutiao's publication string is displayed but
not used as a reliable chronological key because it may be relative or incomplete.

## 4. HTTP models

The exact routes, input constraints, and failure envelopes live in the code-spec. Public projections
are separated by use:

- `SearchRunSummary`: ID, platform, rule-name snapshot, term count, limit, status, progress, derived
  counts, and timestamps for the history list.
- `SearchRunDetail`: summary fields plus ordered term snapshot.
- `SearchResult`: safe content projection, `kind: new|repeated`, ordered `matched_terms`, first/last
  seen times, current-run observation time, and platform publication text.
- List envelopes always own their cursor/pagination metadata; React never infers completion from a
  short malformed payload.

The start endpoint returns 202 with the durable run detail. Reads and cancellation address the
integer run ID; worker UUIDs never cross the public API. Pydantic models are strict and forbid extra
fields. Feature errors use stable Chinese messages and the shared detail envelope.

## 5. Persistent-worker search protocol

Authentication v2 frames remain byte-for-byte compatible. Search receives separate version-1
prefixes so data-bearing item events cannot accidentally weaken the constant-only auth parser.

Search command:

```json
{
  "version": 1,
  "type": "command",
  "command": "search",
  "request_id": "uuid4",
  "platform": "toutiao",
  "terms": ["龙田街道", "龙田社区"],
  "max_results_per_term": 10
}
```

Progress references `term_position`, not the raw term. Each item event also carries a term position
and one existing normalized Toutiao content model. FastAPI validates the position against its
persisted snapshot before storage. Terminal outcomes map one-to-one to public run statuses, except
service-owned timeout and startup interruption.

The worker command stays fixed and credential-free. Search terms travel over inherited stdin, not
argv. Stdout stays protocol-only; stderr is continuously drained and discarded. Search frames have
separate bounds and exact duplicate-key/extra-field/type/UUID/platform validation. Raw frames and
exceptions are never logged or returned.

## 6. Borrowed Chrome and Toutiao adapter

The worker reuses the single lazy Playwright/CDP/browser/default-context session already proven by
the account center. The new operation injects that context into a narrow Toutiao search adapter
instead of invoking `ToutiaoCrawler.start()` or creating a fresh context.

For every run the operation:

- creates and registers one task-owned search page;
- searches terms sequentially through the ordinary visible Toutiao search page;
- classifies result, recognized empty, login wall, official challenge/block, and structure drift;
- applies the existing canonical URL allowlist, bounded visible-text extraction, publisher masking,
  and per-term hard limit;
- deduplicates repeated anchors within a term but intentionally re-emits the same content for a
  different term position;
- never uses context-wide scripts, private responses, signing, retries, pagination, or a fallback
  browser.

Normal completion and cancellation close the owned page. Login/challenge outcomes may leave that
official page visible so the user can act; the worker tracks it and closes it before the next owned
operation or shutdown. Pre-existing pages, the default context, and Chrome remain untouched.

## 7. Frontend experience

### Subject and job

The subject is the operator's collection ledger, not a marketing dashboard. The page's single job is
to start one bounded rule search and make the resulting evidence and freshness unambiguous.

### Visual direction

The current civic visual system remains authoritative: existing background/card/teal/green/amber/
destructive semantic tokens, Songti display text, PingFang/Microsoft YaHei body text, and existing
Shadcn/Base UI primitives. The external design-system search proposed a dark real-time dashboard;
that output is rejected because it conflicts with the established application and the user's prior
feedback against broad palette rewrites. No new global colors, fonts, charts, or decorative metrics
are added.

The page-specific signature is a factual **new/repeated evidence rail**: each result has a textual
freshness badge and a restrained semantic left edge, with matched terms and timestamps aligned as a
compact record. Color reinforces but never replaces the text.

### Routes and layout

`采集任务` becomes the fourth real sidebar destination and is active for both routes:

```text
/collection-runs
+-------------------------------------------------------------+
| 采集任务                                      [开始采集]     |
| [监控规则 ▼] [平台 今日头条] [每词 10]                      |
+-------------------------------------------------------------+
| 正在采集（only when real）                                  |
| 第 2 / 5 个关键词                            [取消任务]     |
+-------------------------------------------------------------+
| 历史任务                                                    |
| 状态 | 规则快照 | 新增/再次命中 | 开始时间 | 查看           |
+-------------------------------------------------------------+

/collection-runs/:runId
+-------------------------------------------------------------+
| ← 返回任务  规则快照  状态/进度                             |
| 新增 8 | 再次命中 3 | 共 11（all real API counts）          |
| [全部] [新增] [再次命中]                                    |
+-------------------------------------------------------------+
| 新增  标题……                         [打开原文]             |
| 命中：龙田街道、龙田社区                                    |
| 平台时间 / 首次发现 / 最近发现                              |
+-------------------------------------------------------------+
```

The start form uses a Shadcn Select for enabled rules, a fixed truthful Toutiao target with the
existing platform logo, a labeled numeric Input, and the Shadcn Button. Rules over 20 terms show a
specific inline error before submission. There is no disabled selector full of unsupported
platforms.

History and detail are deep-linkable. TanStack Query owns server state; React Hook Form + Zod owns
the start form; API modules own runtime decoding and exact `(status, error code)` mapping. Poll once
per second only for active status. New/repeated filters are URL or query-owned so refresh/back works.

Loading uses existing skeletons, empty history invites the real start action, and failures explain
the next step in natural Chinese. `login_required` links to `平台账号`; challenge guidance points to
the visible Chrome page. Every external original link uses a normal anchor with safe target/rel.
Keyboard focus, 44px narrow-screen targets, live progress announcements, reduced motion, and
375/768/1024/1440 responsive checks are mandatory.

## 8. Failure, security, and operational behavior

| Condition | Product behavior |
| --- | --- |
| Disabled/missing/oversized rule | Reject before claiming browser; show exact corrective action |
| Account check or search already active | HTTP 409; existing operation continues |
| Chrome debugging unavailable/disconnected | Terminal browser-unavailable guidance; no fallback |
| Toutiao login wall | Terminal login-required; link to platform account check |
| Official challenge | Stop without retry/bypass; keep official owned page visible |
| 403/429/block | Stop immediately as blocked/rate-limited |
| Unknown DOM | Stop as structure-changed; do not scrape arbitrary text |
| Backend timeout/cancel | Correlated cancel; close only task-owned page; retain partial evidence |
| Malformed child event | Internal error, discard raw frame, recycle worker as needed |
| SQLite unavailable | Constant 503 for new requests; no SQL/path/raw exception |
| Backend restart | Stale active run becomes internal error; no auto-resume |

## 9. Compatibility, delivery, and rollback

- Database migration 2 is forward-only and preserves version-1 monitoring rules. Rollback of code
  must not delete the product database; an older binary will correctly reject the newer schema.
- Existing platform-connection API payloads, auth v2 frames, account states, and monitoring-rule API
  remain compatible. Worker ownership is refactored behind those contracts.
- The MediaCrawler derivative is implemented, tested, committed, and pushed first. Only then may the
  parent gitlink move to its reachable clean revision; parent backend/frontend work is committed
  separately after full verification and user delivery approval.
- If borrowed-context cleanup affects a pre-existing page/context/browser, stop real testing and
  restore the pre-task derivative revision before redesigning. Never reset or delete user runtime
  data as rollback.

## 10. Deferred expansion

The next platform-search adaptations remain separate tasks in this order: Weibo, Kuaishou, Douyin,
then Xiaohongshu. Scheduling is also separate and may reuse durable run/content tables only after the
manual loop proves stable.
