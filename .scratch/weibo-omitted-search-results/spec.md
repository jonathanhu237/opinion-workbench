# 微博翻页后相似结果省略空页的采集修复

Status: resolved

Labels: implemented

## Problem Statement

用户在微博舆情爬取时，同一个关键词的第 1 页已有正常搜索结果，应用也已采集这些内容；进入第 2 页后，微博仍展示分页和“找到 40 条结果，部分相似结果已省略”的提示，并提供“查看全部搜索结果”入口，但当前结果区域没有帖子。应用无法识别这一页面状态，终止采集并提示用户检查登录或安全验证。

核心问题是正常取得结果后的翻页异常中断了采集，不是初次搜索就没有内容。当前页面解析只接受帖子卡片或标准的“未找到结果”提示，其余无卡片页面等待后会被判为无法识别；采集层随后将该状态作为整个尝试的失败返回。因此，虽然前一页已经入库的内容仍在，后续关键词的采集受到阻断，用户也收到了缺乏依据的登录排查提示。

截图中的空白结果区域不能证明关键词无匹配结果，也不能证明登录失效、出现安全验证或平台确实已无更多结果。修复必须处理完整的连续翻页过程，不能只隐藏报错，或把所有空白页一律视为正常结束。

## Solution

应用遇到“当前搜索页等待后仍没有帖子，同时存在相似结果省略提示和可用的查看全部入口”时，在当前关键词内自动通过微博提供的入口尝试继续一次。正常有帖子的页面保持原有采集方式。

补救保留前面所有页面已经取得的结果、当前关键词的去重记录与剩余采集额度。查看全部可能从另一种展示方式的第 1 页开始；即使再次看到已采过的帖子，也不重复入库、不重复消耗条数额度，并继续寻找尚未取得的内容，直到满足原有数量要求或确认没有后续结果。

如果补救后经过有限等待仍无法识别结果，应用保留已有内容，记录该关键词采集不完整，继续下一个关键词。结束时在现有采集记录中简要说明受影响的关键词和原因。真正出现登录、安全验证或限流时，仍暂停整个批次，由用户处理后显式继续。

本次不增加设置页面、额外确认弹窗或专用重试按钮。用户的主要体验变化是这类页面不再让整个采集无故中断，已采结果得到保留，尚未完成的部分得到准确说明。

## User Stories

