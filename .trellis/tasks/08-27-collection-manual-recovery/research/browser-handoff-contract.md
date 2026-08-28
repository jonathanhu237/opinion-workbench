# Research: Browser handoff and term-completion contract

- Query: Identify the smallest safe manual-page handoff, phase-specific diagnostics, five-adapter completion hooks, and pause/continue/skip/cancel/restart lifecycle for collection recovery.
- Scope: internal; read-only source/spec/test research. Only this research file was written. No services, tests, browsers, collection, model calls, product APIs, or Git operations were run.
- Date: 2026-08-28
- Requirements: `.trellis/tasks/08-27-collection-manual-recovery/prd.md`; approved policy is **pause the whole batch after any platform failure**, resume only on explicit Continue or Skip. Manual work stays in borrowed user Chrome. Implementation remains unapproved.

## Findings

### 1. Files found and governing specifications

| File | Responsibility / relevant anchors |
| --- | --- |
| `third_party/MediaCrawler/media_platform/toutiao/product_search.py` | Single task-owned visible search page, term loop at :59, typed failure mapping at :93, cleanup at :103. |
| `third_party/MediaCrawler/media_platform/toutiao/client.py` | Official search navigation at :177; trusted-origin, HTTP, bounded DOM-read and recognition checks at :186–257. |
| `third_party/MediaCrawler/media_platform/weibo/product_search.py` | Mobile homepage and single-attempt HTTP search; URL classifier :140, HTTP/business classifiers :171/:227, term loop :320. |
| `third_party/MediaCrawler/media_platform/kuaishou/product_search.py` | Task-page signer, online account probe, bounded HTTP search; classifiers :130/:165/:199, term loop :345. |
| `third_party/MediaCrawler/media_platform/douyin/product_search.py` | Official homepage/account probe, limited page-local state, HTTP search; classifiers :141/:184/:208, term loop :448. |
| `third_party/MediaCrawler/media_platform/xhs/product_search.py` | Domestic homepage, signed self-info/search requests; classifiers :224/:351/:389, term loop :609; token-bearing result opening is a separate operation at :669. |
| `third_party/MediaCrawler/tools/auth_worker.py` | Lazy borrowed session :135; five-adapter dispatch :270; callbacks/result mapping :593; single active command loop :681. |
| `third_party/MediaCrawler/tools/auth_worker_protocol.py` | Closed auth v2 command/result schema; commands :184–202, strict result pairs :43. |
| `third_party/MediaCrawler/tools/search_worker_protocol.py` | Separate search v1 command/result schema; DTOs :65–132, command decoder :273, event encoder :374. |
| `third_party/MediaCrawler/tools/cdp_browser.py` | Owned-page registry :81, release :87, cleanup :96, safe borrowed transport flags :415, borrowed cleanup :559. |
| `backend/src/longtian_api/services/browser_operations.py` | Shared atomic browser lease, exact-owner release, :10–38. |
| `backend/src/longtian_api/services/media_crawler_auth_worker.py` | Persistent client request lock :213; search :290; existing XHS open :364; event sequencing :623; strict search decoder :934. |
| `backend/src/longtian_api/services/search_runs.py` | Externally owned attempt execution :329; progress/item persistence :393; terminal outcome projection :453. |
| `backend/src/longtian_api/services/search_batches.py` | Restore lease :134; explicit continue :238; cancel :272; serial runner and retained pause lease :320. |
| `backend/src/longtian_api/repositories/search_batches.py` | Startup repair :101; full-snapshot attempt creation :210; current pause decision :300; continue :400. |
| `backend/src/longtian_api/repositories/search_runs.py` | Active-run repair :118; content upsert/provenance :230/:296. |
| `backend/src/longtian_api/main.py` | Startup initialization ordering :60–84 and shutdown ordering :92–96. |

Related specs read: `.trellis/spec/backend/{product-search-guidelines,platform-connection-guidelines,batch-search-guidelines,browser-search-adapter-guidelines,auth-state-guidelines,error-handling}.md`, backend index/quality/logging guides, `.trellis/spec/guides/{index,cross-layer-thinking-guide,code-reuse-thinking-guide}.md`, and `.trellis/workflow.md`.

