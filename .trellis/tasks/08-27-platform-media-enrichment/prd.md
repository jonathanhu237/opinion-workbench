# 平台正文与媒体获取

## Goal

Provide bounded, identity-verified full text and actual image/video inputs for an already collected post. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R1, R5, R6). No model API is needed to validate this child.

## Requirements

- Add narrow downstream enrichment for Toutiao, Weibo, Kuaishou, Douyin and Xiaohongshu. Do not broaden existing search adapters into generic crawling.
- Reuse the user's borrowed browser context, verify the exact stored source identity, and close only owned tabs. Authentication/challenges remain manual.
- Distinguish no media, complete actual media, inaccessible media, unknown structure and limit/format failures. A search snippet/cover cannot stand in for full text/video.
- Transfer bounded local media using opaque handles, not raw state, tokens, signed URLs or large IPC Base64 payloads. Keep platform authentication in the worker.
- Apply the parent's inline input limits without silently truncating, transcoding or uploading anything to an AI provider.

## Acceptance Criteria

- [ ] Each platform has fixture tests for identity, text/media extraction and unavailable/changed-page behavior.
- [ ] Each platform has a live exact-source gate with evidence of actual supported media, not only an `unavailable` result. Unverified formats/platform outcomes stay explicitly unverified.
- [ ] No-media, missing media, cover-only, oversized, unsupported container and audio-not-established inputs cannot be marked complete audiovisual evidence.
- [ ] Malicious URLs, redirects, private hosts, paths, symlinks, wrong IDs, duplicate/out-of-order IPC, oversized files and hash mismatch fail closed without leaking data.
- [ ] Browser contention, cancellation, login and challenge preserve user tabs/context and clean only owned temporary assets.
- [ ] Existing authentication/search/open-result protocols and their regression suites still pass. No paid API request is made by enrichment tests.

## Dependency and Exclusions

- No implementation dependency on settings; execution is scheduled after it to keep review sequential. Produces the typed `EnrichedContent`/temporary-media contract consumed within manual summary generation, not by a standalone screening step. The 2026-08-27 search-first revision does not change the extraction/ownership limits; downstream final review is pending.
- Source audit and evidence anchors: parent `research/platform-media-plan.md`. Protocol/media budget: parent `design.md` section B and `research/model-transport-contract.md`.
- No comments, author profiles, full browser storage reads, CAPTCHA bypass, generic crawler loops, DRM/HLS/DASH handling, media conversion, OSS or new UI dashboard.
