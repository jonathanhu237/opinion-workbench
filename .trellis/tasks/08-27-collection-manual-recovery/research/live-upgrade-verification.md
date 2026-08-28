# Live Upgrade and Recovery Preflight — 2026-08-28

## Authority and boundaries

The user's “好的哦” approved upgrading the application and a bounded real validation on the
original paused batch 8. Local private backup and lightweight API/borrowed-browser work are
authorized; frontend execution remains on Centaurus. No repeated searches, automatic skip,
cancel, earlier-platform recovery, model call, commit, push or archive is included.

## Real pre-upgrade baseline

API/frontend listeners and local worker were stopped. SQLite had no writer or WAL/SHM files;
immutable read-only inspection was safe. The baseline was schema 9, 48 runs, 8 batches and
468 unique stored contents. These are real current counts, not earlier fixture/historical counts.

Batch 8 has 20 terms and a 10-result-per-term cap, paused at item 4 (Xiaohongshu). Its original
attempts/results are:

| Item | Platform | Run | State | Retained results | Trusted completed prefix |
| --- | --- | --- | --- | --- | --- |
| 0 | Toutiao | 47 | structure_changed / failed | 7 | 6 / 20 |
| 1 | Weibo | 48 | completed_with_results | 37 | 20 / 20 |
| 2 | Kuaishou | 49 | completed_with_results | 183 | 20 / 20 |
| 3 | Douyin | 50 | completed_with_results | 28 | 20 / 20 |
| 4 | Xiaohongshu | 51 | manual_challenge_required / paused | 108 | 16 / 20 |

No queued/running run or other active batch existed. Earlier failed Toutiao is not selected for
recovery; the authorized current-item continuation would execute positions 16..19 only.

## Backup, coordinated upgrade and preservation

- Created a consistent private local SQLite backup using `.backup` before application startup.
  Backup directory permissions are 0700 and backup-file permissions 0600. The path is under
  ignored `runtime/`; no backup/data/credentials were synchronized or committed.
- Started current local backend with the current derivative worker source as one rollout unit.
  Startup migrated schema 9 to 10; no worker process was launched merely by startup or GET.
- Compared every pre-existing column/row in nine search relations against the backup, including
  IDs, snapshots, content metadata, relations and timestamps. Every comparison was identical.
  Counts: batches 8, batch terms 39, batch items 33, attempts 28, runs 48, run terms 235,
  contents 468, run/content links 581, run/content/term links 676.
- SQLite integrity: OK. Foreign-key violations: 0. Batch 8 remained paused at item 4,
  revision 0 and run 51. API presents legacy-inferred checkpoints 6/20, 20/20, 20/20, 20/20,
  16/20. No successful platform or historical failed item was requeued.

## Frontend and actual button verification

Centaurus runs the already checked isolated source snapshot with its frozen-install dependencies.
Its existing Vite proxy was overridden at startup, without source edits, to use the dedicated
reverse loopback API forward; unrelated remote listeners were preserved. Requests through local
5173 successfully reach local API 18000 using the same origin.

The existing application tab was claimed and navigated to `/collection-batches/8`. The actual
UI displayed the cause-specific Xiaohongshu pause card, 16/20 completed, four remaining terms,
and `打开平台`, `继续采集`, `跳过此平台`, `取消批次` controls.

Clicked **打开平台 once**. It locked the conflicting controls while pending. Computer Use
read-only inspection identified Chrome's native **要允许远程调试吗？** dialog, explaining that
the application would control the browser session. No approval button, login form or CAPTCHA
was operated. The pending show request timed out and the product displayed `打开平台失败，请稍后重试。`.
The native approval prompt remained visible afterward. No new platform tab was created and all
eight pre-existing Chrome tabs were retained. This is a browser-permission blocker, not evidence
that the platform's previous CAPTCHA was resolved or that a platform page was opened.

After the show timeout, all nine old search relations were compared again and remained identical
to the backup. Active runs: 0. Batch 8 remains paused at item 4, revision 0, with its one original
Xiaohongshu attempt and 108 results. Captured application console warnings/errors: none.

## Checkpoint before the browser-authorization reply

Obtain the user's confirmation for the currently visible native browser-control permission.
After the connection is approved, an explicit page-show action may be needed again because the
first request timed out. Inspect the actual owned platform page; if a login/challenge is required,
hand it to the user and stop. Otherwise perform at most one authorized suffix continuation and
verify full snapshots/history and successful-platform preservation. No continuation has been
issued yet; the one-attempt search budget is unused. Live CAPTCHA handling and successful real
continuation are **not yet verified**. Do not repeat search automatically.

## Runtime handoff

- Local API: process 93908, exec session 69550, loopback 18000.
- SSH forward: process 93989, exec session 21145; local 5173 → remote 35986,
  remote 18010 → local 18000.
- Centaurus Vite: exec session 77698, isolated snapshot
  `/tmp/longtian-recovery-validation.EcUhyX/frontend`, loopback 35986.
