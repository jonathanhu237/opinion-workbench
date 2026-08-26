# Implementation Plan

## Phase 0: Preflight and baselines

- [x] After explicit approval of the final planning summary, start this Trellis task and load the
  curated implement manifest, PRD, design, and implementation plan.
- [x] Record parent HEAD/status, MediaCrawler submodule HEAD/status, database schema version, and any
  active local services. Preserve all user-owned runtime, browser, and unrelated worktree changes.
- [x] Run current backend, frontend, focused MediaCrawler, and submodule integrity baselines before
  editing.

## Phase A: Executable contracts and database migration

- [x] Implement database migration 2 with the five search tables, constraints, indexes, nullable
  source-rule reference, and atomic active-row reconciliation while preserving migration 1 data.
- [x] Add strict Pydantic search-run request/summary/detail/result/list/error models and exact enums.
- [x] Add the search repository for snapshots, state transitions, history/result pagination,
  transactional content upsert, cross-run deduplication, cross-term provenance, counts, filters, and
  sanitized failures.
- [x] Add repository/migration tests covering fresh and v1→v2 databases, reopen persistence, deletion
  of source rules, all deduplication invariants, rollback, deterministic ordering, and stale active
  rows.

## Phase B: MediaCrawler persistent search protocol

- [x] Add separate strict search command/event prefixes and v1 decoders/encoders without changing
  existing auth v2 frame shapes or one-shot auth fallback behavior.
- [x] Extend the persistent worker command loop to accept one serialized Toutiao search, emit
  correlated progress/item/result events, handle cancellation, and retain strict stdout/stderr
  privacy and frame-size bounds.
- [x] Refactor the parent worker client into a lifespan-shareable MediaCrawler worker boundary that
  supports unchanged auth checks plus search callbacks and one request lock.
- [x] Add protocol/client/worker tests for all frames, term-position mapping, terminal outcomes,
  malformed/oversized/mismatched data, cancellation, recycle, shutdown, and auth regressions.

## Phase C: Borrowed-context Toutiao search

- [x] Extract or add a context-injected Toutiao search operation that consumes the borrowed default
  context and creates/registers only task-owned pages.
- [x] Reuse existing visible DOM parsing, URL canonicalization/allowlist, bounded text, masking, and
  typed failure categories; prohibit generic stores, private APIs, context-wide stealth, retries,
  pagination, and fallback browsers.
- [x] Enforce 1–20 terms, 1–50 results per term, sequential execution, within-term deduplication, and
  cross-term re-emission with the correct term position.
- [x] Implement normal/cancel cleanup and the tracked visible login/challenge-page lifecycle without
  closing the browser, default context, or pre-existing tabs.
- [x] Add focused unit/fixture tests plus borrowed-context ownership sentinels for results, empty,
  login, challenge, block, structure drift, disconnect, cancellation, and cleanup.

## Phase D: FastAPI orchestration

- [x] Introduce one lifespan-owned worker and shared browser-operation coordinator; inject them into
  platform connection and search services while preserving existing platform-account behavior.
- [x] Implement asynchronous search-run start, progress/item persistence, outcome mapping, timeout,
  cancellation, shutdown, operation release, and safe partial-result retention.
- [x] Add `/api/v1/search-runs` start/list/detail/results/cancel routes, dependencies, OpenAPI response
  models, exact 404/409/422/503 translations, and main-router registration.
- [x] Test HTTP 202/non-blocking behavior, every validation/error/status mapping, cross-feature
  admission races, account-check regression, polling reads, restart reconciliation, timeout/cancel,
  shutdown, and privacy sentinels.

## Phase E: React 采集任务 experience

- [x] Add only the reviewed Shadcn primitives needed by the page (for example Select/Tabs/Alert),
  preserving Base UI compatibility and existing global tokens.
- [x] Add runtime-validated search-run API models, exact status/code decoding, TanStack Query hooks,
  active-only polling, cancellation, pagination/filter parameters, and abort handling.
- [x] Add the real `采集任务` sidebar link plus lazy `/collection-runs` and
  `/collection-runs/:runId` routes with correct route title, active state, mobile close, and focus.
