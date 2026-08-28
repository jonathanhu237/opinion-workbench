# Scheduled Collection: Execution Boundaries

Read-only source inspection on 2026-08-28 against `00e6973`. The user approved
the scheduling policy below after clarification with hourly examples. This is
a planning decision, not product code or a running schedule.

## Existing Constraints

- `backend/src/longtian_api/services/browser_operations.py:21` owns one atomic
  browser-operation lease shared by platform connection, individual collection,
  batch collection, result opening and media enrichment. Scheduling cannot
  bypass this resource boundary.
- `backend/src/longtian_api/services/search_batches.py:216` refuses a new batch
  while another batch/browser operation owns admission. It currently does not
  create a durable queue of future periodic occurrences.
- `backend/src/longtian_api/services/search_batches.py:167` restores active/paused
  ownership on startup without launching browser work. At `:533`, manual-action
  pause deliberately preserves ownership. A due timer must not auto-continue a
  paused verification flow, steal its browser or silently discard its checkpoint.
- `backend/src/longtian_api/services/search_batches.py:189` checks that the
  selected monitoring rule still exists and is enabled, then freezes its terms
  and platform selection when creating the batch. A scheduled execution must
  retain the same checks/provenance rather than read mutable rules mid-run.
- `backend/src/longtian_api/main.py:110` restores batch ownership before serving
  requests, and shutdown drains summary/enrichment/AI/batch/search/browser owners.
  A new scheduler must integrate with that lifecycle without creating a second
  unrelated browser launcher or bypassing settled shutdown.
- Stage-one content understanding also needs the existing media/browser owner.
  Collection completion must be durably recorded and release ownership before
  its automatic follow-up can acquire media. Scheduling and AI processing remain
  separate operations even when one creates the other's pending work.

## Approved MVP Policy

- A schedule references a monitoring rule and platform selection and uses a
  user-configurable fixed minute/hour interval.
- Admit at most one execution when due. If the previous execution or shared
  browser resource is still busy, record the skipped occurrence/reason and
  advance to the next future due time; do not accumulate unbounded catch-up jobs.
- The backend and usable browser session must be available to execute collection.
  Do not replay every overdue occurrence after downtime. Resume the future
  schedule; preserve enough metadata to explain the missed interval without
  fabricating successful collections while the application was offline.
- Preserve existing challenge/manual-action pauses. No automatic attempt to
  solve verification, steal the paused browser, or continue a paused checkpoint.
- Surface disabled/deleted rules, unavailable browser, skipped due work and
  actual run outcomes distinctly. These are not successful empty collections.
- Missed scheduling occurrences are distinct from already-admitted collection
  or AI work. The policy does not delete saved results, completed
  summaries, pending source provenance or explicit manual recovery state.

Trade-off: avoiding catch-up bursts keeps browser use and repeated collection
bounded, but missed collection rounds are not made up; later collection cannot
guarantee complete coverage of the missed period. Exact interval bounds,
clock handling, persistence/idempotency and arbitration belong to design.
This policy does not define automatic retry
of failed paid AI attempts or historical reprocessing.

## Planned Acceptance Checks

- Consecutive due checks/restarts cannot create duplicate runs for one occurrence.
- A still-running collection, enrichment operation or manual pause is never
  overlapped by a new scheduled browser action.
- Multiple missed offline intervals do not trigger a burst on startup; the next
  due occurrence is visible and future-facing.
- Collection outcomes and skipped schedules are distinguishable in history.
- One completed collection hands off eligible new content to stage one without
  another collection, report creation as a prerequisite, or implicit historical
  rerun. The latest user decision allows a separate automatic report stage to
  follow committed initial analyses. On 2026-08-29 the user confirmed one report
  after each frozen analysis task has attempted all its records, using its
  successful outputs. See `../design.md` for the durable handoff.

No scheduler, model call, collection, migration or implementation agent was
started during this planning research.
