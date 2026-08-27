# Research: Toutiao combined-query source and regression map

- Query: Locate the smallest evidenced Toutiao DOM/client regression seams, common lifecycle/frame protections, and maintained remote test commands for the combined-query repair.
- Scope: Local source/spec inspection only; no source changes, tests, browser, platform/provider requests, runtime data, or Git operations by this researcher.
- Date: 2026-08-27
- Active task: `.trellis/tasks/08-27-toutiao-combined-search-fix/prd.md`; the earlier multimodal task is not resumed.

## Findings

### Evidence boundary

- Source and existing fixtures establish several distinct paths to the public `structure_changed` outcome; they do not reproduce historical run 34 (`龙田街道 投诉`) or establish its cause.
- Main-agent observations supplied during this research, not independently performed here: one mature same-query page had exactly one visible main container, no challenge/login/empty marker, and 31 visible anchors; seven of nine title cards were external and two had double-wrapped official `/a{id}/` targets. The exact existing snapshot script returned two valid candidates. Thus this observation does **not** demonstrate a selector/path defect or external-only empty result.
- Main also reported old-code product run 43 completed with two results in 2.69 seconds. Historical run 34 remains unexplained. A synthetic delayed-render failure can justify bounded readiness hardening, but must not be described as proof of run 34's cause.

### Files and current call boundaries

Paths in this subsection use `MC = third_party/MediaCrawler`.

| File / anchor | Proven current responsibility |
| --- | --- |
| `MC/media_platform/toutiao/client.py:25` | `TOUTIAO_DOM_SNAPSHOT_SCRIPT`: visible `.s-result-list` discovery (`:41`), official URL identity and at-most-two jump unwraps (`:43`), main-only anchor scan (`:86`), human-title scoring (`:95`), bounded same-identity ancestor metadata (`:108`), at most 100 candidates (`:135`). |
| `MC/media_platform/toutiao/client.py:177` | `ToutiaoWebClient.search`: first page only; `urlencode({'keyword': keyword})` preserves a combined string as one query value (`:180`); one `goto` (`:181`), origin/status checks, one 1,500 ms wait and one evaluation (`:194`), then state classification. No keyword splitting here. |
| `MC/media_platform/toutiao/client.py:200` | Non-dict, invalid/non-unique main count, invalid candidates, or no recognized result/empty state are separate structure errors (`:200`, `:213`, `:219`, `:232`); challenge/login precede main classification (`:204`, `:208`). |
| `MC/media_platform/toutiao/help.py:80` | At-most-two official jump unwraps; canonical safe target validation (`:103`), stable content classification (`:155`), required nonempty title/keyword and normalized optional metadata (`:166`), ordered per-term identity deduplication (`:199`). |
| `MC/media_platform/toutiao/product_search.py:31` | One task-owned page in borrowed context; bounded 1–20 terms and limit 1–50 (`:42`), sequential client→normalizer (`:59`), nonempty snapshots becoming zero contents is structure failure (`:68`), output cap (`:72`). |
| `MC/media_platform/toutiao/product_search.py:93` | Maps login/challenge/block/structure to existing constant outcomes; preserves the task page only for login/challenge, otherwise closes registered owned pages in `finally` (`:103`). |
| `backend/src/longtian_api/services/search_runs.py:117` | Whole-search timeout defaults to 180 seconds and wraps the worker call (`:425`); timeout/cancel project to existing terminal states (`:435`). This is not a per-DOM-read budget. |

### Existing fixtures and the smallest seams

All entries below describe test source, not test results from this research. Test paths in the table are under `MC/tests/`.

