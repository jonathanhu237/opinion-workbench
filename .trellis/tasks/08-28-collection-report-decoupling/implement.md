# Implementation Plan: Collection / Analysis / Report Decoupling

Status: approved for A -> B -> C implementation on 2026-08-29. Read `prd.md`
and `design.md` first. Live-operation and commit gates remain separate.
Implementation/spec/check/browser acceptance is now complete; final backend997
and frontend593 gates plus all AC/G mappings are in `research/acceptance-matrix.md`.
The proposed work-commit batch awaits user confirmation in `research/commit-plan.md`.

## 1. Review and Dispatch Gates

- [x] Present the latest complete planning summary and obtain a subsequent
  explicit approval. Earlier product decisions are not this approval.
- [x] Recheck local dirty state, task status, active task and schema baseline.
  Preserve the existing `08-27-ai-opinion-summary` task and unrelated edits.
- [x] Validate each child's PRD/design/implementation plan and both real
  spec/research manifests. Start only the child owning the next deliverable.
- [x] Keep this parent as integration owner, not an implementation worker.
  Dependency order is A -> B -> C; task-tree position is not a scheduler.
- [x] On approved execution, use Trellis implement/check routing. Every dispatch
  starts with `Active task: <actual child path>` and explicit file ownership.
  Shared database/lifespan/router files have only one writer at a time.

## 2. Ordered Delivery

### A — `08-29-shared-results-initial-analysis`

- [x] Add next-version schema, real legacy migration fixtures, markers and
  additive shared-results/initial-analysis/prompt repositories.
- [x] Implement strict prompt/version/authorization and result/provenance APIs.
- [x] Introduce shared idempotent admission, one-click all-never-started
  selection, automatic new-result handoff and independent saved attempts.
- [x] Preserve source/media validation, settled cancellation, no hidden retries,
  known-input-change protection and legacy history. Save completion events.
- [x] Add initial-analysis views, explicit retries, prompt editing and progress;
  keep full feature automation disabled until C integration is accepted.
- [x] Check A's complete scope and freeze its handoff contract before B starts.

### B — `08-29-scheduled-rule-collection` (depends on A)

- [x] Add the next additive schedule/occurrence migration; reuse existing rule
  and batch schemas. No prompt fields in monitoring rules/schedules.
- [x] Implement clock-injected interval calculation, idempotent occurrence/batch
  admission, busy skip, offline no-catch-up and verification-pause preservation.
- [x] Add schedule settings/history and lifecycle teardown; use A's completed
  collection handoff without duplicating source or AI work.
- [x] Check B independently, including A+B integration and rule edit/deletion.

### C — `08-29-automatic-text-reports` (depends on A and B)

- [x] Add the next report migration, immutable sources, typed nodes and coverage.
- [x] Consume completion events exactly once and independently of stage one.
- [x] Implement saved-text-only relevance, bounded leaf sections and overview
  aggregation, all-source coverage/citation checks, usage and retry versions.
- [x] Complete automatic report status, history, relevant/unrelated/uncertain
  views, saved-text interval selection and optional one-off prompt overrides.
- [x] Preserve legacy report routes and source opening; integrate the new module
  with collection pages without calling the old combined creation endpoint.
- [x] Perform final parent acceptance across A+B+C before any live activation.

## 3. Acceptance Test Matrix

| Gate | Tests and owning acceptance |
| --- | --- |
| G1 Persistence | Genuine v11 fixtures -> all new versions, reopen, forward-version rejection, real rollback after a child insert, old rows/JSON/IDs/usage unchanged, no migration-side AI work (AC01, AC08–AC10, AC14–AC15, AC28). |
| G2 Initial analysis | New+repeat+history distinctions, 0/1/101/1,001 eligible records across pages/runs, concurrent bulk/automatic clicks, frozen arrivals, actual media bounds, legacy active conflicts, explicit retry, prompt changes, latest-known-input failure (AC02–AC03, AC13–AC15, AC20–AC25). |
| G3 Scheduling | Fake clock: exact due, multiple due polls, backward/forward jumps, offline long gap, busy browser/analysis/manual pause, disabled/deleted rule, crash before/after durable batch link, shutdown settlement (AC10–AC13). |
| G4 Handoff | Ten records/eight successes/two failures -> one report only after ten attempts; no per-item report, no second click; new arrivals isolated; crash before/after event consumption; zero successful evidence; separate cancellation/interruption (AC03–AC04, AC09, AC26). |
| G5 Text reports | Every ready source judged; only relevant cited; uncertain != failure; 101+ sources and exact 120,000-character boundary with custom prompts; one oversized item; tree fanout/input/output validation; all leaf coverage retained; invalid or omitted citations fail (AC04–AC07, AC16–AC19, AC22–AC24, AC27). |
| G6 Independence | Instrument browser/acquisition/media/stage-one fake counters: report/retry/override adds zero to each; source/prompt edits cannot mutate old report; reuse counts no historic usage; unknown/overflow tokens remain unknown (AC04–AC09, AC17–AC22). |
| G7 Interface | Strict status/code decoding; no-store/local guards; UUID replay and ambiguous transport retry; empty/pending/success/failure controls; keyboard focus; separate stage progress; cross-page citations/XHS origin; first-entry interval and original publication distinction (AC05–AC08, AC14–AC28). |