- [x] Build the start form with enabled rules, fixed Toutiao target, default-10/range-1–50 input,
  >20-term inline rejection, truthful conflict/connection guidance, and Shadcn Button actions.
- [x] Build active progress, durable history, deep-linked detail, real new/repeated/total counts,
  filters, matched terms, timestamps, safe original links, and honest loading/empty/failure states.
- [x] Preserve the existing palette/type/shell; add no fake telemetry, unsupported platform controls,
  decorative metrics, or global recolor. Meet keyboard/live-region/reduced-motion/mobile requirements.
- [x] Add API/hook/route behavior tests for decoding, start, validation, polling, cancellation,
  history, filters, refresh/deep link, all terminal guidance, safe links, navigation, and accessibility.

## Phase F: Automated and cross-layer verification

- [x] MediaCrawler: run focused Toutiao/search/auth-worker tests, maintained test suite as practical,
  compilation/static checks, privacy-pattern scan, and `git diff --check`.
- [x] Backend: run `uv sync --locked`, `uv run --frozen ruff check .`,
  `uv run --frozen ruff format --check .`, `uv run --frozen pytest`, and OpenAPI/import smoke checks.
- [x] Frontend under the configured mise Node: run `pnpm install --frozen-lockfile`,
  `pnpm format:check`, `pnpm lint`, `pnpm typecheck`, `pnpm test:run`, and `pnpm build`.
- [x] Cross-layer: start FastAPI and Vite on loopback; test 202→poll→terminal/result decoding,
  duplicate second run fixtures, cancellation, account/search mutual exclusion, deep links, browser
  console, and responsive overflow at 375/768/1024/1440.
- [x] Verify SQLite counts/relationships directly against API projections without exposing the real
  database path or user terms in retained evidence.

## Phase G: Real Chrome/Toutiao acceptance

- [x] Before the search, record only non-sensitive pre-existing tab/page counts and create or identify
  a harmless sentinel tab without capturing page content.
- [x] Run one approved borrowed-browser Toutiao search (logged in only when the platform requires it)
  for a bounded rule and verify visible progress,
  terminal status, normalized original links, and safe task-page cleanup.
- [x] Run the same search again and verify zero duplicate global content rows, repeated labels/counts,
  preserved first-seen timestamps, updated last-seen timestamps, and matched-term provenance.
- [x] If login/challenge appears, require the user to complete it visibly; verify no automated bypass,
  retry, or private fallback and record only the outcome category.
- [x] Cancel one bounded run or exercise controlled shutdown, then prove Chrome/default context/
  sentinel tabs remain usable and the owned worker/page cleanup is narrow.
- [x] Scan API responses, logs, task evidence, process arguments, and repository diffs for credential,
  profile, raw child/page, or unmasked identity leakage.

## Review, knowledge capture, and delivery

- [x] Dispatch the Trellis full-scope check with the curated check manifest; fix every in-scope
  finding and rerun affected gates.
- [x] Reconcile implementation with the new product-search code-spec and update it through
  `trellis-update-spec` for any contract learned during real acceptance.
- [x] Commit/push the MediaCrawler derivative first only after user delivery approval; verify remote
  reachability and clean submodule state before updating the parent gitlink.
- [ ] Commit/push parent backend/frontend/spec/task changes with Conventional Commits after all gates
  pass and the user approves delivery; then archive the Trellis task and record the session.

## Rollback points

- Any pre-existing Chrome tab, default context, or browser is closed/mutated: stop immediately and
  do not continue real acceptance until borrowed ownership is corrected.
- Search invokes a generic MediaCrawler store/private API or leaks terms through argv/logs: stop the
  integration and restore the prior derivative revision before redesign.
- Auth v2/account checks regress after shared-worker refactor: stop search integration and restore the
  prior worker ownership boundary.
- Database deduplication/provenance/count invariants diverge: stop frontend integration; fix the
  transaction/model before exposing results.
- Parent/backend imports MediaCrawler or submodule becomes dirty/unreachable: stop delivery and keep
  the parent gitlink unchanged.
- Never delete, reset, or downgrade the user's SQLite/runtime/browser data as rollback.
