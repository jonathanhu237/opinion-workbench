# Homepage Workbench

## Goal

Turn the deliberately empty application home into a read-only duty dashboard for the local single-user public-opinion workflow. On entry, the operator must be able to tell whether the system needs intervention, what work is currently running, when the next scheduled collection will occur, and what the latest readable report says.

The homepage is not an analytics dashboard or an incident-management system. Its product value is fast orientation and precise navigation into the existing collection, analysis, report, schedule, and platform-account workflows.

## Background and Confirmed Facts

- `/` is already the stable `Workbench` route and first navigation item, but `frontend/src/routes/workbench.tsx` intentionally renders no content. The earlier product decision was to keep it empty until the underlying workflows matured.
- The product is a local-first, single-machine, single-user desktop application. Existing destinations are Platform Accounts, Monitoring Rules, Collection Tasks, Results and Analysis, and AI Configuration.
- Existing persisted state can describe collection batches and schedules, independent initial-analysis jobs, automatic text reports, and report coverage. Platform connection state is lifespan-owned in memory and is already exposed through its own read endpoint.
- Page entry, GET requests, polling, prompt saves, and history reads must never start collection, media acquisition, initial analysis, or report generation.
- The user approved the following product decisions on 2026-08-29:
  - the homepage is a duty dashboard driven by items that need attention;
  - the product only discovers and summarizes public-opinion material and does not track human follow-up or handling progress;
  - there is no “today’s discoveries” metric or equivalent calendar-day KPI;
  - the main content is the latest readable report summary, while raw collected results remain in Results and Analysis;
  - homepage actions only navigate to an owning page and never mutate state or incur model usage;
  - the layout is: overall duty state, conditional attention list, latest report as the main region, and a secondary activity rail for running work, next collection, and platform readiness;
  - an old issue leaves the homepage automatically when a newer healthy state for the same natural owner supersedes it; user cancellation and intentional schedule disablement are not issues.
- Current AI output distinguishes topic relevance, irrelevance, uncertainty, and technical state. It does not provide a product-wide risk score. The homepage must not rename relevance as risk or as an unhandled incident.

## Requirements

- **R1 — Duty-first hierarchy.** The first screen answers whether anything currently needs intervention. Latest report content is the main reading region after attention; running work, next collection, and platform readiness are secondary.
- **R2 — Current attention semantics.** Attention items are derived only from current blockers or the latest unhealthy outcome for a natural owner such as a platform, enabled schedule, monitoring-rule collection chain, global initial-analysis pipeline, or global report pipeline. A newer healthy outcome for that owner clears the older item. Intentionally cancelled work, disabled schedules, and empty reports are not errors.
- **R3 — Truthful readiness.** A platform whose state has not been checked is unknown, not healthy. The page must not claim “all normal” when any required section is unknown, stale, loading, or unavailable.
- **R4 — Latest readable report.** The main content shows the newest readable terminal report outcome: a completed report overview or a truthful empty-report result. A newer failed report appears in attention while the last readable report remains available. Active report progress is shown separately. Raw collected results and incomplete draft sections are not substituted for a readable report.
- **R5 — No discovery KPI.** The first version has no “today,” rolling-24-hour, trend, comparison, or raw-result feed. Historical discovery remains available in Results and Analysis.
- **R6 — No case-management state.** Do not add follow-up, handled, read/unread, assignee, disposition, or manual incident lifecycle fields. Do not equate AI relevance with risk, urgency, or a human task.
- **R7 — Read-only navigation.** Homepage controls may refresh reads or navigate to Platform Accounts, a collection batch, a collection schedule, an analysis job, or a report. Login checks, retry, cancel, reanalysis, schedule enable/disable, and every cost-bearing action remain on their owning pages.
- **R8 — Global, pagination-independent summary.** Next collection, active work, latest owner state, and latest readable report must be computed across the complete persisted dataset rather than inferred from the first page of existing history endpoints.
- **R9 — No hidden work.** Opening, refreshing, polling, reconnecting, or recovering the homepage cache performs no write and starts no browser, collector, enrichment, analysis, or report operation.
- **R10 — Explicit data state.** Loading, empty, backend unavailable, section unavailable, stale cached data, and protocol-invalid responses are visibly distinct. A failed refresh may retain previously validated data only when it is labelled with its last successful observation time.
- **R11 — Existing visual system.** Preserve the civic teal palette, Songti display role, PingFang/Microsoft YaHei body role, existing spacing/radius tokens, Lucide functional icons, and the established application shell. Do not apply the dark glassmorphism suggestion returned by the generic dashboard search.
- **R12 — Accessible responsive presentation.** The desktop-first two-column layout collapses without horizontal overflow, retains the existing 48rem navigation boundary, uses semantic headings and links, announces real errors, keeps visible keyboard focus, and respects reduced motion. Status is never communicated by color alone.

## Acceptance Criteria

- [ ] **AC01** With no attention items and every section successfully known, the page reports a normal duty state and keeps the attention region compact; with one or more attention items, that region appears before the report and states the item type, owner, time/state evidence, and destination (R1–R3).
- [ ] **AC02** A current platform action requirement, enabled-schedule issue, paused/failed latest collection chain, unsuccessful latest initial-analysis outcome, or failed/interrupted/configuration-blocked latest report is represented by truthful cause-specific copy and a link to its owning page (R2, R7).
- [ ] **AC03** A newer healthy state for the same natural owner removes the older homepage issue, while the historical failure remains visible on its existing detail/history page. User cancellation and an intentionally disabled schedule never create an attention item (R2).
- [ ] **AC04** Unknown platform state, missing section data, stale cached data, and backend failure cannot produce an “all normal” claim or a fabricated zero count (R3, R10).
- [ ] **AC05** The main region shows the latest readable completed report overview and finish time, or the latest truthful empty-report outcome. A newer failed report is surfaced separately without hiding the last readable report; a running report exposes real progress (R4).
- [ ] **AC06** The homepage contains no daily/rolling discovery counters, KPI grid, trend chart, raw-result list, risk score, or manual handling state (R5, R6).
- [ ] **AC07** Every business control on the homepage is a GET/read refresh or a navigation link. Repeated entry, polling, focus refetch, error retry, and reload create no collection, analysis, report, media, platform-attempt, or schedule mutation (R7, R9).
- [ ] **AC08** The next enabled and available schedule is the true global minimum future due time, and active/latest statuses are not limited by history-page pagination (R8).
- [ ] **AC09** Loading, fully empty, partially unavailable, completely unavailable, stale, active, attention, readable-report, and empty-report states all have tested visible behavior (R10).
- [ ] **AC10** At desktop width, the latest report is the dominant region and the activity rail is secondary. At narrow widths the regions stack in priority order, links remain keyboard operable, focus is visible, error text is announced, and no content overflows horizontally (R11, R12).

## Out of Scope

- Human follow-up, handled/read state, assignment, notes, or incident case management.
- Risk scoring, sentiment scoring, verified-incident counts, or treating relevance as risk.
- Daily discovery metrics, rolling metrics, charts, comparisons, raw-result feeds, or a configurable dashboard.
- External notifications through WeCom, email, SMS, mobile applications, or mobile push.
- Mutating shortcuts, task creation, retry, cancellation, login checks, prompt editing, or schedule controls on the homepage.
- Database migrations, new dependencies, collector/model changes, or live collection/AI work as part of homepage reads.