- In-app browser: claimed tab 6, `/collection-batches/8`, marked handoff.
- Leave application and its forwards available. No product source changes or Git operations
  occurred in this live-upgrade turn; task documentation records the new authorization/evidence.

## Authorized continuation — 2026-08-28

The user subsequently replied **“ok”** to the explicit request to allow this application's
control of the current Chrome session, including signed-in pages, and continue the bounded
validation. On fresh inspection the native permission dialog was already absent. Main did not
click a permission button and does not claim it did; the subsequent product operation establishes
that the connection was usable.

### Page show and one continuation

- Rechecked batch 8: still paused at item 4, revision 0, run 51, 16/20 terms and 108 results.
- Clicked `打开平台` once after the prior timeout. The product reported `opened_homepage` and
  opened exactly one new owned Xiaohongshu official homepage. All nine tabs present at this
  resumed turn's pre-show baseline (including the original eight from the prior turn)
  were retained. No login or CAPTCHA prompt was shown on that actual page. Page show left
  all attempt counts, results and checkpoints unchanged; it was not treated as proof of recovery.
- Clicked **继续采集 exactly once**. It created only run **52**, protocol **2**, execution start
  position **16**. Its persisted full 20-term snapshot matches batch 8 exactly. Explicit worker
  completion proofs exist only for positions **16, 17, 18, 19**, each with 10 retained per-term
  matches and a persisted backend acknowledgment timestamp (not a platform-provided timestamp).
  No earlier term was executed by this new run.
- Run 52 started at **2026-08-28 02:48:35 CST** and finished at **02:48:41 CST**, status
  `completed_with_results`. Xiaohongshu now has 20/20 completed, zero remaining, and mixed
  legacy/explicit checkpoint evidence.

### Results and preservation

Run 52 contains **34 distinct results: 18 new and 16 repeated**. Its 16 repeated results overlap
run 51. The four terms have 40 term-result links; these are not 40 unique contents. Merging the
original 108 results and this attempt yields **126 unique contents**, a net increase of **18**.
The batch-level first-discovery totals are **114 new / 12 repeated**; the 16 rediscoveries do not
inflate either the union or the historical first-discovery categorization.

Batch 8 correctly ends `completed_with_failures`, revision **4**: the original Toutiao run 47
remains failed at 6/20 with seven results. Weibo 48, Kuaishou 49 and Douyin 50 retain their single
successful attempts, 20/20 progress and 37/183/28 results respectively. No historical failed-item
recovery, skip/cancel, other-platform rerun or model request was made.

Read-only comparisons with the pre-upgrade backup verify:

- Every old run, term snapshot, attempt and run/content/term relation remains identical.
- Other batches and all platform items except the expected batch-8 Xiaohongshu status update
  remain identical. Batch 8's own state changes are the authorized continuation and settlement.
- All original 468 content IDs, platform identities and first-seen timestamps are preserved.
  Rediscovered content may refresh its normal last-seen/metadata fields; these are not claimed
  to remain byte-identical after a real search.
- Database totals are **486 contents / 49 runs**; queued/running runs **0**; explicit historical
  recoveries **0**; SQLite integrity **OK**; foreign-key violations **0**.

### UI acceptance and remaining limits

The real application shows Xiaohongshu completed with a second attempt. Expanding history shows
both the old safety-verification failure (run 51) and the successful continuation (run 52).
Merged results display **全部 126 / 新增 114 / 再次命中 12**; the repeated filter and matching API
counts were checked. Application console warnings/errors remain empty.

The result view was restored to `全部 126` and marked as the user-facing deliverable. Final
browser metadata confirms all nine pre-show tab IDs (and the original eight) remain. The known
owned manual-page tab was closed during continuation. One unrelated local-app tab's URL changed
within its existing origin and two additional tabs appeared during validation; their ownership
was not established, so neither was closed and no claim is made that every browser URL stayed
unchanged. The selected Xiaohongshu original page and task-owned page were not conflated.

This validates the real official-homepage fallback, unchanged paused state until continue,
suffix execution, old-result preservation, deduplication and successful-platform isolation.
**No actual platform CAPTCHA appeared or was solved**, so no claim of CAPTCHA-resolution
acceptance follows. No forced second failure, skip/cancel or old-Toutiao recovery was performed;
their deterministic behavior remains covered by the existing offline tests. The one-attempt
search allowance is now consumed. Product source remains unchanged; no new full test rerun is
claimed. No Git commit, push or task archive has occurred.

### Independent evidence review

The existing `trellis-check` reviewer read this update and checked it against the source contracts.
It found no new code blocker or data inconsistency and confirmed that the evidence supports one
successful real suffix continuation, with the CAPTCHA, Toutiao, tab-ownership and one-attempt
limits above preserved. The reviewer did not replay live operations, inspect private runtime
data, edit files or rerun automated suites. Main's task-context validation passed (15 entries per
manifest), and both parent and derivative `git diff --check` passed.
