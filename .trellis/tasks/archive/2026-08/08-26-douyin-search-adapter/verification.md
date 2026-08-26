# Verification

## Automated quality gates

- MediaCrawler focused Douyin/product-search suite: 34 passed.
- MediaCrawler suite excluding the two Redis-dependent integration files: 491 passed and 8 skipped.
- MediaCrawler full suite: 493 passed and 8 skipped; only 6 existing Redis/proxy integration cases
  failed because no Redis service was available at local port 6379.
- FastAPI Ruff check and format check: passed.
- FastAPI test suite: 162 passed.
- React frozen install, format, ESLint, TypeScript and production build: passed; the React test suite
  reported 81 passed.
- Responsive smoke at 375, 768, 1024 and 1440 CSS pixels: no horizontal overflow; the Douyin
  option, history and detail presentation rendered without console warnings or errors.
- SQLite migration reached version 5, preserved all existing Toutiao, Weibo and Kuaishou run and
  content counts, and passed `PRAGMA foreign_key_check`.
- Centaurus Linux verification: FastAPI 162 passed; React 81 passed with clean formatting, lint,
  TypeScript and production build; MediaCrawler 488 passed and 11 platform-specific tests skipped.

## Real Douyin acceptance

Date: 2026-08-26 (Asia/Shanghai)

- The application reused the already approved persistent Google Chrome connection; no challenge or
  login wall was encountered.
- First run: `completed_with_results`, five terms, 9 new results, 0 repeated results.
- An immediate second run received a recognized successful but empty platform result and was stored
  truthfully as `completed_empty`; it created no content or duplicate observations.
- A following same-rule run: `completed_with_results`, five terms, 6 results. Douyin's default
  general-search ordering changed between requests, so 3 overlapping works were classified as
  repeated and 3 newly returned works were classified as new.
- Each overlapping work preserved its original `first_seen_at` and advanced `last_seen_at` on the
  later run.
- All observed links matched the exact canonical form
  `https://www.douyin.com/video/<platform_content_id>`, and every content ID was numeric.
- The React history showed all three truthful outcomes, while the successful detail view rendered
  the 3 new and 3 repeated works with six safe original links.
- Runtime SQLite remained at version 5; foreign-key verification returned no violations. Existing
  Toutiao, Weibo and Kuaishou data remained present.
- A mode-0600 runtime backup was created before migration and live writes. Runtime data and the
  backup remain ignored user-owned state and are not included in commits.

## Review corrections

Independent review found and corrected three boundary defects before live acceptance:

- relative login/challenge redirects are resolved against the official Douyin origin before outcome
  classification;
- an exact raw `blocked` response maps to platform blocking instead of protocol drift;
- a full page without the next `extra.logid` stops as `structure_changed` before any second request.

Regression tests cover all three cases.
