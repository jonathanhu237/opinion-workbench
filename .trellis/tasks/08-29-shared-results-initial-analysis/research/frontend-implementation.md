# Frontend implementation boundary

The existing application only exposes per-collection results and legacy combined
summaries. Child A adds `/results` for global source/evidence inspection and
independent initial-analysis admission, without changing collection or legacy
report storage. Backend owns the exact HTTP contract in `backend-contract.md`.

Frontend ownership: `frontend/src/lib/api/{analysis-shared,analysis-settings,
content-analyses,results}.ts`, their decoder fixtures/tests, route composition and
small feature components under `routes/`, router/shell navigation, and behavior
tests. Existing source/failure/token validators will be exported for reuse without
changing their legacy behavior. No dependency, global-theme, backend, scheduler,
report-generation, production-data or Git changes are included.

Design: retain civic pine foreground `#0d3b3a`, teal action `#16736d`, pale green
canvas `#f4f7f4`, white evidence surface `#ffffff`, muted text `#566f6d`, and
warning `#b86b26` through existing semantic tokens. Songti display, PingFang body,
and the existing utility face remain unchanged. The signature is a paired
source/evidence ledger: the source and first-entry provenance remain visible next
to separately labelled initial understanding and its frozen version.

The UI/UX skill design-system searches returned a marketing hero pattern even
after one narrower retry. That pattern and its palette/fonts were not adopted;
the approved civic design and skill's general keyboard, feedback, layout and
reduced-motion guidance are the applicable fallback. No unverified search output
was persisted as a design system.

Layout: full-width all-library action and independently saved prompt/settings
disclosure; filtered, paginated source ledger; selected source with saved evidence,
origins and legacy history; separate paginated job/progress panel. Mobile stacks
these regions and preserves every status/action label. The bulk action never
serializes visible IDs or applies the result filters. Confirmation freezes provider
and both prompts; ambiguous replay retains its UUID. Page entry and polling only
read. Failed retry and completed/legacy reanalysis have separate explicit intents.

Validation runs on the main agent's isolated Centaurus snapshot. Local formatting
is allowed; no local tests, typecheck, build or live provider/browser operation.
Results and follow-ups will be appended after implementation.

## Implemented

- `/results` is a real lazy-loaded route and sixth navigation destination. It
  exposes the paginated global ledger, platform/state/first-entry filters, and
  all-library eligible/active counts independently of the selected page.
- The all-never-started request has no visible-ID array or time filter. Explicit
  first analysis, failed/legacy-attempt retry, and completed/legacy-completed
  reanalysis remain separate intents; reanalysis explicitly reacquires input.
- Confirmation retains both prompt objects and provider revision. An ambiguous
  response retains one UUID even when the dialog is temporarily closed. Definite
  conflicts require refresh and a new explicit confirmation. No GET or polling
  submits a mutation.
- Prompt editors save independently with code-point/UTF validation, compare-and-
  swap versions, pending/error states, and explicit stale-draft recovery. Adopting
  a newer version retains the draft and still requires a separate Save action.
- Automatic authorization is provider-revision-bound and distinguishes saved
  authorization from `available=false` rollout. It does not claim that child A
  alone generates reports.
- Saved understanding exposes attributed location/time/media observations,
  uncertainties, full accepted source text, coverage, media metadata and usage.
  Task prompt/provider snapshots and paginated analysis/origin/legacy history are
  independently readable. XHS uses the exact stored source-run/result tuple.
- Job progress, individual item status/errors, cancellation and completion proof
  remain separate from report status. Terminal transitions refresh evidence once;
  old-task browsing retains cancellation for other active tasks. Legacy queued
  ownership blocks duplicate row actions even without a new job ID.
- Evidence/job navigation moves focus into the requested content; closing source
  details restores focus. Existing collection AI summaries are labelled legacy
  and link to Results and Analysis; old report creation/read contracts are intact.

## Verification (2026-08-29)

All executable gates ran on Centaurus at
`/tmp/longtian-decoupling-impl.dMCxsd/frontend`, after one-way frontend-only rsync.
No runtime data, secrets, dependency directories, build output or Git data was
sent. No remote source edit was made and no sync occurred during a gate run.

Command prefix: `mise x node@24 pnpm@11.14.0 --`.

| Gate | Actual result |
| --- | --- |
| `pnpm install --frozen-lockfile` | Passed; already up to date, pnpm 11.14.0. |
| `pnpm format:check` | Passed; all matched files conform to Prettier. |
| `pnpm lint` | Passed; 0 warnings/errors, 85 files. |
| `pnpm typecheck` | Passed; `tsc -b --pretty false`, exit 0. |
| `pnpm test:run` | Passed; 18 files, 362 tests (74 new), 8.44 s. |
| `pnpm build` | Passed; Vite 8.2.2, 2349 modules, 286 ms; Results lazy chunk 57.38 kB / 16.35 kB gzip. |
| Local `git diff --check -- frontend` | Passed. |
| Checksum dry-run `rsync -rnci` with the same exclusions | No differences reported. |

Earlier verification caught recursive schema type inference and unsupported TS
parameter-property syntax; these were fixed locally. The first full test run
also exposed a consumed synthetic Response reused by a test and an assertion
that needed to await Query's observer notification. Both tests were corrected,
with no product validation weakened. The final passing snapshot includes added
terminal-polling, active-legacy, and keyboard-focus regressions.

Main owns the remaining isolated browser acceptance: desktop/narrow layouts,
console, real HTTP decoders against the fake backend, prompt saves, whole-set
admission and historical source navigation. No live platform opening, provider
request, model-quality claim, production DB change or deployment was performed.
Full report generation and scheduling remain child C/B work, with rollout off.

## Spec handoff

Main should capture the new Results route, explicit/automatic admission distinction,
full-library selection independent of filters, immutable prompt/provider intent,
legacy-origin link and stale-draft/ambiguous-replay recovery contracts in the
owning frontend/backend specs. This frontend worker did not edit specs, task
status, Git history or unrelated backend work.
