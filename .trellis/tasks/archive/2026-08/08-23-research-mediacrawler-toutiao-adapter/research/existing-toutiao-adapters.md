# Research: Existing Toutiao adapters and MediaCrawler upstream signals

- Query: Find open-source implementations and upstream MediaCrawler issues/PRs relevant to low-frequency public Toutiao keyword search and original-link extraction.
- Scope: mixed (local MediaCrawler fork plus public GitHub repositories/issues/commits only)
- Date: 2026-08-23

## Findings

### Evidence method and boundaries

- GitHub issue search was run across **all states** and includes both issues and pull requests. Exact searches for `今日头条` and `toutiao` in `NanmiCoder/MediaCrawler` titles/bodies returned zero results. A broader `头条` search returned only substring false positives about other platforms. Therefore, as of the research date, there is **no indexed open or closed upstream issue/PR specifically proposing Toutiao support**. This does not cover deleted items, Discussions, or unindexed external conversations.
- Repository metadata, licenses, trees, relevant source files, and path-specific commit histories were read from the public GitHub REST API. No repository was cloned or executed, and no crawler/login was run.
- “Verified” below means directly observable in repository metadata or source. “Inference” is explicitly labelled and is not a claim that an approach still works against the live site.
- This artifact was reconciled with `research/toutiao-web-and-official-feasibility.md`. That report verified that [`so.toutiao.com/robots.txt`](https://so.toutiao.com/robots.txt) currently declares `Disallow: /` for all user agents and [`www.toutiao.com/robots.txt`](https://www.toutiao.com/robots.txt) declares `Disallow: /search`. Those project-level stop signals override the technical feasibility suggested by public demo repositories.

### Files found

#### Local MediaCrawler fork

| File | Description |
| --- | --- |
| `third_party/MediaCrawler/main.py` | Imports each crawler and registers the short platform key in a central factory. |
| `third_party/MediaCrawler/cmd_arg/arg.py` | Defines the CLI `PlatformEnum` and platform help text. |
| `third_party/MediaCrawler/config/base_config.py` | Defines default platform, keywords, crawler type, browser mode, and rate-related configuration. |
| `third_party/MediaCrawler/base/base_crawler.py` | Defines crawler/login/store/client abstract boundaries. |
| `third_party/MediaCrawler/media_platform/weibo/core.py` | Representative browser → auth check → keyword loop → store orchestration. |
| `third_party/MediaCrawler/media_platform/weibo/client.py` | Representative authenticated HTTP client and keyword-search method. |
| `third_party/MediaCrawler/store/weibo/__init__.py` | Representative result normalization and store factory boundary. |
| `third_party/MediaCrawler/tools/browser_auth_state.py` | Existing platform-scoped browser Cookie persistence boundary. |
| `third_party/MediaCrawler/LICENSE` | Custom Non-Commercial Learning License 1.1 governing the derivative repository. |

#### External primary sources

| Repository/file | Description |
| --- | --- |
| [`NanmiCoder/NewsCrawler`](https://github.com/NanmiCoder/NewsCrawler) / [`news_extractor_core/adapters/toutiao.py`](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_extractor_core/adapters/toutiao.py#L10-L30) | Same author's maintained multi-platform project; its Toutiao adapter accepts an already-known article URL and delegates detail extraction. |
| [`NanmiCoder/NewsCrawler`](https://github.com/NanmiCoder/NewsCrawler) / [`news_crawler/toutiao_news/toutaio_news.py`](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_crawler/toutiao_news/toutaio_news.py#L31-L146) | HTTP + XPath article-detail extraction; not keyword discovery. |
| [`zhangxiaoxiao9527/toutiao-search-crawler`](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler) / [`crawler.py`](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/src/toutiao_search_crawler/crawler.py#L15-L60) | Small MIT-licensed Playwright demo for keyword search, result-link normalization, scrolling, and optional next-page navigation. |
| [`jslijb/toutiao_agent`](https://github.com/jslijb/toutiao_agent) / [`README.md`](https://github.com/jslijb/toutiao_agent/blob/main/README.md) | README claims a mobile-API search architecture, but the Toutiao crawler source is absent; only compiled bytecode is committed. |
| [`justoneapi/justoneapi-python`](https://github.com/justoneapi/justoneapi-python) / [`toutiao.py`](https://github.com/justoneapi/justoneapi-python/blob/main/justoneapi/generated/resources/toutiao.py#L92-L136) | MIT SDK for a third-party hosted API; exposes web keyword search but not the underlying collection logic. |
| [`SnailDev/toutiao-hot-hub`](https://github.com/SnailDev/toutiao-hot-hub) / [`toutiao.py`](https://github.com/SnailDev/toutiao-hot-hub/blob/main/toutiao.py#L9-L41) | Direct HTTP access to an undocumented mobile hot-board endpoint; it is hot-list aggregation, not arbitrary keyword search. |

### Upstream MediaCrawler issue/PR result

- **Verified:** [`NanmiCoder/MediaCrawler`](https://github.com/NanmiCoder/MediaCrawler) is active (repository head [`d6f7c5b`, 2026-08-14](https://github.com/NanmiCoder/MediaCrawler/commit/d6f7c5bb906b6dac40ddf343ef9e26438a3de092)), but exact all-state GitHub issue/PR searches found no Toutiao proposal:
  - [`今日头条` issue/PR REST search](https://api.github.com/search/issues?q=repo%3ANanmiCoder%2FMediaCrawler%20%E4%BB%8A%E6%97%A5%E5%A4%B4%E6%9D%A1%20in%3Atitle%2Cbody)
  - [`toutiao` issue/PR REST search](https://api.github.com/search/issues?q=repo%3ANanmiCoder%2FMediaCrawler%20toutiao%20in%3Atitle%2Cbody)
  - GitHub REST issue search returns both issues and PRs; both exact terms returned `total_count = 0`.
- **Inference:** no upstream implementation can currently be cherry-picked. If the permission/robots gate is cleared in the future, any derivative-repository adapter should be isolated so it can later be replaced if upstream adopts a different contract.

### Repository assessment

| Repository | Meaningful maintenance signal | License compatibility | Verified approach | Risks and usefulness |
| --- | --- | --- | --- | --- |
| [`NanmiCoder/NewsCrawler`](https://github.com/NanmiCoder/NewsCrawler) | Repository head 2026-08-08; Toutiao adapter/detail files last changed 2025-10-18 / 2025-10-17 ([adapter commit](https://github.com/NanmiCoder/NewsCrawler/commit/12dd9ad71cbc2213831d3551339c62a53b55a64a), [detail commit](https://github.com/NanmiCoder/NewsCrawler/commit/2abeff29e13ae210866a6ac10bc66f4180761a48)). | GPL-3.0. Do **not** copy code into MediaCrawler's custom non-commercial license without legal review/relicensing; GPL redistribution obligations and the custom additional restrictions are not a safe assumed match. | Known `toutiao.com/article/<id>` URL → HTTP page → XPath title/metadata/body → unified model ([source](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_crawler/toutiao_news/toutaio_news.py#L54-L146)). No keyword search. | Useful only as evidence that discovery and detail extraction can be separate adapters. The legacy detail source contains a hard-coded Cookie header ([source location, value intentionally not reproduced](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_crawler/toutiao_news/toutaio_news.py#L22-L29)); never copy or reuse it. |
| [`zhangxiaoxiao9527/toutiao-search-crawler`](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler) | Relevant source changed in four commits on 2026-06-03; no later code change. Recent, but not evidence of sustained maintenance ([latest relevant commit](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/commit/df91d112f50ac2a29121fa3bbb7c56308d1f9f43)). | MIT; suitable only for architectural study here; if code were ever copied after a future compliance review, attribution/notice would be required. | Builds `https://so.toutiao.com/search?...`, opens it with Playwright, scans anchors/page HTML for article IDs, canonicalizes to `https://www.toutiao.com/article/<id>/`, scrolls, and optionally follows visible “下一页” ([search/link source](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/src/toutiao_search_crawler/crawler.py#L98-L160), [normalization source](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/src/toutiao_search_crawler/crawler.py#L207-L269)). | Useful as conditional future architecture evidence only. Current `so.toutiao.com` and `/search` robots rules make this route a project stop, regardless of its MIT license or technical feasibility. It also launches headless by default, adds an anti-detection Chromium flag, performs repeated scrolling, and defaults to four concurrent detail tabs ([source](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/src/toutiao_search_crawler/crawler.py#L32-L83)); none of those choices should be imported. |
| [`jslijb/toutiao_agent`](https://github.com/jslijb/toutiao_agent) | Repository head 2026-05-23; README last changed 2026-05-15. | No license detected: no permission should be assumed for copying. | README claims mobile-API search plus HTTP detail fetch with Playwright fallback and Playwright stealth. The claimed `crawlers/toutiao_crawler.py` is missing; only `.pyc` artifacts are present. | Not independently reviewable and explicitly advertises stealth. Exclude from implementation reference and do not reverse-engineer bytecode. |
| [`justoneapi/justoneapi-python`](https://github.com/justoneapi/justoneapi-python) | Generated Toutiao resource synced 2026-08-08 ([commit](https://github.com/justoneapi/justoneapi-python/commit/c19135a419904ed4ada33f61ed04054de3b31ef8)); repository's very recent head commits are automated and are weak evidence of human maintenance. | MIT SDK only. Use still depends on separate service terms, pricing, and data provenance. | `search_v2(keyword)` calls the vendor's hosted `/api/toutiao/search/v2`; underlying Toutiao access, login, signing, throttling, and compliance are not open. | Possible paid-vendor fallback, not reusable MediaCrawler technology and not evidence for a direct adapter. Do not adopt without separate vendor/provenance review. |
| [`SnailDev/toutiao-hot-hub`](https://github.com/SnailDev/toutiao-hot-hub) | Data repository updates hourly in 2026, but the fetching source last changed 2021-01-13 ([commit](https://github.com/SnailDev/toutiao-hot-hub/commit/c33bb1221bb8ce102e40276367fbaad5ffe6f3e1)). | MIT. | Direct `requests` call to an undocumented `i-lq.snssdk.com` hot-board endpoint. | Automated data commits should not be confused with crawler maintenance. It cannot search arbitrary local-place keywords and relies on an undocumented private endpoint; do not use as the MVP route. |

### Code patterns relevant only if future permission changes the stop decision

1. **Registration is explicit.** A new short key requires a crawler import and factory entry (`third_party/MediaCrawler/main.py:39-67`), a CLI enum/help update (`third_party/MediaCrawler/cmd_arg/arg.py:40-49`, `:159-168`), and a config documentation/default-compatible update (`third_party/MediaCrawler/config/base_config.py:20-32`).
2. **Crawler/client/store remain separate.** `AbstractCrawler` requires `start`, `search`, and browser launch boundaries, while client Cookie refresh is separate (`third_party/MediaCrawler/base/base_crawler.py:26-64`, `:119-127`). The Weibo implementation shows platform orchestration and a keyword loop (`third_party/MediaCrawler/media_platform/weibo/core.py:70-148`, `:150-203`) while its client owns transport/search parameters (`third_party/MediaCrawler/media_platform/weibo/client.py:49-67`, `:152-172`).
3. **Store normalization is platform-owned.** The current store module maps raw cards into an intentionally small persisted contract and delegates to a configured backend (`third_party/MediaCrawler/store/weibo/__init__.py:35-52`, `:70-107`). A future permission-covered Toutiao implementation should follow this boundary instead of logging raw response bodies or page HTML.
4. **Authentication must be justified by a permission-covered live requirement.** If a future documented/authorized search route works without login, omit `login.py` and auth persistence. If a permitted route later proves login is required, use the existing domain-allowlisted state store (`third_party/MediaCrawler/tools/browser_auth_state.py:35-80`, `:82-110`) and the project's authoritative live-check/fallback contract; never inherit hard-coded Cookies from an external repository.
5. **License constraints are stricter than “open source exists.”** MediaCrawler's local license permits modification/merging only for non-commercial learning and prohibits large-scale/disruptive crawling (`third_party/MediaCrawler/LICENSE:12-18`). External GPL or unlicensed code must not be copied into this derivative by assumption.

These patterns document the future impact surface; they are **not authorization to add a Toutiao search module now**.

### Current recommendation

**Do not implement or run a Toutiao DOM/network search adapter under the current rules.** The live official/web research established two stronger stop signals: `so.toutiao.com/robots.txt` disallows `/` and `www.toutiao.com/robots.txt` disallows `/search`. MediaCrawler itself requires obeying platform robots rules (`third_party/MediaCrawler/base/base_crawler.py:10-15`). Low frequency, a visible browser, and non-commercial use do not remove that conflict.

The acceptable next routes are:

1. Obtain a documented official general-search capability, a government/media partnership interface, or explicit written permission covering the intended automated search path, rate, fields, retention, and link redistribution.
2. Otherwise, use a separately reviewed third-party service whose contract explicitly permits keyword discovery and use of Toutiao result links; the service's provenance, coverage, price, and retention terms remain a separate decision.
3. Until one of those routes is approved, keep Toutiao discovery manual. The application may accept manually supplied URLs and perform local deduplication/classification/notification without automating the prohibited search pages.

If official written permission is obtained or the relevant robots/terms later change, re-run the compliance and live-feasibility review before implementation. Only then may the MIT demo's **architectural boundary** be considered as clean-room design evidence, not as code to copy:

```text
keyword
→ visible search page
→ domain-allowlisted links
→ decode redirect URL parameters
→ extract numeric article ID when present
→ canonical https://www.toutiao.com/article/<id>/
→ persist minimal discovery record
```

Even after permission, browser network observation is not an automatic fallback when DOM extraction fails. It requires explicit coverage by that permission, must remain inside the permitted browser context, and must stop if it requires synthesized signatures, device fingerprints, CAPTCHA solving, authentication-header replay, or any access-control bypass.

### Stop / downgrade conditions

- **Current immediate stop:** do not automate `so.toutiao.com` search or `www.toutiao.com/search` while the cited robots rules remain in force, unless explicit official written permission clearly overrides the project boundary.
- Stop and require manual review if the site presents a CAPTCHA, slider, device verification, consent gate, or login challenge; do not automate it.
- Stop the direct adapter if stable results require reverse-engineered signatures, stealth injection, mobile-device emulation intended to evade access controls, or undocumented API replay.
- Downgrade to manual discovery or a separately reviewed, contractually authorized vendor. Do not substitute an unreviewed general search scraper as a workaround.
- Treat selector/query-parameter changes as expected maintenance. Do not claim coverage or stability from the June 2026 demo without a controlled live validation.
- Do not add article-body/comment crawling to the discovery MVP. A known-link detail adapter is a separate scope and privacy/rate decision.

### Related specs

- `.trellis/spec/infra/submodule-guidelines.md` — any later adapter change must be committed/pushed in the MediaCrawler derivative before updating the parent gitlink.
- `.trellis/spec/backend/auth-state-guidelines.md` — applies only if live research proves authentication is necessary; mandates manual safety verification and domain-scoped state.
- `.trellis/tasks/08-23-research-mediacrawler-toutiao-adapter/research/toutiao-web-and-official-feasibility.md` — authoritative current project feasibility decision: no official general-search API was found, and the robots rules stop DOM/network search implementation.
- `third_party/MediaCrawler/LICENSE:12-18` — non-commercial learning scope and low-frequency/no-disruption constraints.

### External references

- MediaCrawler repository and issue tracker: [repository](https://github.com/NanmiCoder/MediaCrawler), [issues/PR search](https://github.com/NanmiCoder/MediaCrawler/issues)
- NewsCrawler source and license: [repository](https://github.com/NanmiCoder/NewsCrawler), [GPL-3.0 license](https://github.com/NanmiCoder/NewsCrawler/blob/main/LICENSE), [Toutiao adapter](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_extractor_core/adapters/toutiao.py), [detail parser](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_crawler/toutiao_news/toutaio_news.py)
- Browser DOM search demo: [repository](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler), [MIT license](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/LICENSE), [crawler source](https://github.com/zhangxiaoxiao9527/toutiao-search-crawler/blob/main/src/toutiao_search_crawler/crawler.py)
- Sources excluded or limited: [`jslijb/toutiao_agent`](https://github.com/jslijb/toutiao_agent), [`justoneapi/justoneapi-python`](https://github.com/justoneapi/justoneapi-python), [`SnailDev/toutiao-hot-hub`](https://github.com/SnailDev/toutiao-hot-hub)

## Caveats / Not Found

- No current technique was proven against the live Toutiao site in this research; source freshness is not runtime proof.
- Separate live research found that the public page is technically viewable but currently disallowed for this project's automated search route by the cited robots rules. Technical accessibility is not project authorization.
- No official/open keyword-search implementation was found in MediaCrawler or NewsCrawler. NewsCrawler only contributes known-link detail parsing.
- No sustained-maintenance, openly licensed, reviewable repository was found that simultaneously provides current Toutiao keyword search, avoids stealth/private APIs, fits MediaCrawler's architecture, and clears the present robots/permission gate. The MIT Playwright demo is only conditional architecture evidence and has risky defaults.
- `jslijb/toutiao_agent` cannot be audited because the claimed crawler source is absent and no license is present. Its README's mobile-API and stealth claims are not verified implementation evidence.
- GitHub issue search does not cover Discussions, deleted content, private forks, or search-index gaps.
- License notes are engineering risk guidance, not legal advice.
