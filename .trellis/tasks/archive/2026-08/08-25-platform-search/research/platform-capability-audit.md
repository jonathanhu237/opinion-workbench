# Research: Five-platform keyword-search capability audit

- Query: Compare the real one-shot keyword-search readiness of Weibo, Douyin, Kuaishou, Xiaohongshu, and Toutiao, especially browser/auth reuse, process safety, output contracts, tests, and challenge behavior; recommend the smallest first end-to-end platform.
- Scope: internal
- Date: 2026-08-25

## Findings

### Recommendation

Implement **Toutiao as the first end-to-end search platform**, behind a persistent FastAPI-owned MediaCrawler worker, and defer the other four platforms until the product-level search protocol and persistence contract are proven.

Toutiao is the only current adapter with all of the following at once:

- a deliberately small, privacy-bounded result model (`content_id`, usable text, canonical URL, source term, discovery time) (`third_party/MediaCrawler/model/m_toutiao.py:12-35`);
- public visible-page DOM parsing rather than a signed/private search API (`third_party/MediaCrawler/media_platform/toutiao/client.py:21-79`);
- explicit distinctions among block/challenge, login wall, empty result, and structure drift (`third_party/MediaCrawler/media_platform/toutiao/client.py:82-120`);
- targeted crawler/parser/URL/store tests (`third_party/MediaCrawler/tests/test_toutiao_crawler.py:44-176`, `third_party/MediaCrawler/tests/test_toutiao_parser.py:43-170`, `third_party/MediaCrawler/tests/test_toutiao_url.py:33-151`, `third_party/MediaCrawler/tests/test_toutiao_store.py:57-161`);
- a recorded live search acceptance yielding 10 usable results (`.trellis/tasks/archive/2026-08/08-23-research-mediacrawler-toutiao-adapter/research/live-validation.md:11-19`, `.trellis/tasks/archive/2026-08/08-23-research-mediacrawler-toutiao-adapter/research/live-validation.md:45-50`).

The recommended expansion order after that is **Weibo, Kuaishou, Douyin, Xiaohongshu**. This is a risk/readiness order, not a claim that the later platforms cannot search.

| Platform | Current search mechanism | Useful output readiness | Main blocker before product use | Recommended order |
| --- | --- | --- | --- | --- |
| Toutiao | One public search navigation and bounded DOM parsing | Strongest: minimal typed model, canonical URL, explicit source term | Ordinary search currently ignores CDP and creates its own fresh context; it must gain a context-injected borrowed-browser path | 1 |
| Weibo | Mobile internal API with up to five retries | Good normalized note ID, content, URL, source term | Raw response/data logging, error-vs-empty ambiguity, and default full-text follow-up risk; force full-text off | 2 |
| Kuaishou | Signed private REST search with page-local signer and up to three rate-limit retries | Good title, URL, source term | Private contract, retry behavior, and ambiguous unsuccessful/empty outcomes | 3 |
| Douyin | Signed internal API using LocalStorage state | Usable URL/title/source term, but also media URLs | Context-wide stealth injection on borrowed context, weak post-login verification, and caught fetch errors can look like success | 4 |
| Xiaohongshu | Signed private API plus a detail request for every search result | Rich but over-broad | Logs search/detail payloads and persists `xsec_token` in fields/URLs; highest current privacy and challenge exposure | 5 |

Platform evidence: Weibo search and retry behavior are in `third_party/MediaCrawler/media_platform/weibo/core.py:241-295` and `third_party/MediaCrawler/media_platform/weibo/client.py:72-102`; its store mapping is in `third_party/MediaCrawler/store/weibo/__init__.py:70-107`. Kuaishou search and retry behavior are in `third_party/MediaCrawler/media_platform/kuaishou/core.py:244-303` and `third_party/MediaCrawler/media_platform/kuaishou/client.py:117-189`; its store mapping is in `third_party/MediaCrawler/store/kuaishou/__init__.py:55-79`. Douyin's borrowed-context stealth and search failure handling are in `third_party/MediaCrawler/media_platform/douyin/core.py:81-144`, `third_party/MediaCrawler/media_platform/douyin/core.py:214-268`, and `third_party/MediaCrawler/media_platform/douyin/core.py:445-489`; LocalStorage/signing and raw error construction are in `third_party/MediaCrawler/media_platform/douyin/client.py:71-135`. Xiaohongshu's search-plus-detail fan-out and logging are in `third_party/MediaCrawler/media_platform/xhs/core.py:280-361`; private signing/retries are in `third_party/MediaCrawler/media_platform/xhs/client.py:91-167`; token-bearing persistence is in `third_party/MediaCrawler/store/xhs/__init__.py:88-131`.

### Browser and authentication lifecycle

All five platforms have recorded real-Chrome **authentication checks**, but those archived acceptances explicitly do not establish keyword-search readiness:

