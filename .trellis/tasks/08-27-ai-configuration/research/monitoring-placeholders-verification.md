# Monitoring-Rule Placeholder Copy — 2026-08-27

## Change

Only two product literals changed in `frontend/src/routes/monitoring-rules.tsx`:

- Monitoring objects: `对象 1\n对象 2\n对象 3`.
- Optional issue keywords: `关键词 1\n关键词 2\n关键词 3`.

One colocated regression test verifies exact three-line placeholders, empty actual values,
zero generated queries and no create/update call. Existing fixtures, labels, styles, defaults,
validation and query/save behavior are unchanged. Prior AI-mask work is preserved.

## Main-Session Verification

- Scoped local Prettier check/write left both edited files unchanged.
- Synchronized source and task notes one-way to Centaurus, without runtime data or credentials.
- Complete frozen frontend gates passed under mise Node 24 / pnpm 11.14.0: install, formatting,
  lint (zero warnings/errors), typecheck, **166 tests / 10 files**, and production build.
  The monitoring-rule component suite now contains 23 tests.
- Opened an owned app tab and the empty New Rule dialog without typing or saving. Both placeholder
  attributes contain the exact expected newlines; both actual textarea values are empty; generated
  query count remains zero. Browser console: zero warnings/errors. Left the dialog available.
- No live rule mutation, search, AI configuration change or provider call was made.
- No additional code-spec contract is needed for this copy-only request. No commit/push/archive.

Independent source review is recorded in `monitoring-placeholders-check.md`; the reviewer did not
independently replay the main-session remote gates or browser smoke.