Important scope distinction: the generic visible-search spec describes fresh contexts; the product-search/platform-connection specs explicitly authorize this persistent worker to borrow the existing default Chrome context. Preserve the product exception. The old batch spec intentionally advances after ordinary failures and on restart; this task changes that contract, not a claim that the old implementation violated its original requirements. Quality/logging guideline files are placeholders; the substantive privacy contract is in `error-handling.md` and the feature specs.

### 2. Current evidence: retained page is not proof of a visible CAPTCHA

- All five adapters call `close_owned_pages()` before creating one new registered page. Current finalizers preserve only login/challenge outcomes; normal completion, ordinary failures, uncaught exceptions and cancellation close the task page. Anchors: Toutiao :47/:93; Weibo :291/:357; Kuaishou :312/:389; Douyin :394/:491; XHS :559/:661.
- XHS navigates only to `https://www.xiaohongshu.com` before search (`xhs/product_search.py:566`), checks a coarse page challenge indicator (:577), proves login via signed self-info (:604), then makes signed HTTP search requests (:617). HTTP 461/471 and challenge business messages become `manual_challenge_required` (:358/:404), **without navigating the visible homepage to a challenge URL**.
- The same basic limitation applies to Weibo/Kuaishou/Douyin HTTP response classifiers. A response `Location` classified as login/challenge is not a browser navigation; these clients set `follow_redirects=False` (Weibo :317; Kuaishou :341; Douyin :445; XHS :601).
- Even a page-derived signal must be worded carefully. XHS's `_has_visible_challenge` includes a body-text phrase (:67–84); Toutiao's `challenge` includes block/risk/frequency text (`toutiao/client.py:29`). These are conservative stop signals, not proof that an actionable CAPTCHA widget exists.
- Therefore keep public run outcomes, evidence source and page-opening outcome separate. “已打开官方页面” may follow a successful show command. It must never mean “验证已出现”, “验证成功”, “登录成功” or “可以继续采集”. Page refresh, missing challenge UI or elapsed time must not advance the batch.

### 3. Minimal manual-page command: show or close, never authenticate/search

Recommended design proposal (new, not existing behavior): extend the **search** IPC, leaving auth v2 untouched. Because term completion/diagnostics change mandatory sequencing, use a coordinated search-protocol version bump rather than accepting unknown fields or silently falling back to the old protocol. Update both the worker schema and backend decoder in the same release; an incompatible worker fails closed.

One finite command family is enough:

```text
command: manual_page
fields: version, type="command", command, action="show"|"close",
        request_id=<fresh canonical UUID4>, platform=<exact five-platform literal>
event: manual_page
fields: version, type="event", event, action, request_id, platform, outcome
```

No URL, Cookie, token, term, HTML, selector, JavaScript, profile path, free-text reason or user-selected tab ID is accepted or emitted. The no-body product endpoint resolves current paused batch/item/latest attempt from storage and supplies platform server-side. A minimal wire command need not duplicate durable batch IDs: the backend verifies the still-current pause under the existing batch lease; worker-local retained-page metadata records the failed request, platform and worker generation. Never select a page merely because its URL resembles a platform. Discard stale retained-page metadata when a new search begins or the session generation changes.

Exact proposed terminal outcomes:

| Action | Allowed outcomes | Meaning |
| --- | --- | --- |
| `show` | `opened_existing`, `opened_homepage`, `browser_unavailable`, `navigation_failed`, `internal_error`, `cancelled` | The two opened outcomes prove only tab activation/one bounded official-page navigation. No auth/verification claim. |
| `close` | `closed`, `not_present`, `browser_unavailable`, `internal_error`, `cancelled` | `not_present` means no owned retained capability exists; `browser_unavailable` does not claim a disconnected tab was physically closed. |

Keep exact UUID/platform/action correlation, duplicate-key rejection, bounds, constant-only errors and one terminal event. Public UI may merge the two opened outcomes into the same concise message while using `opened_homepage` for optional truthful fallback guidance. Cancellation must have an explicit allowed terminal, unlike XHS open-result's existing recycle-on-cancel workaround.

