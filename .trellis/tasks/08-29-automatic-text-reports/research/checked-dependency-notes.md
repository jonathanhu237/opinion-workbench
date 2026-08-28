# Checked dependency notes for C

Main integration review, 2026-08-29. These are implementation observations,
not changes to the approved parent product contract. A has passed its full
656-backend/370-frontend checks and isolated browser acceptance. B has now passed
its full review and browser gates: 740 backend tests/Ruff and 481 frontend
tests/all frozen gates. Read B's `research/full-check.md` and exact contract.
Both source snapshots are released and all owned 46081/46082 services are stopped.

## A event and snapshot seam

- `ContentAnalysisRepository._finish` writes the unique job completion event
  in the same transaction as normal settlement and claim release. Non-normal
  settlement writes no event. Do not make a report result a condition for
  completing an initial-analysis job.
- `completion_events(after_id, limit)` returns ordered event IDs, frozen job
  provider/prompt intent and successful attempt IDs. An event page limit is
  not a source-count limit. Read every frozen job member when materializing
  success/unavailable coverage, and claim the event/report link atomically.
- Successful attempt rows contain immutable source JSON, accepted input JSON,
  understanding JSON, hashes and origin run identity. Use these rows; do not
  reconstruct reports from mutable `search_contents` or a current result page.
- The stage-one service holds the shared AI lease while executing a job and
  releases the browser between members. Any completion notification should
  enqueue report intent without synchronously waiting for another AI lease.
  Report execution owns its separate queue, lease and cancellation lifecycle.
- Test enqueue/runner-exit interleavings as well as durable uniqueness. A's
  queue-empty/admission regression already needed a lock-and-recheck fix.
- Startup reconciliation must remain storage-only. It may materialize missing
  report metadata but must not replay an interrupted potentially billed call.
  GET, reload, prompt save and schedule polling are never model-work triggers.

## Rollout and browser acceptance

- A currently defaults `analysis_automation_available=False`; B also has a
  separate unavailable rollout state. C completes application availability,
  while persisted automation authorization and new schedules stay disabled
  by default. Do not switch on any real runtime data as an implementation test.
- `backend/tests/initial_analysis_smoke.py` is an isolated temporary-DB app
  with fake understanding/media and exact-origin CORS for the forwarded
  frontend on 46081 / API on 46082. Extend or compose a C-only fixture for
  automatic reports, fake judgment/synthesis, failed-node retry and text-only
  counters. Keep real browser launch and provider access fail-closed.
- Main owns services, port forwards and in-app-browser acceptance. Workers own
  their respective remote package snapshots and must finish synchronization
  and checks before main starts those services.
- Browser checks must show normal settlement -> one automatic report without
  a second action, separate stage progress, unrelated/uncertain/unavailable
  coverage, frozen citations/history, independent retry and no extra media
  calls. Include keyboard/narrow layout and no-mutation reload checks.

## Before dispatch

Read B's final backend contract and full-check evidence, recheck schema version,
then give C backend sole ownership of the next migration/lifespan/router edits.
Frontend must consume the exact published report contract rather than guessing
payloads. Final parent G1-G7 and AC01-AC28 remain open until observed acceptance.
