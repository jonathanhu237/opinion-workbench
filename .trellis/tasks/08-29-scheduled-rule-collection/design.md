# Design B: Scheduled Rule Collection

Status: implemented and checked, including isolated browser acceptance. Parent `../08-28-collection-report-decoupling/design.md`
sections 1–2, 4, 6–8 define shared contracts. Depends on completed A.

## Ownership

Own `collection_schedules` backend schema/repository/service/API and frontend
client/forms/history; next additive schedule migration; existing batch admission
extension for an idempotent occurrence token; lifespan timer integration.
Edit shared database/router/lifespan files only after A, never concurrently with C.

## Contracts

- Store fixed integer minute intervals, accepting minutes/hours and normalizing
  to 1–43,200 minutes. Enabling/editing computes next due from now + interval.
- Schedule rows reference rules/platforms and the existing result cap, not prompts.
  Current valid rule content is snapshotted per dispatched batch.
- A unique (schedule, revision, due-time) occurrence plus batch dispatch token
  protects replay across repeated timer checks and failures.
- Link the occurrence/batch durably before browser launch; recovery of a claimed
  but unlaunched occurrence is interrupted, not an automatic duplicate launch.
- Preserve existing browser ownership, serial collection and manual verification.
  Busy/unavailable/invalid-rule cases skip visibly and advance to a future due.
- Use an injectable UTC clock and monotonic waits. Offline/forward-jump ranges
  have bounded audit metadata; no per-missed-minute burst. Backward jumps cannot
  repeat a claimed key.
- Stop admission first on shutdown. Do not steal or resume a paused batch. Turning
  a schedule off stops future runs, not its already admitted current run.

## Integration

Use A's discovery transaction and normal terminal-collection handoff. Never call
an AI model from scheduler code or synthesize a report to mark collection done.
C will test scheduled collection -> initial analysis -> automatic report.

## Recovery

New schedules default disabled; no migration/model/browser side effects.
Rollback disables timer admissions and settles owners; preserve occurrence and
collection history. Additive schema rollback follows the parent policy.
