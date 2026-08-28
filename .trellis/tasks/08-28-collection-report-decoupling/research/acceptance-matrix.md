# Parent acceptance matrix

Integration owner: main. Final implementation acceptance passed on 2026-08-29,
including all R1–R14, AC01–AC28 and G1–G7. Evidence below distinguishes contract/
browser acceptance from unperformed live-model evaluation. All checks use
isolated fixtures, not live accounts, provider quota or the production database.

## Current coverage

| Parent criteria | Final observed evidence | Result |
| --- | --- | --- |
| AC01, AC10 | A/B independent results and frozen rule snapshots; rule-edit/deletion and scheduled batch tests retained in final 997 backend tests. C browser legacy/history reads admitted no work. | Passed |
| AC02, AC13 | A neutral understanding, durable discovery claims and new/repeat/history distinctions; B one post-batch handoff; C preserves all successful text including unrelated sources. | Passed |
| AC03, AC04, AC26 | Exact 10 members/8 successes/2 failures integration creates one report after settlement; zero-success, cancellation and crash cases covered. Browser 103 attempts/101 saved/2 incomplete -> exactly one automatic report without a second click. | Passed |
| AC05, AC06 | Exact half-open UTC-microsecond interval tests use original first-entry times, not repeat/publication time. Browser source101/run2 and source103/run3 citations and saved attempt103 remain readable. | Passed |
| AC07, AC09, AC22 | Report failure retains saved initial text and 11 valid drafts. Override and retry keep media103/initial101 fixed; retry adds four text calls only. Cancellation/failure/frozen-scope suites pass. | Passed |
| AC08, AC28 | Genuine populated v11->v14 migration/reopen/rollback and frozen WB/XHS source-edit tests pass. Browser legacy run4/report1 remains explicitly old, readable and excluded from bulk; no legacy-generation POST. | Passed |
| AC11, AC12 | B clock/crash/lease/recovery, >100 schedules, busy skip/no catch-up/manual pause and current-rule tests remain green in final merged suite; B browser enable/edit/disable/history acceptance passed. | Passed |
| AC14, AC15, AC21, AC25 | History exclusion, explicit retry/reanalysis, 0/1/101/1001 selection, concurrent claims and restart-without-calls retained. C startup/recovery and prompt changes cannot trigger A; browser bulk excludes legacy and already attempted items. | Passed |
| AC16, AC17, AC18, AC20 | Independent shared prompt/CAS tests plus C frozen provenance/compatibility/one-off override. Browser original defaults remain versions1/2; old report1 survives override2 and retry3; 101 judgments/11 chapters reuse compatibly. | Passed |
| AC19, AC23 | Full saved text/media/geography/time/uncertainty contracts and representative fake decisions retained. Browser 96 relevant/3 unrelated/2 uncertain/2 unavailable are distinct; only 96 enter composition. This proves contracts, not live-model geographic or factual accuracy. | Passed at isolated-contract scope |
| AC24, AC27 | Browser from result offset100 admits103 across runs, judges every101 ready text and retains12 detailed chapters plus3 overview nodes. All source/leaf pages inspected; real A->C 1001-source suite and exact input bounds pass. | Passed |

## Child A evidence

- `../../08-29-shared-results-initial-analysis/research/full-check.md`: full-scope
  review, fixed findings, backend 656 tests/Ruff, frontend 370 tests/all frozen
  gates, schema/admission/queue/legacy/HTTP invariants.
- `../../08-29-shared-results-initial-analysis/research/browser-acceptance.md`:
  synthetic 103-member cross-page admission, mixed settlement, full saved text,
  prompt independence, reload safety, keyboard focus, narrow layout and console.
- `../../08-29-shared-results-initial-analysis/research/backend-contract.md`:
  exact HTTP, immutable evidence and durable completion event seam.

## Child B evidence

- `../../08-29-scheduled-rule-collection/research/full-check.md`: full-scope
  review, three corrected projection/timer/dependency findings, backend740 tests
  and frontend481 tests with all configured gates and source parity.
- `../../08-29-scheduled-rule-collection/research/browser-acceptance.md`:
  disabled creation, enable/edit/disable, history/reload/focus/narrow layout,
  preserved paused recovery and constant synthetic counters2/0/0.
- `../../08-29-scheduled-rule-collection/research/backend-contract.md` and
  `collection-schedule-guidelines.md` under backend specs freeze B's seam.

## Child C and final integration evidence

- `../../08-29-automatic-text-reports/research/full-check.md`: independent
  core/UI review, fixed findings, G1–G7 exact executable mapping, backend997 and
  frontend593 final frozen gates. Main separately reviewed the pure engine;
  its implementer did not self-certify independent review.
- `../../08-29-automatic-text-reports/research/browser-acceptance.md`: full
  desktop/narrow interaction, three isolated factories, cross-page coverage,
  legacy/read safety, report-only failure/retry/usage and final decoder-parity
  snapshot revalidation. Intermittent response-delivery errors are retained;
  cause is not asserted. Same-intent recovery and unchanged-code clean repeats
  succeeded without duplicate work. No source fix is claimed for transport.
- `../../08-29-automatic-text-reports/research/backend-implementation.md`:
  final997 tests/Ruff127 files, genuine migration, 101/1001 integration and
  frozen-source/hash/usage proofs. Backend source/test SHA256 aggregate:
  `4befc2b7a7cdc49d0164becc25ecb00a11d08f537e39bc43b0a454963eea587c`.
- Final118-file frontend manifest:
  `49cb397cab26b6b937cc80d94fc34e028d52d3a577a6e4a1f3419e8c8151f637`.

| Final gate | Evidence / result |
| --- | --- |
| G1 persistence | Real historical migrations, unchanged old columns/IDs/usage, foreign keys, forward-version rejection and child-insert rollback: passed. |
| G2 initial analysis | All-source durable ownership, bounded actual input, history/legacy interlocks, prompt and independent retry suites: passed. |
| G3 scheduling | Fixed-interval clock/overlap/offline/manual-pause/startup/shutdown suites plus B browser forms/history: passed. |
| G4 handoff | Exact10/8/2, unique event consumer, partial/empty/cancelled/crash/queue races and no second UI action: passed. |
| G5 text reports | All-ready judgments, relevant-only leaves, 1001-source reducing tree, strict size/citation/graph and retained details: passed. |
| G6 independence | Override/retry/partial drafts preserve text and add zero media/A calls; compatible reuse and honest unknown/overflow usage: passed. |
| G7 interfaces | Strict HTTP/DTO/UUID/CAS/precision/ancestry and UI focus/history/pagination/narrow/response-recovery checks: passed, with documented intermittent transport observation. |

All owned servers, tunnels and browser tabs are closed and temporary fixture
databases cleaned. Local/remote46081/46082 are free. No real rollout activation,
production migration, provider call, Git commit/push or archive occurred. Live
model/platform evaluation and production backup/migration/activation are separate
operational decisions. Source changes remain local and uncommitted for review;
the proposed commit batch excludes pre-existing agent-configuration edits.
