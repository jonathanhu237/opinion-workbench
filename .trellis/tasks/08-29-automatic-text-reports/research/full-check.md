# C and A+B+C full-scope check

Status: scoped code/spec checks and isolated workflow acceptance passed. All
automated gates passed on the final frozen backend/frontend sources; main's full
browser coverage, unchanged-code desktop/narrow repeat and final decoder-only
targeted revalidation are complete. Intermittent response delivery remains an
undiagnosed observation with successful idempotent recovery, not a claimed fix.
This document does not advance task state.

Reviewer: reused `a_frontend`, independently reviewing the C backend core and
frontend owners. The review used `trellis-check`, `trellis-before-dev`, existing
FastAPI guidance and frontend/UI accessibility guidance. No agents were spawned.
The reviewer previously implemented the pure engine: **that engine is excluded
from this independent-review claim**. Main's independent
[engine-review.md](./engine-review.md) covers it; the final merged backend suite
includes its 175 tests.

Read C's PRD/design/implementation/check manifest, exact HTTP and engine seams,
parent R1–R14, every AC01–AC28 and G1–G7, A/B handoff/migration evidence, current
package specifications and the final `topic-report-guidelines.md`. Reviewed
core repository/service/schema/migration/API, lifecycle and A callback changes,
the complete new report client/hooks/actions/details/history UI, actual Results
and legacy collection routes, and their tests. A/B behavior is checked through
the modified shared integration and retained full suites, not merely the C diff.

## Findings and resolution

1. **Frozen identity and interval evidence.** A damaged latest-attempt pointer
   could follow another content row outside the selected interval. Admission now
   checks selected content, attempt, source and first-entry identities before
   freezing; failure rolls back the report and UUID record. Explicit intervals
   choose the newest completed evidence matching the claim's known input
   fingerprint, including behind a later failed/active attempt. A known newer
   input cannot revive old success. Automatic reports still use exact current-job
   attempts; retry never reselects current evidence.

2. **Precision on both sides of the API.** SQLite `julianday` collapsed distinct
   microseconds; frontend `Date.parse` independently did the same in interval
   validation and mutation acknowledgement checks. Backend selection now compares
   normalized UTC microseconds. New C interval endpoints accept at most six
   fractional digits and reject greater precision, without changing shared A/B
   timestamps. Frontend compares normalized six-digit UTC keys, preserving exact
   strings and handling mixed `Z`/`+00:00`, absent/short fractions and second/day
   boundaries. A one-microsecond changed acknowledgement is rejected. Whole-day
   Shanghai date controls remain unchanged.

3. **Recovery and queue termination.** An existing event/report link with event
   state `pending` previously returned the report repeatedly during initialization.
   It now fails closed after one read, with origin/state checks. A per-report
   unexpected exception previously exited the runner and stranded a later queued
   intent; it now settles that report and continues the queue. Empty-queue exit
   rechecks under the admission lock. Cyclic retry ancestry cannot loop: each
   parent must be older than the current version; canonical reused nodes must be
   older than the referring node.

4. **Executable proof and graph integrity.** Main's earlier core review identified
   missing planned-versus-fresh hash checks, canonical original-call reconstruction
   and actual child-membership proof. Final code regenerates calls from frozen
   evidence/current-version graph, checks saved plans, reconstructs the canonical
   original context before reuse, validates output digests and enforces leaf
   exact coverage plus disjoint child unions. Persisted `prepared_json` is audit
   data, never executable authority. Recomputed leaf hashes do not make overlapping
   actual members valid. Final completed projections revalidate the root graph.

5. **Strict persisted projections.** Provider strings, frozen source identity,
   evidence availability, unavailable status/reason, output digest and report
   state are validated before returning saved data. Corruption maps to the fixed
   storage error, not fabricated success or a raw payload. Four report-local
   configuration-blocked reasons use existing constant AI messages without
   widening A/legacy source/node failure unions. UI wording is neutral rather
   than incorrectly declaring every configuration failure a changed model.

6. **Report cache and form recovery.** List reads could choose an older detail
   instead of a newer list; detail reads had the inverse omission. Both now choose
   the greatest known control revision across incoming/detail/all cached lists.
   Tests assert the displayed cancelled state, not just cache contents. Equal
   revisions still permit live node progress. The frontend owner also repaired
   RHF dirty-state subscription; pending dismissal/double submit, preserved draft
   conflict recovery and stable UUID replay are tested. The real legacy route now
   exposes history/navigation without an old combined-generation POST.

