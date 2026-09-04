# 微博单平台收束与未分析内容统一选材

Status: open

Labels: ready-for-agent

## Problem Statement

当前应用虽然决定先跑通微博，但产品界面、接口、数据库约束、自动任务和采集运行时仍保留小红书、抖音、快手、B 站等平台的概念与兼容分支。用户会误以为这些平台已经可用，开发者也必须持续维护已经决定放弃的 MediaCrawler 适配层、旧平台素材、枚举和测试，增加了采集不稳定性与后续修改成本。

报告生成页面同时把“从未分析”和“分析失败”设计成两个选材选项。对用户而言，两者都没有可用总结，都属于未分析内容。当前额外的失败开关、分裂的数量提示和复杂确认信息，让选材动作显得难以理解。

项目需要明确收束为仅支持微博的本地应用，并把报告选材统一成一个“未分析”概念。实现过程中还需要安全清理旧平台任务、备份数据库和 MediaCrawler，同时保留仍然有效的 AI 配置、监测规则、微博专用 Chrome 登录状态以及必要的数据库升级能力。

## Solution

应用在当前产品版本中只展示、接收、存储和运行微博平台。平台账号页仅展示微博；舆情爬取和自动任务不再让用户选择平台，而是清楚显示或隐含固定的“微博”；服务端只允许合法平台值 `wb`。其他平台的当前产品代码、资源、兼容逻辑和 MediaCrawler 依赖全部移除，未来如需支持其他平台，应按届时需求重新实现。

报告生成页提供一个明确的“选中全部未分析内容”动作。未分析内容包括从未总结成功的条目，也包括最近一次总结失败的条目。页面保留失败数量作为诊断信息，但不再要求用户决定是否包含失败项。每次用户明确提交报告生成时，每个失败条目最多新增一次总结尝试；成功条目不再进入未分析集合，历史失败记录仍保留。

数据库通过向前迁移清理非微博业务数据和旧自动任务，并将当前平台约束收紧为只允许 `wb`。本机旧备份数据库以可恢复方式移至废纸篓，MediaCrawler 子模块及其未使用的兼容入口直接删除，不归档其中的本地修改。清理不得影响当前 AI 配置、监测规则和微博专用 Chrome Profile。

## User Stories