1. As an analyst, I want collection to handle a normal first page followed by an omission-only second page, so that a pagination edge case does not stop useful collection.
2. As an analyst, I want posts collected from the first page to remain available, so that a later page problem does not discard my results.
3. As an analyst, I want the application to recognize Weibo's similar-result omission notice, so that it does not incorrectly tell me to log in again.
4. As an analyst, I want the application to wait for a page to load before treating it as an omission-only page, so that slow rendering does not trigger unnecessary recovery.
5. As an analyst, I want pages that contain normal posts to continue through ordinary collection, so that an accompanying omission notice does not disrupt progress.
6. As an analyst, I want the application to use the page's view-all-results entry automatically when appropriate, so that I do not need to perform this routine navigation myself.
7. As an analyst, I want recovery to remain within my current search keyword, so that unrelated search results are not added to my collection.
8. As an analyst, I want recovery to happen only once for a keyword within an attempt, so that the application does not repeatedly switch modes or refresh the same pages.
9. As an analyst, I want collection to continue if the view-all entry returns to an earlier page, so that a different result presentation does not lose my progress.
10. As an analyst, I want previously encountered posts to be recognized across the ordinary and view-all pages, so that revisiting them does not inflate collected counts.
11. As an analyst, I want URL aliases for the same post to retain the existing deduplication behavior, so that changing presentation does not create duplicate library records.
12. As an analyst, I want newly encountered posts after recovery to be saved normally, so that the workaround actually recovers useful content.
13. As an analyst, I want my configured per-keyword result limit to remain in effect throughout recovery, so that automatic navigation does not expand the requested amount of work.
14. As an analyst, I want a keyword that has already reached its limit to finish without unnecessary recovery, so that collection does not browse additional pages after satisfying my request.
15. As an analyst, I want normal pagination to work after opening all results, so that collection can obtain the remaining requested posts.
16. As an analyst, I want recovery to use the existing execution limits, so that it cannot turn a bounded collection into an endless operation.
17. As an analyst, I want a recognized end of results after earlier successful pages to preserve those results, so that the keyword is not represented as having returned nothing.
18. As an analyst, I want unresolved pages after recovery to be recorded as keyword collection incomplete, so that missing coverage is not presented as a successful empty search.
19. As an analyst, I want remaining keywords to continue after this specific recovery cannot obtain results, so that one keyword does not block the rest of my work.
20. As an analyst, I want an incomplete keyword that already has posts to keep both its results and its incomplete status, so that I can use the material without assuming full coverage.
21. As an analyst, I want the final collection record to identify incomplete keywords and their reasons, so that I know what was not finished.
22. As an analyst, I want a collection with only incomplete keywords to remain distinguishable from a successful empty collection, so that I am not misled about the search outcome.
23. As an analyst, I want successful automatic recovery to avoid additional confirmation dialogs, so that routine collection can proceed without interruption.
24. As an analyst, I want incomplete keyword records to survive refreshing the application, so that the explanation is not lost when I revisit collection history.
25. As an analyst, I want a later login or verification barrier to pause the batch normally, so that I can resolve the actual platform obstacle.
26. As an analyst, I want collection to resume only after my explicit action following a platform barrier, so that browser operations do not race with my manual work.
27. As an analyst, I want earlier incomplete keywords to remain visible after a later pause and resume, so that finishing subsequent work does not erase known gaps.
28. As an analyst, I want a new collection to use the existing duplicate detection against stored content, so that retrying does not duplicate my library.
29. As an analyst, I want generic loading, browser failures and invalid pages to retain appropriate failure handling, so that this targeted fix does not conceal other problems.
30. As an analyst, I want posts that merely mention omission or login text to remain ordinary content, so that user-written text cannot change collection behavior.
31. As an analyst, I want the progress and result details to stay in the existing collection interface, so that fixing this failure does not add new controls I must learn.
32. As a maintainer, I want the regression test to reproduce the entire first-page-success and second-page-omission sequence, so that a test of an isolated empty page cannot falsely validate the fix.
33. As a maintainer, I want the real parser, collection coordination and database behavior to be exercised together with controlled browser pages, so that tests prove the user-visible result without repeatedly accessing a live account.
34. As an analyst, I want my existing collection history, monitoring rules and dedicated browser login retained, so that deploying this fix does not require resetting the application.

## Implementation Decisions