7. **Usage persistence seam (main finding; verified fixed).** C's
   `observed_usage` strictly reconstructs transport usage on receipt and again
   before persistence. Mutated invalid usage is unknown (`None`), with attempted
   ownership preserved, rather than corrupt JSON that makes later reads fail.
   Parse-failure handling never falls back to the invalid original object. Four
   regressions cover successful/invalid completion crossed with mutated details/
   wrong usage types; all pass in the final 997-test suite. The engine is unchanged.

8. **Final ancestry decoder parity.** Backend projections rejected self/future
   parent and canonical-node IDs, but the frontend still rejected only equal
   IDs. Two frontend conditions now require strictly older referenced IDs.
   Five regression cases exercise self/future report parents across detail,
   history and retry acknowledgements, self/future canonical nodes across section
   detail/pages, and valid older references. The two future-ID cases failed on
   the old decoder and pass after the fix. This did not change fetch, UI actions,
   backend DTOs, and is not a fix for the transport observations below.

All production fixes were made by the owning implementer except the reviewer's
bounded frontend interval and ancestry-decoder fixes. No design-system,
dependency, public DTO-field, third stage, provider or media transport expansion
was introduced.

## Independent regression file

`backend/tests/test_topic_report_review_boundaries.py` contains 21 cases:

- wrong latest-claim identity with atomic admission/UUID rollback;
- existing linked/pending event rejected once without an unbounded loop;
- exact lower-inclusive/upper-exclusive microsecond membership;
- same-input versus known-new-input failure; queued/acquiring/analysing latest
  attempts retaining a compatible earlier success without waiting or starting A;
- changed planned input cannot be overwritten; forged canonical hash cannot
  replace original frozen prompt/context proof;
- judgment/leaf/overview output-digest corruption, provider/source identity
  corruption and actual overlapping children despite recomputed leaf hashes;
- damaged retry ancestry fails in a bounded number of reads;
- retry retains originally unavailable evidence after a later successful A
  attempt; malformed persisted prepared messages remain non-executable audit data.

Fixtures use real A/C repositories/services over temporary SQLite and existing
fake model/media boundaries. Deliberate corruption removes only disposable test
guards; no production store, browser, account or provider is touched. Every
admission/reuse/projection case asserts no additional model/acquisition calls.

## Parent gate coverage

| Gate | Reviewed executable evidence |
| --- | --- |
| G1 persistence | `test_topic_report_migrations.py`: genuine populated v13 (built from historical v11 plus actual A/B migrations), unchanged old table projections, additive v14/reopen, foreign keys/WAL/busy timeout, rollback after real parent+child inserts, forward-version rejection. Prior A/B migration suites remain included. |
| G2 initial analysis | Retained A repository/API/understanding/media tests, explicit whole-library 101/1,001 admission and legacy interlocks; C changes only the post-settlement callback and application availability, not acquisition. Review interval fallback cases preserve known-input rules. |
| G3 scheduling | Retained B repository/service/API/smoke tests: clock jumps, >100 schedules, busy/manual ownership, no catch-up, current-rule snapshots, atomic batch links, no-I/O startup and one post-release A handoff. See B's [full-check.md](../../08-29-scheduled-rule-collection/research/full-check.md). |
| G4 handoff | `test_ten_members_eight_successes_settle_one_report`, concurrent/rollback event consumers, later arrivals, callback failure isolation, upstream-lease nonblocking notification, empty-queue admission, crash admission/attempt/output boundaries and startup records remaining non-runnable after a later wake. |
| G5 text reports | Actual 101/1,001 pipeline tests, every ready source judged, relevant-only leaves, preserved irrelevant/uncertain summaries, bounded reducing overview tree, retry after composition failure, complete graph/citation/digest checks. Main's separate engine review covers strict shapes and exact 120,000-character bounds. |
| G6 independence | Fake acquisition/initial/model counters across compatible retry, changed instructions/provider, unknown/overflow usage, parse failure, frozen-unavailable retention, cancellation/shutdown and current-version child-ID mapping. No report-only operation starts A or media. |
| G7 interfaces | HTTP local guards/no-store/constant errors, strict decoders/cursors/IDs, stable UUID replay, explicit conflict recovery, two independent stages/defaults, exact interval precision, bounded frozen citation sources and XHS origin opening, real legacy history-only navigation. Main's full browser coverage/repeat and final decoder-only revalidation are recorded below. |

## Validation commands and results

All source edits and formatting were local. Heavy checks ran only on isolated
Centaurus snapshots, serialized with the package owner. No sync occurred during
a package run; no remote source edits or deletion sync was used.