| Existing fixture / anchor | What it covers; remaining seam |
| --- | --- |
| `test_toutiao_parser.py:39`, `:49`, `:75` | `make_page` provides mocked `goto`, wait and evaluate. Ready-state test checks the baseline query URL and exactly one 1,500 ms wait. Smallest place for `evaluate.side_effect=[pending, ready]`, combined-query round-trip encoding, evaluation/wait counts, and terminal-state ordering. |
| `test_toutiao_parser.py:79`, `:101`, `:109`, `:140` | Immediate explicit empty, login/challenge, HTTP 403/429, and static malformed/unknown states. No pending→ready or pending→terminal sequence. Login/challenge client assertion uses their common blocked superclass; product tests assert distinct outcomes. |
| `test_toutiao_parser.py:160`, `:213` | Foreign URL before/after evaluation rejected; navigation abort propagates with exactly one navigation and no DOM fallback. Extend to redirects during any additional wait/read, without weakening these tests. |
| `test_toutiao_parser.py:228`, `:318` | Count 0 or 2 rejected; offline missing-main/sidebar-only and ambiguous-two-main fixtures. Existing mocked count-0 fixture also has `empty=True`, an inconsistent state that must not become a successful empty result. |
| `test_toutiao_parser.py:251`, `:364` | Offline HTML verifies main-only results, human title over cover/duration/detail anchors, same-card snippets, unsafe-link exclusion, and main-scoped empty instead of sidebar empty. These are static DOM snapshots; no delayed mutation/navigation-readiness fixture exists. |
| `test_toutiao_parser.py:393` | Source guard excludes private response listeners/requests, broad document anchor scan and raw outerHTML; checks bounded-card extraction remains. |
| `test_toutiao_url.py:33`, `:51`, `:58`, `:79`, `:115`, `:145`, `:195` | One/two jump wrappers, over-deep/ambiguous wrappers, known IDs, unsafe URL rejection, stable tracking-independent trending identity, invalid/drop/dedup ordering. Reuse normalization seams only if a captured safe target demonstrates a normalization defect. |
| `test_product_search.py:255`, `:292`, `:344` | Borrowed-context/sentinel-tab preservation, per-term re-emission of one identity, canonical tracking cleanup; all candidates invalid→structure; distinct login/challenge outcomes and task-page preservation. A client readiness change does not require worker/item schema changes. |
| `test_toutiao_crawler.py:107`, `:149` | Standalone crawler first-page serial hard-limit/dedup and navigation-error propagation. Regression coverage only; do not route product work through generic crawler startup/loops. |

No existing fixture demonstrates a combined-query-specific parser bug. The clear source-level weakness is a single snapshot after a fixed delay; the repository currently lacks the synthetic failing timing fixture needed to prove that weakness causes a false failure for delayed content.

### Assessment of the main agent's proposed bounded readiness hardening

- Proposed narrow seam: change only client readiness handling after the existing initial 1,500 ms wait, retaining the exact DOM extraction and normalizer unless separate evidence requires changes. Reread at most 20 times at 250 ms intervals for a **well-formed** pending state: count 0 with empty candidates/no explicit empty, or count 1 with empty candidates/no explicit empty. Count 0 is absence, not proof of loading; exhaustion must still report unknown structure.
- Check challenge/login and trusted origin on every attempt; validate origin before **and** after each evaluation because it may change during the interval. Initial HTTP 403/429 still stops before waits; do not add response interception, new HTTP requests, navigation retries or browser fallback.
- Malformed states (including missing/wrong-typed candidate list), ambiguous count >1, invalid count types and contradictory count-0 explicit-empty states must stay terminal. Do not turn arbitrary `structure_changed` exceptions into retryable states; normalization loss remains terminal at product level.
- Immediately return recognized results or main-scoped explicit empty; do not wait to accumulate a larger result set. Keep result caps, stable identity and final unknown classification unchanged.
- At most 21 evaluations and 20 extra intervals give 6.5 seconds of **nominal waits**, not a 6.5-second wall-clock deadline: navigation allows 30 seconds and evaluations also take time. Do not expand the existing whole-search timeout. Multiple sequential terms multiply the cost.
- Cancellation must propagate during both waits and evaluation, reach `product_search.py:103` cleanup and remain a correlated cancelled terminal event. A finite polling loop alone does not prove prompt cancellation or bounded evaluation latency.
- Minimum new tests: pending count 0→ready, count 1/empty candidates→ready, pending→explicit empty, exhaustion with exact bounds/one navigation, pending→challenge/login/malformed/ambiguous/foreign origin stopping immediately, and cancellation during extra wait/evaluate with only owned-page cleanup. Preserve immediate-ready's one-wait assertion.
- Add one fully offline routed synthetic HTML fixture delayed beyond the initial snapshot, with a deterministic gate/handshake where practical to avoid timing flakiness. Block all non-fixture requests; use a fresh headless test browser, no profiles/CDP/user tabs. Demonstrate the old one-snapshot path fails on the same fixture and the bounded path passes; also retain a never-ready fixture. This is a synthetic readiness regression, not a captured run-34 reproduction.

### Common child-frame, lifecycle and API guards

