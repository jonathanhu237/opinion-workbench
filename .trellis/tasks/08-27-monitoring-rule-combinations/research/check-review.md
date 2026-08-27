# Final Rule-Composition Review — 2026-08-27

Scope: approved Q1–Q6, including persistence, API, local preview, full replacement/toggle,
and standalone/batch consumers. The existing uncommitted AI configuration and v8 migration
were preserved. No user runtime database, credentials, live platform/model operation,
service lifecycle, Git commit, or MediaCrawler change was involved.

## Findings (fixed)

### SQLite/Python length mismatch for issue values

- Files: `backend/src/longtian_api/database.py`,
  `backend/tests/test_monitoring_rule_combinations.py`.
- Issue: the new v9 issue table used `CHECK (length(value) BETWEEN 1 AND 100)`.
  SQLite text length stops at NUL, unlike the existing Python Unicode-codepoint
  validation. A synthetic NUL-only object was accepted while the same issue value
  produced `503 monitoring_rule_storage_unavailable` in an isolated Centaurus database,
  despite both passing the shared semantic validator.
- Fix: align the unreleased v9 issue value column with original object storage
  (`TEXT NOT NULL`). Keep FK/cascade, position bounds and both uniqueness constraints.
  The shared composition validator continues enforcing 1–100 code points for every
  input and generated query; neither v8 nor original object storage changed.
- Regression: three API save/reopen cases preserve NUL values, including a 100-codepoint
  composed query; three semantic rejection cases cover oversized objects, issues and
  generated queries containing NUL.
- Existing isolated QA databases already at v9 do not rerun this migration. The new
  boundary was verified using newly created temporary databases, not user data.

### Missing collection UI effective-count regression

- File: `frontend/src/routes/collection-runs.test.tsx`.
- Issue: the collector fixture had been upgraded to the two-group response, but no UI
  regression distinguished the effective query count from either input-group count.
- Fix: add 2×10 and 3×7 fixtures. Assert exact selector counts, one explicit start for
  20 queries, and visible rejection with zero start calls/navigation for 21 queries.
  No collector implementation change was needed.

## Findings (not fixed)

None. No unresolved behavioral or scope findings remain.

## Contract Review

- Strict POST defaults, required full PUT groups, rejection of read-only `terms`, exact
  response shape, status/code mapping, and signed-int64 path guard remain consistent.
- The pure composer validates count before product allocation, preserves trimmed display
  text and internal spaces, rejects normalized input/generated collisions, and is shared
  by writes and read projections. Frontend Python-compatible trimming preserves BOM and
  removes NEL/C0 separators; codepoint limits and preview order match the backend.
- Migration 9 is additive and does not rewrite prior rows. Tests compare all v8 tables,
  including AI settings and run/batch relations; repeated initialization and deleted
  defaults remain safe. Dual groups are read through a single UNION ALL snapshot and
  replaced atomically; partial migration/create/replace failures roll back.
- Edit/toggle use original groups. The preview is pure local derived state, the complete
  bounded list is keyboard-accessible, and pending saves remain distinct from local
  resolver validation. Existing shadcn primitives and semantic theme tokens are retained.
- Standalone/batch admissions count `rule.terms`; child attempts use immutable stored
  batch terms. The 20-query execution cap, result deduplication and provenance remain
  unchanged. CRUD tests intercept platform-worker and model execution.
- Main-session desktop/narrow/focus/console smoke evidence was supplied with the review.
  The reviewer did not start, stop or interact with those QA services.

## Verification

All executable checks ran on the Centaurus source mirror after narrow one-way source/test
sync; Git operations and edits stayed local.

Backend:

```text
uv sync --frozen                  PASS
uv run ruff format --check .      PASS (47 files)
uv run ruff check .               PASS
uv run pytest -q                  PASS (353 tests, 6.03s)
```

Frontend, each command under `mise x node@24 pnpm@11.14.0 --`:

```text
pnpm install --frozen-lockfile    PASS
pnpm format:check                PASS
pnpm lint                        PASS (0 warnings, 0 errors)
pnpm typecheck                   PASS
pnpm test:run                    PASS (164 tests in 10 files, 7.58s)
pnpm build                       PASS
```

Local `git diff --check`: PASS. There is no configured separate Python type-check gate;
the project TypeScript gate passed. No package/configuration/template update was needed.

The main session synchronized the two-group, Python trim/BOM, resolver-focus and
SQLite-length contracts in the approved backend/frontend specs. Final inspection found
no remaining spec discrepancy. A final checksum dry-run confirmed all 15 reviewed
feature source/test files match the Centaurus mirror.