- Weibo: `.trellis/tasks/archive/2026-08/08-24-platform-account-connection-center/research/real-chrome-weibo-acceptance.md:21-39`
- Douyin: `.trellis/tasks/archive/2026-08/08-24-douyin-account-connection/research/real-chrome-acceptance.md:5-27`
- Kuaishou: `.trellis/tasks/archive/2026-08/08-24-kuaishou-account-connection/research/real-chrome-acceptance.md:5-32`
- Toutiao: `.trellis/tasks/archive/2026-08/08-24-toutiao-account-connection/research/real-chrome-acceptance.md:11-31`
- Xiaohongshu: `.trellis/tasks/archive/2026-08/08-24-xiaohongshu-account-connection/research/implementation-results.md:38-61`

MediaCrawler's general CDP manager can attach to an existing browser, use its first/default context, track pages it owns, and leave the borrowed browser/context alive on cleanup (`third_party/MediaCrawler/tools/cdp_browser.py:198-270`, `third_party/MediaCrawler/tools/cdp_browser.py:406-511`, `third_party/MediaCrawler/tools/cdp_browser.py:550-571`). Weibo, Douyin, Kuaishou, and Xiaohongshu ordinary crawlers can enter this path, but each may fall back to a standalone browser if CDP setup fails (`third_party/MediaCrawler/media_platform/douyin/core.py:445-489`, `third_party/MediaCrawler/media_platform/kuaishou/core.py:491-536`, `third_party/MediaCrawler/media_platform/xhs/core.py:659-700`). Such fallback would violate the product's promise to check the approved current browser.

Toutiao is the inverse: its ordinary search deliberately ignores CDP and launches a fresh non-persistent context (`third_party/MediaCrawler/media_platform/toutiao/core.py:145-217`, `third_party/MediaCrawler/media_platform/toutiao/core.py:331-346`). Therefore the existing live Toutiao search acceptance proves its dedicated-context path only, not borrowed-Chrome search.

The smallest safe adaptation is to add a **context-injected Toutiao search operation** to the existing persistent worker. It should create/register/close only task-owned page(s) inside the borrowed default context, never close the browser/context, never install context-wide scripts, never retry a blocked navigation, and never fall back to a different browser. Search must share the worker's global serialization with account checks so two operations cannot race the same browser or provoke a second remote-debugging approval.

This matches the existing worker architecture: one persistent browser session and injected auth checks (`third_party/MediaCrawler/tools/auth_worker.py:108-241`), narrow cleanup (`third_party/MediaCrawler/tools/auth_worker.py:252-267`), strict stdout protocol separation (`third_party/MediaCrawler/tools/auth_worker.py:575-592`), a single shared FastAPI worker with request locking (`backend/src/longtian_api/services/media_crawler_auth_worker.py:114-213`), and process ownership at application lifespan (`backend/src/longtian_api/services/platform_connections.py:51-85`).

### Subprocess and configuration safety

Do **not** make each search run invoke `third_party/MediaCrawler/main.py --keywords ...` and parse its files.

- The generic CLI mutates global configuration from flags (`third_party/MediaCrawler/cmd_arg/arg.py:357-376`) and accepts keywords as one comma-separated string (`third_party/MediaCrawler/cmd_arg/arg.py:155-238`). A legitimate term containing a comma is lossy, and terms become visible in process arguments.
- `main.py` creates and tears down a crawler per invocation (`third_party/MediaCrawler/main.py:110-166`), defeating the approved long-lived browser connection.
- General defaults enable more behavior than this MVP wants, including comments/profile/media-related options (`third_party/MediaCrawler/config/base_config.py:21-31`, `third_party/MediaCrawler/config/base_config.py:95-111`).

Instead, extend the worker's strict NDJSON protocol with a bounded structured `terms: string[]` command. Emit one strict normalized result event per item and one terminal summary/error frame. Reserve stdout for protocol frames and continue draining/discarding stderr; the existing backend already uses `create_subprocess_exec` without a shell, pipes stdin/stdout/stderr, validates strict frames, and drains stderr (`backend/src/longtian_api/services/media_crawler_auth_worker.py:539-607`, `backend/src/longtian_api/services/media_crawler_auth_worker.py:659-689`). Never expose raw child exception text or platform payloads through the API, consistent with `backend/src/longtian_api/services/platform_connections.py:169-224`.

### Results, storage, and deduplication

FastAPI should own run state and normalized results in the product SQLite database. MediaCrawler should act as the adapter and event producer, not as the source of truth.

The generic JSONL writer appends to platform/type/date paths rather than a run-specific artifact (`third_party/MediaCrawler/tools/async_file_writer.py:37-60`), so file scraping cannot reliably identify the records belonging to a request. The product database currently has only the monitoring-rules migration/schema, so search runs/results require an additive migration (`backend/src/longtian_api/database.py:7-15`, `backend/src/longtian_api/database.py:69-137`).

Use `(platform, content_id)` as the canonical content identity. Preserve the ordered set of all terms that matched each item through a result-term association (or equivalent normalized representation). Toutiao currently deduplicates across terms with `seen_ids`, so the first searched term wins and later matching-term provenance is lost (`third_party/MediaCrawler/media_platform/toutiao/core.py:297-329`). That behavior is sufficient for its standalone JSONL but not for explaining why a saved product result matched a selected rule.

