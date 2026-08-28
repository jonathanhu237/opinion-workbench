# Compact Recovery Contract for Context Injection

The full research reports exceed the native per-file context-injection limit. This compact
integration record is the injection entry; the full reports remain available for source anchors
and extended test matrices. Read the task PRD/design/implementation plan before execution.
They are planning artifacts, not authorization to start. Product scope is owned by the PRD;
the canonical technical choices below resolve alternatives in the full reports.

## Confirmed old behavior

- Batch repository `search_batches.py:300` pauses only manual_challenge_required; ordinary
  failures become failed and advance. Continue at `:400` requeues the paused item; attempt
  creation at `:210` copies every term. This is not word-level continuation.
- Worker reader `media_crawler_auth_worker.py:596` awaits each handler. At `:674` it validates
  exact sequential term-start progress and current-term items; successful final result currently
  proves only the last term started plus item-count consistency. There is no completion event.
- All five product adapters fail out of their serial term loops. Safe completion insertion is
  after all per-term page/normalization/item work, including XHS's zero-items/has_more guard
  (`xhs/product_search.py:654`) and Douyin's continuation-ID guard (`douyin/product_search.py:484`).
- Search results already have global `(platform, content_id)` identity and separate immutable
  run relations/provenance; do not add a second content store.
- UI `collection-batch-detail.tsx` currently shows latest-attempt counts and a generic CAPTCHA
  card. `lib/api/search-batches.ts` rejects a paused item whose last outcome is not a CAPTCHA
  and a queued item with a previous attempt. Extend those invariants deliberately.

## Canonical choices

1. **One batch owner throughout pause.** Any persisted platform failure pauses the whole batch.
   Only explicit continue/skip schedules work. GET, refresh, startup and elapsed time never
   launch a worker/connect Chrome. Interrupted active work reconciles to pause, not next-platform
   auto-advance. Explicit user cancellation ends remaining work; service shutdown is interruption.
2. **Search v2, auth v2 unchanged.** Send only the remaining suffix; worker positions are local.
   Run snapshots stay full and immutable, with `execution_start_term_position`. The run service
   alone maps started/item/completed callbacks to original positions. No second offset in adapters.
3. **Explicit term_completed event.** Exact fields include local position and item_count.
   Reader enforces start -> items -> completion -> next start/final result; callbacks commit in
   order. Empty successful terms complete too. Partial failure, malformed result, missing logid,
   signer/transport failure or cancellation cannot emit completion for that term. Invalid version,
   UUID, platform, action, order, count, duplicate keys or oversized frames fails closed.
4. **Proof ledger, not mutable counters.** Next migration after current v9 adds immutable run
   execution offset and search_protocol_version (old 1; every new writer 2), plus completion rows
   keyed by (run_id, term_position), proof/result_count/completed_at/recorded_at. Proof values are
   worker_term_completed, legacy_next_term_started, legacy_run_succeeded. Derive the contiguous
   prefix across all attempts and return explicit/legacy_inferred/mixed/unknown provenance.
5. **Legacy evidence.** Under inspected fail-fast v1 producers plus ordered persisted start p,
   only positions <p are proved, including empty terms. The current/final term is not proved.
   Whole-run success proves its terms. Legacy completed_at remains null. Never apply this inference
   to new v2 rows missing proof. Invalid snapshots/holes/ranges are recovery-unavailable, not an
   excuse to silently replay confirmed work. A valid failure before any start confirms no new work.
6. **No-work continue.** If all N completions committed but the final outcome failed, explicit
   continue completes the item with completion_basis=confirmed_terms. Create no run/empty search
   and keep the failed latest attempt unchanged. Decoder must not require latest-attempt success.
7. **Fresh intent.** Persist control_revision and require expected revision plus exact current
   item/latest run for recovery mutations; null run only for pre-attempt restart pause. Run ID
   alone misses continue-commit/crash-before-new-attempt races. SQL compare-and-update and owner
   checks are authoritative, not disabled frontend buttons. All new errors remain constant-only.
8. **Skipped is not success.** Add skipped item status and honest terminal aggregates/labels.
   Continue, skip and manual-page carry exactly item_position/expected_run_id/expected_revision;
   cancel carries expected_revision. Canonical skip route is POST /search-batches/{id}/skip.
   Do not adopt bodyless recovery/cancel proposals from early research. Exact other endpoints
   and safe error codes are frozen in design.md.
