# Actual Acceptance Progress — 2026-08-27

## Scope and Status

The user approved the final bounded plan, the scoped local-backend exception and subsequently
resolved the browser authorization blocker with “允许”. The bounded live checks are now finished;
task status remains `in_progress` for review/handoff, without archiving or committing.

**Mixed live results:** all five baseline searches succeeded; four combined searches succeeded,
while Toutiao returned `structure_changed`. Stable-identity deduplication is proven on 15 overlapping
Weibo/Douyin/Xiaohongshu results; Kuaishou returned a different set, so its repeat is inconclusive.
Saved-provider text connectivity passed once. No multimedia or per-post AI analysis was performed.
No product/submodule code changes, commit or push were performed.

## Passed: Backup, Migration and Production Startup

- Created one private local runtime backup using SQLite's backup mechanism before startup. Its
  integrity check was OK and schema version was 8. No credential files or runtime data were sent
  to Centaurus.
- Started the actual production FastAPI application (not a fake service) and its normal migration
  advanced the product schema to 9. Integrity is OK; foreign-key violation count is zero.
- Compared every pre-existing application table with the backup using bidirectional row-set
  differences. All 12 tables had zero missing and zero additional rows immediately after migration.
  Preserved counts: 1 rule, 5 object rows, 23 runs, 115 run terms, 92 contents, 144 run/content
  relations, 150 match relations, 3 batches, 15 batch terms, 9 batch items, 7 attempts, 1 AI row.
- The non-secret AI projection still showed key presence and revision 1 for the saved model.
- Frontend is running from Centaurus with a loopback-only frontend forward and API reverse-forward.
  Existing occupied remote ports were not stopped or reused. A refused occupied-port launch made no
  changes; the successful frontend uses its own dynamically assigned port.
- Product health is OK both directly and through the frontend proxy.

## Passed: Real Rule UI and Saved AI Text Request

- Used the real browser UI to create task-labelled rules **3** (baseline) and **4** (one object plus
  one issue keyword). The composed-query preview showed exactly one expected space-joined query;
  saved API projections preserved the two input groups. Existing rule 1 remained unchanged.
- Used the saved production AI service for exactly one `POST /api/v1/ai-settings/test` with revision
  1. HTTP **200**, `status=connected`, approximately **0.587 seconds**. No retry was made.
- The client sent only its fixed synthetic text prompt, not collected posts, images or video.
  Credentials were consumed by the service and were never read back or included in tool output.
  This proves current text connectivity only, not relevance judgment or multimedia understanding.

## Historical First Attempt: Browser Authorization Blocker

- Started **batch 4** from the real collection UI with the baseline rule, all five platforms and
  a five-result/query cap. The API stored one rule snapshot and executed platforms serially.
- First observed state: Toutiao run **27** running; the other four platforms queued.
- Chrome opened the native **“要允许远程调试吗？”** dialog. A read-only Computer Use accessibility
  inspection confirmed the request for full control of the Chrome session and its Allow/Cancel
  buttons. No permission, login or CAPTCHA was accepted automatically.
- Toutiao run 27 finished as **browser_unavailable**, with zero results. The existing batch state
  machine then advanced to Weibo run **28**, still waiting for the same browser authorization.
- Cancelled only this task's batch to avoid further unattended connection attempts. Final state:
  batch 4 **cancelled**; Toutiao **failed/browser_unavailable**; Weibo **cancelled**; Kuaishou,
  Douyin and Xiaohongshu **cancelled without a child attempt**. All result counts are zero.
- Post-cancellation native inspection still showed the authorization dialog. All **11** original
  Chrome tab IDs remained present. The application displayed truthful connection guidance rather
  than empty-search success, and its captured console had zero warnings/errors.
- Copy issue observed: the cancelled page also says **“已完成 5 / 5 个平台”**, because that counter
  counts terminal items including failures/cancellations. It is not five successful searches and
  may mislead the operator despite the cancelled header and individual outcomes. Record only;
  this verification task does not authorize a UI fix.
