# Implementation Boundary — 2026-08-28

The user approved the latest final plan with `来`. Activate this media child first;
the summary child waits for its checked dependency. No commit/push is requested.

## Smallest behavior gap

Collected records have metadata/canonical links but cannot provide identity-verified
full text and actual media to a later summary operation. Add one bounded internal
enrichment command, not a new search flow, public download endpoint or AI call.

## Ownership

- Fork implementer: `third_party/MediaCrawler/tools/` enrichment protocol, safe
  downloader/prober/staging, minimal `auth_worker.py` dispatch changes, five narrow
  `media_platform/*/product_enrichment.py` adapters, their tests, and the task-local
  wire-contract note. Preserve all existing dirty search/recovery code.
- Backend implementer: new typed internal enrichment models, staged-asset validator,
  `services/content_enrichment.py`, integration in `media_crawler_auth_worker.py`
  and `browser_operations.py`, minimal stored-result lookup reuse, and focused
  backend tests. Do not edit the fork, database schema, UI or AI client.
- Main session: coordinate shared contract before both sides implement it, runtime
  isolation/source sync, eventual live acceptance, task/spec records and review.
  Independent checker receives the final bounded diff after implementers freeze it.

All implementers are sharing one dirty workspace. They must not revert each other's
changes, replace whole shared files, or treat existing changes as disposable.

After the backend's 462-test checkpoint, the fork owner explicitly released the
not-yet-created WB/KS/XHS `product_enrichment.py` adapters and their three independent
test files to the backend implementer. That implementer must refresh fork guidelines
before editing them. Shared I/O, protocol, worker/helpers and DY/Toutiao remain with
the original fork owner. Backend files stay frozen except review-directed fixes;
main still owns source synchronization and runtime validation.

## Explicit exclusions and regression proof

No model/provider calls, credential/configuration edits, source DB mutation, new
browser profile, context-wide scripts, generic crawlers, comments/profiles, hidden
state/browser-storage fallback, transcoding, HLS/DASH/DRM, uploads, frontend or
summary migrations in this child. Production browser/media acceptance remains a
separate main-session action, not an implementer test.

Protocol additions preserve auth-v2/search-v2/manual-recovery frames, cancellation
and current-generation page ownership. Any minimal helper refactor needs existing
regressions plus new exact-ID/path/hash/size/coverage/cleanup fixtures. Run source-only
checks on Centaurus, never against the user's runtime or credentials. New work may
not be declared five-platform support on fixtures or unavailable results alone.
