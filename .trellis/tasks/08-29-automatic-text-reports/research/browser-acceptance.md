# C and final A+B+C browser acceptance

Main-owned, 2026-08-29. Passed: full interaction coverage and a clean-fixture
repeat on the 588-test frontend, followed by targeted normal/retry/reuse checks
on the final 593-test frontend. The backend stayed at its released 997-test
snapshot. Response-delivery observations and recovery are retained below;
no live-platform or model-quality claim is made.

## Environment and isolation

- Source of truth stayed local. Services used the frozen Centaurus snapshot
  `/tmp/longtian-decoupling-impl.dMCxsd/`; no source synchronization occurred
  during browser acceptance.
- Backend: `PYTHONPATH=src:tests uv run --frozen uvicorn
  topic_report_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082`.
  Frontend: the frozen Vite application on remote loopback 46081, with
  `VITE_API_BASE_URL=http://127.0.0.1:46082/api/v1`. Both ports were SSH-forwarded
  locally. Existing user services on other ports were untouched.
- The actual A/C application, queue, repositories and HTTP routes ran against
  temporary on-disk SQLite with fail-closed collection/browser workers and fake
  media/model transports. See [smoke-fixture.md](./smoke-fixture.md) for seed,
  transport accounting and the six executable fixture tests.
- Each factory started with all ten counters zero, 104 saved results including
  one legacy result, 103 never-attempted candidates, no schedules and automatic
  new-content authorization off. No real credentials, account, runtime database,
  provider quota or deployment was used.

## Main interaction pass

1. Opened `/results?offset=100`: the visible result page was **101–104 / 104**,
   while the global initial-analysis action correctly offered **103** candidates.
   Read `/collection-runs/4`: the saved legacy report, scope counts and original
   citation remained readable, explicitly labelled old workflow. No old-generation
   button/POST occurred; every counter remained zero.
2. Returned to the later results page and confirmed **one** bulk operation. The
   disclosure showed stage-one prompt version 1, stage-two prompt version 2,
   frozen scope, actual media/text boundaries and separate potential usage.
   Both prompt texts were expanded and inspected. Admission reported 103, not
   the four visible rows; another 103 active items did not remain eligible.
3. Observed separate progress: initial analysis at 72/103 with two incomplete
   inputs while the report said it was waiting for that task. Final settlement
   saved 101/103 texts. Without another generation click or confirmation,
   report #1 became completed: 101 judgments, 96 relevant, 3 unrelated,
   2 uncertain, 2 initial-evidence unavailable and zero technical judgment errors.
4. Report #1 showed all 15 saved nodes: twelve eight-source detailed chapters
   and three overview nodes; root #116 covered all 96 relevant sources. Opened
   all three detailed-chapter pages (1–5, 6–10, 11–12) and all six source pages
   through 101–103. The last chapter cited source 103; source 103 preserved
   collection run #3 while source 101 pointed to run #2. External platform links
   were inspected, never opened. Root -> overview #115 -> child chapter controls
   exposed the retained detailed evidence without expanding all source IDs into
   overview nodes.
5. Reload preserved result offset 100, job 1, detailed offset 10 and source
   offset 100. Followed source 103's internal saved-text link to attempt 103:
   content understanding, geographic ambiguity, unknown event time and media
   observations remained distinct from the stage-two verdict. The link selected
   the exact saved version, not a new acquisition or current-title rewrite.
6. Inspected stage-two usage separately: 101 judgment requests / 1,515 tokens,
   15 composition requests / 225 tokens; report total 116 / 1,740. Prompt
   provenance was shared version 2. Initial-stage usage stayed in its own panel.
   All these reads/pagination/reloads left counters unchanged.
7. The optional interval form initially focused the start date. Empty submit
   displayed both date errors without admission. Escape closed it and restored
   focus to the invoking button. It is visibly optional and distinct from the
   global stage-one action. Exact microsecond interval membership and API
   acknowledgement precision are covered by the merged unit/API gates, not by
   claiming that this browser pass submitted a new interval report.
8. Entered the one-report override
   `验收：失败一次。仅根据本次保存文本生成报告，保留不确定性。`
   and created report #2. Its first leaf failed citation validation; 11 completed
   detailed drafts remained visible, explicitly not a complete report. All 101
   source judgments and both incomplete-source reasons remained readable.
9. Used the report-only retry with the frozen override. Report #3 completed,
   reusing 101 judgments and 11 successful chapters; only four new composition
   requests / 60 tokens were counted. A first-pass response-delivery anomaly is
   documented below, including successful same-UUID API replay and history
   recovery. Old reports #1/#2 and saved initial texts remained intact.
10. Checked both default editors afterward: stage one remained version 1 with
    its original text, stage two version 2 with its original text. Automatic
    new-content analysis remained off. The override did not overwrite defaults.

## Observed counters

These are actual injected-operation counts, not inferred from status labels.
Collection, external-browser and legacy-generation-request counters were zero
at every checkpoint. Each clean fixture had its own cumulative count sequence.

