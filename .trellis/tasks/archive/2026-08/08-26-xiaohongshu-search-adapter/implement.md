# Implementation Plan

## 1. MediaCrawler derivative

- Extend strict search protocol v1 from `toutiao | wb | ks | dy` to
  `toutiao | wb | ks | dy | xhs`, including exact 24-hex ID and canonical URL correlation.
- Add a narrow Xiaohongshu product adapter with task-page ownership, authoritative account proof,
  scoped cookies, existing pure signer, single-attempt search, bounded pagination, note-card
  normalization and typed outcomes.
- Treat only otherwise-valid recognized note cards with an absent, null or blank-string title as
  ignored cards. Retain fail-closed handling for every other malformed shape and never synthesize
  titles.
- Dispatch `xhs` exhaustively in the persistent worker without changing auth v2 or existing adapters.
- Add fixtures and tests for exact compact payload/signing input, one-attempt behavior, per-term
  search ID, pagination, limits, auxiliary cards, deduplication, masking, privacy, outcomes,
  cancellation, disconnect and owned cleanup.
- Add non-tautological sanitized-live regressions for a mixed page of safe, auxiliary and valid
  untitled cards; an all-untitled coherently exhausted response; and malformed near-miss shapes that
  must remain `structure_changed`.
- Extend the strict worker transport with a closed `open_result` command/result containing only one
  stored term, one XHS content ID and a fixed outcome. Keep existing auth/search frames compatible.
- Add a narrow XHS open-original path that proves login, searches exactly one first page once, matches
  the exact ID, holds xsec values only in local memory, navigates one owned official page and hands
  that page to the user only on `opened` or an actionable login/challenge state.
- Add CDP page-ownership release without changing existing cleanup semantics. Test target missing,
  token validation, response-source non-interference, worker-owned source derivation, query
  construction, unavailable 300031, redirect/challenge/block mapping, single request, no
  retry/page/term fallback, cancellation/disconnect and secret-free frames/logs.

## 2. FastAPI and SQLite

- Extend backend search platform and exact link validator to `xhs`.
- Preserve platform end to end and reject mismatched worker events or token-bearing XHS URLs.
- Add SQLite migration 6 while preserving all v5 IDs, rows, relationships, timestamps, indexes,
  foreign keys and autoincrement state.
- Expand migration, API, repository, service and worker-client tests for Xiaohongshu, cross-platform
  ID isolation, repeated runs, URL drift, outcomes and existing-platform regressions.
- Add a repository projection that proves a result belongs to a run and returns only its platform,
  stable content ID and matched terms in original position order; do not add schema or token columns.
- Add `POST /api/v1/search-runs/{run_id}/results/{result_id}/open` with no body. Reuse the global
  browser coordinator, await one bounded worker call and return a strict outcome without target URL,
  term or token. Cover 404 relation failures, non-XHS rejection, 409 contention, 503 storage failure,
  timeout/shutdown/cancellation, outcome mapping and no background orphan operation.

## 3. React

- Extend runtime decoding and platform-dependent URL validation with `xhs`.
- Add 小红书 to the Shadcn Select and presenter map using the existing logo.
- Verify start payload, history/detail labels, safe query-free links, keyboard use, responsive layout
  and unchanged default selection.
- Replace only the XHS result anchor with the existing Shadcn `Button`; keep one page-owned mutation,
  loading/disabled behavior and an `aria-live` result message. Validate the no-body POST and every
  strict outcome at runtime. Keep all other platform anchors unchanged.

## 4. Verification and delivery

Run MediaCrawler, backend and frontend full quality gates; run responsive loopback smoke; then, with
the already approved borrowed browser, execute one real Xiaohongshu search and a same-rule rerun.
Verify overlap is classified correctly, first-seen stays stable, last-seen advances, and existing
tabs/platforms remain intact. Click one stored XHS result and prove a single on-demand search opens the
official note while no xsec value appears in SQLite, API payloads/responses, frontend state or logs.
Also verify target-not-found and login/challenge outcomes remain truthful without extra search pages.

Commit and push the MediaCrawler derivative first. Then commit the reachable gitlink and parent
changes, run Centaurus cross-environment tests, archive this child task and verify a fresh recursive
clone. Once the child is complete, perform the parent multi-platform integration closeout separately.

## Risk and rollback points

- Stop if opening requires xsec persistence/exposure, context-wide mutation, automatic slider solving,
  raw credential export, alternate terms/pages, unbounded retry or requests beyond the single approved
  first-page lookup.
- Stop if migration 6 changes any existing platform identity, relation or timestamp.
- Never delete or overwrite runtime data or browser profiles as rollback.

## Implementation evidence: on-demand open slice

- The framed worker transport now has a separate exact `open_result` command/event; existing auth
  and search shapes remain unchanged. Protocol tests reject wrong platforms, malformed IDs, extra
  secret fields and forbidden outcomes.
- The XHS adapter proves login, performs one first-page request for one stored term, validates every
  returned non-auxiliary card, matches the exact ID, keeps the bounded token in memory, derives the
  fixed `pc_search` channel from the worker-owned search operation instead of trusting the response,
  validates the final page, maps 300031 to `content_unavailable`, and hands off only an opened page.
- A sanitized live correction gate found the exact target once with a valid bounded token and no
  response source. Regression fixtures now omit the source by default and prove a response-provided
  source cannot influence the worker-owned navigation channel.
- FastAPI proves run/result ownership and original term order without a migration, admits the
  bounded operation through the shared browser coordinator, exposes an exact no-body endpoint and
  returns only the fixed outcome. Tests cover relation 404, non-XHS 409, contention, storage 503,
  timeout, cancellation and shutdown cleanup.
- React runtime-decodes the exact outcome. Non-XHS anchors remain unchanged; XHS uses the existing
  Shadcn Button with one page mutation, all-button disabling, active loading text and nearby
  `aria-live` Chinese feedback.
- Frozen local gates passed for the product test suites. The coordinated live gate then returned
  `opened`, retained the released Chrome tab after backend shutdown, and confirmed official
  canonical/Open Graph path correlation plus visible rendered note content without unavailable or
  challenge evidence. SQLite schema/content/term scans contained no xsec value. The gate performed
  no runtime SQLite write; commit and push remain delivery steps.