`show` algorithm:

1. Under the batch service lock, validate paused state, current item/latest-attempt identity, current lease and absence of a runner/other manual action. Store a bounded active manual task and capture the pause identity. Do not hold that lock across a long browser await, so Cancel can still interrupt.
2. Under the worker's existing request lock/single-active-command loop, lazily reuse/reconnect only the approved borrowed Chrome session. The existing `_ensure_connected` safety options apply (`auth_worker.py:190–205`). `show` is an explicit user action; GET/poll/startup must not connect.
3. If the current failure's registered page is live and on an exact trusted platform origin, call `Page.bring_to_front()` only. Do not navigate, reload, click login, poll account state, inspect security controls or repeat the failed request. Check the URL locally before activation and recheck after, without retaining the URL.
4. If there is no usable owned handle, discard a confirmed-closed handle or narrowly close the still-registered unusable page before replacement; never navigate/reacquire an unregistered tab. Create/register exactly one new page, navigate **once** to the fixed official homepage listed below, validate the final origin and activate it. A navigational timeout/error is not success unless a deliberately documented existing platform-specific tolerance is used; do not add automatic refresh/retry. An unsafe redirect cannot return an opened outcome. No content collection/HTTP client runs.
5. Retain the owned page while paused. A repeat Show reuses that same page. Do not transfer it using `release_owned_page()` merely to keep it visible: that unregisters ownership and makes later cleanup/reuse impossible.
6. On return, revalidate the captured pause identity before projecting the result. Late responses cannot reopen, resume or mutate a skipped/cancelled/replaced item.

`close` algorithm:

- Close only the retained registered page for this paused operation; add a narrow public manager accessor/targeted close helper instead of reaching into `_owned_pages` or scanning `browser_context.pages`.
- If no worker/transport/owned capability exists, return `not_present` without launching a worker, opening Chrome settings, reconnecting, navigating or running an account probe.
- When a live retained page exists, await bounded cleanup. Preserve the difference between confirmed `closed` and transport loss. If cleanup/protocol cancellation cannot be acknowledged, recycle only the owned worker process as the existing lifecycle does; never terminate Chrome or claim that an orphan tab was closed.

Bound the full show/close operation, e.g. reuse the existing 45-second user-visible open-operation budget (`search_runs.py:118`) and existing 3-second correlated cancel grace (`media_crawler_auth_worker.py:197`), then owned-worker recycle. Add the new request kind to worker active-command/cancel/shutdown paths and the backend request union, not just to the parser. Existing insertion sites are `auth_worker.py:450/:593/:747/:833` and `media_crawler_auth_worker.py:166/:623/:934`.

Do **not** implement this by calling existing `check`, `search`, `open_result`, a platform's `authenticate_with_context`, or a generic login helper. Auth check runs online probes/manual waits and closes task-owned pages (e.g. XHS `core.py:214–278`). XHS open-result performs self-info plus a first-page search and constructs a transient signed destination (`xhs/product_search.py:669`, test `test_xhs_product_search.py:953–972`). Both do more than show a treatment page and would violate explicit-retry semantics.

### 4. Official fallback entries already present in code

| Platform | Minimal fallback | Existing evidence / limitation |
| --- | --- | --- |
| Toutiao | `https://www.toutiao.com` | `config/toutiao_config.py:9`. Public search entry is separately defined at :10 and constructed with encoded keyword by `toutiao/client.py:180`. Reuse the current failed search tab when available; the minimal fallback does not repeat that search. |
| Weibo | `https://m.weibo.cn` | `weibo/product_search.py:31/:297`. An explicit fixed official login entry also exists: `https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog`, `weibo/login.py:58/:97`. Homepage fallback is sufficient; do not invoke the whole login flow. |
| Kuaishou | `https://www.kuaishou.com?isHome=1` | Exact product navigation at `kuaishou/product_search.py:319`. Showing it does not require installing the search signer. |
| Douyin | `https://www.douyin.com` | `douyin/product_search.py:34/:400`. A public `/search/{term}?type=general` referer exists at :354, but this is not a currently validated recovery navigation contract. Homepage is the minimal fallback. |
| Xiaohongshu | `https://www.xiaohongshu.com` | `xhs/product_search.py:55/:566` and borrowed auth `xhs/core.py:222`. Existing visible-login code knows a homepage login entry (`xhs/login.py:282–301`), not a fixed CAPTCHA URL. No XHS public search-result URL template was found in the inspected platform code. Do not invent `/search_result`, a CAPTCHA URL or an API redirect destination. The user can use the normal homepage search/login UI manually. |

