# Summary integration check — 2026-08-28

Verdict: **PASS for the implemented offline integration after the scoped fixes.**
This is not real provider/media acceptance or whole-five-platform readiness. The
task and media dependency remain open for their separately authorized live gates.

## Scope and method

Loaded `check.jsonl` and its references, PRD, design, implement, implementation
boundary and API contract. Applied `trellis-check`, refreshed `trellis-before-dev`
and the backend/frontend package guidelines, and used `fastapi` for API lifecycle
review and `ui-ux-pro-max` for accessible error/confirmation behavior. No redesign.

Reviewed the v11 migration, summary schemas/repository/service/router, lifespan,
AI settings completion seam, frozen-source enrichment check, transport checkpoint,
summary API decoder, confirmation, history/analysis UI and collection detail entry.
No old recovery logic, MediaCrawler source, user runtime, credentials or browser
state was modified. All product edits were local; only named source/test files
were synchronized to `/tmp/longtian-media-validation.DeYMEC` on Centaurus.
No real provider/platform call, Git operation, commit, push or archive occurred.

## Findings (fixed)

### I1 — Per-source historical matched terms were still capped at20

`frontend/src/lib/api/ai-summaries.ts` rejected a valid source matching21–100
historical terms, although the backend retains up to `MAX_TERMS_PER_RULE=100`.
It now imports that existing constant. The entire ordered array is preserved;
101 entries still fail. This complements the first checkpoint's model-context fix.

### I2 — UTF-16 lengths disagreed with backend code-point bounds

The new decoder's string maxima rejected valid astral Unicode in historical rule
names, titles, snippets, publication text, model reasons/evidence and report prose.
It now reuses `codePointLength` for those bounded fields and the existing term-length
constant. It never trims or truncates saved values. Boundary and one-over tests
cover both source/analysis and context/report payloads. Old search decoders were
not changed.

### I3 — Cancel/interruption guidance was repeated

`frontend/src/routes/collection-ai-summary.tsx` appended retained-analysis guidance
already present in the fixed cancellation/interruption message. It now omits only
that duplicate suffix for those two codes, retaining other failure guidance and
the accessible alert. Two regressions also verify stored analysis stays available
and that rendering does not start generation. Main independently observed the
duplicate in the synthetic browser check.

The frontend tests-only red run had **6 failed /58 passed in4.51s**: both historical
positive cases, both Unicode cases and both repeated-message cases failed at their
intended assertions. After the fixes, the focused two-file run had **64 passed in4.52s**.

### I4 — Summary exception responses lost `Cache-Control: no-store`

The normal response dependency did not cover separately constructed HTTP/validation
error responses. A real isolated API regression found missing headers on404,
path/body422, configuration409, media-type415 and origin403: **1 failed,
10 deselected in0.54s**.

`backend/src/longtian_api/api/v1/ai_summaries.py` now uses a summary-only `APIRoute`
wrapper. It preserves HTTP status/detail/other headers while replacing cache-control
case-insensitively, and maps request validation to the same fixed `invalid_request`
422 response with no-store. The old settings routes/global error handler are unchanged.
An additional regression preserves `Retry-After` and proves only one no-store header.
The initial repaired three-file summary suite passed38 tests; both final regression
cases are included in the complete596-test gate below.

Reviewer product/test writes in this checkpoint are exactly:

- `backend/src/longtian_api/api/v1/ai_summaries.py`
- `backend/tests/test_ai_summary_api.py`
- `frontend/src/lib/api/ai-summaries.ts` and `ai-summaries.test.ts`
- `frontend/src/routes/collection-ai-summary.tsx` and its test

## Positively traced contracts

- Admission freezes every unique stored source and historical context in one SQLite
  transaction; no UI page/filter participates. Zero, active/paused-parent and>100
  source cases make no media/model calls. A real second-child INSERT abort rolls
  back both parent and first child. The additive v10→v11 test preserves old rows.
- UUID replay binds run/refresh/revision, including terminal replay. The stable AI
  lease rejects changed configuration before acquisition and excludes settings edits
  or competing AI work. Source identity/text/terms are rechecked before worker/files.
- Compatible reuse is canonical, never a chain or copied usage. Observation/context/
  configuration/prompt/input versions participate; relative publication labels do
  not invalidate. A newer acquired fingerprint still invalidates older evidence
  when the newer forced analysis failed. Prior versions retain frozen sources.
