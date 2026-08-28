# Independent Scheduled Collection

## Goal

Let users configure fixed-interval collection tasks referencing reusable rules,
without requiring a report. This is child B of `08-28-collection-report-decoupling`.

## Requirements and Scope

The parent PRD owns R1, R7 and R8, plus integration with R2. Collection schedules
select rules/platforms, save each execution and use the existing collector.
Busy occurrences are skipped, offline intervals are not replayed, and human
verification remains explicitly recoverable. Rules contain no schedule or prompts.

## Acceptance Criteria

- [x] Parent AC01: successful collection and saved results do not depend on AI.
- [x] Parent AC10: rules remain configuration and execution snapshots survive edits.
- [x] Parent AC11: enabled interval schedules produce traceable collection runs.
- [x] Parent AC12: busy work is not overlapped/cancelled; repeated due checks
  cannot duplicate a batch; restart advances to a future occurrence; pauses
  cannot auto-resume verification.
- [x] Parent AC13 integration: new saved results reach A's pending admission
  without duplication/loss from a later repeated observation.
- [x] Disabled/deleted rules, unavailable browser and interrupted dispatches are
  visible reasons, not fabricated successful empty runs.

## Dependencies and Exclusions

Depends on A (`08-29-shared-results-initial-analysis`) for persisted discovery
and collection-to-analysis handoff. C follows B for final product integration.
Do not implement prompts, model transport, report generation, cron calendars,
notifications, new platforms or live schedules in planning.

## Execution Gate

The user approved the reviewed parent A -> B -> C plan on 2026-08-29 with
“开始吧。” Keep this child planning until A passes its full check; that dependency
gate, not another product-design discussion, precedes activation. Live schedules,
production migration and Git commit remain separately authorized operations.

## Execution evidence

Main accepted B after independent full review and isolated browser acceptance
on 2026-08-29. Final gates: backend 740 tests/Ruff, frontend 481 tests/all frozen
gates. See `research/full-check.md` and `research/browser-acceptance.md` for exact
commands, fixed findings and limitations. Implementation is checked; commit,
archive, production migration and live activation remain unperformed.
