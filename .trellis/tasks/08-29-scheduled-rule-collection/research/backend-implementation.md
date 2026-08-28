# Child B backend implementation and gate evidence

Implemented 2026-08-29 as the dispatched backend owner, after the checked A
baseline. Read the complete implement context, parent/child plans, A handoff/check
evidence and relevant backend specs; applied `trellis-before-dev`, `fastapi` and
the direct `trellis-check` checklist. No subagent recursion, frontend/spec/task
state edits, Git mutations or production runtime changes.

## Delivered boundary

- v13 appends only `collection_schedules`, ordered platforms and occurrences.
  A genuine populated v12 fixture preserves every earlier table/column/ID/JSON,
  including A eligibility/prompt state and legacy summaries. Migration rollback
  exercises actual DDL; tests cover reopening, forward rejection and FK checks.
- Strict no-store local APIs implement the exact `backend-contract.md`.
  Minute/hour input normalizes to whole minutes 1–43200; create is disabled.
  PUT uses configuration CAS, resets enabled due time, and preserves deleted
  rule labels when disabling. Ticks do not change configuration revision.
- UTC arithmetic and an injected monotonic clock implement anchor-aligned due
  advancement. Claim/advance is atomic; repeated/concurrent checks cannot claim
  the same occurrence. Long offline and forward-jump periods use bounded ranges,
  including every page when more than 100 schedules cross a clock jump.
- Existing batch creation has one shared insertion implementation. The scheduled
  path rechecks schedule revision/enabled state and current rule, then commits
  batch/terms/items/occurrence link atomically before runner creation. Token
  replay returns the same batch without a second runner. The batch-start marker
  permits truthful prelaunch interruption diagnostics after restart.
- The existing browser coordinator and serial batch runner remain authoritative.
  Busy owners, active collection, manual pause, unavailable browser, missing/
  disabled/invalid/too-large rules and changed schedules remain distinct history.
  No timer resumes a checkpoint, cancels another owner or performs model work.
- Main stops/drains scheduler admission before analysis/summary/media/client/
  batch/search/browser cleanup, continuing cleanup even after a prior failure.
  Disabling a schedule does not cancel its already linked collection.
- A remains the only discovery and post-release initial-analysis owner. The
  scheduled batch test observes one batch handoff (not one per child), then two
  successful synthetic initial analyses. Repeated collection adds no duplicate
  analysis job or model work.

### Browser availability semantics

`PersistentAuthWorkerClient.browser_session_available` performs no I/O. It is
false for a new process/backend, readiness alone, a dead/failed generation,
disconnect or shutdown. Validated manual auth `connected` or `disconnected`
(login-required) results establish usable-browser evidence without claiming all
platforms are authenticated. Validated search success/login/challenge/block/
structure outcomes, manual page open and stored-result open also establish it.
Unknown/error outcomes are conservative; disconnect/death clears it. No timer
launches a worker merely to probe availability. Later collection outcomes retain
the existing manual-verification rules. Rollout `available` is separate from this
session evidence and from saved `enabled`; both default product automation gates
remain false until the parent explicitly completes C integration.

## Files

New production files:

- `backend/src/longtian_api/collection_timing.py`
- `backend/src/longtian_api/{api/v1,migrations,repositories,schemas,services}/collection_schedules.py`
- `backend/src/longtian_api/services/collection_schedule_errors.py`

Integration edits: `database.py`, `main.py`, `api/router.py`, repository/service
`search_batches.py`, `services/search_runs.py`, and
`services/media_crawler_auth_worker.py`. `repositories/monitoring_rules.py` gains
an explicit diagnostic-only empty-object read option, so a damaged rule is
visible as invalid in scheduling; ordinary rule reads remain strict.

New tests/fixtures: `collection_schedule_fixtures.py`,
`collection_schedule_smoke.py`, `test_collection_schedule_repository.py`,
`test_collection_schedule_api.py`, `test_collection_schedules.py`,
`test_schedule_browser_availability.py`, `test_collection_schedule_smoke.py`.
Version assertions in existing A/legacy repository tests advance to v13 without
weakening preservation checks. A's API fixture accepts optional app factory
options, reused by the isolated B smoke app without changing default behavior.

One existing auth test now explicitly awaits its original task finalizer before
asserting recycled-worker reuse. Production auth lifecycle is unchanged; every
old assertion remains and unexpected task errors propagate. This fixes a
terminal-publication/before-owner-release test race observed in the first final
gate, not an unrelated production refactor.

## Validation and snapshot

All test/dependency gates ran on the exclusive Centaurus source snapshot:
`/tmp/longtian-decoupling-impl.dMCxsd/backend`. Local work was editing, read-only
inspection and allowed formatting/lint correction. No local heavy test run.

One-way synchronization, completed before each gate (no sync while gates ran):

```sh
rsync -a --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache --exclude='.env*' --exclude='*.pyc' --exclude=runtime backend/ Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/backend/
```

No `--delete`, remote edits, credentials, runtime databases or browser state
were copied. Checksum-only `rsync -rnci` with the same exclusions returned no
differences after the final gate. Sorted Python source/test plus manifest/lock
SHA-256 manifest hash:
`1aade3960c68bed723d5518833780f09bd0fbe5c1dec0fb631993c8091192686`.

Final commands inside the remote backend directory:

```sh
uv run --frozen python -m pytest -q tests/test_platform_connections.py -k malformed_protocol --tb=short
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests --tb=short
```

| Gate | Observed result |
| --- | --- |
| Targeted finalized-worker regression | 7 passed, 79 deselected in 0.55s |
| Locked dependencies | 54 resolved, 52 checked; passed |
| Ruff lint | All checks passed |
| Ruff format | 110 files already formatted |
| Full backend suite | **723 passed in 24.97s**, no skipped tests |
| Python type checker | Not configured; no type-check pass claimed |
| Local whitespace | `git diff --check -- backend` passed |

Earlier evidence: first focused B run exposed one invalid-rule projection defect
and two fixture construction errors (4 failed/55 passed); fixed before the full
715-test green run (24.48s). A+B smoke/CORS checks passed 4 tests in 1.39s. The
first final gate had 722 passes and the old auth finalizer race; a focused
unchanged auth suite passed 86 tests in 1.38s, then the synchronization fix and
the full gate above passed. No failed gate is counted as acceptance.

## Main-owned browser acceptance handoff

The test-only factory is `collection_schedule_smoke:create_smoke_app`:

```sh
PYTHONPATH=src:tests uv run --frozen uvicorn collection_schedule_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
```

It uses a temporary DB, existing fake AI/media, an identity-consistent fake
collector, a fixed clock and exact CORS `http://127.0.0.1:46081` (GET/POST/PUT,
Content-Type only). There is one disabled schedule with 57 occurrence rows
(50+7 pages): skipped busy/unavailable/interrupted entries, offline range,
completed linked batch and a linked prelaunch interruption retaining manual
pause/recovery. Seeded collection work is synthetic, two fake calls; model/media
counters remain zero. `/api/v1/collection-schedule-smoke/counters` is test-only.
Reads/reloads do not add work. The original fail-closed launcher remains unable
to launch a real browser. No services/tunnels were started by this implementer.

## Remaining boundaries

No known B backend blocker remains. Main owns browser acceptance, frontend
integration and the separate checker. C owns text reports and final rollout.
The main-owned schedule spec was read and matches implementation; it should
retain the separate rollout/session/enabled meanings. Tests do not establish
live account/browser availability, platform quality or provider quality. No
real schedule, provider request, production migration, commit/push or archive
was performed; those operational gates remain separate.
