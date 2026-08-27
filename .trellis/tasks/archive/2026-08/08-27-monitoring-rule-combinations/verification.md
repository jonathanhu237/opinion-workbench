# Monitoring-rule combinations verification

## Scope and isolation

- Approved Q1–Q6 implementation only; no media acquisition, AI screening or summary.
- Source changes and Git remain local; source-only one-way synchronization and automated gates run on Centaurus.
- Browser checks use isolated loopback services forwarded from Centaurus (frontend 15573, API 18173) and a disposable SQLite database, never the user's database or credentials.
- The isolated database was initialized with the pre-change v8 code. A disabled legacy rule contains two intact phrases, including internal spaces, to verify the v9 migration and edit behavior.
- No real platform search, browser-account connection or provider request is needed or authorized for this verification.

## Automated checks

Final independent full-scope gates on Centaurus:

- Backend: `uv sync --frozen`, Ruff format/check, **353 tests passed**.
- Frontend: frozen pnpm install, Prettier, Oxlint (zero warnings/errors), TypeScript,
  **164 tests passed**, Vite production build.
- Local `git diff --check`: passed.
- Reviewer fixed only the unpublished v9 issue length constraint and added NUL/20–21 collection
  regressions. No unresolved in-scope findings. See `research/check-review.md`.

## Browser acceptance

Main-session checks on the first synchronized implementation:

1. Passed: v8 legacy complete phrases, their order, stable ID and disabled state survive v9 migration. Edit shows the two whole phrases as objects, with empty issues.
2. Passed: two objects × two issues preview four ordered full phrases; save and reopen retain the original two groups.
3. Passed: toggle retains both groups. A whitespace-only issue textarea saves as `[]`, leaving the two object phrases unchanged. Reload/reopen also retains a separate 3-object/7-issue rule.
4. Passed: 21 generated queries save with an execution warning; 110 queries are rejected without a truncated preview. Unique input groups whose generated queries collide are rejected. A 100-code-point generated phrase saves and wraps without horizontal overflow.
5. Desktop 1280×720 and narrow 375×812 screenshots inspected. Preview has a keyboard-focusable scroll region, all 21 queries remain in the DOM, and narrow preview/page widths do not overflow. Escape and close return focus to the edit button; footer actions remain reachable through scrolling.
6. Passed: collection selector accepts the new response and labels the 3×7 rule as `21 个词`, excluding disabled rules. No collection was started.
7. Fixed and retested: inputs are disabled only during a real save mutation; the submit button additionally guards `isSubmitting`. A genuine mouse click now moves focus to the invalid `rule-issues` textarea after a generated-collision error. New unit regressions cover collisions and over-100 focus. The browser tool's semantic click can refocus Save after the handler, so it is not reliable evidence against the native-event result.
8. Passed after the final Unicode sync: a BOM-prefixed rule name/object remains valid, NEL/C0 outer whitespace is trimmed consistently, the two expected phrases preview correctly, and saving succeeds through the strict decoder. Clean-tab console still has no warnings/errors.

Only synthetic test values were entered. Initial isolated-server API base URL was corrected to include `/api/v1`; setup-only 404s are not product regressions. A newly opened clean-page check returned no console warnings or errors.

Read-only checks of the isolated database after UI CRUD: schema v9, `quick_check=ok`, no foreign-key
violations, zero search runs/batches/contents and zero AI settings. The QA app uses a credential
directory derived from that disposable database directory, never the user's saved credentials.

## Bug analysis: invalid-submit focus

### 1. Root cause category

Implicit lifecycle assumption and test-coverage gap: local resolver execution is part of RHF
`isSubmitting`, not necessarily an actual network save. Disabling every field at that moment can
prevent first-invalid-field focus.

### 2. Why apparent follow-up failure was not another product defect

After separating pending states, unit focus assertions passed. The browser semantic-click helper
still left Save focused; a native mouse click on the same visible button immediately focused
`rule-issues`. No extra effect, timer or speculative focus workaround was added for that tool artifact.

### 3. Prevention

Keep validation and mutation pending responsibilities separate, retain a submit-only duplicate-click
guard, and assert invalid-field focus plus actual-pending-save disabled behavior in regression tests.

### 4. Systematic expansion

This is a form lifecycle pattern, not a new global state abstraction. Review analogous forms when
they change; do not widen this task to unrelated form rewrites.

### 5. Knowledge capture

Recorded in frontend state-management spec and this task's tests/evidence. This repository has no
applicable generated spec-template target. Commit/archival remain deferred to user authorization.

## Delivery state

Implementation, independent review, all automated gates and browser acceptance are complete.
No commit, push or archive requested. User database migration or application restart was not performed.
The two owned browser tabs, QA backend/frontend processes and SSH tunnel were closed; unused
loopback ports were verified. The synthetic QA SQLite file and its empty temporary directory were
removed after services stopped; no user data or credentials were deleted.

Follow-up delivery request: the user subsequently authorized commit and push. Finalize on `main`
with the already-checked AI-configuration dependency, archive only this completed rule task, and
record the work commits in the session journal. No product source changed after the final review.

## Bug analysis: issue-table length constraint

### 1. Root cause category

Cross-layer contract mismatch: SQLite `length(TEXT)` stops at embedded NUL, while the shared Python
composition validator counts the complete string. The new issue table's CHECK could turn a valid
issue into a 503 although the same existing object phrase saves.

### 2. Discriminating evidence

The reviewer reproduced both outcomes against a new disposable database; the pure composer accepted
both. This was not a malformed request or a browser issue.

### 3. Prevention

Match the original object's `TEXT NOT NULL` storage contract in the unpublished v9 issue migration.
Keep common 1–100-code-point validation in the service, plus unique/position/FK constraints. Add
API save/reload and over-length NUL regressions against fresh temporary databases.

### 4. Systematic expansion

Review language/database string-length semantics when adding child tables. Do not rewrite v8,
change legacy object semantics, or rerun migrations on the user's database.

### 5. Knowledge capture

Documented in the monitoring-rule spec and this verification record. The first UI fixture already
had v9 before this correction, so this exact edge case is verified by the reviewer's fresh-database
API tests; ordinary-value UI acceptance remains valid.
