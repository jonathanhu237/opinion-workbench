# Manual Summary Design

Use the revised parent design's summary/API/state contracts and `research/model-transport-contract.md`. One explicit user action owns serial per-item analysis/reuse followed by one text-only composition call, not a standalone screening workflow. Revised final review is pending.

## Ownership and Data Flow

- Add backend summary schemas/repository/service/router, additive `ai_summary_runs`/`ai_summary_items` migration and lifespan registration using the checked AI lease/client. Read the actual post-configuration schema version; no standalone screening tables or worker/MediaCrawler changes in this child.
- POST `/api/v1/search-runs/{id}/ai-summaries` takes `{request_id, force_refresh}`, verifies a nonempty terminal run of at most 100 unique results and freezes all rows, historical rule context and current configuration revision before work. UUID replay returns the same operation; conflicting replay is rejected.
- Reserve AI admission, reuse compatible completed evidence, and acquire browser ownership for serial enrichment of uncached inputs through the media child's service. Release browser ownership before composition. Validate full input coverage before each bounded per-item call; store decision/reason/evidence and immutable input metadata. Source identity alone is not a sufficient cache key; use the parent's observation/context/model/prompt/extractor versions and canonical reuse references.
- Keep phase `analysing`/`summarising`, reconciled counts and per-item completed/input-incomplete/failed/cancelled/interrupted outcomes. A zero-related-evidence operation completes with a truthful no-evidence result and no composition request; missing/failed items are not verdicts. Cancellation and shutdown preserve completed evidence and release every owned resource.
- Build the final text-only prompt from frozen related source text/evidence and application IDs; no author profiles, platform credentials or raw media. Enforce 120,000 characters before composition. Include computed covered/excluded counts outside the model's authority.
- Validate one JSON summary against bounds and supplied IDs; each item has at least one valid citation. Resolve links from stored source records, never model prose. Render as escaped text and link buttons.
- Store completed output on its summary-run version, separate from source rows and item evidence. Failed/interrupted generation leaves prior summaries and completed evidence untouched; no auto-resume/retry. UI polling is read-only. A new explicit request is a new version, normally reusing compatible evidence; UUID replay is the same version. A force-refresh option in this action replaces the old standalone re-screen idea.

## UI

Add `生成汇总` to collection results without a prior related-results section. Disable when source run/configuration/admission is unavailable; show concise progress/cancel/error states, selected summary version, source coverage and inspectable item reasons. There is no separate `AI 筛选` button or screening dashboard. Original results remain candidate leads, not confirmed negative incidents. Reuse shadcn components and current tokens.

Original links use the shared collection source-open behavior, including XHS's backend-mediated ephemeral-token path. No new URL generation or external navigation from model-produced strings.

## Compatibility and Rollback

Two new tables after the checked configuration migration; no source-row mutation or media retention change. Removing summary UI/runner leaves collection and configuration usable. Pre-migration backup is required to downgrade binaries safely.
