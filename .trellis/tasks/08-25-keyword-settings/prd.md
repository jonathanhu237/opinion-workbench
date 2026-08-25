# 监控规则

## Goal

Give the single local operator one place to maintain reusable monitoring rules that define what the
system should search for. A later collection task can select an enabled rule without redefining its
search terms.

## Background

- Platform account connection is the completed upstream capability; monitoring-rule configuration
  is the next product step before collection-task configuration.
- The application is a local single-user React and FastAPI tool. SQLite is the selected persistence
  direction for product data.
- The backend currently has no application database dependency, schema, or migration convention.
  This task establishes the smallest SQLite boundary needed by the product.
- Earlier product discussion confirmed the initial geographic scope as Shenzhen Pingshan District,
  Longtian Subdistrict, with Longtian, Laokeng, Zhukeng, and Nanbu communities.

## Requirements

### Rule model and persistence

- A monitoring rule has a stable ID, a name, one or more ordered search terms, and an enabled state.
- Every term is an independent alternative: a later collector searches each term separately and
  merges and deduplicates results. The rule model has no Boolean-operator field.
- Terms are structurally uniform. The operator may enter a street, community, address, event, or
  any other search text without assigning a system-defined category.
- Persist rules in local SQLite behind a typed FastAPI API with stable ordering, normalization,
  validation, and product-safe error responses.
- Seed a fresh database exactly once with one enabled rule covering `龙田街道`, `龙田社区`,
  `老坑社区`, `竹坑社区`, and `南布社区`. Application restarts must not recreate a
  default rule that the operator later edits or deletes.
- Expose enabled rules through a stable read boundary for a later manual or scheduled collection
  task; this task does not invoke that boundary from MediaCrawler.

### User interface

- Add a real `监控规则` navigation destination and route using the existing React shell and
  shadcn/Base UI foundation.
- Show only persisted rules. Do not display fake counts, sample monitoring results, readiness cards,
  or other placeholder operational data.
- Let the operator create, edit, enable or disable, and delete rules.
- Let the operator paste multiple search terms, with one term per line, and provide clear Chinese
  feedback for invalid or duplicate input.
- Explain once in plain Chinese that every search term will be searched separately; do not show a
  redundant logic selector.
- Keep server resources in TanStack Query, editor state in React Hook Form with Zod, and runtime
  response validation at the frontend API boundary.
- Provide usable loading, empty, failure, retry, pending, success, and delete-confirmation states on
  desktop and mobile.

### Product boundaries

- Monitoring-rule maintenance works regardless of platform login state.
- No page action starts MediaCrawler, opens the browser, selects a platform, schedules work, or runs
  a collection.

## Acceptance Criteria

- [ ] Opening `监控规则` shows actual persisted rules in deterministic order and no invented
      operational data.
- [ ] A fresh database contains the one five-term default rule exactly once; reopening the database
      does not duplicate it, and deleting it is respected after restart.
- [ ] The operator can create a named rule, batch-enter terms, edit it, enable or disable it, and
      delete it; refreshing or restarting the application preserves every successful change.
- [ ] Blank names, empty term lists, whitespace-only terms, over-limit values, duplicate rule names,
      duplicate terms, unknown fields, and malformed payloads cannot create ambiguous data and
      receive stable Chinese feedback.
- [ ] Disabled rules remain visible and editable but are excluded from the enabled-rules read
      boundary intended for future collection tasks.
- [ ] Database failures never expose a filesystem path, SQL text, raw SQLite exception, or rule
      contents through the API or UI.
- [ ] The route works without a connected platform account and cannot launch a worker, browser, or
      collection action.
- [ ] Desktop and 375 px mobile flows remain keyboard-accessible, have no horizontal overflow, and
      expose loading/errors/status changes to assistive technology.
- [ ] Backend and frontend frozen quality gates pass with persistence, API-contract, validation,
      mutation, navigation, async-state, accessibility, and responsive regressions.

## Key Decisions

- The product-facing concept and page name is `监控规则`, not a flat keyword-settings list.
- A rule defines only what to search. Platform selection belongs to the later collection-task
  feature.
- All terms use implicit `或` semantics. `且` is intentionally unsupported in the MVP.
- The page is configuration-only; collection execution is a separate task.

## Out of Scope

- Platform selection, manual or scheduled collection, result storage, merging implementation,
  deduplication implementation, AI analysis, alerts, reports, and dashboards.
- Direct MediaCrawler integration from the monitoring-rule module.
- `且`, NOT, parentheses, nested Boolean expressions, regular expressions, scoring weights,
  AI-generated keyword expansion, synonyms, negative-word dictionaries, and semantic matching.
- Multi-user ownership, authentication, remote database hosting, cloud synchronization, database
  export/backup UI, or behavior for rules referenced by future persisted collection tasks.

## Technical Note

The existing MediaCrawler search loop already treats comma-separated terms as independent searches.
The future collection task may resolve an enabled rule and pass its ordered terms to that boundary,
but it will own platform selection, execution, merging, and deduplication.