1. **Scope and architecture.** Extend the existing native Weibo discovery flow, page-state parser, keyword progress persistence, collection outcome projection and existing collection views. Retain the project-owned dedicated browser and current separation of discovery from content enrichment and report generation.
2. **Primary reproduction.** The required reference sequence is a normal first search page with valid posts and a next-page link, followed by a second page with no post cards, an omission notice and a view-all entry. Recognition operates on the current page, including later pages; it must not assume that an empty current page invalidates earlier results.
3. **Recognition conditions.** Confirm the current search context, allow the existing bounded readiness wait, and require both a platform omission notice in the search-results area and a valid view-all entry while post cards are absent. The screenshot guides the case but is not sufficient to invent exact DOM selectors; verify the rendered result-area structure during implementation.
4. **State precedence.** Recognized login, security verification and rate-limit barriers take precedence over omission handling. Valid post cards follow ordinary collection even when accompanied by an omission notice. A recognized omission notice with a usable entry takes precedence over treating the same cardless result area as a generic no-result message. Other blank pages retain existing unknown-page handling outside the scoped recovery flow.
5. **Bounded automatic recovery.** Follow the page-provided view-all target at most once per keyword per collection attempt. Use normal dedicated-browser navigation; do not synthesize a different search, alter search terms, introduce platform API discovery, or continuously refresh. Existing native navigation to a validated rendered link target is sufficient; a separate browser-control stack is unnecessary.
6. **Target validation.** The entry must resolve to HTTPS on the expected Weibo search host and search path, preserve the current keyword, and represent the page's view-all action. The observed entry uses `nodup=1` and may omit a page number. Validate this entry separately from an ordinary next-page link. Missing, ambiguous or invalid targets do not authorize navigation and retain normal diagnostic handling.
7. **Progress retention.** Switching presentation mode does not create a new keyword attempt, clear prior discoveries or reset the current keyword's deduplication and count state. Previously saved posts stay visible throughout the operation. Following an entry that starts at the view-all first page is allowed without treating it as a fresh collection.
8. **Identity and counts.** Preserve existing canonical post identity and URL deduplication. A post encountered again in the same keyword during recovery must not generate an additional observation that inflates new, repeated or total counts. Existing distinctions between different keyword matches and content already in the library remain unchanged; the configured per-keyword limit continues to count distinct posts encountered within that attempt, not only newly inserted library rows.
9. **Stopping rules.** Stop normally when the configured distinct-post limit is met, a valid result page has no next page, or the platform explicitly confirms no further results without a conflicting omission state. Never use a displayed estimate such as “40 results” as a required target or proof of complete coverage. A terminal empty page after earlier results means no additional results at that point; it does not erase the earlier keyword results.
10. **Pagination after recovery.** Preserve the validated view-all search context across subsequent next-page links. Support a view-all entry without a page number followed by numbered pages. Detect semantically repeated destinations, including equivalent first-page URL forms, so query ordering or an explicit first-page number cannot defeat loop detection. A keyword cannot repeatedly re-enter view-all recovery after switching modes.
11. **Resource limits.** Recovery uses the same attempt-wide page, browser-request and time budgets, including the outer service deadline. Revisited pages and their requests consume these budgets. Keep the existing bounded polling policy unless the real reproduction requires a justified adjustment; do not add user settings. Budget exhaustion, cancellation and browser unavailability keep their existing stop and recovery behavior instead of being converted to keyword-level omission warnings.
12. **Unresolved recovery.** After a valid view-all transition, if the result area remains cardless or in the omission/loading state through bounded waiting, record the current keyword as incomplete and proceed to the next keyword. Repeated omission recovery targets are likewise bounded and must not loop. Recognized empty or valid result pages use ordinary stopping rules. Authentication barriers, wrong search context, malformed result cards and other distinct failures retain their existing handling; the omission branch must not broadly swallow them.
13. **Keyword completion contract.** Extend the existing collector-to-service keyword-end reporting to carry an explicit distinction between normal completion and keyword collection incomplete, plus a structured cause and observed distinct-post count. Do not submit an incomplete keyword as an ordinary successful completion merely to pass existing sequential progress checks.
14. **Durable keyword outcomes.** Persist the keyword identity/position, attempt association, ended outcome, reason and retained count before advancing. Progress and recovery calculations must distinguish “this keyword has ended and was advanced past” from “this keyword successfully completed.” Reuse and extend the existing keyword progress mechanism rather than introducing a second workflow engine.
15. **Pause and resume consistency.** If a later keyword encounters a real platform barrier, keep earlier incomplete outcomes and saved results. Explicit continue resumes through the established keyword checkpoint mechanism, without automatically revisiting earlier keywords already ended as incomplete or relabelling them successful. The currently interrupted keyword follows existing restart semantics; durable page-by-page resume and cross-attempt quota redesign are outside this fix.
16. **Collection outcome.** When processing reaches the end with one or more incomplete keywords, expose a terminal outcome with incomplete coverage rather than plain full success or successful empty collection. It must not leave the batch waiting for manual action solely because this scoped recovery failed. Reuse the existing batch completion-with-failures capability where appropriate, and extend attempt/item contracts only as needed to express the distinction. If a separate global stop occurs later, its paused or failed state remains primary while earlier keyword diagnostics remain visible.
17. **Existing views and contracts.** Add structured incomplete-keyword details to the existing collection progress/detail responses and consume them in the current UI. Show a short explanation, affected keywords and retained counts; successful recovery may appear in the normal progress record without a dialog. If all keywords are incomplete, report that fact even when zero posts were saved. All existing consumers of the collection outcome must handle the new distinction without inventing new report-generation or scheduler policy.
18. **Data compatibility.** If outcome persistence or status constraints require a database change, use a forward migration and update related schemas and projections together. Existing historical outcomes stay unchanged, and old records without the new diagnostics receive an empty/default diagnostic representation. Preserve collection history, content, monitoring rules, settings and the dedicated browser profile. Fresh and upgraded databases must support the same new behavior.
19. **Error wording.** Do not label the omission-only scenario as a login or verification problem. If generic unknown-page text is touched in the shared presenter, describe inability to identify the page neutrally; reserve definite login/security guidance for recognized barriers. This is a targeted wording correction within existing collection views, not a wider UI redesign.
20. **Retry surface.** Add no dedicated incomplete-keyword retry button, preference or modal. Users may start another collection through existing controls; new collection history and prior incomplete history remain separate, and existing library deduplication still applies.

