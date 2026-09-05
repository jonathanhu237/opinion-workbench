# 恢复微博开源获取器行为并修正安全验证误报

Status: open

Labels: ready-for-agent

## Problem Statement

用户从舆情内容库选材生成报告时，任务停在首条内容补全阶段，应用提示“微博需要完成安全验证”。点击“打开微博专用窗口”后没有验证页面，无法按提示解决问题。

原先引入开源获取器的目的是将内容 URL 交给上游维护的获取能力，减少项目自身的平台适配工作。实际实现只复用了 gallery-dl 的微博解析器：项目替换了其请求方法，丢弃传入的请求参数和请求头，并自行用 HTTP 客户端获取正文和下载媒体。正文请求、媒体请求和浏览器判障均存在将普通 HTTP 403 直接解释为安全验证的逻辑。

本机对照已验证：同一条帖子、同一份专用浏览器登录态下，已安装版本 gallery-dl 的原有提取流程取得 HTTP 200 和正文，使用其会话完整下载唯一图片也取得 HTTP 200；按应用当前方式请求同一正文接口返回 HTTP 403。历史任务未保存原始响应，因此本次对照证明当前问题可复现，不是对历史响应的追溯证明。尚未逐项隔离请求头、HTTP 客户端和连接行为的因果贡献。

用户需要的是恢复正文和媒体的正常获取，以及可信的失败提示，而不只是把错误文案改成另一句失败提示。

## Solution

将内容补全接入收薄为受控的开源获取器适配：按选中的微博 URL，复用 gallery-dl 原有的正文提取、请求会话和媒体下载能力；应用继续掌握选材范围、任务进度、执行预算、文件校验、媒体保留及入库。

普通访问拒绝不再被宣称为安全验证。单条内容无法取得可用信息时记录条目失败，继续其他条目；仅部分媒体不可用时保留正文和已取得媒体，按既有部分采集结果流程分析并说明缺口。明确登录、安全验证或限流仍按既有暂停和显式继续规则处理。

沿用现有报告生成页面，不增加获取器设置、自动浏览器补全链路或用户需要理解的新步骤。

## User Stories

1. As an analyst, I want a selected Weibo URL to be handled by the maintained acquisition component, so that platform-specific behavior does not need to be rebuilt in this application.
2. As an analyst, I want readable post text to be retrieved successfully, so that report generation can proceed beyond enrichment.
3. As an analyst, I want available images and videos downloaded with the post, so that analysis can use its available evidence.
4. As an analyst, I want acquisition to use my dedicated browser's existing Weibo login, so that I do not need another account setup.
5. As an analyst, I want my everyday browser credentials left untouched, so that the dedicated application session remains independent.
6. As an analyst, I want only my selected posts processed, so that generating a report does not start unrelated collection.
7. As an analyst, I want ordinary access refusal described accurately, so that I am not asked to solve a nonexistent CAPTCHA.
8. As an analyst, I want genuine login and verification obstacles to remain visible, so that I can resolve them myself.
9. As an analyst, I want the browser-opening action to show relevant context when manual work is required, so that I can understand what needs attention.
10. As an analyst, I want processing to resume only after I explicitly continue, so that background work does not compete with my manual operation.
11. As an analyst, I want an inaccessible post recorded as a failed item while other items continue, so that one failure does not prevent a useful report.
12. As an analyst, I want an unavailable image or video recorded as missing, so that usable text and other media can still be analyzed.
13. As an analyst, I want reports to disclose missing source material, so that incomplete acquisition is not represented as complete understanding.
14. As an analyst, I want a clear failure if no selected material is usable, so that an empty or invented report is not delivered.
15. As an analyst, I want limits on acquisition duration, requests and media size preserved, so that using the upstream component does not introduce unlimited work.
16. As an analyst, I want real rate limiting to stop further platform requests, so that the task does not continuously retry refused operations.
17. As an analyst, I want acquired progress preserved across a manual pause, so that continuing does not discard already usable material.
18. As an analyst, I want my current paused report to have a recovery path after the fix, so that I do not have to delete history to use the application again.
19. As an analyst, I want historical reports, selections, summaries and browser login retained, so that installing the fix does not reset my work.
20. As a maintainer, I want structured failure-stage and classification evidence, so that future access failures can be diagnosed without guessing from a generic message.
21. As a maintainer, I want credentials and signed media links excluded from persisted diagnostics, so that debugging does not expose account access.
22. As a maintainer, I want regression tests to exercise the real upstream request behavior, so that a successful fake parser cannot hide a broken adapter.
23. As a maintainer, I want the component version explicitly controlled, so that upgrades can be verified against the integration contract.
24. As an analyst, I want the existing selection-to-report workflow preserved, so that this repair does not add new controls or change how I start analysis.

## Implementation Decisions

