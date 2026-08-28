# Product Integration Readiness — 2026-08-28

## Evidence and scope

The user accepted the real-video probe's cost and agreed to proceed toward product
integration. The proposed user-facing workflow is one manual `生成汇总` action on
one terminal collection run, reusable per-item evidence, and final text-only
composition. This record updates planning; it does not authorize more live requests.

Authoritative experiment:
`../../08-27-live-search-ai-acceptance/research/media-cost-probe-verification.md`;
independent review: the adjacent `media-cost-probe-check.md`.

- Three actual Douyin MP4s were sent once each to the saved model. Two judgments
  validated; one completed response failed local final-answer validation. Its exact
  failure and substantive judgment are unknown because the first harness discarded
  the answer. Do not attribute that failure to a Markdown fence.
- A subsequent sample had an exact enclosing JSON fence and passed strict validation
  after deterministic fence removal. Another was plain JSON. Neither needed a repair
  request. The two valid decisions were wrong-locality `irrelevant` and locality-not-
  established `uncertain`; they do not yet prove a successful relevant-item report.
- Provider usage totaled 56,913 tokens across all three attempts, including the local
  failure. The verified standard-price estimate was CNY 0.457083, not an account bill
  or a general per-video price. Video contributed about 96% of input tokens.
- The helper's 90-second, 1,200-output-token and three-attempt limits are probe-only.
  Do not silently promote them into product limits. The approved-for-review product
  bounds remain in `model-transport-contract.md` (6 MiB raw media, request <9,000,000
  bytes, per-item 2,048 output tokens). No arbitrary long-video support is claimed.
- All owned video files were deleted. Private probe reports are not production cache
  rows and must not be imported as completed product analysis.

## Current repository facts

- `backend/src/longtian_api/schemas/monitoring_rules.py:23` already has `monitoring_objects` and optional
  `issue_keywords`; the verified child is archived at
  `../../archive/2026-08/08-27-monitoring-rule-combinations/`.
- `backend/src/longtian_api/database.py:9` declares schema v10. Collection-recovery
  code/specs remain dirty and are not owned by this planning revision. Re-read the
  version and IPC contracts before implementation; no new v9 migration or search-v1
  assumption is valid.
- `backend/src/longtian_api/schemas/search_runs.py:91` remains metadata-only;
  `frontend/src/routes/collection-run-detail.tsx` has no summary action. Its result
  page size is 50 and its filter can be new/repeated/all. Summary scope must come
  from the full frozen run, not these rendered rows.
- `AISettingsService.operation(revision)` supplies the one existing stable lease;
  `AIClient.complete_text` currently returns text and ignores optional usage events.
  Extend its typed internal result compatibly for summary consumers; preserve the
  existing text-test API and DNS/TLS/no-redirect/no-proxy/no-retry protections.
- Five-platform production full-text/media enrichment, analysis persistence/cache
  and summary APIs/UI do not exist yet. Do not describe the probe as shipped support.

## Integration decisions

1. Keep the existing two children. Implement a bounded internal media protocol and
   browser/file ownership first, beginning with Douyin's observed canonical-page
   player path, then verify the other four adapters independently. Each new path
   needs fixtures and an authorized live exact-source check; no generic crawler or
   hidden-state/browser-storage fallback is implied by the probe.
2. Keep one user-facing summary action and all current input/coverage limits. Missing,
   oversized or unsupported media skips that item's model call and remains visibly
   unresolved. A model's valid `uncertain` result is different from acquisition or
   transport failure. Search results and all prior analysis remain intact.
3. Product verdicts remain `relevant | irrelevant | uncertain`. The helper's `related`
   enum and extra observation fields are experiment-specific; do not copy its schema.
4. Normalize only an exact whole-response JSON code fence, then require strict JSON,
   field types, enums, bounds and citations. No prose extraction, semantic repair,
   hidden re-prompt or automatic retry. Keep separate stage/error codes, and retain
   validated usage even if final content validation fails.
5. Production diagnostics retain bounded codes/counts/usage, not the probe's private
   raw-answer excerpts. Check model-generated text for secret leakage before any
   persistence or public rendering. No raw response body in public errors or logs.
6. Reused evidence causes no per-item request, no media reopening and no duplicate
   historical token charge. Composition still uses one new text-only call when
   there is eligible evidence; repeated generation is not universally zero cost.
7. No new cost dashboard or pricing configuration. Store optional provider token
   counts with provenance; absent or invalid usage is unknown, never estimated zero.
   Do not infer currency charges from token totals or hard-code the sample price.

## Remaining acceptance

Use fake transports/assets on Centaurus before local-browser or provider checks.
Prove actual supported text/image/video inputs per platform, at least one valid
relevant result, attribution/source citations, media uploaded once per uncached
item, zero per-item calls on compatible reuse, preserved usage on local parse/schema
failures, and no unsolicited work on refresh/restart/search completion. Model audio
grounding still needs comparison against a known spoken fact absent from caption
and cover; a muxed audio track or audio-token count alone is insufficient.

No cross-run/batch-wide report, automatic push, OCR/ASR pipeline, model manager,
transcoding, provider file upload, cloud storage or billing UI is added. Any material
scope/transport change returns to planning; the current revision awaits final review.