## Testing Decisions

1. **Primary seam.** Start collection through the same local application entry used by the frontend, exercise the real native collector, page parser, coordination and temporary SQLite database, and inspect persisted results and collection details. Substitute the external browser/page responses rather than replacing the collector with pre-parsed success outcomes. For the user this means testing a complete collection, not requiring them to operate or understand an API.
2. **Existing prior art.** Reuse the native Weibo discovery fixtures that supply rendered pages, the existing batch pause/resume and result-union tests, and the current collection-detail UI tests. Keep most coverage at the application boundary; add focused parser or URL-validation cases only for edge combinations that are cumbersome to express there. There is no need for a new test framework.
3. **Required continuous regression.** Configure a three-post keyword limit. The normal first page provides posts A and B plus a next-page link; the second page contains no cards but does contain the platform omission notice and valid view-all entry; the view-all first page repeats A and B, and subsequent results provide C. Assert that the same keyword retains progress, A/B are saved only once and do not inflate any counts, C is saved, the limit remains three and collection completes without an erroneous manual pause. The first page must contain fewer posts than the limit so the test actually exercises the second page.
4. **Trigger boundaries.** Verify delayed normal posts do not prematurely trigger recovery, posts plus an omission notice use ordinary collection, plain blank/loading pages without omission evidence keep unknown-page handling, and standard no-result pages without omission evidence end normally. Text inside a user's post, hidden or unrelated page areas, or a missing/invalid entry must not trigger navigation.
5. **View-all navigation.** Exercise an entry without a page number, subsequent pagination carrying view-all context, equivalent first-page URLs, repeated links, wrong keywords, wrong hosts/paths and incompatible redirects. Assert that valid links reach the intended pages and invalid or cyclic routes do not cause unbounded navigation. Do not hard-code exact CSS selector invocation or internal helper call counts as the assertion.
6. **Actual failure fallback.** After saving first-page results, serve the omission-only second page and a persistently unresolved view-all page. Assert bounded recovery, preserved content, a durable incomplete keyword outcome and successful execution of the next keyword. Assert that the batch terminates with incomplete coverage rather than remaining paused or reporting full success.
7. **Outcome combinations.** Cover one incomplete keyword among completed keywords, all keywords incomplete with no saved content, all keywords incomplete with some content, and recognized no-additional-results after earlier successes. These cases must remain distinguishable through the public collection details and counts.
8. **Deduplication and limits.** Cover URL aliases, content already in the library, matches across keywords, a limit already met on the first page, and page/request/time exhaustion during recovery. Opening view-all must neither reset the remaining result allowance nor replenish the attempt budget. Preserve existing pause behavior for genuine budget exhaustion and browser failure.
9. **Manual barriers.** Present login, security verification and rate-limit states before and after a recovery transition. Assert that those states override omission handling, pause the batch, preserve discoveries and require explicit continue. No automatic interaction may complete a challenge.
10. **Durability and checkpoints.** Let one keyword end incomplete and the next encounter a manual barrier. Reopen the stored application state, explicitly continue and verify that the later interrupted keyword resumes under existing rules, the earlier incomplete keyword is not silently retried or marked successful, and its reason/results remain visible after the rest finishes. Prior failures and earlier attempts remain intact.
11. **UI contract.** Use the existing collection pages to verify that structured incomplete diagnostics render with the correct keyword and retained count, successful recovery does not add a blocking dialog, and all-incomplete collection is not displayed as successful empty collection. Verify status handling in existing polling/control code so terminal incomplete coverage does not keep polling as if it were running or display an inappropriate continue button.
12. **Upgrade and compatibility.** If persistence changes, use a representative prior-schema fixture to verify a forward upgrade, historical record preservation, empty default diagnostics, referential integrity and parity with fresh databases. Check existing consumers of run/batch outcomes against the updated contract; no broader automated-workflow redesign is required.
13. **Local verification.** Run relevant backend discovery, recovery and migration tests, frontend collection tests and required static checks. Broaden validation if shared status changes affect other consumers. Automated tests must not repeatedly access a live Weibo account. A local dedicated-browser acceptance check may validate the real rendered structure and ordinary navigation; encountering an actual challenge requires the established user-mediated pause.

