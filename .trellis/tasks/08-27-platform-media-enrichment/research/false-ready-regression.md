# Bug Analysis: malformed media normalized into absence

## 1. Root Cause Category

**D — Test Coverage Gap**, with **B — Cross-Layer Contract** and an implicit
normalization assumption. The Python projector distinguished unknown inventory,
but JavaScript converted present malformed `video` to null and malformed stream
entries into ordinary objects. Python consequently saw fabricated valid absence
or valid stream shape and could return ready.

The discriminating evidence was a network-disabled Chromium test running the real
JavaScript, then `project_note`, then `materialize`. All seven malformed cases
failed before the fix by returning ready. This isolates the normalization boundary;
it is not a live platform response or a model judgment failure.

## 2. Why Earlier Tests Missed It

There was no repeated failed-fix sequence. Direct Python negative fixtures retained
malformed values and therefore passed; existing real-JavaScript tests covered
ordinary fields/privacy/limits, not the two lossy shape transformations.

The review added tests first and main verified seven red cases on Centaurus before
the two JavaScript branches were changed. The combined platform/probe regression
then passed110 cases without skipped browser tests.

## 3. Prevention Mechanisms

| Priority | Mechanism | Action | Status |
| --- | --- | --- | --- |
| P0 | Shape fidelity | Present malformed video stays constant unknown `{}`; malformed stream entry stays null | Implemented |
| P0 | Cross-boundary regression | Real JS → Python projection → materialization, seven malformed cases | Red/green established |
| P1 | Positive coverage | Keep actual absent/valid-media positive cases so the fix cannot make every input incomplete | Retained and strengthened |
| P1 | Code-spec | media-projection-guidelines.md specifies shapes, completeness and assertion matrix | Written |
| P1 | Thinking guide | Add lossy-source-projection questions with a code-spec link | Written |

## 4. Systematic Expansion

The scoped review also checked WB/KS, DY/TT, paired legacy-source validators and
exact media-host additions. WB/KS still explicitly lack full inventory proof; this
review does not promote their availability. DY/TT real DOM/byte evidence remains
separate from fixtures and whole-worker/backend acceptance.

A task-only probe cleanup issue was also fixed: `downloader.close()` failure or
cancellation previously skipped explicit staging-FD close. Nested finally now
closes staging, with fake-I/O tests for failure/cancellation and private temp cleanup.
No new worker process manager, public API or global cleanup policy was introduced.

## 5. Knowledge Capture

- Updated backend code-spec with seven required executable-contract sections.
- Added a cross-layer thinking-guide pointer, not a duplicate implementation rule.
- This application has no `src/templates/markdown/spec/` source-template tree; no
  unrelated template directories were created.
- Spec/code changes remain uncommitted. The active child is not complete and no
  commit, push or archive was requested in this increment.
