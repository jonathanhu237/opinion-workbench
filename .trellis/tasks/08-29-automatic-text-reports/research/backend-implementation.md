# C backend implementation evidence

Status: core implementation and isolated smoke are complete; the final merged
backend gate passed and the snapshot is formally frozen/released to main. Main
owns final C/parent review, browser acceptance and task state.
No commit, deployment, production migration, real browser session or paid model
operation was performed.

## Ownership and changed files

Core-owned new production files:

- `backend/src/longtian_api/migrations/topic_reports.py`
- `backend/src/longtian_api/schemas/topic_reports.py`
- `backend/src/longtian_api/repositories/topic_reports.py`
- `backend/src/longtian_api/services/topic_reports.py`
- `backend/src/longtian_api/services/topic_report_errors.py`
- `backend/src/longtian_api/api/v1/topic_reports.py`

Core integration changes are limited to `database.py` (v14), `api/router.py`,
`main.py` and `services/content_analyses.py` (admission-only completion callback).
No A acquisition or initial-understanding implementation was changed for reports.
The approved pure engine files and its 175 unit tests were authored/released by
the engine owner; this core consumes their frozen boundary without edits.

Core tests/fixtures: `topic_report_fixtures.py`, `test_topic_reports.py`,
`test_topic_report_migrations.py`, `test_topic_report_lifecycle.py`, and
`test_topic_report_api.py`. The existing A API fixture explicitly retains partial
rollout flags for A/B regressions. Existing A/B/legacy migration assertions were
updated only for additive schema14/table names, preserving all old-column checks.
Independent reviewer owns `test_topic_report_review_boundaries.py` (21 cases).
Smoke owner released `topic_report_smoke.py` and `test_topic_report_smoke.py`
(6 cases); main owns all service launches/tunnels.

## Implemented contract and safety proofs

- SQLite14 adds six report tables and immutable source/node/plan/ancestry guards.
  Genuine populated v13 fixtures contain legacy saved summaries, A queued and
  completed attempts/full saved evidence/usage/completion event, and B schedule
  history. Upgrade/reopen preserves every preexisting column; a failure after a
  real v14 source child insert rolls back all new DDL/DML. Version15 is rejected.
- One transaction consumes a normally settled A completion event, creates its
  unique automatic report and freezes every member, including unavailable ones.
  It verifies exact job/attempt/source/first-entry identity and all-member
  settlement. Automatic snapshots never join current content text. Later arrivals
  and later successful analysis cannot expand a retry's frozen scope.
- The A callback only admits/notifies; it does not wait on its own occupied AI
  lease. Report admission errors do not strand A. The report runner rechecks an
  empty queue under its admission lock and isolates unexpected per-report errors
  so later admitted intents remain runnable.
- Every ready saved source is judged once. Only relevant evidence is composed;
  uncertainty, initial unavailability and technical failure remain distinct.
  Persist all <=8-source, <=120000 exact-character leaves before composition,
  and plan each <=8-child overview level before execution. Fill across DB pages,
  carry only final singletons, retain all leaf detail, and never repair/repartition
  after a possibly billed call. 101/1001-source actual A→C integration proves no
  first-page cap, multilevel reduction and zero new A/media calls on retry.
- Fresh calls are regenerated from frozen evidence and actual graph rows. Stored
  `prepared_json` is audit-only. Planned hashes must match execution hashes;
  canonical reuse regenerates the original frozen context/dependencies before
  comparing compatibility. Reused logical child keys map to the new report's
  section IDs. Output digests, ordered membership, real disjoint child unions,
  complete relevant coverage, canonical node order and strictly older report
  ancestry are revalidated; damaged rows fail closed instead of looping.
- Attempts commit before transport. Known usage survives output parsing failure;
  unknown/overflow stays unknown, and reused nodes charge no historical requests.
  C's `observed_usage` reconstructs nested `AIUsage` at transport and persistence
  boundaries; invalid types/details become null usage while retaining attempted
  ownership. It never resurrects invalid raw usage from a parsing exception.
- Startup is storage-only: active reports and pending completion events become
  interrupted/non-runnable with `backend_restart`. Crash boundaries before/after
  admission, attempt marking and output settlement are tested; unrelated later
  queue wakes do not run recovered work. Explicit retry creates a new version.
- Separate report cancellation settles its owned text call without cancelling A
  or browser/media work. Lifespan stops the scheduler first and attempts every
  owner cleanup even when report cleanup fails. Application availability now
  defaults usable, while persisted automation/new schedules remain disabled;
  explicit False injections remain for A/B rollout tests.
