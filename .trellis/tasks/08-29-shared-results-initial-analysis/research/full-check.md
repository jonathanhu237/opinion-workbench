# Child A full review and gate evidence

Reviewed on 2026-08-29 as the directly dispatched `trellis-check` agent. Scope:
all Child A backend/frontend changes, the exact published backend contract,
parent G1/G2/G7 and A portions of G4/G6, and the new initial-analysis spec.
This is Child A review evidence, not completion of parent scheduling/report work.

Read the complete saved check-hook output, child/parent PRD/design/implementation
plans, `check.jsonl` resources, backend/frontend implementation evidence and
applicable specs. Applied `trellis-check`, `trellis-before-dev`, `fastapi` and
UI/UX guidance directly; no reviewer/implementer recursion or delegation.
The frontend response-order fixes and regression-first evidence are detailed in
`frontend-check.md`. Main-owned browser evidence is in `browser-acceptance.md`.

## Findings (fixed)

1. `frontend/src/routes/results-settings.tsx`: independent prompt/policy save
   responses could regress a newer sibling version; an older in-flight GET could
   later undo the successful write in the cache. Both save paths now cancel
   pending settings reads and merge each prompt/policy monotonically. Five
   deterministic reverse-response/late-GET tests cover these cases.
2. `frontend/src/routes/results.tsx`: page Refresh did not recover failed selected
   source/evidence/origin/legacy reads. It now invalidates both owned resource
   families. A regression retries all five failed selected-source reads and
   proves no mutation is submitted.
3. `frontend/src/lib/api/content-analyses.ts`: ready input could declare media
   absent from its asset inventory. The decoder now checks the canonical
   image/video/audio correspondence. Positive ready and incomplete inputs remain
   accepted; six false-ready variants are rejected.
4. `backend/tests/initial_analysis_smoke.py`: browser acceptance's explicit
   cross-port API URL lacked fixture CORS. Added exact-origin middleware for
   `http://127.0.0.1:46081`, GET/POST/PUT and Content-Type only. The production
   application and its mutation guard are unchanged. New
   `test_initial_analysis_smoke.py` has three cases proving permitted reads and
   preflights, rejected other origins/DELETE, and zero model/media work.
5. Backend regression gaps: `test_content_analysis_repository.py` now races an
   automatic handoff and a manual all-never-started request at a barrier, proving
   one 101-member admission, one claim per content, durable replay and no calls.
   `test_content_analyses.py` covers all-input-incomplete and all-model-failed
   jobs: every member settles, one pending completion event has no successful
   IDs, usage stays truthful, claims release, and later cancellation/repeated
   settlement cannot change the event.
6. `backend/tests/test_content_analysis_api.py`: an origin assertion compared
   `source_run_id` with `job.id`, passing only because both fixtures allocated ID
   1. The fixture now gives the source a distinct run ID and asserts the real
   source identity. No production source-opening behavior changed.

Reviewer production edits are limited to the three frontend files above; their
tests are in `routes/results.test.tsx` and `lib/api/content-analyses.test.ts`.
Backend reviewer edits are fixture/tests only (the five backend files named
above). Existing implementer changes, specs, task state, Git and other agents'
files were preserved.

## Reviewed contracts and evidence

| Gate | Code-path and regression evidence |
| --- | --- |
| G1 persistence | Genuine v11 SQL fixtures, unchanged old rows/JSON/IDs/usage, current-version reopen and prompt preservation, forward-version rejection, actual v12 DDL/DML rollback and second-member insert rollback. New claims are registered in the existing source/origin transaction. |
| G2 membership | 0/1/101/1001 uncapped library selection across runs/pages; deterministic frozen IDs, later arrivals excluded, concurrent manual and auto/manual claims, UUID no-op replay, repeat observations preserving first-entry time, new/history/legacy distinctions, explicit retry/reanalysis. |
| G2 evidence/reuse | Neutral strict output without a relevance verdict; complete accepted text and bounded saved metadata; shared actual-media/hash/byte validation; canonical compatible reuse, both prompt versions frozen, report-prompt changes not invalidating initial understanding, newer known failed input fencing older cache. |
| G2 lifecycle | AI/browser owners and queued busy state, configuration revision fencing, settlement-aware database calls, cancellation draining late writes, restart reconciliation without calls, empty-queue/admission barrier, claims released on every terminal path. |
| G4 A handoff | Collector/batch callbacks run after browser release; batch children/manual pause/cancel do not independently trigger automatic work. Durable new backlog recovers a terminal-commit/handoff gap only on later ordinary completion. Normal partial/all-failed settlement publishes one event; cancelled/interrupted/configuration-blocked jobs do not. |
| G6 A independence | Initial understanding never composes a report. Saved evidence survives failed later attempts and configuration/prompt edits. Reuse adds no historical usage; unknown/overflow totals remain unknown. Default rollout is unavailable independently of saved authorization. |
| G7 HTTP/UI | Strict safe-integer/status/count/source/usage decoding, constant no-store errors and local mutation guards, one frozen UUID/provider/two-prompt confirmation, explicit ambiguous retry, CAS draft recovery, all-library intent beyond pagination, history/source tuples, terminal polling and active cancellation while viewing history. |

