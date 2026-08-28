# Existing Collection-to-Analysis Boundary

Inspected locally on 2026-08-27. This is repository research for planning, not a claim that media extraction or model integration has been implemented or live-tested.

Historical record: the later search-first decision supersedes the separate `AI 筛选`/re-screen actions below. The approved implementation uses one `生成汇总` action, with per-item analysis/reuse inside it. Configuration and two-list rules have since shipped; schema is v10. Read the current parent PRD/design and `product-integration-readiness.md` for authoritative scope/baseline; preserve these old anchors as evidence, not current implementation instructions.

## Verified Current Behavior

- `backend/src/longtian_api/search_platforms.py:6` defines the five supported search platforms: Toutiao, Weibo, Kuaishou, Douyin, and Xiaohongshu.
- `backend/src/longtian_api/schemas/search_runs.py:91` exposes search results with `title` (up to 300 characters), `snippet` (up to 1,000 characters), content identity/type, masked publisher fields, publication display text, and a canonical page URL. There is no image list, video input, or separate full-text field.
- `backend/src/longtian_api/repositories/search_runs.py:49` confirms the persistence input has the same limited content projection. Search snippets must not be described as guaranteed full original text.
- `third_party/MediaCrawler/tools/search_worker_protocol.py:97` and `backend/src/longtian_api/services/media_crawler_auth_worker.py:1020` define/validate a strict normalized search-item protocol. Adding media is a cross-boundary change, not just appending arbitrary fields to a response.
- `.trellis/spec/backend/product-search-guidelines.md:155` explicitly confines current product adapters to search. Detail, comment, profile, and media fetching are outside their existing contract. Xiaohongshu's result-open flow uses ephemeral tokens internally without persisting them; a saved canonical URL does not guarantee later authenticated retrieval of the media.
- `backend/src/longtian_api/schemas/monitoring_rules.py:21` only supplies a name, search terms, and enabled state. A geographical/topic analysis brief is not an existing configuration field.
- `backend/pyproject.toml` declares FastAPI as the application dependency. Inspection of `backend/src` found no existing domestic-model integration to reuse. This does not imply the user lacks an API account.

## Planning Consequences

1. Preserve the current search and deduplication contracts. Add an explicitly scoped content/media enrichment step feeding analysis; do not silently make search download every result.
2. Determine the model API before finalizing the media envelope, because accepted modality combinations, audio handling, upload forms, and limits depend on that API.
3. Carry stable stored content references through enrichment, classification, and summary. Model-generated links or unsupported claims cannot substitute for those references.
4. Represent incomplete input separately from a successful unrelated-content decision. Do not claim the model analyzed media that was never supplied.
5. Keep provider credentials, platform Cookies, browser state, and ephemeral authenticated URLs out of public analysis records and logs. No live upload or paid API call has been made during this research.

## Confirmed Filter-First Ordering

The user clarified that AI first filters search results for public-opinion relevance, and only relevant results proceed to the next stage. This is a relevance decision, not a request to run full risk analysis on every collected item.

Keep the original search source set intact and store the screening outcome/reason separately. A proposed minimal semantic result is relevant, unrelated, or uncertain; technical failure is execution state, not an unrelated verdict. Final field names and downstream handling still belong in the design.

The earlier request for direct text/image/video input still applies. Do not silently substitute a title-only classifier that permanently discards posts before their media can be examined. Current adapters do not provide that media, so the explicit enrichment boundary remains necessary. Screening and any downstream summary can reuse the same saved model configuration; no additional provider or classifier cascade is implied.

The user subsequently approved manual initiation through an `AI 筛选` action on the collection results page. This is not authorization to automatically start model calls when a collector finishes or when the page opens.

## Repeated-Content Evidence

`backend/src/longtian_api/repositories/search_runs.py:196` (`observe_item`) reuses an existing content ID on `(platform, platform_content_id)` but updates non-empty title/snippet and other observed fields on subsequent searches. Therefore a content ID is a deduplication identity, not proof that the complete model input is unchanged.

The same post can also appear under different monitoring rules. Screening reuse must include the monitoring context, observed input version, and model/prompt identity rather than globally applying the first verdict for that post. UI pagination and the existing `new`/`repeated` collection labels do not establish whether AI screening is reusable.

The user approved reusing compatible results and offering an explicit re-screen action. Reusing a saved snapshot avoids repeated model calls but cannot establish that an unvisited source post or its media has not changed; continuous old-post polling is not part of this behavior. Observed changes make a cached result unsuitable for the next manually started screening, not permission to start a new job automatically.

## Follow-through

- Source inspection is captured in `platform-media-plan.md`; later live validation must prove each claimed retrieval route without broadening to comments or profiles.
- Provider documentation and the proposed bounded inline transport are captured in `model-transport-contract.md`; actual audiovisual interpretation remains a separately invoked live gate.
- Parent `design.md` now specifies additive database/API/UI boundaries. The user approved a separate manual summary trigger, so no additional automatic analysis stage is implied.

The relevant previous decisions were already available in the current conversation, archived batch-collection PRD, and backend specifications, so additional conversation-log retrieval was unnecessary.