| Checkpoint | Media | Initial | Judgment | Leaf | Overview | Model total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Startup and passive legacy/history reads | 0 | 0 | 0 | 0 | 0 | 0 |
| Automatic report #1 | 103 | 101 | 101 | 12 | 3 | 217 |
| Override report #2 failed | 103 | 101 | 202 | 24 | 3 | 330 |
| Same-prompt report #3 completed | 103 | 101 | 202 | 25 | 6 | 334 |
| Clean-fixture extra narrow-screen retry #4 | 103 | 101 | 202 | 26 | 9 | 338 |

## Response anomaly and clean-fixture revalidation

The first browser's report #2 retry created and completed report #3 but `fetch`
failed before the page received an acknowledgement. The UI retained its frozen
intent and offered same-request confirmation; repeated confirmations did not
create a fourth report or increase counters. The displayed error was the
transport `service_unavailable`, not a JSON/DTO decoder error. No console
warning/error was captured. The API remained reachable.

Main replayed the **already admitted same UUID and identical intent**, not a new
operation, through the isolated HTTP endpoint with the same UI Origin. It
immediately returned 202 with correct CORS/no-store headers and completed report
#3; counters stayed 334. Reloading the browser displayed exactly the three
versions, and report #3's saved text, usage and reuse counts were readable.

Independent source checks found no null-versus-override fetch/serialization
branch explaining the failure. The frozen Uvicorn protocol can omit access logs
when a peer disconnects before response start, consistent with the observed
missing POST log, but the actual disconnect cause was **not established**.
No production or fixture code was changed to conceal or supposedly fix it.

Main stopped the first fake backend normally, confirmed temporary data cleanup,
closed the tab and started a fresh factory using the same source/dependencies/
command/ports. Repeated bulk -> automatic report #1 -> override failure #2 ->
null-override retry #3 **entirely in the UI**. It returned normally, automatically
selected `/results?offset=100&job=1&report=3` and showed completion. Counters
again matched 217 -> 330 -> 334.

To cover the first pass's narrow viewport, selected failed report #2 in history,
set 390×844, expanded the frozen prompt and explicitly retried that same scope
once more. Report #4 returned normally and automatically selected its completed
view; dialog count was zero. This deliberate extra fixture version added only
four composition requests (338 total), not media or initial analysis. Both
retry POSTs in this clean run logged 202. Reload retained report #4.

## Layout, cleanup and limitations

- Inspected the 390×844 override-dialog screenshot: title, textarea, disclosure
  and submit/cancel controls remained readable and in bounds. Dialog client and
  scroll width were both 343 px; page scroll width 375 px at a 390 px viewport.
  The completed narrow report also had no horizontal overflow.
- Initial/dialog focus, Escape recovery, separate pending/completed/failure
  states and preserved history were exercised. Browser warning/error logs were
  empty in both runs. Pending duplicate-submit/close guards and malformed API
  response behavior also have deterministic frontend tests.
- Both fake backends shut down normally; second PID 1905237 confirmed lifespan
  completion. `/tmp/longtian-topic-report-smoke-8q_rknvp` was removed by the
  fixture, and the first temporary fixture was also absent before the restart.
  Owned frontend, SSH tunnel and all browser tabs were closed; viewport reset.
  Local and remote 46081/46082 had no listeners after cleanup. Stopped only
  owned processes; Vite/SSH exit 255 followed explicit Ctrl-C, not a build gate.
- This proves UI/workflow/counter contracts, not real extraction, model
  geographic accuracy, provider availability, scheduling in production or
  absence of future network failures. First-pass response delivery is retained
  as an unresolved environmental observation, with successful unchanged-code
  desktop and narrow revalidation rather than an invented root cause.

## Final decoder-parity snapshot revalidation

After the previous services were stopped, review aligned the frontend's two
ancestry guards with backend strict older-ID ordering and added five tests.
This changed no UI, transport, fixture or backend code. The final frontend
passed all frozen gates with **593 tests / 23 files** and source manifest
`49cb397cab26b6b937cc80d94fc34e028d52d3a577a6e4a1f3419e8c8151f637`.

Main then started another fresh fake factory and the final frontend, with zero
initial counters. Through the actual UI, again admitted 103 sources, inspected
completed automatic report #1, created the same one-off failing report #2 and
retried it to completed report #3. Normal older parent IDs and canonical reused
sections were accepted; report #3 showed 101 reused judgments, 11 reused
chapters and four new composition calls / 60 tokens. Opened its current-version
overview #344 with children #339–342. Reload retained report 3 and section 344.

This pass also observed a transport acknowledgement failure on the **override**
submission, so the observation is not confined to null-override retry. The
existing UI's **same-request confirmation recovered normally in-browser**, closed
the dialog and selected the already saved report #2. No new version or model
request was created by that confirmation. The subsequent null retry returned
normally and selected report #3. Final counters were exactly media103,
initial101, judgment202, leaf25, overview6 and total334; collection/browser/
legacy generation remained zero. No response mismatch or console warning/error
was reported. Intermittent response delivery remains undiagnosed; successful
idempotent recovery is observed, not an asserted network fix.

Final backend PID1921542 logged both accepted/replayed report mutations as 202
and completed graceful shutdown. Its temporary directory
`/tmp/longtian-topic-report-smoke-_hf8cpf7` disappeared. Final frontend and tunnel
were stopped; browser tab list was empty, viewport already reset, and local/
remote 46081/46082 had no listeners. No source changes followed this acceptance.
