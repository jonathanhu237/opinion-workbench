# Implementation Plan

## 1. MediaCrawler derivative

- Extend strict search protocol v1 from `toutiao | wb` to `toutiao | wb | ks`, including exact
  platform-dependent canonical URL validation and cross-platform event correlation.
- Add a narrow Kuaishou product adapter with task-page ownership, page-local signer injection,
  authoritative login proof, single-attempt signed search, bounded sequential pagination,
  normalization, cancellation and typed outcomes.
- Dispatch `ks` exhaustively in the existing persistent worker without changing auth v2 behavior or
  the existing Toutiao/Weibo adapters.
- Add fixtures and tests for signer isolation, exact request body/query, one-attempt behavior,
  pagination/session handling, limits, deduplication, masking, sanitization, all terminal outcomes,
  cancellation, disconnect and owned cleanup.

## 2. FastAPI and SQLite

- Extend the backend-owned search platform type and URL validator to include exact `ks` links.
- Preserve platform end to end through create, durable run, worker request/events, repository and
  response; reject mismatched platform events.
- Add transactional SQLite migration 4 widening both platform checks while preserving all existing
  v3 IDs, rows, relationships, timestamps, indexes, foreign keys and autoincrement state.
- Expand migration, repository, API, service and worker-client tests for Kuaishou, same-ID
  cross-platform isolation, repeated runs, URL drift, terminal mappings, cancellation and
  Toutiao/Weibo regressions.

## 3. React

- Extend runtime platform decoding and platform-dependent URL validation with `ks`.
- Add Kuaishou to the existing Shadcn Select and exhaustive presenter map using the reviewed logo
  asset.
- Verify start payloads, history/detail presentation, safe links, status guidance, keyboard use,
  responsive layout and unchanged default selection.

## 4. Verification and delivery

Run focused tests during development, then complete gates:

```bash
cd third_party/MediaCrawler
uv run pytest tests/test_auth_worker.py tests/test_search_worker_protocol.py tests/test_product_search.py tests/test_kuaishou_product_search.py
uv run pre-commit run --files tools/auth_worker.py tools/search_worker_protocol.py media_platform/kuaishou/product_search.py tests/test_auth_worker.py tests/test_search_worker_protocol.py tests/test_product_search.py tests/test_kuaishou_product_search.py
uv run pytest tests -k 'not redis'

cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd frontend
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```

- Run loopback UI smoke at 375, 768, 1024 and 1440 CSS pixels, checking selection, history, detail,
  safe external links, focus, overflow and console.
- With explicit browser approval, preserve a pre-existing sentinel tab and run one real Kuaishou
  search plus the exact repeated run. Verify usable official links, repeated classification,
  unchanged first-seen, advanced last-seen, one persistent connection, and sentinel survival.
  Record only sanitized outcomes, counts and timestamps.
- Commit and push MediaCrawler first. Then commit the reachable gitlink plus parent code, verify
  clean trees and prove a fresh recursive clone.

## Risk and rollback points

- Stop if signature generation cannot remain page-local or begins requiring browser-wide mutation.
- Stop if the platform requires challenge automation, raw credential extraction, unbounded retry or
  requests beyond the explicit product limit.
- Stop if migration 4 changes any existing Toutiao/Weibo identity, relationship or timestamp.
- Stop if cleanup closes or mutates a pre-existing page, context or browser.
- Never delete or overwrite `runtime/`, browser profiles, logs or user-owned data as rollback.
