# C frontend implementation

## Scope and handoff

Implemented child C in `frontend/**` on top of checked A/B, including B's
same-revision rule-recovery fixes. Backend/public DTO ownership stayed with
`b_backend`; no engine model-call objects are consumed by the frontend. Main owns
isolated browser QA, final integration acceptance and spec/task metadata.

The frontend source snapshot is released to main at
`Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/frontend`. No frontend edit or sync
is planned after release; this evidence document was written after release.

## Delivered behavior

- Results & Analysis retains the existing one-click all-never-started initial
  analysis flow. Its disclosure now covers the frozen initial/report prompt pair
  and automatic second-stage text judgment/composition usage. Normal settlement
  reads the job-filtered report list and shows its report automatically. Empty
  admission visibility only causes GET polling, never a generation POST.
- First-stage results remain independent of second-stage success. Report status,
  frozen total/ready/unavailable coverage, relevant/irrelevant/uncertain/technical
  failure states and composition progress remain separate. Empty states explain
  zero ready text or zero relevant judgments without asserting no real incident.
  Configuration-blocked copy is neutral and uses the exact saved failure reason.
- Report history and independent versions use `report`, `reports_before`,
  `report_section`, `report_sources_offset` and `report_sections_offset` URL keys.
  Report selection clears report-detail pagination only; choosing a different
  initial job clears the report view without clearing result filters.
- Bounded requests read 20 history records, 20 frozen sources or five leaf
  sections per page. All leaf sections remain reachable. Overview citations use
  the current report's real child section IDs; leaf citations resolve from that
  section's own bounded frozen source snapshots, including sources beyond 100.
- Model prose is rendered as React text. No HTML or model-created URL is made
  executable. Non-XHS links use the validated frozen URL; XHS uses the stored
  origin-run/result tuple and retains shared pending/error controls. Saved initial
  text/prompt and original collection-history links remain available.
- Actual report instructions, origin/version and provider configuration are
  inspectable. Judgment/composition/total usage separates attempted/accounted
  calls, partial/unknown totals and compatible reuse without historical tokens.
- Report cancellation, failure recovery and changed-prompt new versions are
  independent of stage one. UUIDv4 and observed report/configuration revisions
  freeze the exact request. Ambiguous responses preserve that intent across
  closing/reopening for explicit replay; mutations never retry automatically.
  Known conflicts require refresh/reconfirmation, retaining form drafts.
- Optional first-entry-time reporting uses inclusive Asia/Shanghai UI dates
  normalized to UTC `[from,to)` and frozen cross-run saved-text scope. A one-off
  override never saves shared defaults or submits stage-one work. Pending actions
  lock duplicate submission/dismissal; dirty form dismissal is explicit.
- Real collection detail uses legacy history-only presentation: the primary
  analysis link leads to `/results`; legacy generation is neither mounted as an
  available action nor triggered on reads. Historical versions, citations and
  cancellation of already active legacy work remain functional.

## Public boundary and safety review

The narrow client matches `research/backend-contract.md`: strict exact fields,
safe IDs/counts, canonical UUIDs, UTC intervals, bounded UTF-8 prose and prompt
length, report origins, settled terminal state, coverage reconciliation, node
counts, page bounds/order and citation ownership are validated. Stage usage sums
include partial accounting and safe-integer overflow, not fabricated zero usage.
Mutation response status/identity/intent and fixed error-code/status/message
triples are checked. Abort signals remain aborts; response failures never leak raw
provider or transport text.

Only `ReportRun.error` accepts the four approved execution-stage configuration
failure codes. Source/node errors continue to use the existing `SummaryFailure`
boundary; A and legacy decoders were not broadened.

Read fencing compares incoming report control revisions with both detail and all
cached report lists. Mutation success cancels outstanding report reads, preserves
the newest observed revision and invalidates bounded queries. Same-revision node
progress is not incorrectly treated as a configuration conflict. Regression tests
cover both list-to-detail and detail-to-list stale-read ordering.

The direct before-dev, frontend-design and ui-ux-pro-max guidance kept the civic
theme, typography and existing Base UI components. It informed visible labels,
focusable validation, dirty/pending dialogs, narrow-layout wrapping, escaped
prose and secondary placement of optional actions. The direct trellis-check pass
found and fixed dirty-state subscription, revision fencing, truthful
configuration wording and the report-only error-union boundary. No dependencies,
global styles or design-system replacements were added.