1. **Architecture.** Retain browser-based discovery and the accepted controlled hybrid acquisition architecture. Use gallery-dl as the acquisition component rather than merely a JSON parser. The application owns orchestration and domain outcomes; upstream owns platform extraction and ordinary transport/download behavior. Do not implement another general-purpose downloader.
2. **Starting version.** Begin with the installed, verified gallery-dl 1.32.10. An upgrade is not a prerequisite. If an upgrade becomes necessary, explain and test it separately within the integration work rather than silently following latest.
3. **Request fidelity.** Remove the URL-only request replacement that drops upstream keyword arguments. Preserve upstream request headers, session behavior and relevant request semantics. Do not replace this with a new manually copied set of platform headers or claim adding a User-Agent alone fixes the issue. Instrumentation and bounded execution must not discard request options.
4. **Media acquisition.** Integrate the upstream download path, including supported media-specific handling, rather than continuing the current independent minimal HTTP implementation. Map produced artifacts back to the application's media inventory and validated cache. Unsupported media remains an explicit gap; upstream recognition alone does not prove complete download.
5. **Integration boundary.** Reuse the existing enrichment worker/result and media-storage boundaries where possible. The parser-only subprocess protocol can be replaced by a bounded acquisition protocol. Process isolation remains an available way to enforce cancellation and deadlines, but is not a reason to strip the component's transport. Keep the implementation limited to specified posts; no user-feed traversal or recursive job expansion.
6. **Credentials.** Supply only the necessary Weibo credentials from the application-owned dedicated browser, in memory, to the local acquisition component. This updates the previous parser-only implementation constraint: the component now performs requests and therefore needs scoped login access. No daily-profile copying, cookie export files, command-line secrets, inherited personal downloader configuration or external data service. Preserve cookie domain scoping; never manually attach Weibo account cookies to CDN or unrelated domains.
7. **Budgets and artifact handling.** Retain existing duration, request, media-count, byte-size and storage limits. Count requests made inside upstream acquisition, including redirects or supplementary lookups. Avoid layered retry loops; keep retries disabled for initial integration unless an existing bounded policy explicitly applies. Cancellation must settle the worker and close response streams; incomplete temporary files must not become ready cache entries. Validate media bytes before analysis, as today.
8. **Access classification.** Audit the shared browser classifier, detail acquisition and media transfer adapters. Status 403 alone is access refusal, not proof of a login, verification or rate-limit challenge. Likewise, an arbitrary redirect does not prove login. Examine bounded response metadata and explicit platform evidence where available; unsupported or ambiguous responses receive neutral diagnostic outcomes.
9. **Evidence requirements.** Genuine verification requires a recognized trusted verification destination or explicit platform verification evidence. Genuine login requires corresponding platform authentication evidence. Ordinary post text mentioning verification must not trigger a pause. Preserve 429 rate-limit protection and recognized explicit rate-limit messages; do not use an unknown-error branch as a synonym for security verification.
10. **Failure scope.** Ordinary detail refusal with no usable material ends that item as failed and advances to the next selected item. A refused media asset becomes unavailable while other allowed assets continue. Use existing eligibility and partial-result behavior for available text/media; do not manufacture missing text or assert analysis covered unavailable media. If no usable items remain, follow the existing report failure path rather than generating an empty report.
11. **Manual pause.** Confirmed login/verification/rate limiting retains the existing browser-dependent work coordination and explicit-continue semantics. Opening a window, refreshing or completing platform interaction must not itself resume the task. A genuine barrier must not be downgraded simply to avoid pausing.
12. **Open-window context.** For confirmed manual obstacles, retain a validated relevant platform destination when available and display that context in the dedicated browser. If no direct verification target exists, open the affected post or appropriate login context and say what was detected without promising a CAPTCHA is visible. Do not navigate to arbitrary response-provided URLs. Never automatically solve a challenge.
13. **Diagnostics.** Record acquisition stage, outcome, HTTP status if available, classification basis, associated item/asset and safe target context. Keep only bounded, allowlisted, redacted information: no raw cookie headers, complete response payloads, raw exception dumps, or signed media query strings. Expose a short useful reason in current item/report details; technical diagnostics need not become a new settings page.
14. **Existing paused work.** Do not rewrite historical pauses as proven misclassifications. On the user's existing explicit continue action, re-evaluate acquisition through the repaired path, preserving selected items and completed work. Legacy records without new evidence must remain readable and must not automatically restart on application startup. The current paused report is a required compatibility case.
15. **Contracts and persistence.** Extend existing outcome/error representations only as necessary for neutral refusal and evidence. Keep backend, frontend presenters and all consumers coherent; remove frontend catch-all wording that labels every unrecognized manual condition as verification. If persistence changes, add a forward migration with defaults for old records. No reset, history deletion or automatic re-analysis of existing successful summaries.
16. **Documentation.** Update integration documentation to accurately state that upstream now performs acquisition, with application-owned bounds and storage. Respect the existing hybrid-acquisition and explicit-resume ADRs. Add an ADR only if a durable architectural trade-off merits it; do not disguise the former no-network parser restriction as a product requirement.

## Testing Decisions

