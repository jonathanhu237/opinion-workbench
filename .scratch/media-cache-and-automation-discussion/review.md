# Implementation review

Review base: `dcc87a8e513782ac652512b15e07f3053565efe1` against the working tree. The already completed report-width change is a separate scope. Reviews are performed directly by the parent task under implement-loop.

## Round 1

Standards: no additional actionable standards findings.

Spec:

- P2: the implementation had not synchronized CONTEXT.md and ADRs with the newly authorized retirement of historical media retention. Return to the same implementation agent to record the changed decision explicitly.
- P2: cleanup correctly retries unlink failures, but outer directory scan/stat I/O errors were still classified as non-retryable. This could allow the migration to discard the ownership index before the remaining managed media was removed. Return to the same implementation agent to preserve retry state on actual filesystem I/O errors and add scan-failure coverage.

Previously identified during implementation and verified in real acceptance: scheduled tick lock re-entry prevented an admitted scheduled run from starting. Moving admission outside the claim lock enabled the actual scheduled collection. The failed zero-collection run remains recorded.

Real acceptance and its coverage limits are recorded in [real-acceptance.md](real-acceptance.md). No further real collections are authorized by this review.

## Round 2

Standards: pass; no remaining actionable findings.

Spec: the two Round 1 findings are resolved. ADR-0012 explicitly records the user's authorization and supersession; directory I/O errors retain migration retry state. Parent verification: media-exit tests plus actual tick regression, **7 passed**; `git diff --check` passed. No additional implementation findings.

Validation limitation: the full backend attempt was interrupted after a stall (**315 passed, 31 failed**). The failures include retired media expectations affected by this change and are not all claimed to be pre-existing. Frontend full-suite results also retain two existing collection-runs failures. Report engine/review-boundary follow-up: **222 passed, 1 existing media-field expectation failed**. This review does not claim a green full suite; see backend-full-pytest-summary.md and real-acceptance.md.

Implementation loop complete after two direct review rounds. Awaiting user acceptance; no commit or push performed for this change.

User acceptance: the user subsequently requested committing and pushing the completed changes on 2026-09-09.
