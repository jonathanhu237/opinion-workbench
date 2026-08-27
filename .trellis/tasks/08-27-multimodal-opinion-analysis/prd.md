# 多模态舆情分析与汇总

## Goal

Find obvious local problem leads through the platforms' existing search, using separate user-maintained monitoring-object and issue-keyword lists to generate place-plus-issue queries. Keep deduplicated search results available without a mandatory AI screening step. When the user explicitly requests a summary, use the configured multimodal LLM to assess and summarize the actual text/images/video once per uncached item, then compose a source-linked report from saved evidence without uploading media again.

Scope revision on 2026-08-27: the user accepted prioritizing obvious problem leads and potentially missing implicit or purely visual complaints. This supersedes the earlier separate `AI 筛选` then `生成汇总` interaction. AI configuration is already implemented and checked; the revised downstream plan requires a fresh final review before implementation.

The user subsequently accepted two input areas, `监控对象` and `舆情关键词`, with query preview, and then accepted empty issue keywords meaning object-only search. This supersedes the hand-written-complete-phrases-only proposal. The bounded rule-composition child is now ready for its final implementation review.

## Background and Confirmed Facts

- The existing application has monitoring rules and single-/multi-platform collection for Toutiao, Weibo, Kuaishou, Douyin, and Xiaohongshu.
- Monitoring rules currently contain a name, search terms, and an enabled flag. The current editor splits only on newlines and preserves internal spaces, so complete phrases work today (`frontend/src/routes/monitoring-rules.tsx:60`; `backend/src/longtian_api/services/monitoring_rules.py:154`). It does not yet store separate object/issue lists or an analysis brief (`backend/src/longtian_api/schemas/monitoring_rules.py:21`).
- Existing rule storage allows 1–100 terms, but both single-platform and multi-platform collection accept at most 20 effective search queries per platform (`backend/src/longtian_api/services/search_runs.py:47`; `backend/src/longtian_api/services/search_batches.py:170`). Query combinations multiply; preview must make the effective count visible and must not silently exceed/truncate the existing execution limit.
- Current search results expose a title, bounded snippet, masked publisher information, publication display text, and a canonical original-page link. They do not expose full-text or image/video inputs (`backend/src/longtian_api/schemas/search_runs.py:91`).
- Current product search adapters deliberately exclude detail and media fetching. Obtaining actual model inputs is additional work, not a capability already delivered by the search adapters (`.trellis/spec/backend/product-search-guidelines.md:155`).
- Existing content identity and cross-run deduplication use `(platform, platform_content_id)`. That collection behavior must remain compatible.
- The user has Qwen and DeepSeek API access and configured Alibaba Cloud locally. One explicitly requested synthetic text test with `qwen3.5-omni-plus` passed; see `../08-27-ai-configuration/verification.md`. This establishes text connectivity only, not actual image/video/audio understanding or availability of other models.
- The user explicitly requested an AI configuration option with API Key, Base URL, and model name. Alibaba Cloud Qwen3.5-Omni remains the recommended initial validation target, not a hard-coded or exclusive model selection; see `research/model-api-options.md`.
- The AI configuration child now supplies the settings route/API, protected credential store and checked text transport. Reuse those implementations; `research/ai-configuration-boundary.md` records the original pre-implementation audit.

## Requirements