Fallback construction uses fixed code-owned HTTPS URLs. Reuse validation should separately allow only explicit existing official origins appropriate to the platform, reject credentials and non-default ports, and never promote broad domain suffix matching into trust. Candidate already-recognized ancillary origins: Weibo `passport.weibo.com`, `security.weibo.com`, `verify.weibo.com` (`weibo/product_search.py:156`); Kuaishou `id.kuaishou.com`, `passport.kuaishou.com` (:151); Douyin `passport.douyin.com`, `sso.douyin.com`, `verify.snssdk.com`, `captcha.snssdk.com` (:162). Treat these as a reviewed list of **existing-page origins**, not URLs to construct or visit to trigger security validation. Toutiao's exact configured origins are `www.toutiao.com` and `so.toutiao.com`; XHS uses the domestic homepage. Unknown XHS subdomains recognized by its current suffix classifier (:245) are not an adequate exact recovery allowlist.

For browser connection failures, retain the current loopback/manual-approval behavior; the settings URL is already `chrome://inspect/#remote-debugging` (`cdp_browser.py:37/:235`). That is connection guidance, not an arbitrary page target and not a platform login failure. The show operation may reconnect on the explicit click; close/GET/startup must not.

### 5. Preserve failure pages without automatic navigation

Feasible narrow change: preserve the single registered **trusted, usable official page** after every non-success/non-cancel search outcome, not just login/challenge. Thus a Toutiao `structure_changed`, API block/rate-limit or client/normalization failure can hand back the already-open page. This avoids new navigation before the user handles the problem whenever such a page exists.

- Change all five finalizers listed in §2 and cover currently uncaught exceptions as well as typed `_SearchOutcomeError` returns. A typed status-only change misses `httpx.ReadTimeout`, browser errors and item-sink errors. Preserve the actual failure category; do not recategorize failures as manual challenges merely to keep a page.
- Keep normal successful completion and cancellation cleanup unchanged. Preserve only page identity owned by the failing operation, not every page in the borrowed context.
- Only inspect URL/liveness needed for ownership and origin safety. Retaining a rate-limited official page is passive; do not refresh it, run background probes or repeat requests.
- A failure before `new_page`, failed navigation leaving `about:blank`, unsafe redirect, user-closed tab, browser disconnection, worker termination or backend restart may leave **no reusable page**. The explicit Show fallback remains necessary. Do not claim all failures can keep a page.
- CDP manager cleanup clears its registry before trying to close pages (`cdp_browser.py:99–108`). A forced worker exit or transport loss can leave an orphan tab, and a new process cannot safely reacquire ownership by URL. Treat such a tab as pre-existing: leave it alone and open a new task-owned fallback only after an explicit Show.
- Do not use `release_owned_page()` for this lifecycle. Its existing use is permanent result-tab handoff (`xhs/product_search.py:796`); recovery needs the opposite: keep ownership until Continue/Skip/Cancel/shutdown.

### 6. Phase-specific failure classifiers and safe diagnostics

Currently the public search result contains only `outcome` (`search_worker_protocol.py:118`, backend :156). Uncaught worker exceptions collapse to `internal_error` (`auth_worker.py:624`), HTTP read timeouts are not generally the service's `timed_out`, and search browser disconnection projects to public `browser_unavailable` (`search_runs.py:454`). A recovery UI cannot reconstruct missing evidence from the outcome alone.

