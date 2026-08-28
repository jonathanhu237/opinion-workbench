# Implementation B

Status: implementation/check/browser gates passed; no commit or archive performed.

## Ordered Work

- [x] Review A's persisted discovery/handoff interface and current schema version.
- [x] Add schedule/occurrence migration, constraints, fixtures and round-trip tests.
- [x] Implement fixed-interval calculation with fake UTC clock/monotonic wait.
- [x] Add idempotent batch occurrence linkage before launching browser work.
- [x] Exercise due/duplicate/busy/unavailable/disabled/deleted-rule/clock-jump/
  offline/crash cases; preserve pause and manual recovery.
- [x] Integrate timer startup/shutdown without catch-up work or duplicate owners.
- [x] Add labelled schedule forms/history and accurate next-due/skipped feedback.
- [x] Verify A+B new-result handoff and parent G3 plus relevant G1/G7 checks.
- [x] Hand off occurrence and collection provenance to C; do not enable real work.

## Verification

Follow parent implementation section 4: edit locally, sync a verified source
snapshot one-way, run all gates on Centaurus, forward isolated UI/API ports.
Backend from its package:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

Frontend from its package:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

Use fake clocks/browsers and temporary databases, not real account automation.
Review every crash boundary, not only timer arithmetic. Disable new schedule
admission for rollback; retain running work/history and parent safeguards.
No commit/archive or next-child activation without the required workflow gate.
