# Homepage Workbench Technical Design

## 1. Scope and Architecture

This is one cross-layer feature because the read contract and its only consumer must agree on status semantics, navigation identities, refresh behavior, and empty/error states. Splitting backend and frontend into child tasks would create an unnecessary contract hand-off for one atomic deliverable.

The design adds a read-only persistent projection:

```text
SQLite domain tables -- one read transaction --> WorkbenchRepository
                                              --> WorkbenchService
                                              --> GET /api/v1/workbench

existing in-memory PlatformConnectionService --> GET /api/v1/platform-connections

React Workbench route --> two independent TanStack queries
                      --> merge known/unknown/attention state
                      --> read-only links to owning routes
```

The existing shell health reducer remains authoritative for whether the local API is reachable. Platform readiness remains on its existing endpoint and query key. The new endpoint owns only persisted collection/schedule/analysis/report projection.

## 2. Backend Boundaries

Add narrowly owned modules:

- `schemas/workbench.py`: strict public response models and status literals.
- `repositories/workbench.py`: one operation-owned SQLite connection and explicit read transaction for a consistent persistent snapshot.
- `services/workbench.py`: clock injection, projection validation, and sanitized `workbench_storage_unavailable` translation.
- `api/v1/workbench.py`: `GET /workbench`, no-store response, and documented 503 envelope.
- Register one `WorkbenchService` during application lifespan and expose it through the standard dependency boundary.

No schema migration is needed. The repository reads existing v14 tables only. It binds query values, uses deterministic ordering, validates stored status/JSON, and closes its connection after each request.

### 2.1 Public response

`GET /api/v1/workbench` returns one exact `WorkbenchSnapshot`:

```text
observed_at: UTC timestamp
attention: ordered persistent WorkbenchAttention[]
activity:
  collection: active/paused batch summary or null
  initial_analysis: active job summary or null
  report: active report summary or null
next_collection: globally earliest enabled+available future schedule or null
latest_report: newest readable completed/empty report outcome or null
```

Attention items contain stable typed evidence rather than backend-authored navigation URLs:

```text
kind: collection_schedule | collection_batch | initial_analysis | report
severity: action_required | warning | error
status/reason: bounded domain literal
resource_id: positive integer
owner label: bounded rule/stage label already safe for product display
occurred_at: UTC timestamp
unsuccessful_count: optional nonnegative count where applicable
```

The frontend maps kinds and IDs to existing routes. It owns Chinese presentation copy; the API never returns raw SQL, exception, prompt, source content, provider output, or credentials.

### 2.2 Latest-state rules

The persistent projection applies these rules across all rows, not a history page:

| Owner | Current/attention rule | Healthy supersession |
| --- | --- | --- |
| Enabled schedule | Current rule dependency invalid, or latest occurrence for the current revision is skipped/missed/interrupted | Schedule disabled intentionally, a new revision, or a later healthy dispatch |
| Collection chain | Active/paused batch plus the latest terminal batch for each live monitoring-rule owner; paused, completed-with-failures, and internal-error are attention | A later completed batch for the same owner |
| Initial analysis | Active global job for progress; latest terminal job is attention when configuration-blocked/interrupted or when settled unsuccessful members remain | A later normally completed job with full successful coverage |
| Report | Active global report for progress; latest terminal report is attention when failed/interrupted/configuration-blocked | A later completed or truthful empty report |

Cancelled jobs/batches and intentionally disabled schedules are excluded from attention. Deleted owners remain in existing history but do not create an immortal homepage issue. Empty reports are successful truthful outcomes, not failures.

Platform attention is derived independently from the current catalog:

- `action_required`, `disconnected`, and `failed` are attention;
- `checking` is activity;
- `not_checked` is unknown readiness and prevents an “all normal” claim without being styled as a failure;
- `coming_soon` remains non-actionable and is excluded from both readiness numerator and denominator.

### 2.3 Latest readable report

Select the newest report whose status is `completed` or `empty`.

- `completed`: validate the root node and return its `ReportDocument.overview` or `OverviewDocument.overview`, finish time, report ID, and coverage.
- `empty`: return the exact empty reason and coverage with no fabricated overview.
- Failed/draft sections are never returned as the main report.
- A newer failed report can coexist with the prior readable result through the attention projection.

Reuse the existing strict topic-report document models when decoding stored root output. Corrupt report graph/output fails the snapshot with the constant storage-unavailable error rather than presenting an older row as current.

