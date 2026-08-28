# Implementation Status

## Approval

On 2026-08-29, after the complete final planning summary and links to PRD/design/
implementation plan, the user replied “开始吧。” This authorizes implementation
of the reviewed A -> B -> C plan and isolated verification. It does not authorize
live account collection, paid model calls, production migration, Git commit,
push or archive. The earlier planning-review.md remains a historical gate record.

After isolated acceptance, the user approved the exact two-commit batch and
requested an application start for hands-on use. Feature commit `61f2b15`
contains all 122 approved implementation/spec paths. The companion documentation
commit records the 54 approved task paths. Push, archive/journal bookkeeping,
production-data migration and live account/provider work remain out of scope.
The hands-on instance will use independent runtime storage on Centaurus and
loopback port forwarding, leaving existing services and data untouched.

## Progress

- A: complete implementation/spec/check/browser gates; feature committed,
  archive authorization pending. Final backend gates: Ruff + 656 tests; frontend all
  frozen gates + 370 tests. Browser: 103 admission, 102 saved, 1 incomplete,
  zero hidden calls, preserved prompts/evidence/history and narrow layout.
  Exact HTTP/event contract and evidence live in child A's `research/`.
- B: complete implementation/spec/check/browser gates. Final backend 740 tests/
  Ruff, frontend 481 tests/all frozen gates; fixed persisted-projection/timer
  validation and same-revision rule-dependency recovery. Browser passed forms,
  enable/edit/disable, history/reload/focus/narrow and paused-batch preservation;
  counters remained 2 collection / 0 model / 0 media. All owned services/ports
  are stopped. Exact evidence and contracts are in B's `research/`.
- C: implementation/spec/independent check/browser gates complete. Final backend
  997 tests/Ruff127 files; frontend593 tests/23 files and all frozen gates.
  Main separately reviewed the175-test pure engine. Browser103->101 ready->one
  automatic report, all-source judgments, full details, report-only override/
  retry, reuse, old/default preservation and narrow layout passed. Intermittent
  transport acknowledgements are documented, with successful same-request
  recovery and unchanged-code repeats; no unproven network fix is claimed.
- Parent: integration owner; implementation progress is recorded here and in
  child task state, not by starting the parent as a code worker.

A/B/C and parent isolated implementation acceptance are passed. See
`acceptance-matrix.md` for every AC01–AC28 and G1–G7. All owned services/tunnels/
tabs from acceptance are closed and disposable databases cleaned. Feature code
is committed; push/archive/production deployment and live evaluation were not
performed. See `commit-plan.md` for the approved commit scope.

## Review Follow-ups During A

- Verify prompt compare-and-swap conflict recovery preserves a local draft but
  requires an explicit action before rebasing onto a newer saved version.
- Exercise the queue-empty/admission race with a deterministic barrier: a new
  durable job must not be stranded when the previous runner is about to exit.
- Keep frontend/API smoke isolated on reserved loopback ports 46081/46082;
  recheck availability before launch. Fixture services must not use real
  provider credentials, platform accounts, browser acquisition or runtime data.
- The first browser connection exposed missing CORS in the cross-port smoke
  fixture, not a product endpoint failure (API reads were HTTP 200/no-store).
  Add an exact-origin test-fixture allowance; leave production guards unchanged.
  Before any mutation, synthetic model/media counters remained 0/0.

## Isolated Environment and Baseline

- Centaurus reachable; dedicated source/test snapshot:
  `/tmp/longtian-decoupling-impl.dMCxsd/`.
- Copied only backend/frontend source, tests, manifests, task/spec documents and
  the required `enrichment_contract_v1.json` fixture. No real runtime database,
  credentials, browser profiles, local environments or Git operations transferred.
- Frozen backend/frontend dependencies installed in that isolated directory.
- Initial remote baseline: backend `uv run --frozen python -m pytest -q tests`
  -> 596 passed in 13.64s; frontend `pnpm test:run` -> 14 files / 288 tests passed.
  These are baseline results, not acceptance of the new feature.
- Active child backend and frontend workers own their respective remote package
  snapshots for sync/checks; source edits remain local. Main does not overwrite
  those packages while their tests are using them.
- Existing remote ports 8000/5173/15173 are occupied and remain untouched.
  Isolated UI/API acceptance will use separately checked ports and fixtures.