1. **Primary business boundary.** Test the user's existing selection-to-report operation through the application's established entry point, real orchestration and temporary SQLite database. Control external platform responses and LLM output. Verify usable material, item outcomes, report completion, pause behavior and persisted diagnostics, not private helper calls. This means testing the workflow the user operates; it does not require a separately deployed public API.
2. **Necessary integration boundary.** Also exercise the real pinned gallery-dl extractor/download integration against controlled HTTP responses. Do not replace gallery-dl itself with pre-parsed success for this coverage. Verify upstream request context reaches the transport, correct artifacts arrive and limits hold. Mock at the HTTP boundary without changing upstream request construction; a small local fixture server is acceptable if needed. Avoid tightly coupled assertions about every upstream header.
3. **Prior art.** Reuse existing report-generation, content-enrichment, best-effort enrichment, staged-media and gallery-component tests and fixtures. Adapt obsolete parser-only tests to the new supported contract; do not retain tests that require behavior explicitly removed by this specification.
4. **Successful regression.** A selected post has valid full text and an image, and the controlled platform requires expected upstream request context. Verify actual enrichment persists usable text and verified image, then summary/report generation completes without a false manual pause. A fixture that accepts the old stripped request equally must not be the only request-compatibility test.
5. **Download outcomes.** Cover supported video acquisition, successful image download, media refusal while text succeeds, invalid/truncated bytes, unsupported media, redirects and exhausted budgets. Assert missing coverage is reported, usable material continues and no incomplete artifact is marked ready. Supplementary media requests must remain bounded and scoped.
6. **Refusal versus manual obstacle.** Plain JSON/HTML 403 without explicit challenge evidence must not yield security-verification guidance. Cover definite login, trusted verification destinations, explicit platform messages, neutral redirects, 429 and unrelated words in post bodies. Test both backend classification and frontend wording.
7. **Multi-item and empty usability.** First item ordinary refusal followed by a successful item produces a report from usable material with a failure record. All items lacking usable material produce a clear failure. Available text with missing media follows existing partial-input analysis and coverage rules.
8. **Pause compatibility.** Genuine barrier pauses browser-dependent processing, preserves progress, and only resumes on explicit continue. Load an existing legacy paused report without new diagnostics and continue through the new component without deleting/recreating the report or duplicating completed summaries.
9. **Credential and process boundaries.** Verify only scoped dedicated-session credentials reach the local component, domain scoping prevents CDN credential leakage, diagnostics contain no secrets, user downloader configuration is not loaded, cancellation terminates work, and budget exhaustion does not permit hidden additional requests.
10. **Local acceptance.** After deterministic tests, perform a small dedicated-session check on the known failed post or an equivalent still-available selected post. Check real upstream extraction and application enrichment, including stored media. Keep requests limited; stop on genuine barriers. A full report check may use a controlled LLM response; avoid silently resuming the user's paused report or incurring live LLM usage merely for validation. Live account tests are not part of routine CI.
11. **Proportional checks.** Run relevant backend acquisition/report tests and affected frontend tests plus static/type checks. Broaden coverage when shared contracts or migrations change. Any migration must preserve representative historical data and work on fresh databases. Report exactly which live paths were exercised and distinguish original-component success from application success.

## Out of Scope

- Additional platforms, MediaCrawler restoration, paid acquisition services or a general-purpose crawler platform.
- A new native-browser detail fallback, browser fingerprint manipulation, challenge bypass or unlimited retry strategy.
- Redesigning search discovery, the recently repaired omission-page pagination, or keyword relevance filtering.
- Comments, new media-format guarantees, LLM/prompt changes, report-navigation redesign or new acquisition settings.
- Copying everyday Chrome credentials, exporting cookie files, resetting profiles or deleting existing data.
- Automatically resuming current paused reports, changing previous outcome history, or treating a single successful live example as proof every Weibo URL will work.

## Further Notes

- Reference verification took place locally on 2026-09-05, using post ID 5246622608918588 and the application-owned Weibo session. The original extractor returned 978 characters of raw text and one media item; this is raw text length, not a promise of clean-text length.
- The image was fully read in memory: HTTP 200, image/jpeg, 536297 bytes, below the diagnostic 2 MiB cap. This test used the upstream session to download the image, not the entire upstream downloader/job pipeline. Full downloader integration therefore still needs implementation and validation.
- A subsequent same-session comparison reproduced HTTP 403 with the current application-style HTTP request. This narrows the failure to differences in acquisition behavior but does not isolate an individual header, TLS behavior or HTTP library as the sole cause. Do not present an untested single-header fix as established fact.
- The investigation did not modify application code, resume the paused report or persist credentials. Diagnostic helper files are not production components and should not become prerequisites for implementation.
- The user requested synthesis and handoff to Luna Max rather than another interview. The test boundary follows existing business-flow tests and adds only the upstream HTTP compatibility boundary required by this observed integration failure. No additional product decisions are blocking this specification.
- Discussion is complete. This publication is documentation only; implementation is a separate user-requested step.