- At that stopping point, no combined search, repeat or original-result inspection had occurred.
  The subsequent authorized attempts are recorded below; batch 4 was not rewritten or continued.

## Authorized Live Search Comparison

- On resumption, no native approval dialog was present. No automatic permission click was needed,
  and no challenge was solved. Captured a fresh baseline of the two Chrome tabs then present;
  both IDs remained present at the end. The prior 11-tab snapshot belongs to the earlier attempt,
  not a claim that user-driven changes between turns were undone.
- Re-enabled only rules 3/4 and created fresh batches. Every run retained at most five results,
  with one query. All 14 new run snapshots match the expected rule query and five-result cap;
  recorded start/finish times confirm serial execution without overlap.

| Platform | Baseline batch 5: run, outcome, new/repeated | Combined batch 6: run, outcome, new/repeated |
| --- | --- | --- |
| Toutiao | 29, completed with 5 results, 4/1 | 34, `structure_changed`, 0/0 |
| Weibo | 30, completed with 5 results, 1/4 | 35, completed with 5 results, 5/0 |
| Kuaishou | 31, completed with 5 results, 2/3 | 36, completed with 5 results, 5/0 |
| Douyin | 32, completed with 5 results, 3/2 | 37, completed with 5 results, 5/0 |
| Xiaohongshu | 33, completed with 5 results, 2/3 | 38, completed with 5 results, 5/0 |

Baseline rule 3 sends `龙田街道`; combined rule 4 sends `龙田街道 投诉`. This is a space-joined
platform query, not guaranteed Boolean AND or a locality filter. Batch 5 completed; batch 6
completed with failures. Toutiao's combined failure was neither retried nor represented as an empty
success. Its exact underlying adapter failure has not been diagnosed by this verification task.

## Observed Search Quality and Public Originals

These are qualitative observations of five retained results per successful search, not recall or
precision measurements. Titles/snippets can be incomplete; no video's spoken or visual content
was analyzed. Allegations in a post are not independently verified facts or proof of an ongoing issue.

| Platform | Baseline observations | Combined observations |
| --- | --- | --- |
| Toutiao | Local football, development, ecology and festival news; mostly neutral/positive | No sample: `structure_changed` |
| Weibo | One local activity plus unrelated or insufficient-location material | Four very similar old local road-access complaints, plus neutral local community news |
| Kuaishou | Scenery, advertising and other locations | General complaint/rights advice; target locality usually unproven |
| Douyin | Some local clips and an old rescue report, mixed with other locations | Complaint-related snippets, but other cities or insufficient locality evidence |
| Xiaohongshu | Maps, schools and rentals | A namesake-town complaint and generic complaint advice; not reliably target-area issues |

Two representative originals were actually opened and checked:

