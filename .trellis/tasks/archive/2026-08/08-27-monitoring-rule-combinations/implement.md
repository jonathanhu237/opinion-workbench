# Monitoring Rule Composition Execution

Approved for implementation on 2026-08-27. Preserve checked uncommitted AI-configuration work. This child requires no media or provider call.

## Ordered Work

1. Final approval received on 2026-08-27. Validate context, activate this child and load Phase 2.1. Dispatch prescribed `trellis-implement` with `Active task: <current child path>` first. Ownership: monitoring-rule storage/API/UI and narrow collector fixture/decoder updates. The implementer is not alone; preserve AI-configuration and unrelated edits.
2. Re-read actual schema and rule/search specs. Add the issue-term migration and repository persistence with isolated tests, preserving old object rows, one-time seed and historical snapshots. Do not overwrite the checked v8 AI migration.
3. Implement pure composition/validation and strict models. Keep derived read-only `terms` for collectors; reject ambiguous write shapes. Test empty issues, spaces/order, duplicates/generated collisions, combined length, 100-query cap and atomic failure.
4. Update frontend decoder/payload, edit fields, local preview and every full PUT/toggle together. Reuse shadcn/Base UI/theme. Test reload/edit/toggle, associated errors, count/20-query warning and no network execution from preview.
5. Update affected fixtures/consumers; prove both search-run and batch services get generated terms while their 20-query gate, frozen history and dedup remain intact. No worker protocol or MediaCrawler gitlink changes.
6. Sync exact source/task/spec changes to Centaurus, excluding runtime/secrets/.git/environments/caches. Run full gates below and forward isolated services for UI verification with a temporary database.
7. Dispatch `trellis-check`; main session updates verified specs, records sanitized evidence and reports this child only. Do not auto-start media/summary or commit/push/archive without a user request.

## Test Matrix

- Fresh/v8/populated/deleted/disabled rules; repeat upgrade; future version; rollback; no changes to AI settings, default deletion or run/batch history.
- 2×2 combinations, empty issues, required objects, embedded spaces, trim/Unicode, 100-character combined boundary, normalized input/generated collisions and 20/21 plus 100/101 query boundaries.
- Exact POST/PUT/GET and status/code errors, full replacement/toggle, stable IDs/order and no raw SQL/paths/input disclosure.
- Zero browser/media/model calls from rule work; derived collector inputs; batch children use original frozen scope after edits.
- Existing frontend tests plus empty optional/preview/limit/save error/toggle cases; desktop/narrow keyboard/scroll/long-content and console checks.

## Full Gates on Centaurus

From `backend/`:

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

From `frontend/`:

```bash
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

Run `git diff --check` locally. Report unavailable Centaurus before resource-intensive local fallback. Use the prescribed browser skill for isolated UI checks, never live searches/provider calls as a substitute for tests.

## Sensitive Integration Points

Shared `database.py`, rule strict schemas, response decoders, derived-query compilation and enabled-toggle writes must ship coherently. Extend the existing checked code, do not reset files, create a branch/PR, rewrite released migrations or change the fork.
