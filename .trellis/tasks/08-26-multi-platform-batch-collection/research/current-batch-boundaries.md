# Current multi-platform batch boundaries

## Repository evidence

- `frontend/src/routes/collection-runs.tsx` owns a React Hook Form whose `platform` value is one literal platform. The Shadcn Select submits exactly one `startSearchRun` request and immediately navigates to that run detail.
- `frontend/src/lib/api/search-runs.ts` validates one scalar `platform` at the HTTP boundary and treats every run as an independently addressable durable resource.
- `backend/src/longtian_api/schemas/search_runs.py` exposes a strict single-platform `SearchRunCreate`; the existing request must stay compatible.
- `backend/src/longtian_api/services/search_runs.py` admits only one current background run, claims the shared `BrowserOperationCoordinator`, and releases it when the run becomes terminal. The worker already serializes one platform request and must not be changed into a concurrent multi-platform request.
- `backend/src/longtian_api/repositories/search_runs.py` and database schema version 6 store immutable single-platform run snapshots and globally deduplicate by `(platform, platform_content_id)`. A batch must compose these runs rather than weakening that identity.
- `.trellis/spec/backend/product-search-guidelines.md` fixes the supported platform catalog and requires exact platform propagation, durable runs, one browser operation, truthful terminal states, narrow cancellation, and credential-free product boundaries.

## Product decisions confirmed with the user

- One submission may select 1–5 platforms and defaults to all five.
- Selected platforms execute in the fixed product catalog order and never in parallel.
- Each platform remains an independent run with its own progress, results and failure reason.
- Submission navigates to a batch overview; platform rows link to the existing run detail.
- Ordinary failures continue to later platforms.
- A manual challenge pauses the batch. After the operator resolves it, continuing creates a new attempt for that same platform before later platforms run.
- Batch queue/progress is durable across refresh and application restart.

## UI guidance evidence

- The local UI/UX guidance matched multi-step progress indicators: the interface must show concrete step progress instead of leaving a long-running batch without feedback.
- The Shadcn stack guidance matched semantic components, preserved focus management, and explicit visible labels. With only five fixed platforms, a visible checkbox group is clearer than a custom hidden multiselect widget.
- The existing civic semantic tokens, typography and platform SVG assets remain authoritative. The page-specific signature is an ordered platform execution rail; it encodes real order and state rather than adding decorative dashboard metrics.

## Consequence

The minimum reliable solution is a durable FastAPI/SQLite batch aggregate that schedules existing single-platform runs. A React-only queue would lose pending work on refresh and could not provide an authoritative continue/cancel contract. A single run containing multiple platforms would blur terminal states and break the current deduplication and detail assumptions.