Use temporary on-disk SQLite and injected fake browser/provider services. Model
JSON tests include malformed output, extra fields, duplicate keys, NaN, missing
terminal stream markers, unknown citations, credential sentinel and usage retained
after local validation failure. Do not turn a contract mock into a quality claim.

## 4. Environment and Validation Commands

All code/Git changes stay local. After edits, sync a verified source snapshot
one-way to a dedicated Centaurus checkout/test directory. Exclude `.git`, runtime
DB/WAL/SHM, credentials, browser profiles, staged media, `.venv`, node_modules,
build outputs and caches. No `--delete` or broad deployment overwrite is required.
Hash the source snapshot; do not modify it while a validation run is using it.

The existing planning copy `/tmp/longtian-decoupling-planning.GlIxvd/` is docs-only,
not the implementation/runtime target. Re-resolve target ownership and free ports
before implementation. If Centaurus is unavailable, report that first; do not
run heavy local tests/builds without permission. Use mise for missing tools.

Backend gates, **on Centaurus from the verified backend directory**:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

There is no configured Python type checker; do not invent a passed mypy gate.
Apply needed format changes to local source, then re-sync; remote is not an editor.

Frontend: format actual edits locally with the project's formatting command;
run frozen gates **on Centaurus from the verified frontend directory**:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

For browser acceptance, start an isolated `create_app` fixture with a temporary
database/fake services, not the default app against real runtime data. Bind backend
and frontend to remote loopback; forward both API and frontend ports locally.
Vite currently proxies to remote `127.0.0.1:8000`; use that free owned port or an
explicit isolated proxy override. Check Host/Origin allow-lists rather than adding
wildcard CORS. Close only owned servers/tunnels after acceptance.

Inspect routes at desktop and narrow widths, keyboard focus, reload, browser
console, separate progress/error states and history/citations. Do not open live
platform accounts or spend model quota as part of mocked UI acceptance.

## 5. Review, Specs and Rollback Points

- [x] Reread parent R1–R14 and all AC01–AC28 after the last child; record actual
  commands/results, gaps and limitations, not just an agent's “done”.
- [x] Update executable specs for the new two-stage trigger/admission/scheduler
  contracts. Keep the old manual-summary contract explicitly legacy and preserve
  shared media/privacy/citation/usage checks. Follow `trellis-update-spec` then.
- [ ] At each additive migration, preserve a recoverable pre-migration snapshot
  for authorized deployment. Tests use disposable fixtures, never production DB.
  This deployment-only gate is not executed or authorized by isolated acceptance.
- [x] Document rollback: disable admissions, settle owned work, leave new tables/
  history intact. No rollback was performed. Do not down-label schemas, drop
  tables or restore a live DB without a separate recovery decision.
- [x] Run final `trellis-check` gates and prepare the Phase3.4 Conventional
  Commit batch with explicit file classification; existing agent edits excluded.
- [ ] Obtain explicit approval and execute the proposed commits. No commit, push
  or task archive has been performed; bookkeeping follows separate authorization.
- [x] Live acquired-media/provider evaluation and enabling real schedules remain
  separate explicit operational gates. Report exactly what mocks did not prove.

Planning exit was completed before implementation approval. Implementation exit
is now supported by the linked full checks, browser observations and acceptance
matrix, not this checklist alone. Live-model/network limitations are retained;
source changes stay uncommitted and tasks unarchived pending the explicit gates.
