# Bug Analysis: Durable recovery boundaries

## 1. Root Cause Category

- **B — Cross-layer contract:** a run can commit its terminal result before the batch item changes.
  The frontend originally rejected this real, consistent snapshot as invalid. Damaged child-term
  history also became unreadable before the unavailable-checkpoint controls could render.
- **D — Test coverage gap:** happy-path service tests did not interrupt the separate run/item writes
  or delete a completion suffix. Independent review added actual API and injected-write regressions.
- **E — Implicit assumption:** a contiguous *remaining* proof set was assumed complete even when
  persisted current progress proved that a proof tail was missing. An old browser callback also
  looked up the newest disconnect event instead of its own session generation.

## 2. Why Earlier Gates Did Not Catch It

The initial full suites passed their existing fixtures; they did not establish correctness for all
read windows or interrupted writes. The new tests ran against unchanged remote source first:
one browser-generation failure, four backend checkpoint/read failures, three backend success/fallback
failures, and six frontend decoder failures. These are deterministic offline regressions, not reports
of a live user's database corruption or a platform CAPTCHA failure.

Historical migration fixture failures were separate: current repositories were accidentally called
against old schemas. Correct historical SQL and old-column comparisons fixed the harness without
weakening migration preservation assertions.

## 3. Prevention Mechanisms

| Priority | Mechanism | Specific action |
| --- | --- | --- |
| P1 | Runtime proof boundary | Check offset, current position and every completed suffix row together; do not infer missing v2 proof. |
| P1 | Read-model boundary | Preserve actual damaged child counts in batch-only diagnostics while recovery stays unavailable; keep independent runs strict. |
| P1 | Lifecycle boundary | Drain SQLite write tasks before ownership release; fallback terminalizes only active child runs and preserves committed success. |
| P1 | Session identity | Capture the original disconnect event and ignore old-generation callbacks. |
| P1 | Integration tests | Inject failures before run-result/item commits and inspect real HTTP transition payloads. |
| P2 | Frontend validation | Recognize the real running-item/terminal-run window without inventing a successful state. |

## 4. Systematic Expansion

Review covered all five adapters' completion emission, the shared worker/manual-page lifecycle,
backend writer/reader boundaries, startup reconciliation, strict API decoders and merged-result
provenance. This did not expand into automatic challenge handling, general database repair, arbitrary
page control or changing collection ordering. No new dependency or interface field was needed.

## 5. Knowledge Capture

- Updated batch-search's executable signatures, proof/transition/error matrix and regression points.
- Updated product-search and platform-connection specs for search-v2 and generation-safe manual pages.
- Updated database and frontend state guidance for settled writes and truthful read projections.
- Added cross-layer guide checks for between-commit visibility and resource-generation identity.
- This application has no `src/templates/markdown/spec/` counterpart to synchronize.
- Spec commits and task archiving remain deferred: the user has not requested Git delivery in this turn.

Final post-fix results are recorded in `implementation-verification.md` rather than inferred here.
