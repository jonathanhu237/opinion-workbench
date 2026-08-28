# Child A frontend review

2026-08-29. Reviewed the saved complete check-hook context, child/parent PRD,
design and implementation plans, exact backend contract and implementation
evidence, frontend specs, and the new independent-analysis spec. Used
`trellis-check`, `trellis-before-dev` and UI/UX guidance. Browser acceptance is
main-owned; this report is not full Child A or parent acceptance.

## Findings (fixed)

1. `frontend/src/routes/results-settings.tsx`: each independent prompt/policy
   save replaced the whole settings cache. Reversed response order rolled back
   the sibling prompt or newer automation authorization. A GET started before
   or during a pending save could also arrive late and overwrite committed state.
   Both successful save paths now cancel in-flight settings reads, then merge
   the independently monotonic prompt IDs and policy revision. No global store,
   public API or backend mutation was added. Five deterministic response-order
   tests cover both prompt orders, authorization and both GET timings.
2. `frontend/src/routes/results.tsx`: Refresh reloaded only the list, settings
   and jobs, leaving failed selected-source/detail/history reads untouched.
   It now invalidates the results and content-analysis resource families, so all
   active evidence/origin/legacy readers can recover. A test fails all five
   selected-source reads, retries through the visible Refresh control, and
   verifies zero analysis, prompt, authorization or source-open mutations.
3. `frontend/src/lib/api/content-analyses.ts`: ready input could declare image,
   video or audio evidence absent from its saved asset inventory. The decoder now
   applies the existing canonical enrichment modality/asset correspondence,
   including audio-bearing video, before accepting readiness. Tests retain valid
   image/video input and incomplete inventory while rejecting six false-ready
   combinations. It does not reinterpret incomplete evidence as unrelated.

Regression files: `frontend/src/routes/results.test.tsx` and
`frontend/src/lib/api/content-analyses.test.ts`. No other frontend file was edited
by this reviewer. All other frontend implementation changes were preserved.

## Reviewed behavior

- All-never-started sends one server-side set intent, not visible IDs or date
  filters. Individual first analysis, retry and legacy/completed reanalysis stay
  separate; active legacy ownership prevents duplicate row actions.
- Confirmation retains its UUID, provider revision and both prompt snapshots;
  ambiguous replay retains the intent and definite conflict requires reconfirmation.
- Prompt drafts remain independent, preserve exact Unicode text and survive CAS
  conflicts. Saved authorization and disabled rollout are separately labelled.
- Read/poll/refresh paths do not submit work. Final settlement refreshes item
  evidence; active cancellation stays available while browsing old jobs.
- Saved source/run identity, old report origin, full accepted text, media
  metadata, uncertainty and unknown/reused usage remain distinct. Output renders
  as escaped text, with application-owned source URLs and stored XHS open tuples.
- No new route calls the legacy generation endpoint; existing legacy history and
  creation contracts are preserved and clearly labelled.

## Verification

Local edits and formatting only. All execution gates ran on the unchanged
Centaurus snapshot `/tmp/longtian-decoupling-impl.dMCxsd/frontend`.
Node `v24.20.0`, pnpm `11.14.0`.

Local formatting: `cd frontend && mise x node@24 pnpm@11.14.0 -- pnpm format`.
One-way source synchronization:

```sh
rsync -a --exclude=node_modules --exclude=dist --exclude='.env*' --exclude='.cache' --exclude='.vite' --exclude='coverage' --exclude='*.tsbuildinfo' frontend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/frontend/
```

No `--delete`, remote source editing, runtime data, credentials or sync during
checks. Repeating the same exclusions with `rsync -rnci` reported no differences.
The local sorted source-path/SHA-256 manifest hash is
`000630f3187ab4d72e9d939e320c3d1e9d77dea864f4edca89b227af3e30e985`.

Command prefix below: `mise x node@24 pnpm@11.14.0 --`, from the remote package.

| Command | Result |
| --- | --- |
| `pnpm test:run src/routes/results.test.tsx -t "keeps both saved prompts\|does not erase newer automation\|keeps saved prompt state\|retries selected-source" --reporter=dot` | Before fix: 6 failed. After fix: 6 passed; 16 intentionally unselected. |
| `pnpm test:run src/lib/api/content-analyses.test.ts -t "validates ready media inventory" --reporter=dot` | Before fix: failed on accepted missing image inventory. |
| `pnpm test:run src/lib/api/content-analyses.test.ts --reporter=dot` | After fix: 14 passed, no skipped tests. |
| `pnpm install --frozen-lockfile` | Passed; already up to date. |
| `pnpm format:check` | Passed. |
| `pnpm lint` | Passed; 0 warnings/errors, 85 files. |
| `pnpm typecheck` | Passed; `tsc -b --pretty false`. |
| `pnpm test:run` | Passed; 370 tests, 18 files, no skipped tests, 8.36 s. |
| `pnpm build` | Passed; 2349 modules, 275 ms, Results chunk 58.03 kB / 16.48 kB gzip. |

## Prevention / scope handoff

The break-loop analysis identifies a test-coverage/implicit-ordering gap: success
responses from independently versioned settings are not globally ordered, and
route-level retry must cover every active read owned by that route. Preserve
these response-order and recovery tests. The media gap was missing boundary
parity, now tested with positive complete and negative incomplete inventories.
Main owns spec changes and Git; the reviewer did not widen its ownership to
write/commit specs despite generic skill suggestions. Recommended spec additions
were sent to main: monotonic independent settings updates with pending-read
cancellation, full active-detail refresh recovery, and ready inventory matching.

No unresolved frontend-local finding remains in this pass. Desktop/narrow browser
layout, keyboard and console acceptance remain main-owned. No live platform,
provider, production database, scheduling/report execution or deployment claim.
Full backend/Child A review continues separately in `full-check.md`.
