# Implementation C

Status: implementation, independent checks, specs and final isolated browser
acceptance passed after checked A/B. Final backend997/frontend593 gates and
actual observations are in `research/`. No commit, archive or live deployment
has been performed. Ownership boundaries were preserved throughout execution.

## Ordered Work

- [x] Verify A event/attempt/prompt contracts and B schedule provenance; recheck
  current schema and final parent requirements before activation.
- [x] Add report tables, immutable source/node fixtures and idempotent event consumer.
- [x] Test settlement/crash boundaries: 10 attempts, 8 successes, 2 failures,
  one automatic report; later arrivals, cancellation and zero-success cases.
- [x] Implement per-source text judgments, bounded leaf composition and overview
  tree; retain all relevant membership and explicit failure/usage details.
- [x] Add text-only retry/version/override/interval APIs with strict guards.
- [x] Add report progress/history/section/citation views and integrate collection
  links without old combined-generation calls.
- [x] Test 101+ and 1,001 sources, exact/oversized prompt/input, tree levels,
  unsupported/unknown/omitted citations, unknown usage and parse failures.
- [x] Instrument zero acquisition/media/stage-one calls for report/retry/override.
- [x] Perform parent G1–G7 and all AC01–AC28 integration, including new/legacy
  states, keyboard/narrow UI and console. Report live-model evidence separately.
- [x] Update specs through the required skill and run the final quality/review
  gate. Enable no real schedules or provider work without explicit authorization.

## Verification

Use parent implementation section 4 for exact Centaurus sync/isolation/tunnel
constraints. From the remote backend package:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

From the remote frontend package:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

Rollback uses disabled admissions/retained snapshots, not old binaries over a
down-labelled schema. Parent completion requires observed acceptance evidence,
not only child implementation success. Follow the explicit commit gate and
Conventional Commits; planning authorizes no commit or archive.