1. As an analyst, I want the product to show only Weibo, so that I know exactly which platform is currently supported.
2. As an analyst, I want the platform account page to contain only my Weibo account, so that unsupported platforms do not distract or mislead me.
3. As an analyst, I want the collection page to state that the collection platform is Weibo, so that the scope of a collection run is unambiguous.
4. As an analyst, I want the collection page to omit a platform selector, so that I cannot accidentally select an unsupported platform.
5. As an analyst, I want a new collection run to use Weibo automatically, so that starting a run requires no redundant platform choice.
6. As an analyst, I want an automatic task to collect from Weibo automatically, so that task setup is simpler.
7. As an analyst, I want automatic-task create and edit forms to omit platform selection, so that they reflect the product's single-platform scope.
8. As an analyst, I want existing obsolete multi-platform automatic tasks removed, so that they cannot execute unexpectedly.
9. As an analyst, I want historical automatic-task run records to remain when they exist, so that genuine operating history is not silently rewritten.
10. As an analyst, I want collection results to retain their platform provenance as Weibo, so that records remain understandable and future-compatible.
11. As an analyst, I want non-Weibo input to be rejected before collection starts, so that invalid work creates no partial data or browser activity.
12. As an analyst, I want the system never to fall back to MediaCrawler, so that collection behavior is predictable.
13. As an analyst, I want Weibo collection to use the dedicated native-browser flow, so that login and security checks can be handled in the browser I control.
14. As an analyst, I want my existing managed Weibo Chrome login profile preserved, so that the product cleanup does not force an unnecessary login.
15. As an analyst, I want the application to pause when Weibo requires login or security verification, so that I can complete the action manually.
16. As an analyst, I want collection to resume only after I explicitly continue it, so that the application does not race ahead while verification is incomplete.
17. As an analyst, I want unsupported platform assets and labels removed, so that no hidden or “coming soon” capability appears to exist.
18. As an analyst, I want current product documentation to describe a Weibo-only product, so that setup and operation instructions match the application.
19. As a developer, I want the canonical platform value to be `wb`, so that every current business invariant has one representation.
20. As a developer, I want database platform constraints to allow only `wb`, so that invalid current-platform data cannot be persisted.
21. As a developer, I want necessary historical migrations preserved, so that an existing local database can still upgrade to the new schema.
22. As a developer, I want non-Weibo compatibility branches removed from active code, so that future changes do not preserve abandoned behavior.
23. As a developer, I want MediaCrawler removed as a source dependency and runtime option, so that the native Weibo collector is the only collection path.
24. As a developer, I want the MediaCrawler submodule metadata removed, so that a fresh checkout does not fetch an unused collector.
25. As a developer, I want current tests and fixtures to model only Weibo, so that the test suite enforces the actual product scope.
26. As a developer, I want historical research and decision documents retained, so that past reasoning remains auditable.
27. As an analyst, I want one button named “选中全部未分析内容”, so that I can prepare all unresolved material without understanding internal status details.
28. As an analyst, I want never-analysed records included in that selection, so that new material is prepared for reporting.
29. As an analyst, I want previously failed records included in that selection, so that transient failures receive another chance.
30. As an analyst, I want no separate “include failed” choice, so that the bulk-selection rule is consistent and easy to predict.
31. As an analyst, I want the page to show “未分析共 X 条”, so that the primary backlog size is immediately visible.
32. As an analyst, I want the page to show how many unanalysed records previously failed, so that I can understand quality risk without making another selection decision.
33. As an analyst, I want failed and never-attempted states to remain distinguishable in row details, so that I can diagnose individual items.
34. As an analyst, I want bulk selection to work across all result pages, so that pagination does not cause material to be missed.
35. As an analyst, I want bulk selection to add eligible records without unexpectedly removing records I selected manually, so that I remain in control of the report material.
36. As an analyst, I want the report dialog to state how many selected records will be retried, so that I understand the effect before submission.
37. As an analyst, I want the report dialog to avoid a second failed-item switch, so that confirmation focuses on the report itself.
38. As an analyst, I want each explicit report submission to retry an eligible failed record at most once, so that one action cannot enter an unbounded retry loop.
39. As an analyst, I want a successful retry to remove the record from the unanalysed set, so that completed work is not repeatedly selected.
40. As an analyst, I want prior failed attempts retained after a later success, so that troubleshooting history remains available.
41. As an analyst, I want one failed record not to prevent the remaining selected records from producing a report, so that partial external failures do not discard useful work.
42. As an analyst, I want each failed item clearly marked, so that I can decide whether to retry it in a later report-generation action.
43. As an analyst, I want report selection to be based on a stable submission snapshot, so that collection changes during processing do not alter the report unexpectedly.
44. As an analyst, I want existing successful summaries to remain reusable in new reports when I explicitly select those records, so that completed analysis work is not wasted.
45. As an analyst, I want “select all unanalysed” to exclude records with a usable successful summary, so that the action means exactly what it says.
46. As an analyst, I want my AI configuration preserved through the migration, so that product cleanup does not change model behavior or credentials.
47. As an analyst, I want my monitoring rules preserved through the migration, so that I do not need to recreate my topics.
48. As an analyst, I want old local backup databases containing abandoned platform data removed from the active workspace, so that stale data cannot be mistaken for current product data.
49. As an analyst, I want backup-database cleanup to be recoverable, so that an accidental target mistake can be reversed.
50. As a developer, I want destructive cleanup to use an explicit target inventory, so that the current runtime database, configuration, and browser profile are protected.
51. As a developer, I want the final migration to be repeatable, so that interrupted upgrades can be diagnosed and safely rerun.
52. As a developer, I want a fresh database and an upgraded database to enforce the same Weibo-only invariants, so that behavior does not depend on installation age.
53. As a developer, I want active source, build configuration, and runtime logs to contain no MediaCrawler execution path, so that abandoned integration cannot return accidentally.
54. As an analyst, I want the application to continue showing historical report and collection records that are valid Weibo data, so that the scope reduction does not erase useful work.

## Implementation Decisions