## Out of Scope

- Supporting additional platforms or restoring MediaCrawler.
- A generic framework for automatically recovering every unknown or empty page.
- Bypassing login, security challenges or rate limits; changing browser fingerprints or copying credentials from the daily browser.
- Replacing browser discovery with direct platform API calls, buying a collection service or introducing another browser automation stack.
- Treating a displayed result estimate as a promise to retrieve all platform matches, or raising the user's configured result limit.
- Unlimited refreshing, repeated view-all switching, automatically increasing execution budgets or silently retrying a whole batch.
- A new dedicated retry UI, settings page, broad status dashboard or collection navigation redesign.
- New page-level durable resume semantics or changes to the established quota behavior across separately requested collection attempts.
- Changing content enrichment, media downloading, comment collection, LLM summaries, report prompts or report-generation orchestration.
- Deleting or resetting runtime databases, existing content, collection history, backups or browser profiles; repairing unrelated Chrome startup locks.
- Rewriting historical failure records to claim that past attempts succeeded.

## Further Notes

- This specification synthesizes the accepted Q1/Q2 decisions and the user's subsequent clarification that page 1 was successful and the problem appeared on page 2. The user delegated remaining presentation and retry details to the implementer and asked to focus on fixing collection; no additional interview is required.
- The test approach follows the repository's established real-business-flow and temporary-database pattern and was described while drafting this specification. It does not require the user to confirm technical interfaces or supply a new testing design.
- The representative screenshot's view-all destination included `nodup=1`; selectors and destination details must be verified against the rendered page when implementing. Do not assume the screenshot's empty area alone proves that all content was omitted or that the DOM has finished loading.
- The current parser waits approximately five seconds through its default poll sequence before classifying an unrecognized page. The specification requires bounded readiness and correct state recognition, not a blanket increase of this timeout as a substitute for implementing the missing branch.
- The existing keyword progress model records successful completions and uses them for sequential admission and recovery checkpoints. Persisting incomplete-but-ended keywords is therefore a necessary part of the targeted fix, not just a frontend label change.
- The fix respects the accepted explicit-resume, discovery/analysis separation and Weibo-only decisions. Keyword-level omission recovery is a bounded ordinary search navigation; explicit platform barriers still follow the existing manual pause policy.
- The discussion is recorded in `discussion.md` alongside this specification. This publication changes documentation only; implementation and live acceptance are subsequent work.

## Implementation

- Added bounded recognition and one-time `nodup=1` recovery for Weibo omission pages, preserving per-keyword deduplication and existing execution budgets.
- Added durable keyword diagnostics and batch aggregation so unresolved recovery continues through later keywords without being shown as login failure or successful empty coverage.
- Added parser, collector, migration, API-contract, batch, and UI regression coverage; the implementation is complete and ready for release validation.