Direct review checked migrations, repositories, services, API routing/lifespan,
legacy admission/cache integration, collector hooks, saved-evidence schema and
the frontend read/mutation boundary. No GET, prompt save, cache miss or startup
path launches initial analysis. Legacy saved judgments remain labelled legacy,
not neutral understanding; old report routes and actual origin tuples remain.

The main-owned synthetic browser pass independently verified nonfirst-page
103-member admission, 102 successful/one incomplete settlement, 102 model and
103 media fake calls, saved full text and neutral evidence, reload with no new
calls, independent prompt versions, Escape focus restoration, narrow layout
without horizontal overflow and an empty warning/error console. The checker
read the written browser report; it did not operate browser/services itself.

The new `.trellis/spec/backend/initial-analysis-guidelines.md`, backend/frontend
index links, legacy scope note and frontend state section match the implemented
contract and fixes. Main owns these spec edits. No additional spec change is
required by this review.

## Verification

All execution gates used the isolated Centaurus snapshot
`/tmp/longtian-decoupling-impl.dMCxsd`; local work was source edits, read-only
inspection and allowed frontend formatting. No real provider/account/media
request, production DB mutation, service deployment, Git mutation or live
automation activation occurred.

Backend synchronization, only after main released its acceptance services:

```sh
rsync -a --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache --exclude='.env*' --exclude='*.pyc' --exclude=runtime backend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/backend/
```

No `--delete` or remote source edits. Formatter diagnostics were fixed locally
and the exact test file re-synced before the final gates. Synchronization had
completed before the final full run; no source sync occurred during that run.
`rsync -rnci` with the same exclusions subsequently reported no differences.
The local sorted source-path/SHA-256 manifest hash is
`7fc9af167131b2d28c0d38770f9231360b54cdd62453863065bad2ad1f8a430a`.

Final backend command:

```sh
ssh -o BatchMode=yes Centaurus 'cd /tmp/longtian-decoupling-impl.dMCxsd/backend && uv sync --locked && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen python -m pytest -q tests --tb=short'
```

| Gate | Observed result |
| --- | --- |
| Backend locked dependencies | Passed; 54 packages resolved, 52 checked. |
| Backend lint | Passed; Ruff reported all checks passed. |
| Backend format | Passed; 96 files already formatted. |
| Backend tests | Passed; **656 tests in 19.38 s**, no skipped tests. |
| Backend type check | Not configured; no mypy/Pyright pass claimed. |
| Frontend frozen install / format / lint | Passed; pnpm 11.14.0, Node v24.20.0; lint 0 warnings/errors. |
| Frontend type check | Passed; `tsc -b --pretty false`. |
| Frontend tests | Passed; **370 tests / 18 files in 8.36 s**, no skipped tests. |
| Frontend build | Passed; 2349 modules, 275 ms. |
| Local whitespace | `git diff --check -- backend frontend` and reviewer research files passed. |

Earlier backend checks: fixture CORS regression **3 passed in 1.00 s**; full
suite before the last boundary additions **653 passed in 19.69 s**. A formatting
check initially requested one assertion unwrap; it was fixed locally and the
entire locked backend gate rerun successfully, not counted as an accepted run.
Frontend red/green commands, final command list and its unchanged snapshot hash
`000630f3187ab4d72e9d939e320c3d1e9d77dea864f4edca89b227af3e30e985`
are recorded in `frontend-check.md`. Frontend source was not changed after those
gates or during main's successful browser acceptance.

## Findings (not fixed) / handoff

No unresolved Child A code or spec blocker was found after these fixes and gates.
The following are intentional boundaries, not claimed completed here:

- B scheduling and C report execution/consumption are separate approved children.
  They must use A's exact `backend-contract.md` handoff. C consumes the unique
  terminal event and frozen attempts/provider/prompts in its own idempotent
  transaction; report failure cannot revoke initial evidence or trigger media
  acquisition. The event includes an empty success set when no member succeeded.
- Keep `analysis_automation_available=False` until parent integration acceptance;
  saved authorization is not sufficient to activate incomplete rollout.
- Synthetic tests/browser checks do not establish live provider quality or
  platform-media availability. Real calls/activation remain separate gates.
- Main owns final Child A acceptance, task progression, specs, Git and any later
  commit/review workflow. This reviewer did not advance or archive task state.

The review and execution gates support freezing A's handoff for the next child.
