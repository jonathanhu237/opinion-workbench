# Design A: Shared Results and Initial Analysis

Status: implemented and checked; read parent `../08-28-collection-report-decoupling/design.md`
sections 1–4 and 7–8 for authoritative shared contracts.

## Ownership

Own new `results`, `analysis_settings` and `content_analyses` families in backend
schemas/repositories/services/API; the first new migration in `database.py`;
discovery registration in `repositories/search_runs.py`; lifecycle/router/dependency
wiring; shared-results/initial-analysis/prompt UI and narrow API clients.
Own necessary legacy admission/completion claim integration, without changing
legacy report JSON or silently redirecting its creation endpoint.

Shared `main.py`, API/frontend routers and `database.py` have one writer. B and C
edit them only after A's handoff, preserving A and unrelated changes.

## Contracts

- Append prompt/settings, claims, jobs, attempts and completion-event tables.
  Preserve genuine v11 data. Old completed/reused history is legacy-completed;
  failures/interruption remain legacy-attempted, not automatic bulk candidates.
- A global result is one existing content ID with separate valid origin tuples.
  First-entry filtering never substitutes publication or last-observation time.
- Freeze the whole never-started selection plus both prompt/provider versions
  on admission, not the current page. Share content claims across automatic,
  manual and legacy work. Admission is independent of current cache matches.
- Acquisition uses existing actual-media validators and leases. Save accepted
  text, attributed clues/observations, coverage and usage; report code is not
  required to persist a success. No prefilter for Shenzhen Longtian.
- Freeze source observation before acquisition and validate it again. Guard
  latest-known fingerprint, settled cancellation and late callbacks.
- Job completion means all members have terminal attempts, not all success.
  Write one unique completion event in that transaction, including successful
  attempt IDs and unsuccessful counts. Cancelled/interrupted work produces no
  automatic report event.
- GET and startup reconciliation do no paid work. Explicit enablement binds
  automatic policy to provider revision; migration never backfills history.

## Integration Handoff

B consumes the same discovery/terminal-collection handoff. C consumes completion
events, immutable attempt text and the frozen report prompt/provider intent.
The event API must expose settlement proof and deterministic source membership;
do not require C to join mutable current content or recreate analysis.

## Compatibility and Rollback

Preserve old report readers, canonical reuse references and usage. Claim checks
must include active legacy work so a new bulk request cannot duplicate it.
Disable new admissions to roll back; leave additive evidence/history intact.
Do not run old binaries on a down-labelled newer database.