- Serial acquisition validates complete text/media, releases the browser before
  composition, and makes no item call for incomplete input. The checked transport
  still sends exact bounded bytes once, with no cover/text fallback or repair call.
- Valid uncertain is a completed analysis. Only relevant saved evidence enters one
  text-only composition. Empty relevant evidence makes no composition call; oversize
  final input and invalid citations preserve completed item analyses.
- Cancellation at acquisition/analysis/composition, cancellation during an in-flight
  SQLite write, graceful shutdown and startup interruption preserve completed evidence
  and settle owned work. GET/polling/reload/startup do not resume paid work.
- Accounting sums only new attempts, including composition; local parse failure
  retains valid usage, reuse contributes none, missing usage is unknown and aggregate
  overflow returns null/incomplete while preserving bounded per-attempt counts.
- The UI freezes the displayed destination/revision and full source count, prevents
  duplicate submits, reuses the same UUID only for an explicit ambiguous retry, and
  requires reconfirmation after stale configuration. History and display pagination
  are URL state; full-set citation checks resolve result IDs independently of pages.
  Model prose is escaped text, never executable HTML/links. XHS retains the existing
  stored-result opening action; original results remain usable without AI.

## Verification

Reviewer-run, source-only Centaurus checks:

```sh
cd /tmp/longtian-media-validation.DeYMEC/backend
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/pytest -q tests/ --tb=short

cd /tmp/longtian-media-validation.DeYMEC/frontend
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

- Backend final: **596 passed in11.94s**, zero skips; Ruff clean, **68 files formatted**.
  No separate Python type-checker is configured; no such pass is claimed.
- Frontend final: **281 passed /14 files in7.95s**, zero skips; frozen install,
  format, lint (**0 warnings/errors**), TypeScript and production build all pass.
  After main stopped its owned preview, the exact verified isolated `node_modules`
  symlink alone was unlinked; a fresh447-package frozen install completed in543ms.
  Its shared dependency target was not modified or removed.
- SHA256 comparison covered30 current backend/frontend source/test/package/lock
  files. It caught one unsynchronized owner-final schema hardening (UUID length and
  closed public error codes). That local file was narrowly resynchronized, and the
  backend gate above was rerun. **All30 local/remote hashes now match**; the earlier
 596-test12.13s run is not the final frozen-source evidence.
- Main-run actual UI with isolated synthetic API/media/model boundaries passed
  full-scope confirmation, keyboard dismissal, mixed outcomes, citations, reuse,
  read-only reload, force cancellation, old versions and no horizontal overflow;
  warning/error logs were empty. See `verification.md`. This was not independently
  replayed by the reviewer and is not actual model/media-quality evidence.
- Main's post-fix preview reopened run1/summary#3 using the fresh isolated frontend
  dependencies. Cancellation guidance appeared once; one completed/three cancelled
  analyses,15 synthetic tokens with incomplete accounting, and analysis disclosure
  remained. GET/reopen added no calls, staging stayed empty, and warning/error logs
  were empty. The existing fake API process was preserved for history; final API
  no-store coverage comes from the reviewer-run tests, not that older process.

## Findings (not fixed) / remaining boundaries

No remaining concrete blocker was found in this scoped implementation. Main completed
the post-fix preview and owns task/spec evidence. The reviewed new summary guide and
state-management contract are consistent; main reports the final wording now explicitly
states combined title+body20,000-character bounds and no-store on declared summary
success/error responses.

- A separately authorized real acquired-media→provider→saved-analysis→text-summary
  acceptance is still pending. Synthetic images/responses and the earlier private
  cost probe do not prove that product chain or five-platform completeness.
- Media compatibility remains the exact reviewed DashScope endpoint/model pair;
  other configurations support complete text-only inputs without a media fallback.
- Existing media-worker quarantine/abnormal-exit limitations remain inherited:
  writer quiescence is not proof of whole-process-group cleanup. No global process
  manager change or false resource-reclamation claim was introduced here.
- Citation membership/strict parsing cannot prove semantic truth. Saved judgments
  remain attributed source analysis, not verified incidents or a quality benchmark.

Source remains frozen. The final UI/evidence reconciliation above changes no product files.