- `MC/tests/test_product_search.py:89` validates closed/bounded commands; `:441` correlated progress/item/result in a persistent worker; `:529` safe item URL/timestamp serialization; `:793` matching cancel; `:815` cancel wins same-turn completion race.
- `MC/tests/test_auth_worker_protocol.py:68`, `:137`, `:142`, `:205`, `:228`: exact command shape, malformed/duplicate/unterminated/oversized frames, constant events and secret-sentinel exclusion.
- `MC/tests/test_auth_worker.py:123`, `:241`, `:266`, `:285`, `:309`, `:467`, `:501`: lazy reuse, idle/busy disconnect races, constant exception/shutdown handling, cancellation transport release and explicit-operation-only reconnection.
- `MC/tests/test_cdp_browser.py:92`, `:124`, `:209`, `:239`: persistent borrowing without new default context, no usable default context failure, registered-page-only cleanup, released-page handoff. Existing worker cancellation tests use a fake session, so they do not replace a new cancellation-during-Toutiao-read test.
- `backend/tests/test_search_worker_client.py:389`, `:682`, `:712`, `:733`, `:886`: safe correlated frames, cancellation, invalid URL/timestamp and inconsistent event sequences recycle the child.
- `backend/tests/test_search_runs.py:109`, `:410`, `:477`, `:867`, `:901`, `:1052`: durable identity/history, composed terms frozen, repeated result dedup, cancel/timeout/partial-result preservation. `:410` sends spaced composed strings intact to a **fake WB worker**, not through Toutiao DOM; it does not establish Toutiao live correctness.
- `backend/tests/test_search_batches.py:313`, `:402`, `:450`, `:530`: frozen composition, challenge pauses, cancellation and restart recovery. `backend/tests/test_platform_connections.py:649`, `:1022`, `:1056`, `:1126` protect malformed/raw frames, shutdown, stderr discard and inherited child pipes.

### Exact maintained test commands on Centaurus

Main verified remote root `/home/jonathanhu237/code/longtian-public-opinion-management` and the MediaCrawler `.venv`. Commands below run **on Centaurus**, after main's source-only sync. No remote command was executed by this researcher. Use the crawler's own environment, not backend Python; no SSH alias or new dependency installation is assumed.

Focused crawler regression:

```bash
cd /home/jonathanhu237/code/longtian-public-opinion-management/third_party/MediaCrawler
.venv/bin/python -m pytest -q -ra tests/test_toutiao_parser.py tests/test_toutiao_url.py tests/test_toutiao_crawler.py tests/test_product_search.py tests/test_auth_worker_protocol.py tests/test_auth_worker.py tests/test_cdp_browser.py
```

Required maintained crawler suite (explicit `tests`, not legacy `test`):

```bash
cd /home/jonathanhu237/code/longtian-public-opinion-management/third_party/MediaCrawler
.venv/bin/python -m pytest -q -ra tests
```

Affected backend regression plus normal quality checks, in its separate environment:

```bash
cd /home/jonathanhu237/code/longtian-public-opinion-management/backend
uv run --frozen python -m pytest -q -ra tests/test_search_worker_client.py tests/test_search_runs.py tests/test_search_batches.py tests/test_monitoring_rule_combinations.py tests/test_platform_connections.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q -ra tests
```

Do not use unrestricted crawler-root `pytest`: legacy `MC/test/test_mongodb_integration.py:33`, `MC/test/test_db_sync.py:141` and `MC/test/test_redis_cache.py` include real-service/integration work outside the maintained fixture suite.

Offline DOM tests currently skip without an executable detected by `MC/tools/browser_launcher.py:45` (`test_toutiao_parser.py:36`, `:247`). Linux detection uses fixed `/usr/bin`/`/snap/bin` browser paths (`browser_launcher.py:81`), not the Playwright browser cache. Keep `-ra`, report skips explicitly, and have main provision an approved remote test browser if needed; a green suite with skipped DOM fixtures does not prove the delayed-DOM acceptance gate.

### Related specs and external references

- `.trellis/spec/backend/browser-search-adapter-guidelines.md`: main-column extraction, bounded platform DOM, public navigation and ownership safety.
- `.trellis/spec/backend/product-search-guidelines.md:151`, `:213`, `:237`, `:262`, `:338`: persistent worker/single borrowed context, unique Toutiao main and truthful empty, strict bounded frames, page lifecycle and required tests.
- `.trellis/workflow.md` plus current PRD: evidence before fix; local edits/source-only Centaurus testing; independent review and honest live gates. No unrelated frontend, sorting, media or rule redesign.
- No external documentation was needed or fetched. Declared dependencies are `MC/pyproject.toml:7` Python >=3.11, `:24` Playwright >=1.61.0, `:38` pytest >=7.4.0, `:39` pytest-asyncio >=0.21.0; these are constraints, not measured remote versions. Root `README.md:62` documents backend pytest/ruff commands.

## Caveats / Not Found

- No historical failing DOM snapshot, early-state trace, or current combined-query failure fixture was inspected. No confirmed production root cause or implemented fix is claimed.
- Bounded rereads cannot distinguish permanent selector drift/external-only results from temporarily pending content; exhaustion must remain truthful `structure_changed`, not fabricated empty. Mature/live old-code success supports keeping selectors and URL normalization unchanged absent further evidence.
- Live acceptance, repeat identity reuse, database/history/rule cleanup and user-tab integrity belong to the main agent under the PRD's bounded authorization, not this research. Synthetic passing tests alone cannot close those gates.
