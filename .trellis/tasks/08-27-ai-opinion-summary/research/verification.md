# Manual Summary Integration Verification — 2026-08-28

## Earlier isolated implementation and QA scope

This section records the isolated implementation/QA phase before subsequent delivery and the
local real-source attempts documented below. That phase implemented the existing full-run manual
summary task. Local source is authoritative;
execution used the isolated Centaurus checkout `/tmp/longtian-media-validation.DeYMEC`. No user
database, credentials, browser profile, runtime directory, or private cost-probe cache was copied.
No real provider requests, platform-browser acquisition, commit, push or archive occurred during
that isolated phase.

The task-only `verification/preview_app.py` creates its own `mkdtemp` SQLite/runtime, seeds four
synthetic results, and injects fake model and media workers into the real product application,
repository, enrichment service and summary pipeline. Its platform process launcher rejects live
browser startup. Input media is a tiny synthetic PNG; the model's JSON and token counts are fake.
This proves application integration, not actual model quality, media understanding or billing.

## Automated gates

- First transport checkpoint: **160 passed**, scoped Ruff and formatting clean; local/remote
  hashes matched. The 21/100 historical-query cases failed before the 20→100 compatibility fix.
  See `transport-check.md`.
- First full backend gate: **593 passed, 1 failed**. The failure was a test-only Pydantic injection
  that did not run; it was replaced by a real SQLite trigger aborting the second item insert to
  verify rollback of both the parent and first child.
- First frontend gate: **274 passed / 14 files**, formatting/lint/typecheck/build passed. The
  subsequent independent review added matched-term/Unicode/error-copy regressions.
- Final independent gate after source-hash reconciliation: backend **596 passed in 11.94s**,
  Ruff/check-format **68 files** clean. Frontend independent frozen install **447 packages**,
  **281 passed / 14 files**, formatting, lint (0 errors/warnings), typecheck and production build
  all passed. Thirty key source/test/package/lock hashes matched local and remote. See
  `integration-check.md` for narrow review fixes and red/green evidence.

## Browser acceptance

The local browser visited a forwarded isolated frontend at `127.0.0.1:15184`, proxying only the
fake API on `127.0.0.1:18080`. Existing services on 5173/8000/15173/15174 were not used or stopped.

1. Initial result page and read-only summary history: zero model and media calls. Original results
   remained visible without AI. Choosing “再次命中 0” hid result rows but confirmation still stated
   the entire four-result run, not zero or the current page.
2. Confirmation displayed the saved endpoint/model and explicit media/quota boundary. Escape
   dismissed it; counters stayed at zero. No key was displayed or submitted through the UI.
3. Summary #1 showed pending/progress/cancel, then completed with **1 relevant, 1 irrelevant,
   1 uncertain, 1 input-incomplete, 0 failed**. The incomplete source said no model was called.
   Three item calls plus one text-composition call yielded **60 synthetic tokens / 4 calls**.
4. The report cited only the relevant source, resolving to the stored original result URL.
   Expanding “内容分析” showed distinct decisions/reasons and the explicit incomplete-input message.
   No fake source link was followed to a live platform.
5. Summary #2 reused all three completed analyses, retried only the unresolved acquisition, and
   made just one new text-composition call: **15 synthetic tokens / 1 call**, “复用分析 3”.
   Totals after two complete versions were 5 fake model responses and 5 media acquisitions.
6. Reload restored #2 without new calls. Force-refresh #3 followed by cancellation retained one
   completed analysis and cancelled the other three. It showed two attempted requests but only
   one accounted response: **15 synthetic tokens, accounting incomplete**.
7. Selecting #1 after cancellation restored its original report/coverage/60-token accounting;
   old versions were not overwritten. The observed 1265px viewport had equal scroll/client width
   (no horizontal overflow); screenshot review matched the existing theme. No responsive override
   or visual redesign was performed. Browser warning/error logs were empty.
8. Owned staging directories were empty after each terminal operation. The first owned preview
   tab and Vite process were closed before the independent dependency-install gate. Only exact
   task-owned processes were stopped; shared dependency targets and other servers were untouched.

