# B isolated browser acceptance

Observed 2026-08-29 using the in-app browser and stable implementer snapshots:
backend 723 tests, frontend 476 tests. Independent review follows this browser
pass; any subsequent projection-only fixes need their regression gates as well.

## Environment

- Centaurus `/tmp/longtian-decoupling-impl.dMCxsd/`, temporary on-disk DB and
  `collection_schedule_smoke:create_smoke_app` on remote loopback 46082.
- Vite on remote loopback 46081, explicit API URL
  `http://127.0.0.1:46082/api/v1`; both ports forwarded locally.
- Exact fixture-only CORS, fake collector/AI/media and fixed clock. Seeded
  57 occurrence rows, a completed batch and a linked interrupted/manual-paused
  batch. Initial counters were collection 2 / model 0 / media 0.
- No source synchronization or edits during this browser pass. The reviewer
  respected a read-only freeze until services were stopped.

## Observed behavior

| Check | Result |
| --- | --- |
| Existing manual collection | Existing paused batch remains visible; new manual collection is disabled while its browser owner is retained. |
| History outcomes | Claimed work is not fabricated as success. UI distinguished busy skip, unavailable browser with manual-check guidance, interrupted dispatch, completed linked batch and a 10-round offline missed range. |
| Cursor and reload | History uses 20 rows; older page changed URL to `schedule=1&occurrencesBefore=38`. Reload preserved that page; latest-page navigation worked. |
| History focus | Opening history focused its heading; collapse restored focus to `查看定时执行记录`. |
| Required rule | Submit without a rule produced a labelled local error and no schedule. |
| Interval bounds | 721 hours was rejected with the 43,200-minute/720-hour bound. |
| Disabled creation | Created schedule 2 for the existing rule, only 微博, 2 hours, cap10. It was revision1, disabled, next due unarranged. No collection/model/media call occurred. |
| Enable confirmation | Escape restored focus to the enable action. Explicit confirmation produced revision2, enabled, next due 05:42 from fixture clock03:42. |
| Enabled edit | Changed to 30 minutes; revision3 remained enabled and next due became04:12. No rule, source or prior batch changed. |
| Disable | Confirmation explained future-only scope. Schedule2 became revision4, disabled, next due unarranged; reload preserved values. |
| Linked work preservation | Enabled then disabled seeded schedule1, reaching revision5. Its interrupted/paused batch2 and source link remained. Opening `/collection-batches/2` showed explicit open/continue/skip/cancel controls and 0/5 confirmed terms; no recovery was automatically submitted. |
| Narrow form | At390x844 the dialog was343px wide, bounded to the viewport with vertical scrolling and reachable save controls. |
| Narrow history | Screenshot inspected; clientWidth/scrollWidth375/375. Cards, controls and long failure explanations fit without horizontal overflow. |
| Console | Both schedule/history and paused-batch view had no warning/error logs. |
| Read/mutation independence | After all reads/reloads/create/edit/enable/disable actions, counters stayed collection2/model0/media0. Fixed fake time prevented ambient dispatch. No new batch or AI job was caused by configuration/read work. |

## Cleanup and limits

Closed the owned browser tab and reset viewport. Closed the local SSH sessions
and port forward; checked remote listener PIDs and their exact fixture commands/
working directories before gracefully terminating the two remaining owned
remote processes. Follow-up remote `ss` and local `lsof` showed no listeners
on 46081/46082; the fixture database was owned by its temporary-directory cleanup.

No real platform link/account was opened, model quota spent, production DB
changed, source deployed, Git operation performed or real schedule enabled.
Clock/crash/concurrent/invalid-rule behaviors are proven by the separate fake
regression suite, not by waiting for real intervals in this browser pass. This
acceptance does not establish live platform availability or C report behavior.