Reviewer focused backend command, inside
`/tmp/longtian-decoupling-impl.dMCxsd/backend`:

```sh
uv run --frozen ruff check tests/test_topic_report_review_boundaries.py
uv run --frozen ruff format --check tests/test_topic_report_review_boundaries.py
uv run --frozen python -m pytest -q tests/test_topic_report_review_boundaries.py --tb=short
```

The initial 18-case version passed all commands: **18 passed in 2.73s**. An earlier
lint-only attempt found one E501 SQL string; it was fixed locally before that
run. Three subsequent contract cases make the final file 21 cases; core owns the
final merged execution and passed all 21 within its 40-case focused gate (4.98s)
and final 997-test suite. The superseded 18-case file had matching
local/remote SHA-256 and empty explicit-file dry-run parity. Final 21-case local
SHA-256 is `8b837ddd676949472199cfb1d2a649eed0b5db5070b3f29a7f2b032b23310ef5`.

Core-owned final merged backend commands, in the same isolated backend directory:

| Command | Result |
| --- | --- |
| `uv sync --locked` | Passed; resolved 54 / checked 52 packages. |
| `uv run --frozen ruff check .` | Passed. |
| `uv run --frozen ruff format --check .` | Passed; 127 files already formatted. |
| `uv run --frozen python -m pytest -q tests` | **997 passed in 92.52s**, exit 0. |

This contains the accepted A/B 740-test baseline, 175 pure-engine tests and 82
core/reviewer/smoke cases, including the final four usage and two WB/XHS
frozen-source-edit regressions. The backend has no configured Python type checker.
See the owner's [backend-implementation.md](./backend-implementation.md) for
chronology and complete ownership. Source/tests/manifests `rsync -aicn` was empty.
The local and remote aggregate SHA-256 of Python files under `src` and `tests` is
`4befc2b7a7cdc49d0164becc25ecb00a11d08f537e39bc43b0a454963eea587c`.
Matching manifest digests are `pyproject.toml`
`374b57593376f451a6e39090a91ed3053f2543f37ea9ef5a5c560ca530f5ae0c`
and `uv.lock`
`a21e2245deb5f5c4a1f0ada5c587cc81981a6e04baba32d7847d3f83135e618c`.

Final reviewer frontend commands, inside
`/tmp/longtian-decoupling-impl.dMCxsd/frontend`, each prefixed with
`mise x node@24 pnpm@11.14.0 --`:

| Command | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | Passed; already up to date, pnpm 11.14.0. |
| `pnpm format:check` | Passed; all files formatted. |
| `pnpm lint` | Passed; 101 files, zero warnings/errors. |
| `pnpm typecheck` | Passed. |
| `pnpm test:run` | **593 passed in 23 files**, 9.04 seconds. |
| `pnpm build` | Passed; 2,358 modules transformed in 295ms. |

This supersedes the owner's 575-test gate with 13 exact-time/acknowledgement tests
and five ancestry-parity tests. The intervening 588-test gate (9.25s) was the
snapshot used for the full main-owned browser pass/repeat. Its manifest was
`fc82271482a2391e45a65254f0e9b0320cbecf4ca7fd38e695f5d28c04756b60`.

The final parity regression command was
`pnpm test:run src/lib/api/topic-reports.test.ts`, with the same mise prefix.
Before the production change, the new future-report/future-node cases failed:
**2 failed / 80 passed**. After only the two comparison changes, **82 passed**
in 872ms. No fixture, dependency or other source change was needed.

The final 118-file local and remote source manifest matches:
`49cb397cab26b6b937cc80d94fc34e028d52d3a577a6e4a1f3419e8c8151f637`.
Final explicit-file SHA-256 values are:

- `frontend/src/lib/api/topic-reports.ts`:
  `c6d1340b8443de95e91221417a96909ad0c596b610053bea11094fcff2b2166b`
- `frontend/src/lib/api/topic-reports.test.ts`:
  `f2791ac2054066b110dbb3f5dfed56461b1acddfa01535f97c4e5eb67e7d22f8`

```sh
rg --files --hidden frontend -g '!node_modules' -g '!dist' -g '!.env*' -g '!*.local' -g '!.git' -g '!.vite' -g '!.cache' -g '!coverage' -g '!*.tsbuildinfo' -g '!runtime' -g '!profiles' -g '!media' | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256
rsync -rcni --exclude=node_modules --exclude=dist --exclude='.env*' --exclude='*.local' --exclude=.git --exclude=.vite --exclude=.cache --exclude=coverage --exclude='*.tsbuildinfo' --exclude=runtime --exclude=profiles --exclude=media frontend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/frontend/
```

