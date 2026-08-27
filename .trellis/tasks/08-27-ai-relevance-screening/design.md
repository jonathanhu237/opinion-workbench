# AI Screening Design

Status: deferred outside the first version as of 2026-08-27. This is historical design, not an implementation contract. Use the revised parent and integrated-summary child instead; do not create standalone screening tables/routes/UI from this document.

Use parent design sections B–D and the model transport/output contract. `current-input-boundary.md` explains why source identity is not immutable input and why the search schema must remain separate.

## Ownership

- New backend screening schemas/repository/service/router under existing layer directories; `database.py` adds screening-run/item tables after the actual settings migration.
- `main.py` owns startup interruption marking and bounded shutdown, not auto-resume. Reuse configuration lease/model client and internal content enrichment; no duplicate clients or browser launcher.
- New frontend screening API module/query hook and a feature section consumed by `routes/collection-run-detail.tsx`. Preserve existing collection-result components/open behavior; add only a narrow shared source-link consumer if summary needs it later.

## Execution Contract

POST freezes the full unique source set, run rule snapshot and configuration. A UUID distinguishes one user intent; replay returns its persisted job. Reserve AI/browser admission before side effects and release both on every terminal path. Iterate serially; complete compatible cached items without refetching. Other items enrich, validate coverage, call once, validate JSON and persist.

Missing text/media is `input_incomplete` with no LLM verdict/call. Model `uncertain` is a completed judgment; transport/output failure is failed. Counts must reconcile to the frozen item set. Source identity/link/context are application-owned; the model can only supply decision/reason/evidence. No raw model response is stored on failure.

Every item records observed source hash and immutable input metadata. Cache matching excludes timestamps/signed URLs but includes all context/model/prompt/extractor versions and observed media hashes. Store a reference to the original completed item for reuse; avoid recursive unbounded reference chains by resolving to a canonical completed item.

Startup marks incomplete jobs/items interrupted without running them. An explicit normal rerun reuses already completed compatible items and retries incomplete ones; force ignores cache. Cancel does not promise undoing provider billing already incurred, and never deletes completed results.

The UI presents full-scope/destination disclosure before start, active progress/cancel, and related-first filters after completion. Query hooks only GET/poll; POST occurs exclusively in event handlers. Keep source result and screening pagination/filter state separate in the URL.

## Rollback

Additive schema and routes only; original search rows and run statuses never become AI statuses. Disable the runner/UI to roll back functionality, preserve completed history. A binary downgrade requires a verified database backup.
