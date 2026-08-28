# B frontend implementation evidence

Date: 2026-08-29. Owner: `b_frontend`. Scope is the frontend portion of child B;
this is not parent completion or browser-acceptance evidence.

## Implemented surface

The existing `/collection-runs` page now has a separate **定时采集** section
between its active manual batch and existing collection history. The manual
start form, batch pause/recovery controls and single-run/batch history routes
are unchanged. The six existing navigation destinations remain intact.

- Create a disabled schedule using a rule, catalog-ordered platforms, per-term
  cap and a whole-minute/hour interval. No independent schedule name, cron,
  prompt, model or report fields were added. The saved rule name is its label.
- Edit dirty configuration using the observed `expected_revision`; interval
  values normalize to 1–43,200 minutes. An enabled save preserves enablement
  and displays the server's new future due time. There is no client-side clock
  calculation of authoritative due times.
- Enable/disable uses a separate explicit confirmation and full current
  configuration. Stale controls require rereading and confirmation; disabling
  explains that already submitted batches, including manual pauses, remain.
- Rule state, saved enablement and rollout `available` are separate UI states.
  `available=false` explicitly says configuration can be saved but does not
  execute automatically. Browser-unavailable occurrence text advises a manual
  platform connection check after backend restart, without implying that every
  platform is authenticated.
- Schedule and occurrence pages use 20-row descending-ID cursors. URL state is
  `schedule`, `schedulesBefore`, `occurrencesBefore`, with bounded ID parsing and
  invalid-link recovery. Times are labelled and rendered in Beijing time.
- Claimed, dispatched, skipped, missed and interrupted outcomes remain
  distinct. The UI displays bounded reason copy, current linked batch state,
  missed count/range, source-safe batch detail links and the shared `/results`
  link. Dispatch is never presented as successful-empty collection.

## Changed files

Added:

- `frontend/src/lib/api/collection-schedules.ts`: exact backend request/error
  boundary, strict schedule/occurrence decoders, pagination and normalized input
  validation. `expected_revision` is less than `Number.MAX_SAFE_INTEGER` so its
  increment remains safe; output revision permits that maximum.
- `frontend/src/hooks/use-collection-schedules.ts`: read-only list/detail/history
  queries and bounded active polling; post-save cancellation of stale reads and
  revision-preserving cache updates.
- `frontend/src/routes/collection-schedules.tsx`: list, selection, history,
  paging, truthful status/next-due copy and guarded enable/disable confirmation.
- `frontend/src/routes/collection-schedule-editor.tsx`: labelled Base UI/RHF/Zod
  form, pending locks, dirty dismissal, draft-preserving CAS recovery and deleted
  reference handling.
- `frontend/src/lib/api/collection-schedules.fixtures.ts`: typed isolated
  schedule/occurrence fixtures.
- `frontend/src/lib/api/collection-schedules.test.ts`: 77 boundary tests.
- `frontend/src/routes/collection-schedules.test.tsx`: 29 interaction, form,
  revision and read-race tests.

Small integration changes:

- `frontend/src/lib/api/search-batches.ts`: export the existing batch-status
  schema; no change to its accepted statuses or behavior.
- `frontend/src/routes/collection-runs.tsx`: import and mount the new section.
- `frontend/src/routes/collection-runs.test.tsx`: add an empty schedule-list
  fixture; make the existing batch/run "查看" link assertions exact to avoid
  conflating the new shared-results link with existing source links.
- `frontend/src/App.test.tsx`: add an empty schedule-list fixture. Existing A
  navigation/test edits are preserved and are not attributed to B.

No backend, spec, task metadata, package/lockfile, global CSS, deployment or Git
state changes were made by this owner. No new dependencies were added.

## Safety and accessibility checks

Read-only route entry, selection, refresh and polling cannot submit a schedule
or batch. Query cancellation fences GETs started before or during a successful
save; an older mutation response cannot replace a newer cached revision.
Conflict recovery retains dirty values and needs explicit adoption of the new
revision before another save. Pending submission locks duplicate actions and
dialog dismissal, while validation still leaves invalid fields focusable.

The before-dev, frontend-design and ui-ux-pro-max guidance kept the existing
civic palette/type hierarchy and Base UI components, added visible field labels
and error associations, and informed narrow-layout wrapping and keyboard focus
handling. The implementation quality pass also fixed Base UI's empty-value
placeholder behavior for a deleted rule: the UI uses a dedicated display value
but submits the backend's null reference. Main-owned browser QA still validates
the actual rendered narrow layout and keyboard/console behavior.

The main-owned `collection-schedule-guidelines.md` matches these frontend URL,
CAS, history and polling boundaries. No factual drift found at handoff.

## Verification

All code edits and formatting were local. Source was synced one-way using:

```sh
rsync -a --exclude=node_modules --exclude=dist --exclude='.env*' --exclude='.vite' --exclude='.cache' --exclude=coverage --exclude='*.tsbuildinfo' frontend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/frontend/
```

No remote files were edited, and no source sync occurred during checks. Final
gates ran on Centaurus in that frontend directory with
`mise x node@24 pnpm@11.14.0 --`:

| Gate | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | Passed; already up to date; pnpm 11.14.0 |
| `pnpm format:check` | Passed; all matched files formatted |
| `pnpm lint` | Passed; 0 warnings, 0 errors, 92 files |
| `pnpm typecheck` | Passed |
| `pnpm test:run` | Passed; 476 tests in 20 files; 8.72 seconds |
| `pnpm build` | Passed; 2,353 modules transformed |
| Local `git diff --check -- frontend` | Passed |
| Post-gate checksum `rsync -rcni` with the same exclusions | Empty output; local/remote source parity |

The total is A's 370 existing tests plus 106 new schedule tests. This includes
the unchanged manual-collection, recovery, result-library, settings-save race,
summary and application navigation suites. Targeted tests were run first; early
test/label issues were corrected before this full clean gate.

Final local source manifest: 109 files, SHA-256
`7e05f94aaf5fb9104e6e2122db9b193aab18a06b0c797ec090a7eebcc45c742f`, generated by:

```sh
rg --files --hidden frontend -g '!node_modules' -g '!dist' -g '!.env*' -g '!.vite' -g '!.cache' -g '!coverage' -g '!*.tsbuildinfo' | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256
```

The remote source snapshot was released to main after all gates and the empty
checksum dry run. Only this evidence document was written after release.

## Remaining acceptance

Main owns isolated fake-backend browser QA, final combined backend/frontend
review and C rollout. This owner did not start services, drive a browser, create
real schedules, contact accounts/providers, deploy, commit, push or archive.
Mock/unit gates do not establish live browser readiness, login state or platform
collection quality.
