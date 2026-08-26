# Verification

## Automated quality gates

- Local FastAPI: Ruff check/format passed; 195 tests passed.
- Local React: frozen install, Prettier, Oxlint, TypeScript and production build passed; 97 tests
  passed.
- Local MediaCrawler maintained tests: 533 passed. XHS/protocol/CDP scoped tests reported 76 passed,
  and the open-result slice reported 16 passed.
- MediaCrawler scoped Ruff, format, mypy, compileall and pre-commit passed.
- Trellis task validation, root/submodule `git diff --check`, and privacy/artifact scans passed.
- The upstream repository-wide MediaCrawler run had the same six Redis and two Mongo integration
  failures on both the working tree and a clean `HEAD`; they are external-environment failures and
  not product-search regressions.

## Centaurus Linux verification

- The local repository was synchronized one-way without Git metadata, runtime SQLite data,
  dependency directories or build output.
- FastAPI Ruff check/format passed; 195 tests passed.
- MediaCrawler maintained tests: 530 passed and 3 platform-specific tests skipped.
- React used the project-pinned Node 24 and an ephemeral pnpm 11.14.0 selection; frozen install,
  Prettier, Oxlint, TypeScript, 97 tests and the production build passed.

## Real Xiaohongshu search acceptance

Date: 2026-08-26 (Asia/Shanghai)

- The product reused the already approved persistent Google Chrome connection after a competing
  automation client was released.
- Two completed five-term runs stored 12 and 14 results. Eight identities overlapped; the second run
  classified every overlap as repeated, preserved `first_seen_at`, and advanced `last_seen_at`.
- Every persisted identity URL used the exact query-free
  `https://www.xiaohongshu.com/explore/<platform_content_id>` form and correlated with a lowercase
  24-hex content ID.
- A sanitized live page contained safe notes, known auxiliary cards and otherwise-valid untitled
  cards. The adapter retained safe results, ignored only the narrow untitled/auxiliary shapes and
  did not synthesize titles.

## Real open-original acceptance

- Directly navigating a stored query-free identity URL produced Xiaohongshu business error 300031,
  proving that the stable identity URL is not a reliable user-facing link.
- The approved no-body open endpoint then performed one first-page lookup for the first stored
  matched term. A sanitized correction gate proved the exact target and bounded token were present
  while the response omitted a source field; the worker-owned operation therefore derives the fixed
  `pc_search` channel and does not trust response input for it.
- After that correction, the endpoint returned only `opened`. The worker proved the exact target ID
  before handoff, and FastAPI shutdown released the CDP transport without closing the handed-off
  Chrome tab.
- Post-release checks found an exact official explore path, matching canonical and Open Graph paths,
  a fully loaded visible note container/title/media, and no unavailable or challenge marker.
- SQLite schema, content, run-term and monitoring-rule-term scans each found zero xsec matches. The
  API response contained only the fixed outcome. No destination, term, token, author identity, raw
  response or raw page content is retained in this evidence.

## Independent review corrections

- Final-page success now requires the exact target in Xiaohongshu's initial note-detail state at
  navigation time; arbitrary non-empty page content cannot prove `opened`.
- Business error 300031 is trusted only on an exact official Xiaohongshu HTTPS destination without
  credentials, explicit port or fragment.
- A malformed challenge probe maps to `structure_changed` instead of escaping as an internal error.
- The search response is not required or allowed to control `xsec_source`; a single private
  worker-owned constant derives the fixed search channel, while the exact target and bounded token
  remain fail-closed.
