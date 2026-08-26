# Verification

## Automated quality gates

- MediaCrawler focused product-search suite: 68 passed.
- MediaCrawler full non-Redis suite: 462 passed.
- FastAPI Ruff check and format check: passed.
- FastAPI test suite: 155 passed.
- React format, ESLint, TypeScript and production build: passed.
- React test suite: 77 passed.
- Responsive smoke at 375, 768, 1024 and 1440 CSS pixels: no horizontal overflow; the Kuaishou
  option, history and detail presentation rendered without console warnings or errors.
- SQLite migration reached version 4, preserved existing Toutiao and Weibo data, and passed
  `PRAGMA foreign_key_check`.
- Centaurus Linux verification: MediaCrawler 459 passed and 3 platform-specific tests skipped;
  FastAPI 155 passed; React 77 passed and the production build completed. The remote environment
  required the official Python package index after its configured mirror returned HTTP 403, and
  mise installed the project-pinned pnpm 11.14.0 without changing repository files.

## Real Kuaishou acceptance

Date: 2026-08-26 (Asia/Shanghai)

- The application reused the already approved persistent Google Chrome connection; no challenge or
  login wall was encountered.
- First run: `completed_with_results`, five terms, 15 new results, 0 repeated results.
- Immediate same-rule rerun: `completed_with_results`, five terms, 15 results. Kuaishou's default
  real-time ordering changed between requests, so 3 overlapping works were classified as repeated
  and 12 newly returned works were classified as new.
- Each overlapping work preserved its original `first_seen_at` and advanced `last_seen_at` on the
  second run.
- All observed work links matched the exact canonical form
  `https://www.kuaishou.com/short-video/<platform_content_id>`.
- Runtime SQLite remained at version 4; foreign-key verification returned no violations. Existing
  Toutiao and Weibo content remained present.
- A mode-0600 runtime backup was created before live writes. Runtime data and the backup remain
  ignored user-owned state and are not included in commits.

## Review correction

Final review found that Kuaishou URL validation initially accepted some syntactically equivalent but
non-canonical URL variants. The protocol now requires exact string equality with the canonical URL,
and regression tests reject explicit ports, hostname case variants, queries, fragments and mismatched
content IDs.
