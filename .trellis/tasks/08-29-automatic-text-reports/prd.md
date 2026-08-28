# Automatic Text-only Analysis Reports

## Goal

Automatically generate one report after an initial-analysis task has attempted
all its records, using its successfully saved text and reporting only relevant
material. This is child C of `08-28-collection-report-decoupling`.

## Requirements and Scope

Implement parent R3–R6 and R9–R14 report portions. Topic relevance and synthesis
are one user-facing second stage. Both source/prompt versions are frozen;
automatic generation needs no second button or partial-readiness confirmation.
Preserve one logical report for large inputs, with bounded calls and full
source accounting. Add independent text-only retries, history, first-entry
interval selection and optional prompt overrides.

## Acceptance Criteria

- [x] Parent AC03–AC09: automatic reports from saved text across runs, truthful
  readiness/time/provenance, preserved history, no media or stage-one reruns.
- [x] Parent AC16–AC23: editable independent report instructions, relevance/
  uncertainty distinctions, version-safe reuse, retained evidence and usage.
- [x] Parent AC24–AC27: one-click stage one feeds exactly one report per settled
  task, including eight successes/two failures; all ready sources enter
  judgment, including >100, without silent clipping or manual narrowing.
- [x] Parent AC28: legacy reports/citations remain readable, without mislabelling
  old analyses as new-stage completed evidence.
- [x] Parent AC01–AC28 final integration passes across A+B+C using isolated
  contract/browser acceptance, with live-model limitations reported honestly.

## Dependencies and Exclusions

Depends on completed A for immutable evidence/prompts/completion events and B
for scheduled-flow integration. No new media acquisition/transport/provider,
third user-facing stage, report delivery, template library, permanent media
archive or real model-quality claim is in scope.

## Execution Gate

The user approved the reviewed parent A -> B -> C plan on 2026-08-29 with
“开始吧。” A/B/C checks and parent isolated integration are now accepted. Exact
997-backend/593-frontend gates, browser response-recovery observations and
cleanup are recorded in `research/full-check.md` and `browser-acceptance.md`.
Live provider work, production migration and Git commit remain separately
authorized operations; no such operation or task archive was performed.