Follow-up after the independent text/decoder fixes: reopened the same isolated source and restored
cancelled summary #3. Its retention notice appeared only once, completed-analysis access and partial
token accounting remained, warning/error logs were still empty, counters did not increase, and
staging was empty. This final view reused the original fake backend; final route-header changes
were covered by the freshly synchronized backend API tests, not claimed as a live-provider run.
The final preview tab, task-owned API/Vite processes and SSH port forward were then closed; no
regular application service or shared dependency target was stopped or removed.

## Remaining live acceptance

The task remains `in_progress`. A separately authorized real source must still pass the complete
worker → acquired actual media → configured model → saved analysis → text summary chain. Confirm
content fidelity, cited claims, usage and reuse on that source. The earlier private video cost probe
and this synthetic acceptance are not that gate. The media child remains open, including incomplete
WB/KS inventory, XHS acquisition and abnormal-worker cleanup limitations already documented there.
Do not claim five-platform complete-media readiness, automatically run a paid acceptance, or treat
an AI source claim as a verified incident.

## Local real-source attempts — 2026-08-28

The user authorized a small real run and then continued after the browser-authorization
prompt. These attempts used the normal Mac application at 5173/8000 and its local database;
no user runtime or credentials were transferred to Centaurus. Source run **41** was frozen
in full: five Douyin results **124, 125, 121, 122, 123**, historical rule
`验收0827·投诉组合`, term `龙田街道 投诉`. Both versions used configuration revision **1**,
`qwen3.5-omni-plus` at `https://dashscope.aliyuncs.com/compatible-mode/v1`, and
`force_refresh=false`. The bound was five new item requests plus at most one text composition,
not an authorization to analyse other runs or all history.

| Version | Request ID | UTC start–finish | Outcome | Provider requests / tokens |
| --- | --- | --- | --- | --- |
| 1 | `cd637a0c-0444-4d94-83ec-bd089f988709` | 08:14:15–08:19:17 | Five input-incomplete items, no saved normalized input | 0 / 0 |
| 2 | `a2b4d8e0-37f5-4c64-9d3a-76c548a38f22` | 08:43:21–08:44:16 | Five input-incomplete items, no reusable analysis | 0 / 0 |

During version 1 a read-only native Chrome inspection found the remote-debugging permission
dialog. This is an observed blocker, not proof of the exact internal outcome of every item:
the public acquisition error currently merges multiple worker outcomes. After the user's
continuation, the dialog was absent and Chrome displayed its automation-control indicator.
Version 2 acquired one normalized partial input, so this attempt was not simply waiting on
the original permission dialog.

Version 2's persisted input was inspected read-only with an explicit metadata projection,
not a dump of input text or credentials. Result **124** has partial text, incomplete media
inventory, and one unavailable video (`media_missing`); MIME, bytes and duration are null,
audio is unknown. Its normalized issues are `text_incomplete`, `media_missing`, and
`inventory_unknown`. Results **125, 121, 122, 123** have no saved normalized input and
`acquisition_failed`. No item is relevant, irrelevant or uncertain, and none was attempted
against the model. Per-item elapsed times were approximately 10.85–11.35 seconds.

Both versions reached the existing `completed` terminal state with the deterministic empty
document. This means the runner settled, **not** that an AI report was generated or that the
five posts were unrelated. The visible summary panel correctly shows five incomplete items
and `本次未调用模型`. There are no provider-usage or report-quality claims to make.

### Focused read-only diagnosis

After version 2 ended, one new Chrome audit tab opened result 124's exact stored canonical
URL. It initially showed video loading, then displayed the post and played normally, with
no observed login or CAPTCHA. The exact-ID info/player scopes each contained one heading/video;
the heading and player were visible and the scoped expand button was not visible. This
does not prove every failed worker item had the same DOM at its earlier snapshot.

- Production currently waits at most **10 seconds** for structural readiness, then takes a
  single snapshot even on timeout. The observed timing and later usable page make premature
  readiness failure a hypothesis to investigate, not a proven root cause or permission to
  weaken completeness checks.
- The observed player used HTTPS host **`v95-web-sz.douyinvod.com`**, whereas the current Douyin
  downloader allows only **`v26-weba.douyinvod.com`**. This is an additional compatibility gap
  if acquisition reaches download, not an explanation for result 124's earlier `media_missing`
  projection; the other four worker outcomes remain unspecified.
  Only the hostname was retained; no signed URL or media bytes were saved. Player metadata
  was 20.033333 seconds, 720×1280; actual MIME, byte count and audio-track validation remain
  unproved.
