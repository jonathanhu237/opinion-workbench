# 舆情手动汇总

## Goal

Let the user click `生成汇总` directly from a terminal collection run, optionally turning search-first candidate leads into a concise source-linked report. The same operation assesses each uncached complete post once, saves reusable evidence, then composes text without uploading media again. No independent screening step is required. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R1–R6, R10–R12, R14).

## Background and Confirmed Facts

The user accepted search-first scope and possible missed implicit complaints on 2026-08-27, then the real-video probe's cost and product-integration direction on 2026-08-28. Configuration and rule composition already exist. The probe made no final composition call and produced no product cache or summary UI. One local output failure plus a later valid fenced response motivate strict parsing and retained usage, not automatic repair requests.

## Requirements

- **S1 — Explicit action.** Manual trigger only; search completion, route entry, refresh and restart never generate analysis or a summary. Original results remain usable without AI.
- **S2 — Immutable full-run scope.** Freeze all unique stored results of one terminal collection run and its historical rule context, regardless of UI pagination/filter. Show the destination, source count and media-upload/quota boundary before starting. Later collection recovery cannot rewrite that snapshot.
- **S3 — One strict judgment.** Enrich complete uncached inputs with actual text/images/video and make one per-item call returning decision, reason and evidence. Retain `relevant | irrelevant | uncertain` outcomes; input failures and request errors are distinct and never fabricated as unrelated. Normalize only an exact whole-response JSON fence before strict schema validation; no semantic repair or hidden retry.
- **S4 — Evidence reuse.** Reuse compatible completed item evidence across requested summaries. Known content/context/config/prompt/input changes invalidate reuse; an explicit force-refresh option reacquires media. No continuous remote refresh and no standalone screening action. Private probe reports are not eligible cached product items.
- **S5 — Text-only composition.** Compose the report from completed related evidence only, using the same saved configuration. The final call is text-only; show excluded/unresolved counts and never upload item media a second time for composition.
- **S6 — Traceable output.** Preserve real source references; never trust LLM-invented links/IDs, events, coverage claims or incident counts. Keep raw sources, reusable evidence and prior summary provenance intact.
- **S7 — Small interface.** Keep the UI within collection results using existing shadcn components/theme; no cross-run daily report, notification, assignment workflow or extra model configuration.
- **S8 — Usage and safe failures.** Store validated provider token usage for new attempts, including completed responses failing local JSON/schema validation. Missing usage remains unknown; cached-item reuse does not duplicate historical usage. Show compact token totals with incomplete accounting explicit, not currency charges. Persist bounded error stages/codes instead of raw diagnostic responses; no repair call, cost dashboard or hard-coded pricing.

## Acceptance Criteria

- Automated and isolated-browser checks below do not replace the separately authorized real-media/provider gate. Evidence: `research/verification.md` and `research/integration-check.md`.

- [x] Existing results remain visible without AI. One explicit generation starts the full pipeline without a screening prerequisite, including results spanning multiple pages/new-repeat filters (S1, S2).
- [ ] Each complete uncached item reaches the model once with actual media; compatible reuse makes no per-item request. Force/known changes, incomplete inputs, invalid output and technical failures have truthful distinct outcomes (S3, S4).
- [x] Reject empty/active runs and runs above 100 unique sources before any media/model work. Empty or oversized final evidence makes no composition request; previously obtained item evidence remains available (S2, S5).
- [x] Exactly the relevant unique evidence set enters the final text-only prompt; media is not re-uploaded. Unknown/empty citations and invalid output fail safely (S5, S6).
- [x] Repeated POST with the same request UUID does not duplicate generation; refresh/restart restores display without automatic paid calls (S1).
- [x] Summary shows source coverage, related items and original links; XHS uses the existing stored-result reopening action (S6, S7).
- [x] Cancellation, browser contention and shutdown release owned resources without deleting sources; restart marks interrupted work and makes no paid requests (S1, S2). Existing abnormal-media-worker quarantine limits remain in the media child.
- [x] Later generation/force-refresh/configuration changes or collection recovery cannot silently overwrite old summary source versions; errors preserve prior evidence/results (S2, S4, S6).
- [x] Plain and exactly fenced valid JSON work without retries; malformed or secret-bearing output fails safely with bounded codes. Optional usage survives local parse/schema failure, unknown usage is not zero and reused evidence does not count historical tokens as new consumption (S3, S8).
- [x] Backend/frontend frozen gates, secret-safe transport tests and keyboard/pending/error/source-link UI checks pass (S1–S8).

## Dependencies and Limits

- Reuse checked `08-27-ai-configuration` and the checked internal contract/increment of `08-27-platform-media-enrichment`. On 2026-08-28 the user approved proceeding with saved per-item analysis and text-only composition without waiting for all five platforms' live media acceptance. First integration acceptance targets one complete Douyin sample; this does not narrow the full-run product scope or declare other platforms ready. Incomplete input remains unresolved and makes no item model request. Do not implement another browser launcher or download path. The old standalone screening child is deferred, not a dependency.
- First-version limits: at most 100 unique sources per generation, the parent's per-item input bounds, and 120,000 characters for final composition. Validate each bound before its corresponding provider work; do not truncate or silently split. An operation may use N uncached-item calls plus one text-composition call, not one request for the entire run.
- No automatic clustering pipeline, separate screening UI/API, semantic deterministic filters, keyword editor, multi-provider settings, provider File API, cross-run report, automatic repair/retry, raw-response viewer or billing dashboard.

## Artifact Status

Converged on 2026-08-28 with explicit S1–S8 acceptance and parent R14 mapping. The user approved the final summary with `来`, then approved the clarified saved-analysis/minimal-chain approach with `行吧，我觉得可以`. PRD, design, checklist and real implement/check contexts are ready. Activation depends on the checked media service contract, not whole-five-platform live acceptance. No summary implementation or live model acceptance is claimed at activation.

2026-08-28 implementation update: the manual full-run pipeline, v11 persistence/cache, strict model
boundary and shadcn UI are implemented and independently checked (596 backend / 281 frontend tests,
isolated browser flow). The task remains `in_progress` for separately authorized real-source/provider
acceptance. No commit, push, archive, user-database migration or new paid call occurred in this round.
