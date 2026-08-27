# Existing Rule Boundary — 2026-08-27

Read-only local source inspection; no runtime database, credentials, browser session or provider request accessed.

- `backend/src/longtian_api/schemas/monitoring_rules.py`: strict flat request/read contracts; extend input groups and retain explicit projections.
- `backend/src/longtian_api/services/monitoring_rules.py:154`: display phrases preserve internal spaces; duplicate identity is trim/NFKC/casefold. `list_enabled()` supplies collector-facing values.
- `backend/src/longtian_api/repositories/monitoring_rules.py`: ordered aggregates and atomic replacement; avoid a naïve join of two one-to-many child groups that duplicates rows.
- `backend/src/longtian_api/database.py`: current v8 includes AI settings; v1 owns original terms and the one-time seed. Retain term rows as object input and add an empty optional issue table.
- `backend/src/longtian_api/services/search_runs.py:47` and `services/search_batches.py:170`: 20 effective terms per platform, with frozen run/batch terms independent of later rule edits.
- `frontend/src/lib/api/monitoring-rules.ts`: strict Zod projections and exact HTTP/code errors; update writers/decoders/fixtures together.
- `frontend/src/routes/monitoring-rules.tsx:60`: newline-only input splitting. Edit and the full-replacement enabled toggle near line 357 must use original groups rather than compiled terms.
- `frontend/src/routes/collection-runs.tsx:265`: selector count uses effective `terms.length`; start rejects above 20.

Old flat phrases as objects with empty issues are lossless. Derived read-only `terms` preserves collector/worker wire semantics. Persist source groups, not only flattened preview strings. No new browser/model client, shared dictionary, preview service or design system is needed.

React/RHF/Zod and shadcn `base-nova` Base UI are confirmed in package.json/components.json. Targeted ui-ux-pro-max `form validation textarea --stack shadcn` returned applicable schema-validator/FieldError guidance; TanStack Form guidance is inapplicable. Preserve existing user-approved theme and emphasize the functional generated-query preview only.
