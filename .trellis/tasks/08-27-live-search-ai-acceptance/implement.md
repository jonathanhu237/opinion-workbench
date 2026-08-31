# Execution Plan — Verification Only

## Approval Gate

- [x] Obtain approval of the final scope, bounded live requests and local-backend exception.
- [x] Run `task.py start` only after that approval. Do not implement product code.

## Checks

1. Recheck clean product source, reachable Centaurus, available ports and no unrelated active work.
   Read the in-app-browser skill before UI interaction; read the Chrome/computer-use skill only if
   direct user-browser UI inspection is needed. Use the product worker for platform operations.
2. Verify the current database and writer/WAL state, back it up under ignored local runtime, then
   start the existing production backend and confirm migration 9 preserves original data/settings.
3. Synchronize code one-way to Centaurus excluding runtime, credentials, `.git`, dependency/cache
   artifacts. Start the frontend and loopback-only forwarding; verify health and real UI state.
4. Create the two labelled acceptance rules through the normal product boundary; verify their
   original groups and derived single-query snapshots through the UI and API.
5. Run the five-platform baseline and combined-query comparisons sequentially with a five-result
   cap. Record batch/run IDs and terminal outcomes. Pause on manual challenges; do not retry
   blocked targets or invent empty success. Keep progress visible to the user.
6. Inspect counts and representative results, then repeat successful combined targets once. Verify
   stable-identity intersections, new/repeated relationships and first/last-seen preservation using
   API projections and minimal read-only SQL. Report any inconclusive comparison.
7. Read only the non-secret AI settings projection. Test the saved revision once; capture status
   and elapsed time only. Report missing credentials/configuration without reading secret files.
8. Disable the task-created rules, preserve results, expose the result page to the user, and record
   sanitized evidence in `verification.md` plus a clear list of remaining capability gaps.
9. Dispatch an independent `trellis-check` agent with a read-only, no-browser/no-provider/no-code
   mandate to review evidence and conclusions. Main session owns any live follow-up.

## Validation and Stop Conditions

- `git diff --check`, `task.py validate <task-dir>`; confirm no product/submodule source changes.
- SQLite integrity/foreign-key checks and exact historical identity/count preservation around
  migration; active states must not be interrupted as test setup.
- UI: real rule preview, batch progress, result drill-down and new/repeated filters; inspect console
  for application errors without dumping unrelated data.
- Reuse the already-passed 353 backend / 164 frontend test baseline if source is unchanged; execute
  any needed additional standard checks on Centaurus, not as a substitute for live acceptance.
- Product defects are reported, not silently fixed. Login, challenge, authorization and provider
  failures remain explicit outcomes. Broader calls or feature implementation require new direction.
- No commit, push, database rollback or cleanup of unrelated tasks/data is authorized by this task.

## Completed One-Rule Cleanup Follow-up

- [x] Identify original rule 1 and disabled, task-owned acceptance rules 3/4 using the real API.
- [x] Inspect the current foreign-key actions and verify all stored operations are terminal.
- [x] Create a fresh private local backup and validate integrity/foreign keys.
- [x] DELETE only rule 3 and rule 4 through the product API; both return HTTP 204.
- [x] Compare all nine search tables row-for-row against the fresh backup. The only allowed
  change is nulling references to the deleted rule IDs in runs/batches.
- [x] Verify exact original rule/term preservation, one remaining rule, integrity OK and no
  foreign-key violations. Record evidence without credential paths or raw browser data.
- [x] Independently check the cleanup evidence and distinguish source observations from an
  unproven root cause of the Toutiao combined-search failure.

No product source changed during this follow-up. Preserve the earlier, separately verified
uncommitted frontend changes; do not treat them as part of this data cleanup.

## Real-Media Follow-up — 2026-08-28

1. Follow the user-approved bounded addendum in `research/media-cost-probe-plan.md`.
2. Inspect existing originals and obtain complete local audio-bearing MP4s only.
3. Test the isolated harness with fake transports on Centaurus and independently
   check its call cap, usage capture and credential/output safety before live use.
4. Pause the idle production AI owner, run the small local saved-model probe once,
   then restore the existing application without changing its data/configuration.
5. Report actual decisions and usage, distinguish list-price estimates from billing,
   remove owned temporary media and preserve a sanitized verification record.

## Current End-to-End Follow-up — 2026-08-30

1. Re-read the current local-first runtime instructions and relevant backend/frontend/infra
   specs. Inspect the implemented collection, initial-analysis, and topic-report API/UI path.
2. Resolve the real runtime database and current process/port state without exposing secrets.
   Confirm no active job owns the workflow, take a private SQLite backup, and record integrity,
   schema version, rule count, source count, analysis count, and report count.
3. Start only missing local services with the repository's supported commands. Verify health,
   frontend/API connectivity, saved AI readiness projection, and browser/CDP availability.
4. Inspect the existing `龙田街道及四个社区` rule and derive a bounded issue vocabulary from its
   configured terms and the current product contract. Record each effective query and cap.
5. Execute one real product collection workflow. Follow progress through terminal job/batch/run
   states; never bypass login, permission, challenge, throttling, or platform protections.
6. Observe the product-owned AI initial-understanding/summary stages and automatic report handoff
   to terminal states. Do not retry provider calls merely to obtain a passing result.
7. Inspect the generated aggregate report in the UI and API. Cross-check counts, source IDs,
   citation targets, relevant/irrelevant/uncertain classifications, and a small sample of actual
   collected records; note false positives, stale items, and location namesakes.
8. Re-run integrity/foreign-key checks, disable only a task-created rule if one was necessary,
   preserve histories, and append sanitized evidence plus a pass/partial/fail matrix to
   `verification.md`.
9. Dispatch a read-only `trellis-check` reviewer after live work. It must not make platform or
   provider calls, operate the browser, mutate the database, or change product code.

## Authorized Analysis-Wait Bug Fix — 2026-08-31

1. Add a focused failing regression for an `AnalysisAdmission` whose nested job is
   queued/running when admitted and later settles through `ContentAnalysisService.read`.
2. Normalize the admitted child to `admission.job` before calling the existing child
   wait loop; preserve replay/recovery paths that already read a job directly.
3. Run the focused automation workflow tests, backend lint/type checks relevant to the
   changed files, then dispatch an independent `trellis-check` review.
4. Do not run live collection, enrichment, AI, reporting, or mutate runtime data.