Add an exact, finite diagnostic record at the layer that knows the failure. Suggested fields are `stage`, `reason`, `evidence_source`, and nullable `term_position`; persist only those codes with attempt identity/time. With the slice design in §8, child positions remain command-local and the one service mapping converts them to original positions before persistence. No raw exception, response message/body, URL, term, signature, header, page text or credential enters diagnostics. The UI obtains the display term from the stored snapshot using the position.

| Phase / local evidence | Truthful classification and actionable limits |
| --- | --- |
| Worker launch / CDP attach | `browser_unavailable`; distinguish safe reasons such as `browser_not_ready` and `browser_disconnected`. No invented failed term before term-start. `_ensure_connected` wraps errors at `auth_worker.py:212–216`. |
| Initial official-page navigation | `page_navigation_failed` or `untrusted_page`; inspect typed exception/origin, not exception text. XHS retains only its existing bounded homepage-timeout tolerance (:571), followed by origin checks. Do not convert navigation trouble into login-required. |
| Pre-search account probe | XHS strict boolean false (:484) and Kuaishou result 0 (:223) prove login-required; malformed probe shapes are structure errors. Douyin `disconnected` (:414) differs from inconclusive plus no visible stop signal (:425). Weibo has no separate product preflight login probe. Toutiao product search has no login prerequisite at all. |
| Security indication | Preserve `manual_challenge_required`, with source `page_marker`, `api_http_status`, or `api_business_response`; none alone claims an actionable CAPTCHA. XHS HTTP 461/471 (:358), Douyin/Kuaishou 418/432, Weibo error/status 418/432, and their known message classes are existing evidence. Do not probe again just to refine the label. |
| Platform restriction | HTTP 403/429 or known blocked/rate-limit result → `platform_blocked_or_rate_limited`; retain page passively, give wait/skip/cancel guidance, never promise re-login repairs it. Current XHS blocked/frequency checks precede challenge-message checks (:399); preserve tested precedence rather than flattening categories. |
| Search client preparation | Signer failure or missing required page state is not login failure. Kuaishou signer errors currently map to structure (:250); XHS signer failure to internal (:430); Douyin missing/invalid `xmst` to structure (:427). Use a safe reason such as `client_preparation_failed` while preserving terminal category. |
| Search request transport | Typed HTTP/browser timeout or connection error → safe `search_transport_failed` / `request_timed_out` diagnostic and documented terminal mapping. Current `httpx.ReadTimeout` propagates and becomes internal; the existing propagation fixture is `test_xhs_product_search.py:829`. Do not silently claim it was a CAPTCHA or account failure. |
| Response/DOM/normalization | `structure_changed` with finite reasons such as `response_shape_unrecognized`, `results_not_recognized`, `result_normalization_failed`. Toutiao pending DOM has a fixed 21-read budget (:194–257), not unbounded retry. No login advice as the primary remedy. |
| IPC / storage / backend interruption | Backend-owned `worker_protocol_failed`, `storage_write_failed`, `operation_timed_out`, `interrupted_on_restart` codes; do not ask the child to diagnose backend persistence. Preserve committed observations/completions and stop scheduling. |

Track diagnostic stage explicitly in adapter control flow rather than infer it from a generic result after return. Keep reason/stage combinations closed and tested; failure before any term must have null failed-term position and resume from the first unconfirmed term. Record historical evidence time; a saved DOM indication is not a fresh claim about the current page. Page show must not update readiness or the attempt's failure reason to “verified”.

### 7. Term progress and safe completion-hook insertion sites

Every adapter uses `ProgressSink = Callable[[int, int], None]` and `enumerate(terms)`, and emits progress **before** the per-term request. Item callbacks are awaited but zero-result terms emit no items. The worker encodes this explicitly as `phase="term_started"` (`search_worker_protocol.py:389`). Current backend success validation only requires the last term to have started and item-count consistency (`media_crawler_auth_worker.py:711–717`); it is not a completion ledger.

