# Manual Summary Design

Use the revised parent design's summary/API/state contracts and its `research/model-transport-contract.md`. One explicit user action owns serial per-item analysis/reuse followed by one text-only composition call, not a standalone screening workflow. The user approved this scope on 2026-08-28, then approved starting against the checked media service contract while full-five-platform live acceptance remains open. See `research/implementation-boundary.md` for this integration slice.

Read the parent's `research/product-integration-readiness.md` for the post-probe decisions and strict boundary between experiment and product. Do not copy its `related` enum, optional private raw-answer diagnostics or per-process attempt limits into the production contract.

## Ownership and Data Flow

- Add backend summary schemas/repository/service/router, additive `ai_summary_runs`/`ai_summary_items` migration and lifespan registration using the checked AI lease/client. Read the actual current schema (v10 at this planning refresh), preserving existing manual-recovery edits; no standalone screening tables or worker/MediaCrawler changes in this child.
- POST `/api/v1/search-runs/{id}/ai-summaries` takes `{request_id, force_refresh, configuration_revision}`, verifies a nonempty terminal run of at most 100 unique results and freezes all rows, historical rule context and the exact configuration revision disclosed by the confirmation before work. Stale configuration is rejected before any media/model request; UUID replay returns the same operation and binds source run, force flag and configuration revision. Conflicting replay is rejected.
- Reserve AI admission, reuse compatible completed evidence, and acquire browser ownership for serial enrichment of uncached inputs through the media child's service. Release browser ownership before composition. Validate full input coverage before each bounded per-item call; store decision/reason/evidence and immutable input metadata. Source identity alone is not a sufficient cache key; use the parent's observation/context/model/prompt/extractor versions and canonical reuse references.
- Keep phase `analysing`/`summarising`, reconciled counts and per-item completed/input-incomplete/failed/cancelled/interrupted outcomes. A zero-related-evidence operation completes with a truthful no-evidence result and no composition request; missing/failed items are not verdicts. Cancellation and shutdown preserve completed evidence and release every owned resource.
- Build the final text-only prompt from frozen related source text/evidence and application IDs; no author profiles, platform credentials or raw media. Enforce 120,000 characters before composition. Include computed covered/excluded counts outside the model's authority.
- Validate one JSON summary against bounds and supplied IDs; each item has at least one valid citation. Resolve links from stored source records, never model prose. Render as escaped text and link buttons.
- Store completed output on its summary-run version, separate from source rows and item evidence. Failed/interrupted generation leaves prior summaries and completed evidence untouched; no auto-resume/retry. UI polling is read-only. A new explicit request is a new version, normally reusing compatible evidence; UUID replay is the same version. A force-refresh option in this action replaces the old standalone re-screen idea.
- Extend the existing AI client's internal typed result compatibly to carry optional validated usage while keeping `complete_text`/connection-test behavior. Store numeric usage and stage/code even if local output validation fails; never persist raw failed-answer excerpts. Trim whitespace/remove only an exact whole-response JSON fence before strict schema/citation validation. Scan accepted prose for literal/escaped credential leakage; no semantic repair or paid retry. Product decisions remain `relevant | irrelevant | uncertain`.
- Item reuse references prior evidence but has no new provider attempt/usage. Aggregate only new item and final-composition usage, marking absent/malformed accounting unknown. No hard-coded currency estimate. Later manual collection recovery may add observations but must not rewrite this AI run's immutable scope.

## UI

Add `生成汇总` to collection results without a prior related-results section. Disable when source run/configuration/admission is unavailable; show concise progress/cancel/error states, selected summary version, source coverage and inspectable item reasons. There is no separate `AI 筛选` button or screening dashboard. Original results remain candidate leads, not confirmed negative incidents. Reuse shadcn components and current tokens.

Show token consumption as a compact optional figure with incomplete/unknown accounting labeled, not a new card or billing panel. Distinguish media acquisition, model response format and a valid uncertain verdict without dumping raw responses. The final text-only call can consume tokens even when all item evidence was reused.

Original links use the shared collection source-open behavior, including XHS's backend-mediated ephemeral-token path. No new URL generation or external navigation from model-produced strings.

## Compatibility and Rollback

Two new tables after the checked configuration migration; no source-row mutation or media retention change. Removing summary UI/runner leaves collection and configuration usable. Pre-migration backup is required to downgrade binaries safely.