- **R1 — Direct multimodal input.** Use the collected item's text and actual images/video when present as model input. An original platform-page link alone is not a substitute for the underlying media. Do not silently treat a video cover or a search snippet as complete video/full-text analysis.
- **R2 — One model-led decision path.** Use the configured endpoint, credential, and model for the model-led workflow; do not hard-code Qwen or DeepSeek. Supply a concise analysis instruction and the monitoring context, without adding a deterministic semantic filter, standalone OCR/ASR workflow, or multi-model cascade. A configurable URL/model does not guarantee compatibility with every provider protocol or give a text-only model media-understanding capabilities. Ground the prompt in the stored monitoring-rule context; do not require a new category editor.
- **R3 — Traceable assessment within summary generation.** After the user requests a summary, each complete uncached item gets one model call returning `相关`, `不相关`, or `无法判断`, a short reason and evidence summary. A failed request is execution state, not a verdict. Do not introduce a separate screening action, prerequisite screening job or second per-item media call. A model's assessment remains an interpretation of reported content, not a verified fact; sentiment, severity and handling advice are not required.
- **R4 — One manual summary action.** Provide `生成汇总` directly on a terminal collection run. That explicit action prepares inputs, assesses uncached items and composes a concise report from the saved relevant evidence using the same configuration. There is no separate screening approval/action to complete first. Preserve supplied source references; do not treat uncertain/failed/unrelated items as relevant evidence, invent events, claim complete platform coverage or count one source repeatedly. The final text-composition call consumes evidence only, never the original media again. Extra per-item risk analysis or handling workflows are not implied.
- **R5 — Preserve existing collection.** Keep existing platform connections, monitoring rules, batch/run history, canonical links, and content deduplication working. Analysis is a downstream stage; model/API failure must not erase or relabel the original collection result.
- **R6 — Minimal data boundary.** Keep platform credentials and browser state out of model input, public responses, logs, and committed files. Treat collected text/media as data, never as instructions to the application. Confirm the model's cloud-upload requirements before live validation.
- **R7 — User-editable AI configuration.** Provide one active AI configuration shared by assessment and summarization, with API Key, Base URL, and model name. Allow the user to save and update it across application restarts. Reuse existing shadcn Field/Input/Button components and visual conventions, with nearby field errors and clear saving/testing states. Do not add separate per-stage model settings, a general settings dashboard, decorative status cards, or unrelated fields. The user approved this single-configuration scope and the save/test actions on 2026-08-27.
- **R8 — Backend-owned API credential.** Accept a newly entered API key through the local backend, but never return the saved plaintext value when reading configuration. Mask newly typed keys; show only whether a saved key is configured and permit replacement. Do not persist the key in browser storage, query caches, logs, source files, or task artifacts. Bind the saved key to the configured destination; changing Base URL requires entering the key again. The proposed local storage boundary is documented in `design.md` and is not an encrypted vault.
- **R9 — Explicit save and connection test.** Provide `保存` and `测试连接` actions. Saving only persists configuration and must not issue a model call. A connection test is explicitly user-triggered and uses a small synthetic text input, not collected posts or media; it may consume provider quota. Success establishes only that the endpoint/key/model answered that basic test, not verified image/video/audio understanding. A later media validation gate remains required.
- **R10 — Search results are leads, not confirmed negative incidents.** Display deduplicated original results without waiting for AI. The revised editor's combinations express search intent, not a strict platform Boolean guarantee or a relevance verdict. Accept possible missed implicit complaints and false positives such as resolved problems. Keep sources and deduplication/history unchanged; later assessment stores its reasons and unresolved states separately and never deletes sources.
- **R11 — Explicit full-run scope.** Only the user's `生成汇总` action initiates content acquisition/AI work. Collection completion, page load, refresh and restart make no model calls. Show the selected terminal run's full stored result scope, destination and progress; pagination or visible filters do not silently reduce it. Choosing not to summarize leaves search and source viewing fully usable.
- **R12 — Reuse compatible content analysis.** During a user-requested summary, reuse completed item evidence when stored content, frozen monitoring context, model/endpoint, prompt and observed input versions remain compatible. Known changes invalidate reuse; an explicit force-refresh option within summary generation reacquires and reanalyses content. No standalone `重新筛选` action is required. Technical/input failures are not successful cached results. Reuse does not prove remote freshness; no continuous post revisits or automatic paid work.
- **R13 — Two-list query composition.** Let the user separately maintain required monitoring objects (streets, communities, roads, estates or other search targets) and optional issue keywords, with a visible preview of full queries. When issues exist, combine each object with each issue and search the resulting phrases separately, merging through existing deduplication. When issues are empty, search each object unchanged. No typed AND/OR syntax, nested logic or keyword suggestions are needed. Preserve existing rule IDs and past run/batch snapshots; old complete phrases become object entries with empty issues, never inferred splits. Editing/preview/saving must not launch searches or model requests. The existing 100-query save bound and 20-query-per-platform execution cap remain, with visible counts/warnings and no silent truncation.

