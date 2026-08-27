# Monitoring Rule Composition Design

Approved for implementation on 2026-08-27. Parent R5/R10/R13 and child Q1–Q6 govern scope.

## Boundary

Two ordered input lists -> local full-query preview -> explicit save -> backend validation/persistence -> derived effective `terms` -> existing explicit run/batch snapshot -> unchanged search/deduplication.

Extend existing monitoring-rule layers and React editor. No standalone rule engine, preview API, new crawler path or provider dependency. Source anchors are in `research/current-rule-boundary.md`.

## Storage and Compatibility

- Keep `monitoring_rules` and `monitoring_rule_terms` rows. The latter stores the monitoring-object group; old complete phrases remain valid objects unchanged. Do not infer phrase splits.
- Add ordered `monitoring_rule_issue_terms` with rule FK/`ON DELETE CASCADE`, value, normalized value and position, including per-rule normalized uniqueness. Empty rows for a rule mean no issue restriction. No duplicated materialized generated-query table.
- Use an additive migration after the actual current version (v8 at planning). Add the empty issue table/version atomically; preserve AI settings and all collection/history tables. Migration 1 remains the only default-rule seed owner.
- Repository records expose distinct `monitoring_objects` and `issue_keywords`. Create/replace both groups in one transaction; preserve stable ordering and sanitized errors. Avoid joining both one-to-many groups into a duplicated Cartesian rowset when reading aggregates.
- Generate effective queries at the service projection boundary. Keep `search_run_terms` and batch snapshots unchanged; edits to a current rule cannot affect old/queued batch children.
- Ship the local frontend/backend contract together. Update every in-repo writer and strict decoder; no permanent ambiguous legacy-write adapter. Existing user data is preserved. A stale client sending the old write shape must reload rather than silently changing group semantics.

## API and Pure Composition

Keep existing routes, HTTP statuses, strict Pydantic responses and constant error categories. Preserve current Annotated dependencies and synchronous SQLite endpoints; no blocking SQL in the event loop.

- POST: `{name, monitoring_objects, issue_keywords?, enabled?}`. Omitted issue list means `[]`; enabled keeps the current default.
- PUT: `{name, monitoring_objects, issue_keywords, enabled}` is full replacement; issue list is explicit even when empty.
- GET/save projection: `{id, name, monitoring_objects, issue_keywords, terms, enabled}`. `terms` is derived/read-only and continues serving current collectors. Reject client-supplied `terms` or mixed legacy/new fields.
- One pure backend composition helper serves validated create/replace and read projections. With empty issues, return trimmed objects unchanged. Otherwise combine `object + " " + issue` in object-major/input order, preserving embedded spaces/punctuation without parsing logical operators.
- Retain names of 1–80 Unicode code points, each input/effective query of 1–100 characters, 1–100 objects, 0–100 issues and 1–100 effective queries. Check the product count before building large combinations. Retain outer-trim/NFKC/casefold identity and duplicate rejection within each group; reject normalized generated collisions using the existing duplicate-term error category, without silently dropping entries.
- Reuse existing 422 semantic/duplicate, 409 name-conflict, 404 missing-rule and 503 storage contracts. Messages may identify the affected group without echoing full input. Backend validation remains authoritative for Unicode edge cases; frontend checks do not replace it.

## UI

Detected stack: React, RHF/Zod, TanStack Query and shadcn `base-nova` Base UI. Reuse existing Dialog/Field/Input/Textarea/Button/Badge and focus/dismissal behavior; no new dependency, palette, typography or global CSS is expected.

The page is a single operator's reusable-search editor. Its useful visual focus is the actual generated-query preview, not decorative status. Existing theme and user preferences override generic stylistic recommendations.

```text
规则名称
监控对象                    每行一个，必填
舆情关键词（选填）          留空时只搜索监控对象
生成的搜索词 · 共 N 个       full queries in execution order
[超过 20 个时提示需拆分后采集]
取消                        保存
```

- Preserve the dialog's viewport/scroll constraints, labeled fields and footer access. Keep the preview readable and bounded, with all content keyboard-accessible and no horizontal overflow.
- A small pure TypeScript helper generates preview from watched form values without requests. For valid input, preview/order must match backend output; test shared multi-word/Unicode/length examples. Existing server normalization is the final gate for rejected Unicode collisions. Do not introduce a keystroke preview endpoint or divergent payload transformations.
- Show effective count. Warn above 20 while allowing valid 21–100-query rules to save, matching current behavior; the collection page retains its existing rejection. More than 100 or excessive combined length blocks save. No hidden truncation or extra searches.
- Edit initializes from original groups, not generated `terms`. Every full PUT, including enable/disable, preserves both groups. List content distinguishes groups and effective count; collection selection continues counting `terms.length`.
- Use FieldLabel/FieldDescription/FieldError with associated errors, current pending disabling and cache updates. Do not announce the entire preview on every keystroke or add a new dashboard.

The targeted ui-ux-pro-max shadcn search supports schema validation and FieldError; its TanStack Form result is not applicable to this RHF project. `frontend-design` contributes content-first restraint and continuity, not a visual redesign.

## Verification and Rollback

Test migration/reopen/atomic failures, strict shapes, order/limits/collisions, group-preserving toggle, collector snapshots and zero execution during CRUD/preview. UI checks cover desktop/narrow widths, keyboard, empty optional input, long preview and error/pending states; no live platform/model request is needed.

Work/Git stay local; sync source/task/spec files only to Centaurus and run gates there. Forward isolated services using a temporary test database; never sync user runtime or credentials. No production database migration/restart during planning.

Storage is additive, but older binaries reject newer schemas. Binary downgrade requires a verified pre-migration backup; do not drop tables or delete user data as a shortcut.
