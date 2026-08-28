# A isolated browser acceptance

Observed on 2026-08-29 with the Codex In-app Browser. This is functional and
layout evidence using synthetic fixtures, not live account/provider evaluation.

## Environment

- Source snapshot: `Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/`.
- Backend: `PYTHONPATH=src:tests uv run --frozen uvicorn
  initial_analysis_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082`.
- Frontend: `VITE_API_BASE_URL=http://127.0.0.1:46082/api/v1
  mise x node@24 pnpm@11.14.0 -- pnpm dev --host 127.0.0.1 --port 46081 --strictPort`.
- Both loopback ports forwarded locally with an owned SSH connection. No existing
  service/port was replaced. Source snapshots remained unchanged during UI checks.
- Temporary on-disk DB, 103 cross-run synthetic sources, fake model/media worker,
  fail-closed real browser launcher; content ID 1008 intentionally incomplete.
- First attempt exposed a fixture-only cross-origin setup omission. The checker
  added exact-origin CORS for `http://127.0.0.1:46081`, GET/POST/PUT and Content-Type,
  with tests rejecting other origins/DELETE. Production app/security stayed unchanged.

## Observed checks

| Check | Observed result |
| --- | --- |
| Startup/read safety | Synthetic model/media counters stayed 0/0 after startup, API reads and opening Results. Product result API returned HTTP 200 with `Cache-Control: no-store`. |
| Failed-read recovery | With unavailable cross-port reads, actions were disabled and cause-safe errors shown. Page Refresh loaded the same selected view after the fixture became reachable. |
| Nonfirst-page scope | Entered `/results?offset=50`, displaying 51–70 of 103. Whole-library eligible count and confirmation still said 103. |
| Independent prompt save | Initial prompt changed from version 1 to 3 while report remained version 2; report then changed to version 4 while initial stayed 3. Both saved success feedback appeared. Counters remained 0/0. |
| Frozen confirmation | Confirmation displayed provider revision 1 and prompt versions 3/4 with full-library scope and media/usage disclosure. No calls occurred before confirming. |
| Keyboard dismissal | Escape dismissed confirmation and restored focus to `一键初步分析`; reopening still made no model/media call. |
| All-library admission | One confirmation admitted exactly 103 records, not the 20 visible rows. Active job exposed cancel and progress controls; whole-library eligible count became 0. |
| Mixed settlement | Job 1 reached 103/103 processed, 102 saved and 1 unsuccessful; incomplete row explicitly said no model call. Counters were 102 synthetic model calls and 103 synthetic media acquisitions. |
| Honest usage/state | UI showed 102 attempted/accounted calls, 1,530 tokens, and explicitly distinguished settled initial analysis from all-success/report-generated. |
| Saved evidence | Opened the first successful attempt from its frozen link. Focus moved to `来源与初步分析`; source understanding, attributed geography/time, media observation and uncertainty were readable. |
| Full accepted text | Expanded input coverage showed complete text, one verified image and the synthetic full body, not just the collection snippet. It explained that only text/media metadata is retained. |
| Reload/history safety | Reload preserved `offset=50&job=1&result=1&attempt=1`, the same saved evidence and 102/1 outcomes. Counters remained 102/103; no retry or new job was triggered. |
| Responsive layout | Default desktop screenshot and 390x844 viewport screenshots inspected. Content width/scrollWidth were equal (375/375 at narrow viewport); controls and detail sections stacked without horizontal overflow. |
| Console | Warn/error query returned an empty list after successful loading, settlement, evidence inspection and reload. |

## Cleanup and boundaries

Closed the owned temporary tab, restored the browser viewport, stopped the owned
API/frontend servers and SSH tunnel. Remote `ss` and local `lsof` confirmed no
listeners on 46081/46082. The fixture's temporary DB cleaned up on normal shutdown.

No real platform link was opened, account connected, credential entered, paid
provider called, production database changed, Git operation performed, or real
automation enabled. These checks do not prove model quality, live platform media
availability, B scheduling, or C report execution. Backend/frontend regression
gates cover the additional cancellation/race/legacy/error contracts; full-A
independent review evidence is recorded separately.