The final checksum dry run was empty. Centaurus lacked `rg`; remote manifest
verification therefore consumed the exact local sorted file list via SSH and
`xargs sha256sum | sha256sum`, producing the same manifest hash.

## Main-owned browser evidence

The detailed actual observations are in
[browser-acceptance.md](./browser-acceptance.md). The full interaction pass and
unchanged-code repeat used the released 588-test frontend and 997-test backend,
not the later decoder-only snapshot:

- The later result page showed four rows while one-click analysis admitted all
  103 never-started candidates. One normally settled task produced one automatic
  report without a second generation click: 101 ready, two unavailable, 96
  relevant, three unrelated and two uncertain.
- All 12 leaf chapters, three overviews and six source pages were inspected.
  Source 103 retained its run-3 origin; saved-text links, old reports, both shared
  prompt defaults, URL pagination/reload and legacy history remained intact.
- Exact fake model totals were 217 after automatic completion, 330 after a
  one-off override's deliberate leaf failure, and 334 after compatible text-only
  retry. A further narrow-screen retry reached 338. Media stayed 103 and initial
  analysis 101 throughout report-only work; collection, external-browser and
  legacy-generation counts stayed zero.
- Date-error focus/Escape recovery, 390x844 layout, pending/failure/completion and
  readonly reload/history were exercised. No console warning/error or horizontal
  overflow was observed. The interval form was validated but not submitted in
  this pass; precise interval execution is covered by the API/unit regressions.

The first null-override browser retry completed server-side but its `fetch`
failed before acknowledgement; the UI retained its UUID/intent. Identical-UUID
HTTP replay returned 202 with correct CORS/no-store and no duplicate/counter
increase; reload recovered the completed third version. The actual disconnect
cause was not established. Without changing any code/dependency, a clean fixture
repeated the full sequence successfully in the desktop UI and then again at
390x844, each retry automatically selecting its completed report. Do not attribute
the initial transport event to the later, independently found decoder-parity fix.

Main confirmed cleanup after those runs: owned backend/frontend/tunnel and tabs
stopped, viewport reset, both temporary databases removed, and local/remote
46081/46082 free.

Main then tested the final 593-test snapshot with a fresh zero-counter fixture.
The UI again admitted all 103 sources, displayed automatic report #1, admitted
the one-off failing report #2 and retried it to completed report #3. Legal older
parent and canonical node IDs decoded successfully; the report displayed 101
reused judgments, 11 reused chapters and four new composition calls / 60 tokens.
Current-version overview #344 linked children #339-342; reload retained report 3
and section 344.

This final pass also observed an acknowledgement failure on the override
submission, so it was not specific to null retry. The UI's existing same-UUID
confirmation recovered in-browser, closed the dialog and selected already-saved
report #2 without another report or model call. The following null retry selected
completed report #3 normally. Final counters were media 103, initial 101,
judgment 202, leaf 25, overview 6 and model total 334; collection/browser/legacy
generation remained zero. No DTO mismatch or console warning/error was reported.

Final cleanup is recorded by main: backend PID 1921542 shut down gracefully,
`/tmp/longtian-topic-report-smoke-_hf8cpf7` was removed, frontend/tunnel/tabs were
closed, viewport reset and local/remote 46081/46082 free. No source change
followed that acceptance. The repeated transport observation is retained as a
limitation; neither the decoder fix nor a clean repeat establishes its root cause.

## Reviewer edits and conclusion

Reviewer-owned changes in this check:

- `backend/tests/test_topic_report_review_boundaries.py`
- `frontend/src/lib/api/topic-reports.ts`
- `frontend/src/lib/api/topic-reports.test.ts`
- this `research/full-check.md`

No code/spec finding remains open in this scoped review. The final 593-test
frontend and 997-test backend are frozen/released, and main's final browser
revalidation and cleanup are complete. Retain the intermittent response-delivery
observation and verified replay recovery above. Main owns task/spec status and
the formal Trellis gate; this reviewer made no task-status or Git changes.

No live model/account/media work, production migration, real schedule activation,
deployment, Git commit/push or archive was performed. Mock geography and semantic
examples establish contracts only, not live-model factual accuracy or platform
readiness. More sources still require more bounded text requests and provider
quota; neither unlimited model context nor automatic recovery of missed work is
claimed.
