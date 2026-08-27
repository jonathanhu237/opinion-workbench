# AI 舆情相关性筛选

## Deferred — Not a First-Version Delivery

On 2026-08-27 the user accepted search-first obvious-issue leads and the missed-content trade-off. The revised parent PRD supersedes the standalone screening interaction below. Do not activate this child or treat it as a summary dependency. Per-item assessment/evidence reuse now belongs inside `../08-27-ai-opinion-summary/prd.md` when the user requests a summary. The remaining sections are retained as historical planning, not current implementation requirements. Resuming a standalone screening product requires a new decision and review; it has not been implemented or completed.

## Goal

Let the user manually screen all stored results of one terminal collection run with actual text/image/video inputs, then inspect related, unrelated and unresolved items without deleting sources. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R1–R3, R5, R6, R10–R12).

## Requirements

- `AI 筛选` explicitly freezes the full run scope, historical rule context and saved model configuration; page filters/pagination do not narrow submitted work.
- For each complete uncached input use one LLM call, returning relevance, reason and short evidence summary. No rules engine, text-only discard stage, sentiment/risk requirement or second per-item call.
- Preserve original results and show model uncertainty, missing inputs and technical failures separately. Only completed related items are eligible for summary.
- Reuse compatible completed judgments; known input/context/config/prompt changes invalidate reuse. Explicit `重新筛选` reacquires inputs and makes a fresh decision. No continuous remote-post refresh.
- Show real progress, reuse counts, cancel/retry state and source links with existing shadcn components; no auto-start on collection completion, navigation, refresh or application restart.

## Acceptance Criteria

- [ ] Full-scope test spans multiple UI pages and includes both new/repeated contents; no hidden first-page/new-only processing.
- [ ] Text/image/audio-bearing video fixtures reach the model with verified actual inputs; incomplete/unsupported media makes no false completed decision.
- [ ] Valid related/unrelated/uncertain outputs, invalid JSON, API errors and missing inputs have distinct persisted states and visible reasons.
- [ ] Compatible repeated content makes zero extra model calls; explicit force and observed context/content/config/prompt changes do not reuse stale judgments.
- [ ] Idempotent POST replay, concurrent start, browser contention, cancellation and restart cannot duplicate paid work or overwrite source history.
- [ ] Existing collection status/dedup remains unchanged; source links including XHS reopen still work.
- [ ] All full backend/frontend gates and local forwarded UI checks pass; no real credentials/data in test artifacts.

## Dependencies and Exclusions

- Must wait for checked `08-27-ai-configuration` and `08-27-platform-media-enrichment` contracts. Do not replace either with hard-coded credentials or fake media.
- Produces immutable screening/item/evidence references for `08-27-ai-opinion-summary`.
- No automatic summary, cross-run dashboard, arbitrary item selection, provider profiles, author profiling, scheduled collection/analysis or notification workflow.
