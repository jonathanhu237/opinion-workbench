# Research: GitHub candidates for Weibo, Kuaishou, and Xiaohongshu enrichment

- Query: Find maintained GitHub libraries/projects that can obtain detail-page full text and image/video metadata or bytes for Weibo, Kuaishou, and Xiaohongshu, preferably by reusing a user-controlled logged-in Chrome/CDP session; compare them with repairing this project's current enrichment adapters.
- Scope: mixed (local architecture and primary upstream GitHub sources)
- Date: 2026-08-31 (Asia/Shanghai)

## Executive finding

No reviewed repository is a safe drop-in replacement for the complete requirement:

`WB + KS + XHS detail text + exhaustive media inventory + media bytes + existing logged-in Chrome/CDP + permissive commercial license + this project's strict source/security contract`.

The closest technical match is [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler), but this project already vendors a customized MediaCrawler derivative. Upstream therefore offers code-parity references, not a new turnkey dependency. Its [NON-COMMERCIAL LEARNING LICENSE 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE) also prohibits commercial use without written consent, so it is not OSI-style open source and cannot be treated as a generally reusable commercial dependency.

The recommended decision is **hybrid, led by direct repair**:

1. Keep the existing shared Playwright/CDP worker, exact-source validation, bounded navigation, private staging, byte limits, MIME/probe/hash checks, cancellation, and manual-challenge behavior.
2. Repair each current platform projection so it can prove complete text and exhaustive media inventory.
3. Port only narrowly audited parsing ideas or fixtures from candidate projects when their license is compatible; do not replace the current worker or import their cookie/download subsystems.
4. Consider `yt-dlp` only as an optional video extractor/downloader behind the current security boundary for WB/XHS. It does not cover Kuaishou and does not solve image inventory.
5. Treat GPL downloaders as references or separately reviewed optional processes, not automatic embedded dependencies. Obtain legal review before distributing a combined product.

This approach has less implementation and security risk than introducing three unrelated authentication, retry, storage, and download stacks.

## Local architecture and the actual missing pieces

### Files found

- `third_party/MediaCrawler/tools/auth_worker.py:484-550` — one persistent worker owns the borrowed Chrome/CDP context and dispatches enrichment for all five platforms.
- `third_party/MediaCrawler/tools/product_media.py:36-44` — only exact, live-verified CDN hosts are trusted; WB, KS, and XHS currently have empty host sets.
- `third_party/MediaCrawler/media_platform/weibo/product_enrichment.py:48-87` — parses text and pictures but deliberately marks media inventory incomplete because video/no-video is not proved.
- `third_party/MediaCrawler/media_platform/kuaishou/product_enrichment.py:49-102` — fetches a minimal detail GraphQL response and one video candidate, but deliberately marks caption partial, inventory incomplete, and `structure_changed`.
- `third_party/MediaCrawler/media_platform/xhs/product_enrichment.py:98-163` — has the strongest current projection: complete title/description is possible and it distinguishes image/video inventory, but actual media URLs still fail the shared empty host allowlist.
- `backend/src/longtian_api/services/enrichment_models.py:233-244` — downstream readiness requires complete text, complete inventory, actual valid assets, and no issues.
- `.trellis/spec/backend/media-projection-guidelines.md` — forbids turning unknown/malformed media into absence and requires actual media validation before ready.
- `.trellis/spec/backend/auth-state-guidelines.md` — credentials must remain platform-scoped, secret-safe, and subordinate to a live login check; challenges stay manual.
- `.trellis/spec/backend/browser-search-adapter-guidelines.md` — visible browser work is bounded, challenge-aware, and must not fall back to private API replay or broad retries.
- `.trellis/spec/infra/submodule-guidelines.md` — third-party source adoption requires a clean, reachable, pinned gitlink and license/reproducibility review.

### Why a standalone downloader does not automatically fix enrichment

The product needs more than a playable media URL. A successful enrichment must prove:

