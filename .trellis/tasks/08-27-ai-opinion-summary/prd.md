# 舆情手动汇总

## Goal

Let the user click `生成汇总` directly from a terminal collection run, optionally turning search-first candidate leads into a concise source-linked report. The same operation assesses each uncached complete post once, saves reusable evidence, then composes text without uploading media again. No independent screening step is required. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R1–R6, R10–R12).

The user accepted search-first scope and possible missed implicit complaints on 2026-08-27. This revised downstream plan still requires final review before activation.

## Requirements

- Manual trigger only; search completion, route entry, refresh and restart never generate analysis or a summary. Original results remain usable without AI.
- Freeze all unique stored results of one terminal collection run and its historical rule context, regardless of UI pagination/filter. Show the destination, source count and media-upload/quota boundary before starting.
- Enrich complete uncached inputs with actual text/images/video and make one per-item call returning decision, reason and evidence. Retain related/unrelated/uncertain outcomes; input failures and request errors are distinct and never fabricated as unrelated.
- Reuse compatible completed item evidence across requested summaries. Known content/context/config/prompt/input changes invalidate reuse; an explicit force-refresh option reacquires media. No continuous remote refresh and no standalone screening action.
- Compose the report from completed related evidence only, using the same saved configuration. The final call is text-only; show excluded/unresolved counts and never upload item media a second time for composition.
- Preserve real source references; never trust LLM-invented links/IDs, events, coverage claims or incident counts. Keep raw sources, reusable evidence and prior summary provenance intact.
- Keep the UI small within collection results; no cross-run daily report, notification, assignment workflow or extra model configuration.

## Acceptance Criteria

- [ ] Existing results remain visible without AI. One explicit generation starts the full pipeline without a screening prerequisite, including results spanning multiple pages/new-repeat filters.
- [ ] Each complete uncached item reaches the model once with actual media; compatible reuse makes no per-item request. Force/known changes, incomplete inputs, invalid output and technical failures have truthful distinct outcomes.
- [ ] Reject empty/active runs and runs above 100 unique sources before any media/model work. Empty or oversized final evidence makes no composition request; previously obtained item evidence remains available.
- [ ] Exactly the relevant unique evidence set enters the final text-only prompt; media is not re-uploaded. Unknown/empty citations and invalid output fail safely.
- [ ] Repeated POST with the same request UUID does not duplicate generation; refresh/restart restores display without automatic paid calls.
- [ ] Summary shows source coverage, related items and original links; XHS uses the existing stored-result reopening action.
- [ ] Cancellation, browser contention and shutdown release owned resources without deleting sources; restart marks interrupted work and makes no paid requests.
- [ ] Later generation/force-refresh/configuration changes cannot silently overwrite old summary source versions; errors preserve prior evidence/results.
- [ ] Backend/frontend frozen gates, secret-safe transport tests and keyboard/pending/error/source-link UI checks pass.

## Dependencies and Limits

- Wait for checked `08-27-ai-configuration` and `08-27-platform-media-enrichment`. Reuse the stable AI lease/client and internal enrichment service; do not implement another browser launcher or download path. The old standalone screening child is deferred, not a dependency.
- First-version limits: at most 100 unique sources per generation, the parent's per-item input bounds, and 120,000 characters for final composition. Validate each bound before its corresponding provider work; do not truncate or silently split. An operation may use N uncached-item calls plus one text-composition call, not one request for the entire run.
- No automatic clustering pipeline, separate screening UI/API, semantic deterministic filters, keyword editor, multi-provider settings, provider File API or cross-run report.