| Adapter | Start event | Completion hook placement | Empty / bounded completion meaning |
| --- | --- | --- | --- |
| Toutiao | `product_search.py:60` | After the complete `for content` loop ending :87; before the next term. | Successful recognized empty `client.search` completes; failed candidate normalization at :68 does not. One first page is the configured unit. |
| Weibo | :321 | At term-loop indentation after bounded page loop ends :351, before final return :352. | Empty recognized mblogs, short page, hard limit or configured max-page budget completes the unit. No completion after a partial-page parse/request failure. |
| Kuaishou | :346 | After bounded page loop :383, before final return :384. | Recognized empty feeds, short page, `no_more`, hard limit or page budget completes. Signer/probe failure is not completion. |
| Douyin | :449 | After the entire page loop including continuation-ID guard :484–485, before :486. | Short/empty page or limit/budget completes; missing required continuation ID remains failure, even after safe items were emitted. |
| XHS | :610 | **After** the `term_emitted == 0 and last_has_more` guard at :654–655, before :656. | Coherently exhausted auxiliary/valid untitled-only cards can complete empty. Zero persistable items with `has_more=True` at budget exhaustion must not be checkpointed. |

“Completed” means completed the requested bounded collection unit, not exhaustive coverage of the platform. Preserve existing page caps, sort and per-term hard limits; this task adds neither pagination nor automatic retry.

Recommended event addition: `term_completed` for the current local position/count. Emit exactly once only after all successful item emissions and all post-loop checks. Add a corresponding callback through adapter → `WorkerBrowserSession.search` (:273) → `PersistentAuthWorker._execute_search` (:593) → strict backend decoder/event reducer (:674) → repository. An awaited adapter completion hook is a clear interface; its current worker sink only writes a frame, so do not describe it as a synchronous database acknowledgement.

Backend durability rule: its event reader already awaits each item's persistence callback (:702). Commit `term_completed` only after all preceding item callbacks have committed; require the current term to be started, reject duplicate/mismatched completion and reject items after completion. Require every term completed before a successful terminal result. If producer/consumer/process crashes before checkpoint commit, that term remains unconfirmed and is retried conservatively; already saved partial results stay deduplicated. Never derive completion from result count, latest content, a started event or a later term's presence.

### 8. List slicing can be safe only with an explicit positional mapping

Passing `terms[start:]` to existing adapters reduces requests correctly but reindexes callbacks to `0..remaining-1`; persisting those positions directly corrupts provenance and progress. All five `enumerate` loops and backend decoder (:681)/repository callbacks (`search_runs.py:401–411`) currently assume zero-based positions in the supplied command.

Minimal proposal: keep each attempt's full immutable original term snapshot (already copied at `backend/src/longtian_api/repositories/search_batches.py:230–264`), persist its resume offset, send only `record.terms[start:]`, and map every started/item/completed/diagnostic callback in **one** service boundary: `original_position = start + local_position`. Keep worker `term_count` equal to the actual slice length; the product reports original position/count from the stored snapshot. Do not also offset in adapters or map by term string. Repeated term values must remain positional. A new protocol carrying explicit original positions is also possible, but changes more validators; do not mix the two models.

- Before worker dispatch, validate `0 <= start < original_count`; a completely confirmed prefix equal to the count is a no-work case, not a valid empty search command. It needs explicit orchestration/reconciliation without fabricating a new successful search or rewriting the failed historical attempt.
- Restore from committed completion markers, not `current_term_position`. Preflight failure resumes at the same unconfirmed position even when no new term-start was emitted.
- For legacy data without markers, do not infer zero-result completion from absence of observations. Use a documented conservative fallback and display that precise older progress is unavailable. Successful historical whole-platform attempts can remain completed; uncertain failed attempts cannot have invented per-term completion.
- Retrying a partial failed term creates a new immutable attempt. Global content upsert already deduplicates platform/content IDs (`search_runs` repository :230–294), but item/batch result totals must use a distinct union across attempts rather than summing attempt counts. The latest attempt alone omits completed-prefix observations. Preserve attempt-level new/repeated semantics and old provenance.

### 9. Lifecycle and race contract

