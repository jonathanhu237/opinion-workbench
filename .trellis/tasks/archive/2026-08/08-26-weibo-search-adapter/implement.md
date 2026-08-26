# Implementation Plan

## 1. MediaCrawler derivative

- Generalize `tools/search_worker_protocol.py` from Toutiao-only to the exact `toutiao | wb`
  platform set while keeping protocol version 1 and platform-dependent URL validation.
- Add the narrow Weibo product-search adapter with fixed real-time mode, bounded sequential pages,
  single-attempt requests, normalization, typed outcomes, task-page ownership, and cancellation.
- Dispatch search exhaustively by platform in `tools/auth_worker.py`; preserve all authentication
  behavior and the existing Toutiao path.
- Add focused tests for strict frames, cross-platform correlation, Weibo request parameters,
  flat/nested cards, deduplication, limits, sanitization, outcomes, disconnect, and owned cleanup.

## 2. FastAPI and SQLite

- Add one backend-owned `SearchPlatform` alias and extend strict request/response validation to
  `toutiao | wb` with platform-specific URL rules.
- Pass the platform through `SearchRunService`, `PersistentAuthWorkerClient`, callbacks, and every
  correlated event check; remove hard-coded Toutiao substitutions.
- Add SQLite migration 3 that rebuilds the search aggregate transactionally, preserves version-2
  data/IDs/relations, widens platform checks, and recreates indexes.
- Parameterize repository create/lookup/insert paths by platform and retain the existing global
  `(platform, platform_content_id)` deduplication behavior.
- Expand backend tests for migration 2→3, same-ID cross-platform isolation, Weibo repeated runs,
  exact worker frames, mismatched platform rejection, URL validation, service outcomes, cancellation,
  public envelopes, and unchanged Toutiao behavior.

## 3. React

- Extend the search-run API types and runtime decoders with the exact two supported platforms and
  correlated URL validation.
- Replace the fixed Toutiao presentation with a Shadcn platform Select and one platform presenter
  map containing the existing Toutiao and Weibo logo assets.
- Render the correct platform in start, history, and detail views without adding placeholder
  platforms or a search-sort control.
- Expand behavior tests for request payloads, platform switching, runtime drift, safe links, history
  and detail rendering, keyboard interaction, mobile layout, and existing Toutiao defaults.

## 4. Verification and delivery

Run focused tests during implementation, then the full gates:

```bash
cd third_party/MediaCrawler
uv run pytest tests/test_auth_worker.py tests/test_search_worker_protocol.py tests/test_weibo_product_search.py
uv run pre-commit run --all-files
uv run pytest tests -k 'not redis'

cd backend
uv run ruff check .
uv run pytest

cd frontend
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm format
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```

- Run a loopback UI smoke test at 375, 768, 1024, and 1440 CSS pixels; check selection, history,
  detail, external links, cancellation, overflow, focus, and browser console.
- With the user's approved persistent Chrome connection, preserve a pre-existing sentinel tab and
  execute one real-time Weibo run plus the same run again. Confirm usable official links, second-run
  repeated classification, unchanged first-seen time, updated last-seen time, no overlap with an
  account check, and sentinel survival. Store only sanitized categories/counts/timestamps as task
  evidence.
- Confirm both parent and submodule working trees are clean. Commit and push MediaCrawler first,
  then move the parent gitlink. Validate the reachable SHA, recursive submodule status, and a fresh
  recursive clone before parent delivery.

## Risk and rollback points

- Stop if the real endpoint requires new signing, broad browser-state extraction, or challenge
  automation; return to planning instead of expanding scope.
- Stop if one Weibo request can silently retry through the generic five-attempt client path.
- Stop if migration 3 changes existing Toutiao IDs, counts, terms, or timestamps.
- Stop if cleanup closes or mutates a pre-existing tab/context/browser.
- Never delete or overwrite `runtime/`, `db_data/`, browser profiles, logs, or user-owned content as
  a rollback mechanism.