- No new model run, source substitution, allowlist expansion, completeness relaxation, or
  application code change followed these findings. Independent Trellis review read version
  2 and its items once and confirmed the frozen scope, zero calls, incomplete classifications
  and empty-template outcome.

The real worker → full media → model → saved analysis → text report gate remains **open**.
Resolve and verify the Douyin media-acquisition issues before another paid-path acceptance;
do not mark the unchecked real-media/reuse criterion complete from these attempts.

## Authorized Douyin video repair — 2026-08-28

The user approved the repair. Scope and ownership are in
`douyin-media-repair.md`. This follow-up supersedes the earlier diagnosis-only
boundary, not the complete-input or provider-call limits.

One exact-source browser navigation per stored result identified **124 as a
video and 125/121/122/123 as image posts**. All four latter URLs redirect from
`/video/<id>` to `/note/<same-id>` and show the note layout. Their earlier missing
normalized inputs must not be attributed solely to slow video rendering. The
current video adapter deliberately rejects those layouts; this repair does not
claim image-post support or use their recommended video players.

After the exact observed hostname was added, the existing file-only live probe
used result 124's actual player locator via private stdin. Production downloader
and ffprobe validation returned **ready**, **2,295,446 bytes**, **video/mp4**,
**20,034 ms**, **720×1280**, **audio_track=present**. Its owned operation was empty
and the temporary root was removed afterward. No signed URL, media, cookies,
credentials or source text was retained in the record. Initial helper startup
attempts used the backend environment without Pillow and failed before downloading;
the successful probe used the existing derivative environment. No model or
database write was performed by this probe. It proves the guarded file path, not
the complete worker → model → report chain.

### Repair gates and current live blocker

- Old real-DOM regression: three failures and one pass reproduced premature
  classification of hidden caption/player and empty `currentSrc`.
- Implementer final focused gate: **253 passed**, zero skipped Chromium fixtures;
  scoped Ruff and format passed.
- Independent final gate: maintained derivative `tests/` **1,058 passed / 0 skip**
  (47.70 s), backend **596 passed** (12.52 s), backend Ruff/format **69 files** and
  changed derivative-file checks clean. Frozen source hashes matched the isolated
  Centaurus checkout. See `douyin-media-repair-check.md` for the independent record.
- The normal local backend restarted safely after confirming no active search,
  batch, summary or connection operation. Database/history/configuration revision
  1 were retained; no automatic model call occurred on restart.
- A single UI-confirmed follow-up started **summary 3**, request
  `748af409-3d2b-480f-ae59-10c1a060076f`, at **09:17:26 UTC**, same five results,
  revision 1 and `force_refresh=false`. Native Chrome again displayed the
  remote-debugging permission dialog granting full control of the browser.
  The main agent did not approve that privileged reconnection without an
  action-time user confirmation. The attempt was cancelled while awaiting that
  confirmation; this is not model/report acceptance.
  Cancellation settled at **09:19:05 UTC** with **1 input-incomplete, 4 cancelled,
  0 model requests, 0 tokens**, and no document. Do not retry this request ID to
  create new work; any user-approved continuation must be a new explicit intent.

The code repair and actual-file validation are complete; the full live
worker/model/report gate remains open. The task stays `in_progress`, with no
commit, push or archive in this repair turn.

### User-approved continuation

The user then confirmed the requested browser reconnection with `ok`. A fresh
native inspection found no remote-debugging dialog; no permission button was
clicked in that absence. The existing local backend remained running, without
another restart. Through the normal application confirmation, main started
**summary 4**, request `d8edb542-47da-4bcf-b0a3-a2d5368ce40c`, at **09:22:18 UTC**.
This is a new explicit intent after cancelled version 3, not a transport retry:
same run 41, five sources, saved configuration revision 1 and `force_refresh=false`,
with the unchanged maximum of five item calls plus one text-composition call.
An immediate native check again found no authorization dialog. Final acquisition,
model and report results are recorded below after the operation settles.

Summary 4 settled at **09:23:01 UTC** with five incomplete inputs and **zero model
requests/tokens**, not a generated AI report. Unlike versions 1–3, result 124 now
saved a complete actual MP4 asset (2,295,446 bytes, 20,034 ms, 720×1280, audio
present, complete inventory); its sole remaining issue was `text_incomplete`.
The four note redirects failed quickly in approximately 2–3 seconds each.