| Transition | Required behavior / implementation anchors |
| --- | --- |
| Any platform attempt fails | Persist actual terminal failure and committed checkpoints; mark item/batch paused atomically; keep batch lease; settle worker task; retain usable official page; start no later item. Change repository `finish_item` :313–318; runner already retains lease when paused (:355–358). |
| User clicks Show | Run only the bounded manual-page command under the existing `search_batch` owner. Do not claim a second top-level browser operation: `BrowserOperationCoordinator.try_claim` rejects any existing owner (:24). Store active manual task separately from the runner. |
| User manually operates Chrome | Product remains paused and performs no browser reads/navigation/probes/search. Polling product DB is allowed, but cannot trigger a browser command. |
| Continue | Require still-current pause and no active manual command; concurrent duplicate Continue/Show/Skip returns a safe conflict. Close the retained page through the worker, settle cleanup, then atomically queue a new immutable attempt at the first unconfirmed term and dispatch under the retained batch lease. Fresh normal adapter preflight occurs only now. Any repeated failure pauses again. |
| Skip | Require the current paused item; close/settle retained page, durably mark a real `skipped` item (not success), preserve attempts/results, and only then dispatch the next queued platform under the same lease. If no next item exists, finalize with a non-success aggregate and release lease. |
| Cancel | Win durably against Continue/Skip; interrupt/await any active runner or manual-page command, perform bounded owned-page cleanup, then release the exact lease once. Never hold the service lock while awaiting a task whose finalizer needs it. Existing cancel waits outside lock (:272–295); extend it to manual actions. |
| Paused worker/browser disconnect | Invalidate only ephemeral page/transport capability; preserve durable paused item, diagnostics and checkpoint. Do not reconnect automatically. Later explicit Show may reconnect/open fallback; explicit Continue may run normal preflight. |
| Backend shutdown/restart | Preserve paused state and completion ledger. Graceful shutdown may close registered task pages and stop Playwright transport, not user Chrome. New startup restores only the lease/projection, no browser/runner work. Reconcile interrupted running/queued batches to a manual pause, not the old next-platform auto-advance. |

Current pitfalls to cover:

1. Paused Cancel currently has no running worker operation to cancel and no page-close command (`search_batches.py:284`); releasing the coordinator alone leaves the retained page registered until another operation/shutdown. Explicit cleanup must be added.
2. `SearchBatchService.resume_after_startup` currently starts every non-paused active batch (:150). Repository startup turns running items into failed (:101), and the current restart test explicitly expects automatic Weibo execution (`backend/tests/test_search_batches.py:530–559`). Replace that expectation for the new no-automatic-retry policy. Startup initializes run repair before batch repair (`main.py:60/:72`).
3. Worker `_release_transport` and CDP borrowed cleanup close only registered pages and stop Playwright (`auth_worker.py:402–417`, `cdp_browser.py:567–580`). Retained page handles cannot survive process restart. Do not persist/reacquire a URL or Chrome tab identifier to fake ownership continuity.
4. The worker command loop currently rejects cancel while idle (`auth_worker.py:855`), so sending the old finished search's cancel cannot clean up a paused page. Add the new command and its request lifecycle deliberately.
5. Backend session-event ordering currently uses only auth `previous_phase` (`media_crawler_auth_worker.py:653`); search progress does not set that field (:685). When introducing manual-page/completion progress, use operation-kind-aware started/progress state and add ordering tests rather than assume the auth guard covers these kinds.
6. Shutdown currently releases the batch owner before shared worker shutdown (`main.py:92–96`). Public shutdown admission must reject late recovery calls; no late manual callback may create a new task after cancellation or owner release. Storage/cleanup failures must stop scheduling and remain honestly recoverable, never silently advance.

### 10. Tests to add or update (not executed in this research)