1. The current product has one legal collection platform: Weibo, represented canonically as `wb`. The `platform` concept remains in domain records for provenance and future extensibility, but active validation and database constraints accept only `wb`.
2. Platform accounts expose exactly one Weibo connection. All other platform cards, icons, status labels, URL validators, form choices, catalog entries and active compatibility branches are removed rather than hidden.
3. The collection form has no editable platform selector. It displays a compact fixed-platform indication and submits a Weibo-only request. The service validates the invariant again and refuses non-Weibo values without creating a run or invoking a worker.
4. Automatic-task create and edit flows have no platform selector. New and updated task definitions are persisted as Weibo tasks by the system. The scheduler receives the same server-side Weibo-only validation as an interactive collection.
5. Existing batch and record boundaries may remain where they serve progress, cancellation, provenance or recovery, but they must not imply that a current run can fan out to multiple platforms.
6. Native browser collection is the only Weibo collector. The MediaCrawler worker, legacy backend selector, fallback logic, submodule configuration, source dependencies and active setup instructions are removed. An obsolete environment setting must not silently reactivate or select MediaCrawler.
7. Browser login and security-verification handling remains user-mediated: the run pauses, reports the required action, and continues only after an explicit user command. The managed Weibo Chrome Profile is outside destructive cleanup.
8. The report-selection domain uses one canonical eligibility rule: a record is unanalysed when it has no usable successful summary. This includes never-attempted records and records whose latest usable outcome is failure.
9. Failed and never-attempted remain separate diagnostic states, but they are not separate bulk-selection policies. Any `include_failed` input, menu choice, compatibility default or alternate preview path is removed from the current application contract.
10. The bulk-selection preview returns the combined unanalysed count and a failed-subset count. User-facing copy leads with “未分析共 X 条” and may add “其中 Y 条曾分析失败”. It must not describe failed records as an optional group.
11. “选中全部未分析内容” computes eligibility against the complete result library, not just the visible table page. It adds eligible record identifiers to the current selection while preserving manually selected eligible records.
12. Report submission freezes the chosen record identifiers into a stable run snapshot. Later collection, pagination, filtering or status changes do not silently change that run's material.
13. During one explicit report-generation submission, each selected failed record receives no more than one new summary attempt. There is no automatic per-item infinite retry inside the run.
14. A successful summary is the authoritative signal that a record has left the unanalysed set. Earlier failed attempts remain as history and do not make that record eligible again while a usable success exists.
15. Item-level failures are recorded and surfaced without aborting all other selected items. Report generation continues with successfully prepared material according to the existing partial-success policy.
16. The database upgrade first removes obsolete non-Weibo business rows and the four known disabled multi-platform automatic-task definitions, then rebuilds or tightens current platform constraints to accept only `wb`. Referential cleanup is transactional and ordered so that no orphaned rows remain.
17. The known obsolete automatic-task definitions are the four locally identified multi-platform tasks. Their definitions are removed; existing automatic-task run history is not broadly deleted. If a referenced task has run history, the migration must preserve the historical record or stop with a clear migration error rather than silently breaking referential history.
18. Existing valid Weibo collection data, reports, AI configuration and monitoring rules are preserved. The current runtime database is never treated as a disposable backup file.
19. The 23 identified backup SQLite databases containing obsolete multi-platform data are cleaned using an explicit, reviewed inventory and moved to the operating system's Trash instead of being permanently erased. The operation records which files were moved and must exclude the runtime database and browser profile directories.
20. The dirty MediaCrawler working tree is intentionally not archived or migrated. Removing the submodule during implementation is the authorized outcome, but the removal must be limited to that exact submodule and its repository metadata.
21. Historical research, prior specifications and ADRs remain as historical evidence even when they mention other platforms or MediaCrawler. Current product documentation, setup commands and architecture guidance are updated to point only to the native Weibo path and the superseding decision.
22. Historical schema migrations needed to upgrade an existing local database remain intact even if they contain old platform values. A new final migration establishes the current invariant; fresh installs and upgraded installs converge on the same schema and behavior.
23. Current application fixtures, examples and test data remove non-Weibo product cases. Purpose-built migration fixtures may still contain old platform values solely to prove that the upgrade cleans them correctly.
24. No compatibility API is retained for local callers that submit other platforms or the former `include_failed` option. Invalid obsolete input produces an explicit validation error and no side effects.

## Testing Decisions

