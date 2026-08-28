# 平台正文与媒体获取

## Goal

Provide bounded, identity-verified full text and actual image/video inputs for an already collected post. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R1, R5, R6). No model API is needed to validate this child.

## Background and Confirmed Facts

Search is metadata-only, not full-content acquisition. The 2026-08-28 isolated probe obtained three real Douyin MP4s from exact canonical pages, but no product extractor or durable media protocol exists. Its manually acquired bytes, temporary helper and deleted media files are not reusable production cache. The original source audit and the post-probe readiness record are complementary evidence, not five-platform acceptance.

## Requirements

- **M1 — Narrow acquisition.** Add downstream enrichment for Toutiao, Weibo, Kuaishou, Douyin and Xiaohongshu. Do not broaden existing search adapters into generic crawling. Begin with the observed Douyin canonical-page/player path, verifying ID, caption completeness and real bytes; validate each other platform independently.
- **M2 — Browser ownership.** Reuse the user's borrowed browser context, verify the exact stored source identity, and close only owned tabs. Authentication/challenges remain manual. Preserve current search/batch/account/open/recovery mutual exclusion; failure must not strand browser ownership or reclaim a user tab.
- **M3 — Honest coverage.** Distinguish no media, complete actual media, inaccessible media, unknown structure and limit/format failures. A search snippet/cover cannot stand in for full text/video. A blob source or unsupported stream is not silently converted, re-recorded or replaced with a cover.
- **M4 — Safe handoff.** Transfer bounded local media using opaque handles, not raw state, tokens, signed URLs or large IPC Base64 payloads. Keep platform authentication in the worker; prove size, MIME, hashes, path containment and owned cleanup on both sides.
- **M5 — Bounded inputs only.** Apply the parent's inline input limits without silently truncating, transcoding or uploading anything to an AI provider. The probe's 90-second bound is not a product entitlement or automatic product limit; inherit the reviewed transport contract rather than copying the standalone harness.

## Acceptance Criteria

- [x] Each platform has fixture tests for identity, text/media extraction and unavailable/changed-page behavior (M1, M3). See the 2026-08-28 maintained-product checkpoint; fixtures do not prove live completeness.
- [ ] Each platform has a live exact-source gate with evidence of actual supported media, not only an `unavailable` result. Unverified formats/platform outcomes stay explicitly unverified; three manually obtained Douyin samples do not satisfy the other platform gates (M1).
- [ ] No-media, missing media, cover-only, oversized, unsupported container and audio-not-established inputs cannot be marked complete audiovisual evidence (M3, M5).
- [ ] Malicious URLs, redirects, private hosts, paths, symlinks, wrong IDs, duplicate/out-of-order IPC, oversized files and hash mismatch fail closed without leaking data (M4).
- [ ] Browser contention, cancellation, login and challenge preserve user tabs/context and clean only owned temporary assets; current manual recovery retains its ownership semantics (M2, M4).
- [ ] Existing authentication/search/open-result protocols and their regression suites still pass. No paid API request is made by enrichment tests (M1, M2, M5).

## Dependency and Exclusions

- No implementation dependency on settings; that child is already implemented/checked. Produces the typed `EnrichedContent`/temporary-media contract consumed within manual summary generation, not by a standalone screening step. No database migration is needed for this child.
- Source audit and evidence anchors: parent `research/platform-media-plan.md`. Protocol/media budget: parent `design.md` section B and `research/model-transport-contract.md`.
- No comments, author profiles, full browser storage reads, CAPTCHA bypass, generic crawler loops, DRM/HLS/DASH handling, media conversion, OSS or new UI dashboard.

## Artifact Status

Converged on 2026-08-28 with parent requirement mapping intact, explicit M1–M5 acceptance and design/execution/curated contexts refreshed from the real probe. The user approved the latest final summary with `来`, and this child was activated as `in_progress`. Fork/backend implementation and isolated checks are authorized; further scope changes still need review. See `verification.md` for actual acceptance, separate from planning evidence.