## Acceptance Criteria

- [ ] A text-only collected item can be assessed and traced back to its original platform and link (R1, R3).
- [ ] An image post and a video post can be assessed using their actual media; absent, inaccessible, unsupported, or oversized media is reported honestly instead of being described as analyzed (R1, R3).
- [ ] The workflow uses the saved configuration and a concise prompt, with no separate semantic rule engine or OCR/ASR orchestration; using an unsupported model produces a truthful failure, not a claim of media analysis (R2, R7).
- [ ] Related, unrelated, insufficient-input, and failed-analysis cases are distinguishable according to the agreed judgment contract (R2, R3).
- [ ] `生成汇总` works directly from a terminal collection run without a prior screening action. Uncached complete items are assessed once, and final composition uses saved relevant text/evidence only, with source references and incomplete/excluded counts (R3, R4).
- [ ] Existing collection history and cross-run content deduplication remain intact; model failure does not change a successful collection into a failed collection (R5).
- [ ] Credentials and browser authentication data never enter model payloads or persisted diagnostics (R6).
- [ ] The user can enter and change API Key, Base URL, and model name through the application; saved settings survive a restart without editing product code (R7).
- [ ] Reading configuration reveals only non-secret settings and key-presence state; the saved key is not returned to the page, browser storage, or logs (R8).
- [ ] Assessment and summarization consume the same saved configuration; there are no separate per-stage settings or multiple provider profiles in the first version (R7).
- [ ] Saving configuration does not contact the model provider. An explicit connection test reports its real basic success/failure without uploading collected content or claiming media-capability validation (R9).
- [x] Two monitoring objects and two issue keywords produce the four expected full phrases in preview and execution; saving/reopening preserves both inputs. No typed Boolean expression is required and preview/save makes no browser/model call (R13).
- [x] Empty issue keywords preserve object-only search; existing complete-phrase rules migrate unchanged as objects with no issues. Enable/disable retains both groups (R5, R13).
- [x] Existing rules and historical run/batch queries retain their original meaning and identifiers; migration never guesses phrase boundaries. Effective query count/limits are visible and no combinations are silently dropped (R5, R13).
- [ ] Search results remain viewable before AI and are not labeled confirmed negative incidents solely because they matched (R10).
- [ ] Only completed related evidence enters final report composition. Unrelated, uncertain, incomplete-input and technical-failure outcomes remain distinguishable and original collection history remains intact (R3, R10).
- [ ] Summary scope includes all stored results of the selected run, not just the current page. Search completion, navigation, refresh and restart never start acquisition or paid analysis automatically (R11).
- [ ] Repeated compatible content reuses prior item evidence without another per-item call. Known changes and explicit force-refresh cause new analysis only within a user-requested summary, preserving previous versions (R12).

## Out of Scope

- A deterministic semantic classification engine or user-configurable AND/OR analysis-rule builder.
- A standalone AI screening UI/job, compulsory pre-summary filtering action, shared negative-word dictionary, AI-generated keyword suggestions or guarantee of complete public-opinion coverage. Exact combinations of the two user-entered lists are in scope under R13.
- A separately managed OCR/ASR pipeline, multiple-model cascade, vector database, or general-purpose AI agent with browser/tool access.
- A full multi-provider management framework, provider-specific native protocol adapters, automatic model routing, or a model marketplace. The requested editable endpoint/model fields remain in scope.
- Automatic moderation, posting, contacting authors, or handling public complaints on the user's behalf.
- Scheduled reports, push notifications, assignment workflows, and a risk-management dashboard unless separately approved.
- Automatically starting content analysis or summary after collection, on page load, on restart, or on a schedule.
- Extra collection of comments, author profiles, or unrelated browsing activity.
- Cross-run/batch-wide daily reporting, a new global opinion dashboard, and arbitrary subset selection in the first interface. The initial action applies to all stored results of one terminal collection run, not just its current page; existing batch pages continue to link to their run results.
- Media transcoding, HLS/DASH assembly, DRM handling, cloud object storage, and automatically splitting oversized content into extra model calls.