Main's `topic-report-guidelines.md` public/interface/error guidance matches the
final frontend contract. No factual spec drift was found at handoff. New patterns
and cross-layer documentation remain main-owned.

## C files

New:

- `frontend/src/lib/api/topic-reports.ts`
- `frontend/src/lib/api/topic-reports.fixtures.ts`
- `frontend/src/lib/api/topic-reports.test.ts`
- `frontend/src/hooks/use-topic-reports.ts`
- `frontend/src/routes/results-report-actions.tsx`
- `frontend/src/routes/results-report-details.tsx`
- `frontend/src/routes/results-reports.tsx`
- `frontend/src/routes/results-reports.test.tsx`
- `frontend/src/routes/results-presenters.test.tsx`

Updated:

- `frontend/src/routes/results.tsx`
- `frontend/src/routes/results-jobs.tsx`
- `frontend/src/routes/results-confirmation.tsx`
- `frontend/src/routes/results-presenters.tsx`
- `frontend/src/routes/results.test.tsx`
- `frontend/src/routes/collection-ai-summary.tsx`
- `frontend/src/routes/collection-ai-summary.test.tsx`
- `frontend/src/routes/collection-run-detail.tsx`
- `frontend/src/routes/collection-runs.test.tsx`

Existing A/B changes elsewhere in the dirty worktree are preserved and are not
attributed to C. The eight obsolete real-route legacy-generation assertions were
updated to the approved history-only behavior; the existing historical content,
safe citation, pagination and active-legacy cancellation cases still exercise the
real collection detail route. Legacy API and confirmation component tests remain.

## Verification

All edits and formatting were local. One-way source sync, without deletion:

```sh
rsync -az --exclude=node_modules --exclude=dist --exclude='.env*' --exclude='*.local' --exclude=.git --exclude=.vite --exclude=.cache --exclude=coverage --exclude='*.tsbuildinfo' --exclude=runtime --exclude=profiles --exclude=media frontend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/frontend/
```

No source sync or remote edits occurred during a gate run. All final gates ran in
the remote frontend directory with `mise x node@24 pnpm@11.14.0 --`:

| Gate | Final result |
| --- | --- |
| `pnpm install --frozen-lockfile` | Passed; already up to date, pnpm 11.14.0 |
| `pnpm format:check` | Passed; all matched files formatted |
| `pnpm lint` | Passed; 0 warnings, 0 errors; 101 files |
| `pnpm typecheck` | Passed |
| `pnpm test:run` | Passed; 575 tests in 23 files; 9.06 seconds |
| `pnpm build` | Passed; 2,358 modules transformed |
| Local `git diff --check -- frontend` | Passed |
| Post-gate `rsync -rcni` with identical exclusions | Empty output; local/remote source parity |

This is checked B's 481 tests plus 94 C tests: 64 report client cases, 25 report
view/action cases, three frozen-source presentation cases, one real Results route
integration case and one real collection navigation case. Coverage includes 8/10
automatic settlement/no POST, nonnormal upstream suppression, all report states,
empty/unavailable distinctions, frozen prompts and usage, >100 source citations,
current-version child links, independent pagination, dirty override, Shanghai
intervals, explicit ambiguity replay, known conflict reconfirmation, pending
double-click/dismissal locks and both read-revision inversions. Existing A settings
save races, one-click whole-library admission, manual collection, batch recovery,
B schedules and legacy citations/cancellation are green.

Final source manifest: **118 files**, SHA-256
`8b40687f4f91c191d12aab6cf1c047cdd6027c3a3af4bcac7103adc8c87ad524`.

```sh
rg --files --hidden frontend -g '!node_modules' -g '!dist' -g '!.env*' -g '!*.local' -g '!.git' -g '!.vite' -g '!.cache' -g '!coverage' -g '!*.tsbuildinfo' -g '!runtime' -g '!profiles' -g '!media' | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256
```

## Remaining acceptance

Main's isolated fake-service browser QA and final cross-layer review remain.
This owner did not start services/tunnels, drive a browser, enable persisted
automation, create real schedules, call accounts/providers, deploy, commit, push
or archive. Mock/unit checks do not establish live model quality or production
platform readiness.