- the final page still identifies the exact stored content ID and supported source type;
- title/body coverage is complete rather than merely non-empty;
- the source media inventory is exhaustive, including proven absence;
- every claimed asset is an original source asset, not a cover/recommendation;
- URL, redirects, DNS, response size/type, decoded image, and video/audio properties are safe;
- no raw Cookie, signed URL, private response, temporary bytes, or account data is persisted;
- a login wall, CAPTCHA, safety challenge, 403, or 429 stops for user action rather than being retried around.

Most downloaders establish only “this URL yielded a file”. They do not establish the complete-source contract needed by the LLM admission gate.

## Ranked shortlist

Repository activity and stars below are a 2026-08-31 GitHub API snapshot and are weak health signals, not acceptance evidence. “CDP” means reuse of the already running user-controlled Chrome context, not merely browser-cookie import.

| Rank | Candidate | Platform / fidelity | Auth and CAPTCHA shape | License | Integration assessment |
| --- | --- | --- | --- | --- | --- |
| 1 | [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | WB/KS/XHS; keyword, detail and creator modes; XHS image/video download, WB images; current KS core exposes detail but no equivalent media-download path found | Python + Playwright; [CDP is enabled by default and can connect to existing Chrome](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py#L55-L87); README directs manual handling when verification appears | [Non-Commercial Learning License 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE), commercial use prohibited | Best code reference and closest runtime fit, but already the project's base. Selective parity/cherry-pick only; do not replace hardened derivative. License is a release blocker for commercial use without permission. |
| 2 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Strong WB video metadata/description/formats and XHS video metadata/title/description/formats; no Kuaishou extractor found; images are not its primary output | Python library/CLI; accepts cookie files or `--cookies-from-browser`, but does not attach to current CDP context; challenge handling is extractor failure, not the product's manual-action protocol | Source/PyPI is [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#license), while bundled executables can become GPL because of included components | Mature optional video helper only. Wrap behind current staging/redirect/size/probe rules and provide only platform-scoped ephemeral credentials if adopted. It cannot be the main enrichment engine. |
| 3 | [gallery-dl](https://github.com/mikf/gallery-dl) | WB full status objects, long-text detail, exhaustive mixed images/GIF/Live Photo/video extraction; no XHS or KS extractor found | Python CLI/library; Cookie file or browser database extraction, no CDP attachment; aborts on login redirects | [GPL-2.0](https://github.com/mikf/gallery-dl/blob/master/LICENSE) | High-value WB reference and possible isolated WB downloader. Embedding/distribution has copyleft implications; its auth/cache and request stack should not replace the product worker. |
| 4 | [JoeanAmier/KS-Downloader](https://github.com/JoeanAmier/KS-Downloader) | KS detail metadata and video/image file download; FastAPI mode and local persistence; active dedicated platform code | Python + `curl_cffi`; dynamic/manual Cookie, not CDP; configured retries (default five) conflict with stop-on-block policy | [GPL-3.0](https://github.com/JoeanAmier/KS-Downloader/blob/master/LICENSE); README also carries broad disclaimer/reuse language | Best current KS implementation reference. A direct embedded dependency is high-risk for license, duplicate retries, cookie handling, and storage. Port only independently validated concepts after legal review. |
| 5 | [ReaJason/xhs](https://github.com/ReaJason/xhs) | XHS feed/detail HTML/API, full note object, image/video URL derivation and download helpers | Synchronous `requests`; caller supplies Cookie and a signing function; explicitly raises verification/IP-block/sign errors; no Playwright/CDP reuse | [MIT](https://github.com/ReaJason/xhs/blob/master/LICENSE) | Permissive and library-shaped, but last source push was 2025-07-01 and signing/endpoint logic is brittle. Useful for field maps/tests, not for replacing browser ownership or direct use of its downloader. |
| 6 | [Andy-SoulShell/xhs-downloader](https://github.com/Andy-SoulShell/xhs-downloader) | XHS-only detail/download/search with Python SDK, FastAPI and an extension/managed-browser route | Privacy-positive browser extension claims not to read/transfer Cookies; does not reuse this project's CDP worker; adds an extension, local capability protocol, queue, and UI | [MIT](https://github.com/Andy-SoulShell/xhs-downloader/blob/main/LICENSE) | Architecturally interesting but created 2026-07-23, last pushed 2026-07-28, and had only 2 stars/0 forks in the snapshot. Too new and duplicative for the primary path; re-evaluate after maturity. |
| 7 | [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) | Strong XHS detail metadata plus image/video/Live Photo downloads; API/MCP modes | Direct HTTP/curl impersonation; README says browser-Cookie reading is currently broken and advises manually copying a Cookie; old links may trigger controls | [GPL-3.0](https://github.com/JoeanAmier/XHS-Downloader/blob/master/LICENSE) | Capable standalone tool, poor credential/CDP fit, copyleft, and duplicates capabilities of better-fitting candidates. Reference only. |

### 1. NanmiCoder/MediaCrawler — closest but not a new dependency

Primary evidence:

- [README](https://github.com/NanmiCoder/MediaCrawler#readme) lists WB, KS, and XHS search/detail/login-state support and describes Playwright-based signing.
- [Base configuration](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py#L21-L32) exposes `search`, `detail`, and `creator`; [lines 55-87](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py#L55-L87) enable existing-browser CDP; [lines 101-111](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py#L101-L111) expose bounded result and media flags.
- [XHS core](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/core.py) fetches detail and has image/video download methods.
- [KS core](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/kuaishou/core.py) fetches `visionVideoDetail`, but no general media download method comparable to XHS was found.
- [Weibo core](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/weibo/core.py) expands long text and downloads images; no complete general video path was found in the core.
- [License](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE) limits use/modification/merging to non-commercial learning and research.

Snapshot: 64,139 stars, 12,469 forks, pushed 2026-08-14. Platform-specific commits in August 2026 show active XHS/KS maintenance; stars do not remove the license or live-regression requirement.

Fit judgment:

- **Positive:** same Python/Playwright/CDP family; upstream has current field knowledge and has already addressed platform-cookie scoping.
- **Negative:** the local derivative deliberately added stricter source identity, media projection, SSRF, staging, cancellation, and privacy behavior. Wholesale upstream replacement would lose those contracts. Upstream also uses automatic retry/skip behavior in places where this product requires a truthful manual stop.
- **Use:** diff platform clients/field projections and port small, tested pieces. Do not pull its whole auth, storage, or retry path into the backend.

### 2. yt-dlp — optional video component, not content enrichment

Primary evidence:

- [WB extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/weibo.py#L104-L130) returns description, formats, thumbnail, timestamp and counts; [lines 193-209](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/weibo.py#L193-L209) read the status API and mixed media.
- [XHS extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xiaohongshu.py#L43-L108) parses page initial state, format streams, images as thumbnails, title and description.
- The repository tree contains no `yt_dlp/extractor/kuaishou.py` as of the snapshot.
- [Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) states `--cookies-from-browser` can export the browser session and warns that writing a cookie file exports cookies for all sites.
- A recent official [XHS extractor failure report #15467](https://github.com/yt-dlp/yt-dlp/issues/15467) from 2026-01-02 documents server-side validation fragility even when the link works in a browser. The extractor remains present, so this is a brittleness signal, not proof of current failure.

Snapshot: 188,023 stars, 16,268 forks, pushed 2026-08-30. XHS extractor's last path-specific commit found was 2025-01-20; WB's was 2026-06-21.

Fit judgment:

- Good for decoding video format manifests, selecting a format, and downloading robustly.
- Cannot prove an image-post inventory, long-text expansion, or source-page fidelity by itself.
- Never call its broad browser-cookie exporter against the user's everyday Chrome. If used, credentials must come from the existing worker as an operation-scoped, platform-only capability and must not be logged or persisted.
- Its output URL still has to pass the project's exact-host, redirect, byte, MIME, ffprobe and staging checks.

### 3. gallery-dl — strong WB media reference

Primary evidence:

- [WB extractor](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/weibo.py#L19-L60) uses scoped `SUB`/`SUBP` cookies and login detection.
- [Lines 77-130](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/weibo.py#L77-L130) enumerate status media and optionally fetch long text.
- [Lines 132-201](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/weibo.py#L132-L201) handle mixed pictures, GIF, Live Photo and video variants and retrieve the long status.
- [README Cookie section](https://github.com/mikf/gallery-dl#cookies) supports cookie files or browser database extraction, not CDP attachment.

Snapshot: 19,362 stars, 1,465 forks, pushed 2026-08-29. The GitHub repository announced a move to Codeberg, so future source-of-truth and pinning must be checked before adoption.

Fit judgment: excellent WB structure test/reference; limited platform coverage and GPL-2.0 make it a poor universal embedded dependency.

### 4. JoeanAmier/KS-Downloader — strongest dedicated KS reference

Primary evidence:

- [README](https://github.com/JoeanAmier/KS-Downloader#readme) documents KS short-video/share-link support, metadata persistence, video/image downloads, an API mode, browser impersonation, Cookie configuration, bounded timeouts and configurable retries.
- [Latest release 1.6](https://github.com/JoeanAmier/KS-Downloader/releases/tag/1.6) was published 2026-07-05.
- [GPL-3.0 license](https://github.com/JoeanAmier/KS-Downloader/blob/master/LICENSE).

Snapshot: 840 stars, 204 forks, pushed 2026-08-29.

Fit judgment:

- Its current KS response fields and media selection logic are worth comparing with the local minimal GraphQL projection.
- It is a standalone downloader/API with its own SQLite state and direct HTTP stack, not a Playwright page adapter.
- Automatic retry, direct Cookie configuration, curl impersonation and independent storage conflict with the local single-owner/manual-action design.
- GPL-3.0 and additional README disclaimer language need legal review before any code copy, linking, packaging, or service bundling.

### 5. ReaJason/xhs — permissive XHS field-map reference

Primary evidence:

- [`XhsClient`](https://github.com/ReaJason/xhs/blob/master/xhs/core.py#L93-L175) is a synchronous `requests.Session` wrapper; it accepts a Cookie and signing callback, and raises explicit verification/IP-block/sign failures.
- [Detail methods](https://github.com/ReaJason/xhs/blob/master/xhs/core.py#L206-L264) use the feed API or parse `window.__INITIAL_STATE__`.
- [File save helper](https://github.com/ReaJason/xhs/blob/master/xhs/core.py#L309-L336) chooses video or all images.
- [Media helpers](https://github.com/ReaJason/xhs/blob/master/xhs/help.py#L81-L147) derive CDN URLs and download directly. They randomly choose among CDN aliases and do not implement this project's exact-source host/redirect/byte/probe checks.
- [MIT license](https://github.com/ReaJason/xhs/blob/master/LICENSE).

Snapshot: 2,203 stars, 453 forks, last pushed 2025-07-01, no GitHub release found, 48 open issues.

Fit judgment: useful source-shape comparison under a permissive license. The embedded signature algorithm, direct Cookie/session handling, synchronous I/O, and age make it less reliable than the current browser-derived signature path.

### 6. Andy-SoulShell/xhs-downloader — promising privacy architecture, immature

Primary evidence:

- [README](https://github.com/Andy-SoulShell/xhs-downloader#readme) exposes detail/download, a Python SDK, local FastAPI, and browser-extension or managed-browser routes.
- It states the extension uses the current browser login but cannot read or transmit Cookies, a useful privacy pattern.
- [MIT license](https://github.com/Andy-SoulShell/xhs-downloader/blob/main/LICENSE).

Snapshot: created 2026-07-23, pushed 2026-07-28, 2 stars, 0 forks, no release found.

Fit judgment: its capability-token/extension approach deserves later study, but installing and trusting an additional extension and local service would expand the attack surface and duplicate the current CDP owner. Its short history provides insufficient live stability evidence.

### 7. JoeanAmier/XHS-Downloader — capable but poor auth/license fit

Primary evidence:

- [README](https://github.com/JoeanAmier/XHS-Downloader#readme) documents full detail metadata, image/video/Live Photo download, API/MCP modes, formats and local data recording.
- The same README says browser Cookie reading has failed and instructs users to obtain/copy a Cookie manually; it also warns stale share URLs may be risk-controlled.
- [Latest release 2.7](https://github.com/JoeanAmier/XHS-Downloader/releases/tag/2.7) was published 2026-02-09.
- [GPL-3.0 license](https://github.com/JoeanAmier/XHS-Downloader/blob/master/LICENSE).

Snapshot: 12,542 stars, 1,842 forks, pushed 2026-08-29.

Fit judgment: strong standalone feature coverage, but copying Cookies, a second request stack, GPL-3.0, and duplicated API/storage make it inferior to fixing the current XHS adapter.

## Excluded, dead, unlicensed, or thin wrappers

### dataabc/weiboSpider

- [Repository](https://github.com/dataabc/weiboSpider) is active (pushed 2026-02-04; 9,698 stars) and documents full post text plus original images/video.
- Its main boundary is crawling one or more user timelines, not enriching an arbitrary already-discovered status through the current CDP page.
- GitHub reports no detected license and the repository root has no `LICENSE` file. Public source without an explicit license is not permission to copy, modify, or distribute. Exclude from code reuse unless the owner supplies a suitable license.

### sonderlau/KuaiShouVideoDownload

- [Repository](https://github.com/sonderlau/KuaiShouVideoDownload) is MIT but last pushed 2022-12-09, requires manually captured request headers/Cookies, and targets author downloads/merging. It is stale and incompatible with the CDP ownership boundary.

### zyipeng/video-downloader

- [Repository](https://github.com/zyipeng/video-downloader) is a small MIT shell/agent skill created and pushed in June 2026.
- It delegates WB/XHS to `yt-dlp` and uses a custom KS share-page parser. It caches a broad Chrome cookie export for 24 hours. It adds no full-text/image-inventory contract and conflicts with credential minimization; use its claims only as test ideas.

### smile7up/xiaohongshu-downloader and similar wrappers

- [Repository](https://github.com/smile7up/xiaohongshu-downloader) has only two commits and wraps `yt-dlp` plus optional Whisper. It does not add a stable XHS extractor or CDP integration; adopting `yt-dlp` directly is clearer.

### Browser userscripts

- Projects such as [gbandszxc/weibo-image-downloader](https://github.com/gbandszxc/weibo-image-downloader) can enumerate visible WB images/video from the logged-in page, but are interactive download tools rather than Python libraries. A userscript/extension could be a future last-resort browser capability, but it adds deployment, permission, trust and result-transfer work.

## Build path: direct changes recommended by platform

This is a design recommendation, not an implementation performed by this research task.

### Shared boundary

1. Keep the one current CDP worker and borrow its already verified default context.
2. Keep one owned page per source, exact platform/content-ID checks before and after reads, and bounded waits.
3. Expand the source projection only with fields needed to prove title/body and exhaustive media. Do not retain users, comments, tokens, profiles or raw response objects.
4. Convert candidates into actual assets only after exact observed-host approval and the current downloader's redirect/DNS/byte/MIME/image/ffprobe validation.
5. Add real offline browser fixtures plus pure projection/materialization tests; a Python dictionary fixture alone cannot detect lossy JavaScript projection.
6. On login, permission, CAPTCHA, challenge, 403, 429 or unexplained structure, stop with an explicit outcome. Do not inherit external projects' retries or bypass behavior.

### Weibo

Current defect: text and `pics` are visible, but `page_info`/mixed media/video absence is not projected, so inventory is always false. Long text can also stay partial.

Recommended repair:

- Extend the bounded page projection to distinguish ordinary pictures, mixed-media items, GIF/Live Photo and video from a verified exact-status representation.
- Resolve `isLongText` through the authenticated detail representation and prove the returned text is fully expanded; do not accept the presence of text alone.
- Use gallery-dl and upstream MediaCrawler only to identify candidate field cases and build fixtures; independently implement against the current minimal model.
- Add exact observed Sina media hosts only after live source-player evidence, and test redirect/host confusion cases.

### Kuaishou

Current defect: the adapter intentionally calls all captions partial, ignores image-post completeness, treats status semantics as unknown, and always emits `structure_changed`; a downloaded video can never become ready.

Recommended repair:

- Establish the real `visionVideoDetail.status` success/error semantics with a bounded live acceptance and fixtures.
- Expand the minimal GraphQL selection just enough to prove post type, complete caption, exhaustive image/video variants, and supported transport. Keep author/comment/recommendation fields out.
- Handle video and image-post unions explicitly; a cover is never a source asset.
- Compare the response/media selection with KS-Downloader, but retain current CDP-scoped Cookie conversion and no-retry/manual-stop behavior.
- Approve only observed exact Kuaishou media hosts and retain ffprobe/audio verification.

### Xiaohongshu

Current projection is closest to complete. It already distinguishes a normal note's image list from a video's cover and retains malformed inventory as unknown.

Recommended repair:

- Preserve the current token lookup and exact note-page identity checks.
- Capture live evidence for the exact image/video CDN hosts actually emitted by the source note, then populate a versioned exact-host allowlist with adversarial suffix/credential/port/redirect tests.
- Preserve all images in order and one actual source video; do not randomly synthesize a CDN hostname from an origin key as ReaJason/xhs does.
- Add token-expiry/lookup-miss/manual-challenge tests and avoid retrying with stale share URLs.

## Optional dependency path and proof-of-concept gates

If the team still wants to test reuse before committing to the build path, use isolated, network-disabled contract probes first:

1. **yt-dlp WB/XHS video probe:** feed sanitized HTML/JSON fixtures into pinned extractors, map only IDs, description and format candidates, and prove no filesystem/browser-cookie access. Reject adoption if the output cannot pass current exact-source and media guards.
2. **gallery-dl WB parser probe:** exercise long text, pure image, pure video, GIF, Live Photo and mixed media fixtures. Use it to compare inventory completeness, not to download or read Cookies.
3. **KS-Downloader parser study:** identify its minimal response fields and media-choice rules. Do not copy GPL code into the product during the study.
4. **License gate:** decide whether this application is distributed or used commercially. Obtain written MediaCrawler permission or legal review before further upstream copying; review GPL obligations before embedding or shipping GPL tools.
5. **Live gate:** only after offline safety/contract tests, run one user-approved item per platform in the existing worker. Never send a real Cookie or signed URL to an untrusted external service.

## Buy / build / hybrid recommendation

| Option | Benefit | Principal cost/risk | Recommendation |
| --- | --- | --- | --- |
| Replace with one GitHub project | Superficially faster | No candidate meets platform + CDP + fidelity + license + security requirements; would regress source/privacy contracts | Reject |
| Add three platform downloaders | Can obtain more files quickly | Three auth stacks, Cookie exposure, retries, storage, licenses, result schemas and update cycles; still no unified completeness proof | Reject as the main architecture |
| Directly repair current adapters | Best fit with existing worker and model contract | Requires platform-specific fixtures and occasional maintenance | Primary path |
| Hybrid: repair + narrow external components | Reuses mature video/field knowledge while preserving security | Requires adapter boundaries, pins, license review and regression tests | Recommended |
| Paid/hosted platform API | Potential operational stability/SLA | Not part of this GitHub-only search; content/credential transfer, price, lawful-use and coverage require separate review | Separate future research |

Recommended concrete selection:

- **Core:** current fork and current CDP worker.
- **Reference/parity:** upstream MediaCrawler, subject to its non-commercial license.
- **Optional permissive component:** pinned `yt-dlp` source package for WB/XHS video parsing only, if an offline proof shows clear value.
- **Platform references:** gallery-dl for WB mixed-media cases, KS-Downloader for KS media fields, ReaJason/xhs for XHS shapes.
- **Do not adopt now:** broad Cookie exporters, standalone API services with their own retry/storage, unlicensed code, or a second browser extension.

## Security, privacy, and operational risks

- A browser Cookie is a bearer credential. `--cookies-from-browser` may read/export many unrelated sites; this violates the project's platform-scoped state contract unless tightly replaced with an operation-scoped bridge.
- A local HTTP service accepting raw Cookie strings still expands the credential attack surface. Loopback-only is helpful but not equivalent to keeping the credential inside the worker.
- Signed CDN URLs can contain identifiers/tokens and expire. Never persist or log them; save only validated metadata/hash and bounded model evidence.
- Blind CDN wildcarding enables suffix-confusion, compromised-subdomain and redirect attacks. Continue exact-host validation plus DNS/private-address rejection.
- External downloaders commonly follow redirects, retry blocks, or select alternative formats. Those behaviors must be disabled or wrapped because they can cross the product's source and manual-action boundaries.
- Direct internal API/signature replay can increase platform-account risk and may violate platform terms. The user-controlled visible page remains the authoritative access boundary.
- Downloading a valid file does not authorize reuse, redistribution, or model processing of it. Copyright, privacy, retention and platform-terms review remains separate.
- Repository popularity is not a security audit. Pin dependencies, inspect transitive packages, verify releases/checksums, and run network-disabled fixtures before live use.

## External references and version/activity snapshot

- [MediaCrawler repository](https://github.com/NanmiCoder/MediaCrawler), [license](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE), [architecture](https://github.com/NanmiCoder/MediaCrawler/blob/main/docs/%E9%A1%B9%E7%9B%AE%E6%9E%B6%E6%9E%84%E6%96%87%E6%A1%A3.md), [CDP configuration](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py#L55-L87).
- [yt-dlp repository](https://github.com/yt-dlp/yt-dlp), [license notes](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#license), [WB extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/weibo.py), [XHS extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xiaohongshu.py), [Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
- [gallery-dl repository](https://github.com/mikf/gallery-dl), [WB extractor](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/weibo.py), [GPL-2.0 license](https://github.com/mikf/gallery-dl/blob/master/LICENSE).
- [KS-Downloader repository](https://github.com/JoeanAmier/KS-Downloader), [release 1.6](https://github.com/JoeanAmier/KS-Downloader/releases/tag/1.6), [GPL-3.0 license](https://github.com/JoeanAmier/KS-Downloader/blob/master/LICENSE).
- [ReaJason/xhs repository](https://github.com/ReaJason/xhs), [core](https://github.com/ReaJason/xhs/blob/master/xhs/core.py), [helpers](https://github.com/ReaJason/xhs/blob/master/xhs/help.py), [MIT license](https://github.com/ReaJason/xhs/blob/master/LICENSE).
- [Andy-SoulShell/xhs-downloader](https://github.com/Andy-SoulShell/xhs-downloader), [MIT license](https://github.com/Andy-SoulShell/xhs-downloader/blob/main/LICENSE).
- [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader), [release 2.7](https://github.com/JoeanAmier/XHS-Downloader/releases/tag/2.7), [GPL-3.0 license](https://github.com/JoeanAmier/XHS-Downloader/blob/master/LICENSE).
- GitHub REST repository metadata was checked on 2026-08-31 at `https://api.github.com/repos/{owner}/{repo}`; values are a point-in-time snapshot.

## Related specs

- `.trellis/spec/backend/media-projection-guidelines.md`
- `.trellis/spec/backend/initial-analysis-guidelines.md`
- `.trellis/spec/backend/auth-state-guidelines.md`
- `.trellis/spec/backend/browser-search-adapter-guidelines.md`
- `.trellis/spec/infra/submodule-guidelines.md`
- `.trellis/tasks/08-27-live-search-ai-acceptance/prd.md`
- `.trellis/tasks/08-27-live-search-ai-acceptance/design.md`

## Caveats / Not Found

- No live crawler, platform, browser, model or media request was run. Candidate quality claims are documentation/source assessments, not live acceptance.
- No single maintained permissively licensed repository covering WB + KS + XHS with existing-browser CDP, complete text and complete media was found.
- No Kuaishou extractor was found in the current `yt-dlp` or `gallery-dl` source trees.
- No XHS or Kuaishou extractor was found in the current `gallery-dl` source tree.
- Upstream MediaCrawler did not show an equivalent complete KS media-download path or a complete WB video path in the reviewed core files.
- GitHub API license detection is not legal advice. Repository README disclaimers or third-party code can impose additional obligations; commercial/distribution use needs a proper license review.
- Platform DOM/API/CDN behavior changes frequently. A recent commit or large star count cannot replace pinned revisions, fixtures and bounded live regression.
- Paid data providers were intentionally not assessed because this query was for GitHub libraries/projects; they need a separate privacy, contract, data-provenance and cost study.