- Interval reports use exact UTC microseconds in `[from,to)` and reject more than
  six fractional digits before admission. Choose the newest completed evidence
  matching the known input fingerprint, even behind a same-input failed/active
  attempt; never resurrect a success behind a known newer fingerprint. Shared
  prompt defaults are not overwritten by exact one-off overrides or retries.

The exact public boundary is in `research/backend-contract.md`; no frontend
consumer depends on engine/private messages. Run-only configuration failures
preserve the four approved existing AI codes/messages without widening A/legacy.

## Validation chronology

All heavy checks ran only on Centaurus at
`/tmp/longtian-decoupling-impl.dMCxsd/backend`, from one-way local source snapshots.
Local commands were formatting/import organization and read-only checks only.

- Engine owner: scoped Ruff/format + 175 tests passed in0.87s; exact file parity.
- Initial core A→C integration: 8 passed in35.87s; strengthened projection rerun
  8 passed in37.31s. Includes 10/8/2, 101/1001, bounded tree, compatible reuse,
  partial composition failure and empty outcomes.
- API/migration/lifecycle/independent review: 53 passed in7.62s.
- First merged full suite: 976 passed in79.19s; Ruff and format (125 Python files
  at that point) green.
- Additional API/lifespan + migration checks: 25 passed in4.20s.
- Final pre-usage migration/lifecycle/reviewer21 cases: 40 passed in4.98s.
- Smoke owner: scoped Ruff/format; 6 passed in13.86s with exact source parity.
- Usage regression was deliberately red on old core (`topic_report_storage_unavailable`
  after mutated nested counters). After the C-only fix: 4 passed,16 deselected
  in0.54s. No hidden retry or false zero accounting.
- Post-usage merged suite: 995 passed in93.24s, Ruff and format127 files green.
- Final explicit WB/XHS source-edit checks: 2 passed,8 deselected in0.46s. Both
  automatic creation and retry retain old frozen title/origin tuples after current
  source edits, without new stage-one/media work. No additional scope follows.

Early implementation-only failures were fixed rather than waived: SQL/import
formatting, async test wrappers (the project uses `asyncio.run`, no added plugin),
and a fixture using positional instead of keyword `AIUsage` construction.
No test dependency, type-checker configuration, ignore rule or production network
dependency was added. No configured backend Python type checker exists.

Final gate, exact frozen snapshot:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

Results: locked sync resolved54/checked52 packages; Ruff check passed;
format check reported127 files already formatted; **997 passed in92.52s
(0:01:32)**. This includes the accepted A/B740 baseline,175 pure-engine cases
and82 report core/review/smoke cases. The final command exited0. All commands owned
by this worker have ended; this worker started no services or tunnels. Main's
frontend46081 listener is not worker-owned and was left untouched;46082 was free
at the read-only pre-release check.

Local/remote parity: `rsync -aicn` for source/tests/manifests returned no changes;
`git diff --check -- backend` was clean. Sorted SHA256 manifests of every `.py`
under `src` and `tests` have the identical aggregate digest on both hosts:
`4befc2b7a7cdc49d0164becc25ecb00a11d08f537e39bc43b0a454963eea587c`.
Manifests also match exactly: `pyproject.toml`
`374b57593376f451a6e39090a91ed3053f2543f37ea9ef5a5c560ca530f5ae0c`,
`uv.lock` `a21e2245deb5f5c4a1f0ada5c587cc81981a6e04baba32d7847d3f83135e618c`.
No backend source/test edits or actual synchronization occur after this snapshot.

## Browser handoff and remaining work

See `research/smoke-fixture.md` for exact startup, URLs, fake-only override and
counter expectations. Entry point is
`topic_report_smoke:create_smoke_app` on127.0.0.1:46082; CORS permits only
`http://127.0.0.1:46081`. Main alone starts/stops it and the frontend.

The fixture has103 initial candidates across runs2/3 plus a separate readable
legacy run4/result104/summary1. Normal one-click initial analysis produces one
report with101 ready,2 unavailable,96 relevant,3 irrelevant,2 uncertain.
Override `验收：失败一次` fails one fake leaf once; explicit retry reuses101
judgments and11 leaves, then completes the missing leaf/tree. Fake model totals
are217→330→334, with media103,initial101,collection0 unchanged during report-only
work. Legacy generation requests stay0 during passive legacy navigation.

No source changes or remote sync are allowed while main's browser service snapshot
is live. Browser/parent acceptance and any resulting bounded fixes remain main's
responsibility; automated tests do not claim live-provider semantic quality.