## 3. Frontend Data Ownership

Add:

- `lib/api/workbench.ts`: query key, Zod decoder, abortable GET boundary, exact 503 handling, and status helpers.
- `hooks/use-workbench.ts`: one shared query with no mutation and adaptive polling.
- `routes/workbench.tsx`: route-level composition and mapping from typed resource identities to links.
- `routes/workbench.test.tsx`: behavior tests with the narrow API functions mocked.

The page also consumes the existing platform-connections query. Extend its hook with an optional idle polling interval without changing the Platform Accounts default behavior.

Polling policy:

- persistent snapshot: 5 seconds while any activity exists, otherwise 30 seconds;
- platform catalog: existing 1-second polling while checking/action-required plus a 30-second idle interval only for the homepage observer;
- keep last validated data if a later refetch fails, show `observed_at`, and label the snapshot stale;
- `retry: false`; explicit Refresh refetches both independent queries and health uses the shell's existing retry owner.

TanStack Query owns all server state. No local copy, client store, browser storage, or URL filter is introduced.

## 4. Presentation Design

Subject: a Shenzhen subdistrict operator checking a local public-opinion pipeline. Single job: determine current duty state, then read the newest trustworthy summary.

Use the existing civic visual system; do not add fonts, colors, animation libraries, or a new generic dashboard kit.

```text
+-------------------------------------------------------------+
| Duty signal · Normal / N items need attention · updated ... |
+-------------------------------------------------------------+
| Conditional attention list (full width, only when needed)   |
+--------------------------------------+----------------------+
| Latest readable report              | Collection stage     |
| main overview prose                  | Analysis stage       |
| finish time + coverage + read link   | Report stage         |
|                                      | -------------------- |
|                                      | Next collection      |
|                                      | Platform readiness   |
+--------------------------------------+----------------------+
```

The signature element is a quiet three-stage civic signal rail—collection, initial understanding, report—echoing the existing connected-node language used by the platform page. Only the currently active stage may pulse, using existing motion rules; everything else remains static. This is functional state encoding, not decoration.

At narrow width, order is duty signal, attention, latest report, activity rail. The report overview may be visually clamped in the card but remains valid text and always has a clearly named “Read full report” link. Do not introduce KPI tiles, charts, raw-result previews, glass effects, or a second page title.

## 5. Loading, Error, Empty, and Stale States

- Initial loading: stable skeleton/placeholder geometry for the report and rail; never render zeros.
- Fully empty: explain that no readable report or schedule exists and link to the owning configuration/history pages.
- Independent platform failure: persistent snapshot still renders; readiness is “unavailable,” not zero.
- Persistent snapshot failure: platform readiness can still render; report/activity area has one retryable read error.
- Cached refetch failure: retain prior content, show last successful observation time and an explicit stale/update-failed message.
- Backend unavailable: reuse shell health guidance and present the workbench read error without duplicating technical details.
- Protocol-invalid response: same bounded invalid-response treatment as other frontend API boundaries.

Use `role="alert"` for actual read failures and `role="status"`/polite announcements for loading or state transitions. Status labels include text/icons, never color alone.

## 6. Compatibility, Rollout, and Rollback

- Additive GET endpoint only; existing endpoints and saved rows are unchanged.
- No migration, dependency, worker, browser, AI, schedule, or prompt behavior changes.
- Existing route remains `/`; navigation and shell contracts stay stable.
- Rollback removes the endpoint registration and restores `Workbench` to `null`; persisted product data is unaffected.
- The implementation must preserve unrelated dirty-worktree edits and must not rewrite active task artifacts outside this task.

## 7. Validation Strategy

Backend tests use temporary on-disk SQLite and fake clocks/services. Prove global next-due ordering, natural-owner supersession, cancellation/disable exclusions, active progress, completed/empty latest report projection, newer-failure coexistence, strict corrupt-output failure, no-store/error envelope, and zero writes/browser/model calls on repeated GET.

Frontend tests prove loading, fully empty, normal, unknown readiness, each attention category, healthy supersession fixture, active progress, latest completed/empty report, newer failure plus older readable report, partial errors, stale cached data, retry, exact deep links, and absence of mutations/KPIs/raw results/manual handling copy.

Run the full local backend and frontend gates. Then use a temporary database/fake services on loopback for browser QA at desktop and narrow widths, verifying keyboard focus, error announcements, no overflow, no console errors, and zero mutations caused by route entry/polling.