1. Tests assert externally visible behavior and persisted outcomes, not internal helper calls or implementation structure.
2. The primary seam is the complete local application boundary backed by a real temporary SQLite database. Browser automation, Weibo network responses, media downloading and LLM calls are replaced with controllable test doubles so that business behavior is deterministic without live accounts or paid services.
3. A single end-to-end business-flow suite should cover platform discovery, interactive collection creation, automatic-task creation, report selection, summary attempts and report completion through the same service or HTTP boundaries used by the application.
4. Platform behavior tests verify that the product catalog exposes only Weibo, collection and automatic tasks persist `wb`, and obsolete platform input is rejected before database rows or worker activity are created.
5. Report-selection tests seed never-attempted, currently failed and successfully summarised records. They verify the combined unanalysed count, failed subset count, cross-page bulk selection, additive selection behavior and exclusion of records with a usable success.
6. Report-run tests verify that one explicit submission creates at most one new attempt per eligible failed item, that one item failure does not prevent successful items from continuing, that later success exits the unanalysed set, and that historical failures remain queryable.
7. Snapshot tests at the business-flow boundary verify that records collected or updated after submission do not alter the selected material for an active report run.
8. Focused page interaction tests cover only critical user-visible contracts: the single Weibo account card, fixed Weibo collection display, lack of platform controls in automatic-task forms, the “选中全部未分析内容” action, count copy and confirmation retry count.
9. Migration tests use a representative pre-upgrade database containing valid configuration, monitoring rules, Weibo rows, non-Weibo rows and obsolete automatic tasks. They verify transactional cleanup, preservation of valid configuration and Weibo data, removal of obsolete product data, lack of orphaned references and rejection of new non-`wb` values.
10. Fresh-database tests verify the same `wb`-only constraints as the upgraded-database tests.
11. Cleanup validation uses a temporary filesystem fixture and an explicit manifest to prove that only listed backup databases are moved and protected paths remain untouched. The actual one-time local cleanup is separately verified by reviewing the resulting inventory; tests must not operate on the user's live files.
12. Repository validation verifies that the active build and runtime do not require the MediaCrawler submodule, do not expose a legacy backend choice and do not import its worker. Historical documents are excluded from this assertion by design.
13. Existing integration-test patterns that exercise the application against temporary SQLite storage are preferred. Narrow unit tests are added only for state-transition edge cases that cannot be observed reliably through the primary seam.
14. Live Weibo collection is a manual acceptance check, not a required automated test. It verifies the dedicated Chrome Profile, pause/continue verification flow and successful native collection without risking repeated automated login challenges.

## Out of Scope

- Reintroducing Xiaohongshu, Douyin, Kuaishou, Bilibili or any other platform.
- Designing a generic multi-platform collector framework in anticipation of future platforms.
- Preserving, packaging or documenting the dirty local modifications inside MediaCrawler.
- Maintaining compatibility for callers that still submit old platform values or the former `include_failed` selection flag.
- Collecting comments. The current collection scope remains search results, post text, images and video where available.
- Redesigning LLM prompts, report-writing algorithms, AI-provider configuration or media-cache retention policy.
- Redesigning the automatic-task scheduler beyond fixing its collection platform to Weibo and cleaning obsolete task definitions.
- Deleting historical research documents, ADRs or prior specifications that explain earlier decisions.
- Automatically running a complete collection-and-report workflow from one click; that orchestration remains a later automation concern.
- Guaranteeing that live Weibo pages, authentication or anti-abuse controls will never change.

## Further Notes

- This specification supersedes the active product assumptions in the earlier collector-redesign specification where they conflict, especially the optional inclusion of failed items, multi-platform UI compatibility and deferred MediaCrawler removal. Earlier documents remain historical records.
- Read-only inspection found no current search contents, collection runs, batches, report generations or automatic-task runs in the runtime database. It found four disabled multi-platform automatic-task definitions. These observations justify the selected cleanup path but do not replace migration safeguards.
- Read-only inspection identified 23 obsolete backup SQLite databases for recoverable cleanup. Implementation must resolve and review the exact paths immediately before moving them because the workspace may change after this specification is published.
- Destructive cleanup is authorized by the settled discussion but is not performed while publishing this specification. It belongs to the implementation task and must report what was removed or moved and how the backup files can be recovered.
- The test seam described above was presented before publication: full local business behavior with a real temporary database, controllable substitutes for browser/platform/LLM dependencies, focused page checks and dedicated migration/cleanup validation.