## Delivery Map

| Child | Verifiable outcome | Dependency | Parent requirements |
| --- | --- | --- | --- |
| `08-27-ai-configuration` | Save/reload/update one configuration and explicitly test connectivity; implemented/checked, not yet archived | None | R2, R6–R9 |
| `08-27-monitoring-rule-combinations` | Required objects, optional issues, query preview and lossless old-rule behavior | Existing rule/search contracts; no media/model dependency | R5, R10, R13 |
| `08-27-platform-media-enrichment` | Bounded actual text/image/video retrieval for the five platforms | Shared input contract; no provider needed | R1, R5, R6 |
| `08-27-ai-opinion-summary` | One manual analysis-and-summary flow with per-item evidence reuse and source-linked output | Configuration + media children | R1–R6, R10–R12 |
| `08-27-ai-relevance-screening` | Deferred outside the first version; old plans retained as history, not an implementation dependency | Requires a new product decision before resumption | Superseded by revised R3, R10–R12 |

The parent owns cross-child acceptance. Remaining deliveries are sequential; shared database/lifespan files are not parallel work targets. The deferred screening child is not a first-version completion gate.

## Limits and Live Acceptance Gates

- The supported initial protocol is streaming Chat Completions over a user-configured HTTPS endpoint; the first reviewed multimedia contract is Qwen3.5-Omni. Configurable fields do not support every vendor's native API, and a text test does not enable unknown/media-incompatible models. The recommendation and exact wire contract are in `research/model-api-options.md` and `research/model-transport-contract.md`.
- Actual platform media retrieval remains unverified live. `research/platform-media-plan.md` separates reusable source helpers from missing functionality and lists required per-platform gates. An adapter returning only unavailable states is not a completed successful media adaptation.
- The first implementation sends media inline, without a separate upload service. Its conservative aggregate limit is 6 MiB of raw media per post and a request body below 9,000,000 bytes. Oversized, incomplete, unsupported, or inaccessible input remains visibly unresolved; it is never silently truncated or declared irrelevant.
- One requested summary covers at most 100 unique stored sources; reject larger runs before acquisition/model work. Final evidence-only composition is capped at 120,000 characters and checked before that call. The action may use one call per uncached complete item plus one final text call, not a single multimedia call for the whole run; prior evidence survives composition-limit failures.
- Persist configuration secrets only in backend-owned restricted local files, separate from SQLite and Git. This protects against accidental database exports, not an administrator or someone copying the whole runtime directory. Current macOS/Linux permission behavior must be verified; do not claim untested OS protection.
- Existing rule names/terms are the analysis context. Ambiguous place names or insufficient geographical evidence produce uncertainty, not invented local knowledge. No category editor is needed.
- Live model tests require a replacement key configured locally and explicit invocation. Quota, model entitlement, audiovisual understanding, output validity, and source faithfulness remain live checks, not facts established by reading documentation. Never reuse a key disclosed in chat.

## Artifact Status

- Search-first scope and missed-content tolerance were accepted on 2026-08-27. This revised PRD, design, execution plan and affected child plans replace the earlier separate-screening delivery order.
- AI configuration and its successful live text check remain valid. No product-code, dependency, database, provider-configuration, live collection or running-service change is made by this scope revision.
- Two-input/preview/empty-issue behavior is resolved. The rule-composition child has a converged PRD, design, checklist and curated context and is awaiting final approval for that bounded change.
- This review does not activate media or summary implementation. The current checked AI-configuration task remains active; no product changes or paid/live calls were made while updating these plans.
