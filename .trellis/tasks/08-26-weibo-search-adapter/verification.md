# Verification Evidence

## Automated gates

- MediaCrawler focused product-search suite: 42 passed.
- MediaCrawler full non-Redis suite: 448 passed; one pre-existing SQLAlchemy deprecation warning.
- FastAPI Ruff check and format check: passed.
- FastAPI suite: 149 passed.
- React format, lint, typecheck, and production build: passed.
- React suite: 73 passed.
- SQLite version 2 to 3 migration: existing Toutiao runs, contents, identities, relationships,
  timestamps, foreign keys, and autoincrement behavior preserved.
- Loopback UI at 375, 768, 1024, and 1440 CSS pixels: no horizontal overflow; platform selection,
  history/detail presentation, Shadcn Select behavior, and browser console passed.

## Real borrowed-browser acceptance

- Date: 2026-08-26.
- An existing Chrome session was explicitly approved for the persistent worker.
- First Weibo run: five terms, limit three per term, `completed_with_results`, 15 new results.
- Immediate identical second run: `completed_with_results`, 14 repeated results and one newly
  surfaced result. Dynamic real-time ranking accounts for the one changed result.
- All 14 overlapping rows retained their original `first_seen_at`, advanced `last_seen_at`, and were
  recorded as `repeated` in the second run.
- SQLite foreign-key check returned no violations.
- The persistent worker reused the approved connection for the repeated run without another
  permission prompt.
- A pre-existing unrelated browser tab retained the same provider identity, title, and URL after
  both runs.
- No Cookie, authentication header, browser-profile path, raw response, raw exception, search term
  value beyond the public rule definition, or unmasked creator identity is recorded here.
