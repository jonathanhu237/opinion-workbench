# Final independent quality review

Date: 2026-08-28. Reviewer: dispatched `trellis-check` agent.

## Verdict and scope

No remaining in-scope product-code blocker was found after the fixes below. Product source is
frozen. This is an offline implementation/quality verdict, not real-platform challenge acceptance
or Git delivery approval.

The reviewer loaded the task manifests, PRD, design, implementation plan, research digest and
applicable backend/frontend/infra specifications, including package Quality Check requirements.
The approved all-failure pause, search-v2 and owned-failure-page contracts supersede older
auto-advance/full-retry behavior. No nested agents, runtime databases, user browsers, credentials,
model calls, remote operations or Git operations were used by this reviewer.

Review covered all five adapters and worker framing; original/suffix position mapping; SQLite v10
migration and proof provenance; paused ownership; stale controls; explicit historical recovery and
audit; shutdown/cancellation/thread draining; startup crash windows; no-work completion; aggregate
results/source runs; API schemas; frontend decoders, controls, cache/URL state, feedback and history.
Existing unrelated AI configuration/monitoring UI edits and theme were preserved.

## Findings (fixed)

1. **Late browser disconnect crossed session generations.**
   `third_party/MediaCrawler/tools/auth_worker.py` captured the disconnect event belonging to the
   registered browser and rejects obsolete callbacks, instead of invalidating the newest session.
   `tests/test_product_search_recovery.py` adds reconnect, manual disconnect/cancel/shutdown and
   owned-page/borrowed-browser preservation sentinels. This earlier review fix remains unchanged.
2. **Internally consecutive proofs could conceal a missing tail.**
   `backend/src/longtian_api/search_checkpoints.py` now also validates v2 current progress against
   the proof boundary. Both legitimate start-before-completion and completion-before-next-start
   states remain valid; a success requires all suffix proofs. Missing evidence never becomes a
   trusted zero-based retry. Failed attempts with an unconfirmed final term still retry that term.
3. **Damaged child snapshots prevented safe stop controls.**
   Batch-only reads in `repositories/search_batches.py` opt into an empty-term read projection in
   `repositories/search_runs.py`; actual term counts, including zero, remain truthful. Storage and
   standalone-run reads are unchanged. The batch-only frontend summary accepts that read-only
   history and bounded invalid historical progress; a trusted checkpoint still requires matching
   counts and in-range progress. Continue remains 409; detail/history/skip/cancel remain usable.
4. **The frontend rejected a real run/item commit interval.**
   `frontend/src/lib/api/search-batches.ts` accepts a running item whose latest run has already
   committed a terminal outcome. It does not fabricate item completion or change the run result.
   Real FastAPI payload tests and decoder tests cover success, failure and cancellation intervals.
5. **Exceptional runner cleanup could leave an active child or misclassify success.**
   Repository fallback now atomically settles still-active children, preserves successful runs and
   projects their items completed before marking other unfinished items failed. It shares the
   existing startup settlement logic and retains the existing `internal_error` batch fallback;
   there is no retry. The backend implementer's final two `fail_batch` awaits now use
   `database_call`, so cancellation drains their SQLite threads before owner release; reviewed and
   retained. Failure-injection tests cover failure before result commit and before item commit,
   unchanged successful records, no later-platform execution and subsequent explicit admission.

Final-scope regression additions are in `backend/tests/test_search_recovery.py` and
`frontend/src/lib/api/search-batches.test.ts`. No new public field, status, dependency or theme was
introduced by the review fixes.

## Verification

Main owns Centaurus execution/synchronization and supplied the remote results below. They were
not independently replayed by the reviewer. Remote validation uses the isolated code-only
`/tmp/longtian-recovery-validation.EcUhyX` snapshot, never the user database/browser.

