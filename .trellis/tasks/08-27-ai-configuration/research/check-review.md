# Independent AI Configuration Review

Reviewed on 2026-08-27 by the dispatched Trellis check role. This is review evidence,
not a parent acceptance decision. Source changes stayed local and were synchronized
one-way to Centaurus. No real provider request, credential, runtime database,
browser profile, submodule, commit, or push was used.

## Scope

Reviewed the complete new configuration implementation, including untracked files:
schema/repository/credential store/service/client/errors/API; migration v8,
lifespan, dependencies/router, backend manifest/lock; frontend HTTP boundary,
form, route/shell integration, and all added/updated tests. Read the child PRD,
design, execution plan, curated check context, parent configuration/transport
contracts, and applicable backend/frontend specifications.

The implementation remains configuration-only. Media, screening, and summary
children are not implemented by this task. No platform template/configuration
touchpoint or submodule change was necessary.

## Findings (fixed)

### Stale success feedback after editing

- Files: `frontend/src/routes/ai-settings.tsx`, adjacent test file.
- Issue: after a successful connection test, editing Base URL and attempting an
  invalid save left the previous connection-success message visible beside the
  unsaved endpoint and required-key error.
- Fix: clear operation feedback on user form changes. New regression exercises
  success, endpoint editing, invalid submission, disabled testing, and no save.
- Before fix: the new regression failed because the success message remained.
- Additional coverage: exercise recovery from an initial
  `ai_credentials_unavailable` read, re-entry of settings/key, successful save,
  cleared key input, and non-secret cache. The earlier test name claimed this
  path but only exercised a generic storage retry; its title now matches its
  actual behavior.

### Excessively nested JSON escaped the stream error contract

- Files: `backend/src/longtian_api/services/ai_client.py`,
  `backend/tests/test_ai_client.py`.
- Issue: a bounded SSE event containing deeply nested JSON raises
  `RecursionError`, which escaped the client boundary and would be converted by
  the route into generic provider-unavailable instead of invalid-response.
- Fix: sanitize decoder recursion failures as `ai_invalid_response`; add a
  named excessive-nesting regression and an explicit audio-output rejection
  case. The existing stream-closing assertion also covers both cases.
- Before fix: the deep-JSON regression raised `RecursionError` instead of the
  expected domain error.

### AI close failure skipped existing service cleanup

- Files: `backend/src/longtian_api/main.py`, `backend/tests/test_ai_settings.py`.
- Issue: a failure while closing the newly added AI client prevented the
  pre-existing batch, search-run, and platform shutdown operations from running.
- Fix: put the unchanged existing cleanup sequence in a `finally` around AI
  teardown. Do not swallow the AI close failure or redesign existing lifetimes.
- Before fix: the regression's existing-service shutdown spies were never
  awaited. After the fix each is awaited once.

## Findings (not fixed)

No remaining in-scope blocking finding. Real-provider connectivity, entitlement,
quota, and multimedia support were intentionally not exercised. Permission
behavior was tested on Centaurus/Linux with temporary files; this run does not
claim a macOS or Windows runtime credential-store acceptance test. Plaintext
credential storage remains the approved permission-protected boundary, not
encryption or protection against the same OS user/full-runtime backups.

Browser verification and final lifecycle edits belong to the main session. Main
reported the post-HMR success/edit/invalid-save regression passed, navigation
remained functional, and the dev logs contained no warnings/errors. Three explicit
browser test clicks produced exactly three fake client calls; save/read/reload
produced none. The owning specification now records the three regression
contracts; its source/test correspondence was rechecked by this reviewer.

## Verification

All final package gates ran on Centaurus after the fixes:

| Package | Command | Result |
| --- | --- | --- |
| Backend | `uv sync --frozen` | Pass; 52 packages checked |
| Backend | `uv run ruff format --check .` | Pass; 46 files formatted |
| Backend | `uv run ruff check .` | Pass |
| Backend | `uv run pytest -q` | Pass; 308 tests, 4.85 s |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile` | Pass |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm format:check` | Pass |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm lint` | Pass; zero warnings/errors |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm typecheck` | Pass |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm test:run` | Pass; 136 tests / 9 files |
| Frontend | `mise x node@24 pnpm@11.14.0 -- pnpm build` | Pass; 2,333 modules |

Backend has no configured static type-check command. Local `pnpm format` completed
without changing any file; local `git diff --check` passed. Focused post-fix suites
also passed: 101 backend AI tests and 12 frontend form tests.

Confirmed the locked HTTP transport implementation consumes `sni_hostname` as
TLS `server_hostname`, so the configured hostname is retained for certificate
verification while the connection target is the validated IP. No live TLS or
provider test was needed for that source-level check.

## Bug Analysis: State validity and failure ownership

### 1. Root Cause Category

- **D — Test Coverage Gap:** form tests checked isolated success and validation
  states, but not success followed by an edit; the missing-key test name also
  exceeded its coverage.
- **E — Implicit Assumption:** JSON decoding was assumed to fail only with
  value/Unicode errors, and the new close operation was assumed not to raise.

### 2. Why Fixes Failed

No repeated or failed fix attempts. Each product defect was reproduced with a
new failing regression before its narrow source fix.

### 3. Prevention Mechanisms

| Priority | Mechanism | Action | Status |
| --- | --- | --- | --- |
| P1 | Behavioral regression | Test feedback across success/edit/invalid-save transitions | Done |
| P1 | Boundary regression | Include bounded but excessively nested external JSON | Done |
| P1 | Lifecycle regression | Inject new-owner close failure; assert existing cleanup still runs | Done |
| P1 | Recovery regression | Test the actual missing-key read/save recovery path | Done |
| P2 | Specification | Record feedback lifetime, decoder failure, and teardown isolation contracts | Done; main updated, reviewer verified |

### 4. Systematic Expansion

Inspected shared request errors, route registration, credential replacement,
lease admission/cancellation, and client shutdown rather than changing adjacent
features. Existing cleanup order is retained. No new scheduler, store, protocol,
fallback provider, or generalized abstraction was introduced.

### 5. Knowledge Capture

This record preserves the evidence. Main updated
`.trellis/spec/backend/ai-configuration-guidelines.md`, and the reviewer verified
the feedback, nested-JSON, teardown, and recovery-test contracts against the final
implementation. The frontend state-management guide retains its cross-reference.
No template copy exists for this product specification, and no Git commit is
authorized.
