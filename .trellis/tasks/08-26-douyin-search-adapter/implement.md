# Implementation Plan

## 1. MediaCrawler derivative

- Extend strict search protocol v1 from `toutiao | wb | ks` to `toutiao | wb | ks | dy`, including
  exact numeric ID and canonical URL correlation.
- Add a narrow Douyin product adapter with task-page ownership, authoritative account proof, minimal
  temporary state, single-attempt general search, bounded pagination, normalization and typed
  outcomes.
- Dispatch `dy` exhaustively in the persistent worker without changing auth v2 or existing adapters.
- Add fixtures and tests for exact parameters, one-attempt behavior, offset/search-ID propagation,
  limits, deduplication, masking, privacy, outcomes, cancellation, disconnect and owned cleanup.

## 2. FastAPI and SQLite

- Extend backend search platform and exact link validator to `dy`.
- Preserve platform end to end and reject mismatched worker events.
- Add SQLite migration 5 while preserving all v4 IDs, rows, relationships, timestamps, indexes,
  foreign keys and autoincrement state.
- Expand migration, API, repository, service and worker-client tests for Douyin, cross-platform ID
  isolation, repeated runs, URL drift, outcomes and existing-platform regressions.

## 3. React

- Extend runtime decoding and platform-dependent URL validation with `dy`.
- Add 抖音 to the Shadcn Select and presenter map using the existing logo.
- Verify start payload, history/detail labels, safe links, keyboard use, responsive layout and
  unchanged default selection.

## 4. Verification and delivery

Run MediaCrawler, backend and frontend full quality gates; run responsive loopback smoke; then, with
the already approved borrowed browser, execute one real Douyin search and the immediate same-rule
rerun. Verify official links, overlap classification, stable first-seen, advanced last-seen, typed
login/challenge behavior and preservation of existing tabs and platforms.

Commit and push the MediaCrawler derivative first. Then commit the reachable gitlink and parent
changes, run Centaurus cross-environment tests, archive this child task and verify a fresh recursive
clone.

## Risk and rollback points

- Stop if the endpoint requires context-wide state mutation, automatic slider solving, raw credential
  export, unbounded retry or requests beyond the explicit product limit.
- Stop if migration 5 changes any existing platform identity, relation or timestamp.
- Never delete or overwrite runtime data or browser profiles as rollback.