| Gate | Evidence |
| --- | --- |
| Reviewer local lightweight lint/format | Scoped backend Ruff check and format: 5 files pass. Frontend scoped Prettier: 2 files pass. |
| Backend final, main-run | Ruff check and format pass (50 files); **408 tests passed**, 9.47s. No separate backend type-check command is configured. |
| Frontend final, main-run | TypeScript, lint (0 warnings/errors), format, production build pass; **215 tests in 11 files passed**, 7.72s after the frozen install. |
| Frontend frozen dependency install, main-run | `pnpm install --frozen-lockfile` passed in the isolated directory (8.6s); manifest/lockfile local and remote hashes match and remain unchanged. All frontend gates reran successfully afterward. |
| Derivative, main-run | **634 passed**, zero skips, 15.95s after generation fix; source unchanged since. Focused recovery/auth worker: **63 passed**. |
| Derivative lint | Changed generation-fix files clean. **35 inherited Ruff findings** were baseline-compared by the implementer/main, not hidden or broadened into legacy cleanup. One inherited SQLAlchemy warning remains. |
| Independent synthetic HTTP, main-run | Fresh database third replay **PASS**: suffix, union, stale controls, show-only, skip and restart; no real platform work. |
| Synthetic UI, main-run | Open-only, suffix continuation, merged results, history, filters and skip passed; screenshots preserve existing theme; console warnings/errors empty. |
| Migration preservation, main-run | Actual historical v9 fixture to v10: all nine old relations' column hashes/counts identical, FK errors 0, 82 inferred proofs with null historical completion times; current paused item preserved. |

Behavioral red evidence preceded source fixes:

- Generation race: 1 failure at the new session's connected-state assertion.
- Initial backend additions: 4 failed / 2 passed (missing proof tails and empty child snapshots).
- Initial frontend additions: 5 failed / 27 passed (damaged snapshots and terminal-run intervals).
- Additional backend additions: 3 failures (successful run missing final proof and both exceptional
  cleanup write windows). Expanded frontend additions: 6 failed / 27 passed, including historical
  out-of-range progress. Final complete suites above pass.

The seven final-scope source/test hashes were checked locally by the reviewer; main confirmed each
remote hash matches. Main's final frozen-source preview reload preserved the persisted results and
still produced no console warnings/errors. Detailed execution evidence is maintained in
`research/implementation-verification.md`.

## Findings (not fixed) / validation limits

- No remaining in-scope code finding. Deliberately inherited derivative lint diagnostics were not
  changed because they are unrelated baseline code, not introduced by recovery work.
- No actual platform challenge was triggered or solved. The HTTP/UI worker is synthetic. No claim
  of live CAPTCHA handling, mobile-browser QA, user-runtime upgrade or production recovery follows
  from these tests. Any live step remains separately coordinated by main and the user.
- No Git stage/commit/push/archive or submodule pointer delivery occurred. Infra reachability,
  clean derivative pointer and fresh-clone reproducibility gates belong to later authorized Git
  delivery; they are not claimed as passed here.

## Bug analysis and prevention

1. **Root cause categories:** cross-layer contract and test coverage gaps (B/D), plus implicit
   assumptions (E): proof-row continuity alone is insufficient; one read transaction does not make
   two write transactions atomic; a valid standalone run schema cannot represent damaged batch
   history; releasing an owner requires settling both normal and exception-path writes.
2. **Why earlier green gates missed them:** healthy-state fixtures and layer-local tests did not
   exercise proof deletion, the exact terminal-run/item-write interval or fallback write failures.
   The new tests failed on the pre-fix source at the predicted assertions, providing direct evidence
   rather than an inferred live-platform explanation.
3. **Prevention:** explicit proof-boundary validation, batch-specific read-only decoding, one shared
   interruption settlement helper, cancellation-safe writes and actual API/failure-injection
   regressions are now in place. Browser generation capability tests cover obsolete callbacks.
4. **Systematic check:** reviewed equivalent startup/fallback paths, all five completion producers,
   frontend detail/history consumers and standalone-run preservation. No broader database repair,
   interface expansion or automatic recovery was introduced.
5. **Knowledge capture:** main synchronized the domain specs (batch/search/database/platform and
   frontend state management), including these approved exceptions. `trellis-break-loop` informed
   this prevention record; its generic commit/template steps are not authorized in this task and
   were not executed.