- Five-adapter event-order fixtures: successful non-empty and zero-result terms emit one started/completed pair; failure after partial items does not complete that term; no future term starts; cancellation never emits completion for interrupted work. Cover each insertion site's post-loop guard, especially XHS `has_more` and Douyin missing continuation ID.
- Resume fixture: six confirmed terms plus a partial seventh, including one zero-result term; Continue requests only the seventh onward. Assert original global positions, repeated term values, full immutable snapshots, old observations, distinct item totals and no duplicate global content. Cover final completion frame committed before process failure/no-work continuation.
- Strict IPC fixtures: new command/event/phase closed shapes, allowed action-outcome pairs, matching UUID/platform/action, wrong/old protocol version, unknown fields, duplicate keys, bool-as-int, out-of-order starts/items/completions, duplicate terminal/completion, late old-generation events, cancellation and disconnect ordering. Existing locations: `third_party/MediaCrawler/tests/test_product_search.py:89/:441/:793`, `backend/tests/test_search_worker_client.py:389/:886`.
- Owned-page fixtures for all failure classes: keep one trusted registered failed page; Show activates it with **zero** navigation, search, auth-probe, HTTP, signer, Cookie and security-control calls. Repeat Show creates no extra tab. Sentinel pre-existing tabs/context/browser must never be closed or selected.
- Fallback fixtures: closed/missing/stale-generation/unsafe-origin retained handle creates at most one registered official-homepage tab; validate final origin, credentials, ports, lookalike domains and redirects; failed navigation reports failure, not opened/verified. XHS API challenge with homepage having no challenge UI must say only API verification requested / official page opened. No CAPTCHA reachability assertion is valid without later explicit live evidence.
- Page-close fixtures: close is idempotent, performs no reconnect/worker launch when absent, cancels bounded show safely, and never closes an unregistered result tab. Reuse `test_cdp_browser.py:209/:239` and XHS result handoff `test_xhs_product_search.py:927` to ensure recovery retention does not regress permanent result-tab handoff.
- Service concurrency fixtures: batch paused lease rejects standalone search/account check/result opening; manual Show uses that lease. Cover Show/Continue, Show/Skip, Show/Cancel, duplicate requests, late completion, cleanup failure, worker crash and cancellation before runner start. No later platform request occurs before explicit Continue/Skip.
- Restart fixtures: GET/startup/refresh reconnects nothing; all nonterminal interrupted batches reconcile to paused, hold the lease and preserve committed progress. Retained-page capability is absent after restart, Show reopens safely and Continue retries only unconfirmed work. Replace old auto-advance test :530 and generalize challenge-only pause test :402.
- Secret sentinels: page URL/query, response body, request term, Cookie, signer/token, raw exception and stderr never enter diagnostics/API/logs/evidence. Tests may assert absence without retaining actual account material.

## External References / Versions

No web sources or live platform evidence were used. Fallback entries above are derived only from repository code; their present CAPTCHA reachability is **unproven**.

Dependency versions recorded from the checked-in lockfile: Playwright **1.61.0** (`third_party/MediaCrawler/uv.lock:1261`), httpx **0.28.1** (:592), xhshow **0.2.0** (:2003). These are repository versions, not a claim about the newest releases. Local installed Playwright source confirms `Page.bring_to_front()` activates the tab (`third_party/MediaCrawler/.venv/lib/python3.11/site-packages/playwright/async_api/_generated.py:10344`), `Page.is_closed()` (:10821), and `BrowserContext.new_page()` (:14353); this is supporting local API evidence, not a file to edit.

## Caveats / Not Found

- The task's design/implementation artifacts were absent when research began; parent owns assembling them. No `implement.jsonl` or `check.jsonl` was loaded.
- There is no existing generic manual-page command, per-term completion event or durable completion marker. The commands, diagnostics and lifecycle above are proposals, not implemented capabilities.
- An API-requested security check does not identify a visible treatment page. No guaranteed XHS CAPTCHA/search URL was found; official homepage plus user-driven normal login/search is the supported fallback proposal. Never automatically bypass, solve, refresh or provoke a security challenge.
- Preserving an official task-created page is feasible for ordinary failures but cannot overcome a missing/closed page, unsafe navigation or lost transport/ownership. A successful Show proves only page opening, never login/verification/search readiness.
- No tests, live failure reproduction or browser verification were performed. Existing test names/fixtures are source evidence, not newly passed validation. Later execution follows the user-approved Centaurus workflow; no such execution is authorized by this planning research.