Main inspected the same video once in a fresh owned Chrome tab. The screenshot
showed its complete 62-character caption on two lines, with no visible expand
control. Read-only DOM metrics found `h1 { display: inline; font-size: 32px;
line-height: 0px }`, client/scroll dimensions zero but a 71px-high inline box.
The clipping parent's top/bottom were approximately 679.28/731.28px and its
client/scroll heights were 52/57px. The actual text rectangles were 25px high,
at y=679.78 and 705.78 (last bottom 730.78): both fit inside the parent. The
current element-box test therefore treats valid inline metrics as unknown and
may mistake oversized inline font boxes for hidden caption text. This finding
requires a focused regression and actual-text-range correction, not disabling
clipping checks or treating all partial input as complete.
The local media spool was empty after this terminal run; acquired media was not
retained as a private cache or transferred into the isolated test environment.

The two real inline/glyph-overflow regressions failed before the caption fix.
The implementer's final caption gate passed **123 tests / zero skips** (30.97s)
with scoped Ruff/format clean. It exercises actual `enrich_with_context` through
single navigation, text projection, one materialization and owned-page cleanup;
negative cases retain real clipping, hidden text, line-clamp, unsupported
transforms and unknown geometry as incomplete. Only the existing Douyin adapter
and its test module changed in this follow-up. The 30-second readiness budget,
exact source/type guards, downloader, model envelope, API and database schema
are unchanged. The independent full gate and subsequent live result follow.

Independent final caption gate: **1,089 passed / zero skips** in the maintained
derivative suite (64.61s); scoped lint/format and frozen local/remote hashes passed.
The unchanged backend retains its prior 596-test evidence; it was not rerun in
this caption-only gate. The normal local backend was safely restarted after
confirming no active jobs/connections and retained configuration revision 1.

Main started **summary 5**, request `7081ea5f-3a39-410b-bfb2-e3bc8f2954d8`, at
**09:43:23 UTC**, via the normal same-origin application API. It retains exactly
the same five run-41 sources and `force_refresh=false`; prior attempts still made
no paid model calls. Native browser checks found no remote-debugging permission
dialog. This is the bounded post-fix live verification, not another platform or
historical-data batch.

Summary 5 settled at **09:44:07 UTC** with five incomplete inputs, **zero model
requests/tokens**, and no AI-generated report. Item 21 (source 124) again acquired
the actual complete MP4 (2,295,446 bytes, 20,034 ms, 720×1280, audio present,
complete media inventory), but its 62-character caption remained partial with
the sole issue `text_incomplete`. Its acquisition took approximately 33.75
seconds. The four unsupported note redirects again failed in 2–3 seconds each.
The offline 1,089-test gate therefore does not establish actual caption or report
acceptance. Main stopped full-summary retries pending a discriminating read-only
inspection of the remaining real DOM predicate; the task stays `in_progress`.

### Configured versus actual line clamping

The subsequent read-only inspection identified an unconditional legacy-clamp
guard as the remaining rejected condition. Source 124 has a two-line maximum,
but its actual complete caption occupies only those two lines. Detailed evidence,
including the harmless empty zero-width float and genuine omitted-line
counterexamples, is in `douyin-media-repair.md`. No alternate source, hidden
application state, CSS mutation or model request was used for this diagnosis.

The implementer's final narrow caption gate passed **160 Douyin tests / zero
skips** (52.08s); scoped Ruff/format passed. The real-DOM proof distinguishes
full two-line text from a hidden third line even in a tall container, and from
zero-height generated content consuming a clamp line. The final fixed-display
screenshot control passed two tests (2.15s), avoiding a change from `flow-root`
to legacy box layout when comparing clamped and unclamped rendering. Main also
confirmed that the actual source meets the new row/pseudo-layout predicates.
This is not yet a full application/model result. Frozen hashes:

- Adapter: `9d0a4ea33abf827dd8631d9df5f66855422dc491b538150b85b7780edd6cfa11`.
- Douyin tests: `873f29c5714ceab112b7363ef769f90a8098a0317262296137e300d54cbf73d5`.

The independent reviewer now owns the isolated full-suite gate. The normal local
application remains on its previously loaded code until that gate passes.

