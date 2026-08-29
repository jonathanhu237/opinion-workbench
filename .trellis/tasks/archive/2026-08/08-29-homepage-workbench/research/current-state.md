# Homepage Workbench Current-State Research

## Repository Evidence

- The stable route is already registered at `/` and `Workbench` currently returns `null` (`frontend/src/app/router.tsx`, `frontend/src/routes/workbench.tsx`). Existing application tests explicitly protect the empty route until a real feature replaces it.
- The shell owns page naming, health state, responsive navigation, focus transfer, and the maximum-width content frame (`frontend/src/app/shell.tsx`). The homepage should consume shell health instead of introducing a second health owner.
- Platform connection state is a complete catalog projection from `GET /api/v1/platform-connections`; it is in memory, resets on backend restart, and distinguishes `not_checked`, `checking`, `action_required`, `connected`, `disconnected`, and `failed` (`frontend/src/lib/api/platform-connections.ts`, backend platform-connection contract).
- Persisted collection, schedule, initial-analysis, and report history endpoints are paginated. Frontend composition of only their first pages cannot prove a global next due schedule or latest state for every natural owner.
- Only one collection batch can be active/paused. Initial-analysis jobs and report jobs expose strict active/terminal status and progress counts. Their GET/list paths do not start work.
- Schedule projections include next due time, current rule state, rollout availability, and latest occurrence, but the list is ID-ordered rather than globally ordered by due time.
- A readable report overview lives in the validated root report section. A report-list row alone contains status, coverage, and root-section identity but not the overview prose.
- Results and Analysis already supports deep links through `job` and `report` query parameters. Collection supports batch detail paths and schedule selection through the `schedule` query parameter.

## UX Research

- The local design-system search classified the product as a real-time operations/status dashboard. The useful guidance is current-source timestamps, visible stale state, keyboard access, and reduced-motion behavior.
- Its generic dark glassmorphism palette and Fira typography conflict with the established civic theme and were rejected.
- The focused alert-prioritization search returned no exact rule. A narrower verified match reinforced that error messages must be announced rather than represented only by color. The final hierarchy therefore follows approved product decisions plus the existing accessibility spec, not an invented database match.

## Architecture Conclusion

Add one read-only persistent workbench snapshot endpoint and keep platform connections as an independent existing query. The persistent endpoint can query all relevant tables without pagination, expose one observation timestamp, and validate the latest readable report overview. Independent queries let platform readiness remain visible if the persistent snapshot fails, and vice versa.

No migration, model/collector call, background job, or new package is required.

