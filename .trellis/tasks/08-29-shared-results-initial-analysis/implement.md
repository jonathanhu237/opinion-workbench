# Implementation A

Status: implementation and full-scope check passed after parent approval.
See `research/full-check.md` and `research/browser-acceptance.md`.

## Ordered Work

- [x] Recheck v11/current schema and all overlapping edits; load parent artifacts,
  this design and both manifests, then activate only A after approval.
- [x] Add genuine historical fixtures and migration/transaction tests first.
- [x] Implement new storage and legacy markers, then prompt/version/policy APIs.
- [x] Implement global result/provenance queries and strict frontend boundaries.
- [x] Add idempotent automatic/manual/legacy admission and all-never-started
  selection; test 0/1/101/1,001 records, races and frozen later arrivals.
- [x] Extract/reuse validated media, structured output and usage helpers; save
  immutable successes with no report prerequisite.
- [x] Add cancellation/restart/configuration-change handling and unique completion
  events, with crash/late-write tests.
- [x] Implement result/attempt/prompt/progress views using existing theme and
  labelled controls; no placeholder report action or hidden generation call.
- [x] Verify parent G1, G2 and initial-analysis portions of G4/G6/G7; document
  handoff for B/C and keep full-feature automation disabled.

## Verification

Use parent `../08-28-collection-report-decoupling/implement.md` section 4 for
local-to-Centaurus sync, isolated database/services and port-forwarded browser QA.
Run on the verified remote snapshot, from each respective package:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

No real runtime DB/account/provider. Final review must verify old/new active
admission exclusion and source provenance, not only happy-path model mocks.
Disable admissions and retain all old/new data on rollback. Use the parent
spec-update/check/commit gates. B can activate under the approved parent plan
only after A passes its complete check; no commit or archive is authorized.
