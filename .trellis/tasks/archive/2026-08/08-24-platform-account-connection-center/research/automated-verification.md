# Automated verification

Date: 2026-08-24 (Asia/Shanghai)

## Backend

- `uv sync --frozen --group dev`: passed.
- Ruff check and format check: passed.
- Pytest after final protocol-transition tightening: `35 passed`.
- Import/OpenAPI smoke: passed; both platform-connection routes are present.

## Frontend

- Runtime: mise Node 24, pnpm 11.14.0.
- Frozen install, Prettier write/check, Oxlint, TypeScript: passed.
- Vitest after the administration-shell correction: `19 passed`.
- Vite production build: passed.
- Loopback browser smoke after the administration-shell correction: desktop workbench/platform
  routes and 390 px narrow layouts had no horizontal overflow; future modules remained disabled,
  the mobile navigation sheet restored focus after Escape, and console warnings/errors were `0`.

## MediaCrawler derivative

- Focused authentication/CDP/Weibo suite after the macOS LaunchServices regression fix:
  `36 passed`.
- Maintained non-Redis `tests/` suite after the final regression addition: `231 passed`.
- Python compileall, scoped pre-commit hooks for changed files, secret-literal scan, and
  `git diff --check`: passed.
- Full repository pytest result after the final regression addition: `240 passed`, `8 skipped`,
  `6 failed`, `4 subtests passed`.
  All six failures are unchanged integration tests that require Redis at `127.0.0.1:6379`:
  three `TestIpPool` cases and three `TestRedisCache` cases. Redis was not started because it is
  outside this authentication-only task.

## Cross-layer

- Exact five-platform GET payload: passed.
- Safe unknown-platform 404 envelope: passed.
- POST/poll path exercised through React against loopback FastAPI.
- First real attempt exercised the browser-approval timeout path; the second reached `connected`.
- API, UI, child protocol, and evidence contain no credential or QR payload fields.
