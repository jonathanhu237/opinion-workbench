# Shared Results and Initial Analysis

## Goal

Make collected records and reusable initial understanding available independently
of topic reports. This is child A of `08-28-collection-report-decoupling`.

## Requirements and Scope

The parent PRD is authoritative: implement the stage-one portions of R1, R2,
R4–R6, R9, R10 and R12–R14. Provide shared global results/provenance, two editable
prompt defaults, versioned authorization, immutable per-record evidence, automatic
new-result admission and explicit one-click selection of all never-started records.
Keep legacy history and explicit retry/reanalysis separate from bulk eligibility.
Save a durable completion event; do not make report creation a success condition.

## Acceptance Criteria

- [x] Parent AC01–AC03 initial-analysis portions: collection/results work without
  reports; eligible new sources are analysed regardless of topic relevance.
- [x] Parent AC05–AC06 provenance/time portions, AC08 history and AC09 recovery:
  frozen evidence, first-entry time, valid source origins and old reports survive.
- [x] Parent AC13–AC15: pending new work survives repeat collection; no upgrade/
  prompt-edit history sweep; failed/interrupted attempts require explicit retry.
- [x] Parent AC16–AC18 and AC20–AC23 stage-one portions: independent prompt edits,
  exact snapshots, compatible reuse and media/text evidence preserve uncertainty.
- [x] Parent AC24–AC26 stage-one portions: 101+ across-page records admitted by
  one action without duplicate work; all attempts settle before one completion
  event; completed text is independently readable.
- [x] Parent AC28: legacy output remains labelled history, not falsely imported
  as new generic understanding; no migration-side model calls.

## Dependencies and Exclusions

No predecessor. B and C depend on this child's committed contracts. Scheduling
and report execution are outside A; C owns report portions of shared acceptance.
Keep full-feature automation disabled until parent integration passes. No new
provider/media support, permanent archive, live model calls or deployment.

## Execution Status

Parent final-summary approval and explicit activation occurred on 2026-08-29.
Implementation, independent full-scope check, spec updates and isolated browser
acceptance passed. Final remote gates: backend 656 tests + Ruff; frontend 370
tests + all frozen gates. Evidence is in `research/full-check.md` and
`research/browser-acceptance.md`. B may proceed under the approved parent plan.
Git commit/archive and live-operation gates remain separate and unperformed.