1. [Weibo original](https://m.weibo.cn/detail/5008729703713273), global content **112**, run **35**:
   the rendered original explicitly names Shenzhen/Pingshan/Longtian/Laokeng and alleges blocked
   road and emergency-vehicle access. Its visible date is **2024-03-06**, not a new incident from
   this collection date. Three other similar complaint posts have distinct platform post IDs;
   record-level deduplication does not merge them into one event.
2. [Xiaohongshu canonical original](https://www.xiaohongshu.com/explore/68a926c7000000001d01a8c4),
   global content **126**, run **38**: the rendered complaint explicitly names **福清市龙田镇**,
   not Shenzhen's Longtian Street. The product's no-body original-open endpoint returned `opened`;
   no signed navigation URL or token is reproduced here. It is a concrete namesake false match.

Additional title/snippet evidence includes a Douyin local rescue post dated **2025-08-05**,
[canonical video](https://www.douyin.com/video/7534996258398768393); the video itself was not watched
or sent to a model. The time evidence illustrates that **newly inserted is not newly published**.

Adding `投诉` surfaces more complaint-related material in this small sample, but does not eliminate
wrong locations, generic tutorials, neutral posts or stale incidents. A simple complaint-keyword
search cannot by itself identify current, target-area public-opinion information.

## Live Repeat and Stable-Identity Deduplication

Batch **7** repeated only the four successful combined searches once, with the same query/cap.

| Platform | Repeat run | New / repeated | Stable-ID overlap with combined run | Conclusion |
| --- | --- | --- | --- | --- |
| Weibo | 39 | 0 / 5 | 5 with run 35 | Proven for these five contents |
| Kuaishou | 40 | 5 / 0 | 0 with run 36 | Inconclusive: returned a different set |
| Douyin | 41 | 0 / 5 | 5 with run 37 | Proven for these five contents |
| Xiaohongshu | 42 | 0 / 5 | 5 with run 38 | Proven for these five contents |

All 15 intersecting identities reused the same global content row, were marked `repeated`, retained
the original `first_seen_at`, and strictly advanced `last_seen_at`. No duplicate global
`(platform, platform_content_id)` exists. No third Kuaishou search was made to manufacture overlap.
Toutiao was ineligible for this repeat because its combined run failed.

The three finished batches stored **65 run/content observations** and added **37 global contents**
(92 before, 129 after). This is not 65 unique posts or 37 newly published events. Per-run first-pass
counts can already include repeats from earlier history.

## Final UI, Preservation and Handoff

- In the real Weibo repeat page `/collection-runs/39`, selecting **新增 0** showed the proper empty
  state; selecting **再次命中 5** showed five articles. Counts, dates, snapshot query and original
  links were visible. Captured application console: zero warnings/errors.
- Final database integrity: **OK**; foreign-key violations: **0**; active runs/batches: **0**.
  Every original row in the 11 non-content tables remains unchanged. Original content identities
  and first-seen timestamps remain intact; content metadata/last-seen can update on a rediscovery.
- Rules 3/4 were disabled again through normal full replacement with both input groups preserved;
  rule 1 remains enabled and unchanged. AI revision remains 1. The real AI test was not repeated.
- Keep the owned app/tunnel and result tabs available. Comparison: `/collection-batches/6`;
  repeat/deduplication: `/collection-batches/7`; baseline: `/collection-batches/5`. Failed/cancelled
  batch 4 is preserved. No database rollback or deletion was performed.
- Product gaps remain: Toutiao combined-search failure; misleading terminal-progress wording;
  namesake/neutral/stale-result filtering; no event-level merging. Media acquisition, per-result
  AI analysis and final summary generation remain unimplemented, so there is no full AI pipeline
  acceptance. Any fixes or new provider calls require separate direction.

## Owned Runtime Handles (For Narrow Cleanup/Resume)

- Local backend: process **66821**, exec session **17086**, loopback port **18000**.
- Centaurus frontend: exec session **8977**, loopback port **35985**.
- SSH forward: process **66922**, exec session **79203**; local **5173** to remote frontend, remote
  loopback **18000** to local backend. An earlier obsolete forward process was terminated by exact ID.
- In-app browser: owned tab **6**, showing the batch result. Two task-owned original-inspection
  tabs (Weibo and Xiaohongshu) are retained as deliverables; the latter was opened through the
  product and then claimed for rendered-page inspection. Neither was a pre-existing user tab.
- Backup remains in the task-owned ignored local runtime directory, not synchronized or committed.
- The system SQLite CLI also rejected a read-only post-run check; Python's `sqlite3` read-only
  connection completed the integrity/count/foreign-key checks successfully. Use that established
  read-only path for follow-up checks rather than changing database permissions or assuming damage.

## Later User-Approved Rule Cleanup — 2026-08-27

The earlier handoff above describes the pre-cleanup state. The user subsequently requested one
remaining rule group. Only acceptance rules 3/4 have now been deleted through the product API,
after a fresh private local backup. Original rule 1 and all 39 runs, 7 batches and 129 contents
remain. Full row comparisons of the nine search tables allow only the expected nulling of
deleted-rule references; snapshots, results and attempts did not change. Integrity is OK and
there are no foreign-key violations. No new platform/model request or product fix occurred.
Details and the still-unresolved Toutiao follow-up: `research/rule-cleanup-verification.md`.