### Challenge and terminal-state contract

The product API should distinguish at least: `completed_with_results`, `completed_empty`, `login_required`, `manual_challenge_required`, `platform_blocked_or_rate_limited`, `structure_changed`, `cancelled`, and `internal_error`. Toutiao already supplies the clearest raw distinctions (`third_party/MediaCrawler/media_platform/toutiao/client.py:82-120`). For other platforms, their current loops often break/return normally on fetch or login failure, so adapting them later must convert those paths into explicit typed terminal events rather than a false-success empty run.

The UI can then satisfy the PRD's intended behavior without automating a CAPTCHA or slider: retain partial normalized results only if the run contract allows it, end the run, and instruct the operator to finish the platform's official login/challenge in the visible browser before retrying.

## Files Found

- `.trellis/tasks/08-25-platform-search/prd.md` — current one-shot search scope, rule selection, normalized output, and open platform-sequencing question.
- `.trellis/spec/backend/platform-connection-guidelines.md` — persistent worker, borrowed-browser ownership, serialization, strict protocol, and privacy rules.
- `.trellis/spec/backend/browser-search-adapter-guidelines.md` — original dedicated-context browser-search contract and typed failure matrix.
- `.trellis/spec/backend/monitoring-rules-guidelines.md` — ordered term persistence and the approved `list_enabled` execution boundary.
- `.trellis/spec/backend/error-handling.md` — subprocess error/log redaction boundary.
- `backend/src/longtian_api/services/media_crawler_auth_worker.py` — current persistent subprocess protocol client.
- `backend/src/longtian_api/services/platform_connections.py` — FastAPI lifespan ownership and platform-check terminal mapping.
- `backend/src/longtian_api/services/monitoring_rules.py` — enabled-rule query available to future collection.
- `third_party/MediaCrawler/tools/auth_worker.py` — persistent borrowed-Chrome worker that should be generalized for search.
- `third_party/MediaCrawler/tools/cdp_browser.py` — borrowed browser/context/page ownership implementation.
- `third_party/MediaCrawler/media_platform/{toutiao,weibo,kuaishou,douyin,xhs}/` — platform search, login, client, and challenge behavior.
- `third_party/MediaCrawler/store/{toutiao,weibo,kuaishou,douyin,xhs}/` — platform-specific persisted output shapes.
- `.trellis/tasks/archive/2026-08/` — implementation and live-acceptance evidence for Toutiao search and all five login checks.

## Related Specs

- The monitoring-rules contract intentionally separates rule editing from execution and exposes ordered enabled terms (`.trellis/spec/backend/monitoring-rules-guidelines.md:9-12`, `.trellis/spec/backend/monitoring-rules-guidelines.md:57-67`, `.trellis/spec/backend/monitoring-rules-guidelines.md:124-125`).
- The platform-connection contract requires one lazily started shared worker/context, serialized operations, and narrow borrowed-context ownership (`.trellis/spec/backend/platform-connection-guidelines.md:47-64`, `.trellis/spec/backend/platform-connection-guidelines.md:114-126`).
- The older browser-search adapter contract requires a fresh non-persistent context and forbids the everyday browser (`.trellis/spec/backend/browser-search-adapter-guidelines.md:69-74`). This now conflicts with the later user-approved borrowed-Chrome product decision. Before implementation, preserve the dedicated-adapter scenario but add/update an explicit borrowed-browser product-search contract through the Trellis spec workflow; do not silently violate either document.
- Raw child/user data must not enter public API errors or uncontrolled logs (`.trellis/spec/backend/error-handling.md:7-9`, `.trellis/spec/backend/error-handling.md:39-51`).

## External References

None. This audit intentionally used repository code, tests, archived live evidence, and project specs only; it did not re-query platform documentation or endpoints.

## Caveats / Not Found

- Only Toutiao has located dedicated keyword-search tests and a recorded real search run. No equivalent focused search-orchestration tests or live keyword-search acceptance were found for Weibo, Douyin, Kuaishou, or Xiaohongshu. Their real-Chrome evidence is authentication-only.
- Toutiao's archived task records that `so.toutiao.com/robots.txt` disallowed `/` and `www.toutiao.com/robots.txt` disallowed `/search`, and that the user knowingly accepted this access/maintenance risk (`.trellis/tasks/archive/2026-08/08-23-research-mediacrawler-toutiao-adapter/prd.md:11-13`). This historical fact was not externally revalidated in this audit.
- Current Toutiao tests/live evidence cover its dedicated fresh-context implementation, not the proposed context-injected borrowed-Chrome path. That new path needs offline ownership/protocol tests plus one explicit manual live acceptance before calling the first E2E complete.
- Private/internal platform APIs and page structures can change without notice. The ordering above minimizes the first implementation risk; it does not establish API stability or permission to automate.