9. **Explicit old-failure recover.** POST items/{position}/recover may reopen ONE failed item in
   completed_with_failures, only with no active/paused/foreign owner and exact revision/latest run.
   It enters pause with no search/new attempt; other completed/skipped items remain unchanged.
   Store previous batch/item finish timestamps and prior state in an append-only recovery record.
   Do not reopen cancelled/successful/internal_error batches or switch away from another pause.
10. **Aggregate results.** Group all item attempts by content ID, classify by earliest attempt
    relationship, union matched original term positions. Counts/list/filter use the same query,
    never SUM(run counts). A/B then B/C gives A/B/C, preserving old-only results. Return a proven
    source_run_id for XHS's existing relation-checked open endpoint. Preserve each run's own counts
    and global first-seen/monotonic last-seen. Per-attempt request caps remain unchanged.
11. **Coherent reads and writes.** Batch detail/attempt/checkpoint/counts use one read snapshot.
    Each write validates active run/current attempt and is a short transaction. Drain in-flight
    to_thread writes and browser tasks before ownership transfer; cancelling a coroutine does
    not cancel its SQLite thread. Never await a task while holding the lock its finalizer needs.

## Manual-page boundary

- Keep a usable trusted owned failure page across every non-success/non-cancel outcome, not
  merely login/challenge. Do not preserve unsafe-origin/blank/dead handles as trusted pages.
- New search-v2 manual_page command has action show|close, fresh request UUID and platform.
  It takes no URL, terms, tab ID, cookie, token or script. Backend validates paused ownership.
- Show uses the current failure's registered page and bring_to_front only. If missing/closed/
  stale-generation/unsafe, open one new registered page at a fixed official homepage, validating
  final origin. No search, auth check, open_result, signer, Cookie read, challenge inspection,
  refresh, credential entry or security-control interaction occurs in this operation.
- Fallbacks already in source: www.toutiao.com; m.weibo.cn; www.kuaishou.com?isHome=1;
  www.douyin.com; www.xiaohongshu.com. Exact trusted ancillary origins may be used only for
  retaining an already-open official page after explicit allowlist review, not constructed CAPTCHA
  navigation. Do not invent an XHS challenge/search URL.
- Show outcomes: opened_existing|opened_homepage|browser_unavailable|navigation_failed|
  internal_error|cancelled. Close outcomes: closed|not_present|browser_unavailable|internal_error|
  cancelled. Opened means only shown, never authenticated/verified. Close with no handle/transport
  does not launch or reconnect. Skip/cancel settles cleanup before new platform dispatch.
- XHS and other HTTP search adapters can classify verification from API responses while the
  visible tab remains a normal homepage. Even DOM stop markers need not be an actionable CAPTCHA.
  Never state a verification widget exists without observing it. No such live claim was verified.
- Existing 30s navigation, 45s open budget and 3s cancel grace can bound manual operations. Track
  an active manual task separately, allow cancellation, and reject late results from an old pause.
  Release only owned worker transport/process on failure; never close borrowed browser/context.
- Worker restart loses owned-page capability. Do not reacquire tabs by URL/history; old surviving
  tabs become pre-existing and are untouched. Explicit show may create a new safe fallback.
- Fine-grained stage/evidence-source diagnostic schema suggested in the browser report is deferred.
  MVP uses existing real failure categories plus bounded restart/recovery reasons and truthful copy.

## UI and quality

Reuse the current Shadcn/Base UI theme and batch page. Compact cause-specific card exposes
打开平台 / 继续采集 / 跳过此平台 / 取消批次. Existing eligible failures expose 处理此平台.
Keep aggregate results visible and old attempt links; no new sidebar, fake status or global theme.
Query owns durable state; URL owns result filter/platform/offset. Mutations invalidate relevant
resources; stale errors refetch without replaying actions. Keep loading feedback, keyboard focus,
nearby live-region errors and mobile wrapping. Opening XHS results may not steal paused ownership.

Required tests include all five completion boundaries, empty prefix and partial retry dedup,
v9 migration/rollback/foreign keys/legacy proof, no-work continue, old-item audited recover,
stale/double actions, late DB writes, startup pause, show/close sentinels, truthful API challenge
with normal homepage, strict frontend projections and unchanged existing run/result/auth behavior.
Run execution-heavy tests on Centaurus after local-source-only rsync; never sync runtime/keys.
Live browser gates require bounded explicit approval; record untriggered CAPTCHA as untriggered.
Neither research report executed tests or inspected the live DB/browser. No implementation or Git
delivery is authorized merely by these documents.

Full evidence: backend-checkpoint-contract.md; browser-handoff-contract.md;
ui-recovery-evidence.md in this directory. Canonical endpoint/schema decisions are in design.md.