The independent final gate passed **1,126 maintained derivative tests / zero
skips** (85.35s), scoped lint/format and frozen-hash checks. Backend/frontend were
unchanged, so their earlier 596/281-test evidence was not rerun. Main safely
restarted the local backend after confirming no active/paused collection,
summary or connection work; saved configuration revision 1 was unchanged.

Main started **summary 6**, request `d209b706-caa2-4b40-b23a-d3d0a613c27d`, at
**10:26:19 UTC** through the normal same-origin API: same five run-41 sources,
same Qwen configuration and `force_refresh=false`. Chrome displayed the exact
remote-debugging permission prompt for which the user had confirmed `ok`.
Main clicked the freshly observed Allow control; a subsequent native check
showed the automation indicator and no remaining permission dialog. This is
the first actual permission click in this continuation. Model/report results
are recorded below after this bounded operation settles.

### Final live acceptance: actual video analysis and report

Summary **6** completed at **2026-08-28 10:27:15.752526 UTC**, with **1 relevant,
4 input-incomplete, 0 failed**, and a generated report. This is the first
successful real worker → complete media input → Qwen → text-composition run in
this repair continuation; summaries 1–5 are not counted as model acceptance.

- Source **124** acquired its complete **62-character caption** and actual MP4:
  **2,295,446 bytes**, **20,034 ms**, **720×1280**, audio present. Its persisted
  input was `ready`, with complete text/media coverage and no input issues.
- The item made **one** model request using saved configuration revision **1**
  (`qwen3.5-omni-plus`). Provider usage was **12,391 input + 235 output = 12,626
  tokens**. Input details reported **367 text, 11,882 video, 142 audio tokens**:
  the successful analysis was not a caption-only or cover-image substitute.
- Composition made **one text-only request**, verified in the persisted usage:
  **593 input + 299 output = 892 tokens**. It reused the saved item evidence;
  the video was not uploaded a second time for the report.
- Total provider-accounted usage was **2 attempted/accounted requests**,
  **12,984 input + 534 output = 13,518 tokens**, with complete usage accounting.
- The report cites **source 124**. Its media evidence includes visual content,
  overlaid location text and audio. Allegations remain attributed to the
  publisher and explicitly unverified; the location's administrative belonging
  is also unconfirmed. No allegations or personal names are copied into this
  verification record.
- Sources **125, 121, 122 and 123** are the previously verified same-ID `/note/`
  redirects, outside this narrow video adapter. They remain input-incomplete
  and made **no model requests**; they are not successful empty analyses or
  evidence that all five sources/platforms have complete media support.
- Replaying the **same request UUID and payload** returned summary 6 unchanged,
  including its finish time, two attempts and 13,518-token total. No additional
  generation or model request occurred. This validates real request replay;
  **cross-generation paid cache reuse was not live-tested** here and retains
  only its existing automated-test evidence.
- The local `runtime/media` spool contained **zero files** after completion.
  Runtime, credentials, media and the database were not copied to Centaurus.

The independent frozen-source gate remains **1,126 passed / zero skips**;
backend/frontend were unchanged and their previous **596/281** results were
not rerun in this caption-only continuation. The report URL is
`http://127.0.0.1:5173/collection-runs/41?summary=6`. Opening it in the app was
queued, not verified as visibly displayed. The normal local frontend/backend
remain running for user review. No further paid verification, commit, push or
archive was performed. The broader task remains `in_progress`; this narrow
Douyin video acquisition repair and its real report verification are complete.

### Report hyperlink follow-up

The user subsequently requested recognizable hyperlinks attached to the report.
This presentation-only change now places underlined `原文 N · 平台` citations
inside each report paragraph, resolving the existing frozen source records.
The full stored title remains accessible; XHS retains its existing action path.
No report regeneration or media/model/backend change was required.

Implementer and independent checker both passed the frozen frontend gates,
including **288 tests / 14 files** and the **26-case** summary component suite.
Main verified the actual saved summary 6: correct Douyin href, paragraph placement,
persistent underline, visible focus, no overflow at the default 380px report width
and no console warnings/errors. Saved status, finish time and **2 requests /
13,518 tokens** were unchanged. Live XHS opening and full live Tab order were not
exercised; their behavior is covered by tests. Details and final hashes are in
`report-source-links.md` and `report-source-links-check.md`. No commit, push or
archive was performed in this follow-up.
