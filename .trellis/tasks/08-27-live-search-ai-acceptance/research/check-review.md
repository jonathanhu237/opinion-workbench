# Independent Evidence Review — 2026-08-27

## Scope and Conclusion

Reviewed the updated PRD, design, execution plan, task notes and `verification.md` against the
injected contracts and relevant committed code. This reviews recorded main-session evidence;
it does **not** independently replay browser, provider, API, database, secret, log or service
operations. Only this review file was written.

The earlier authorization-blocked conclusion is superseded. Following user authorization, the
bounded checks finished with mixed outcomes: batch 5 returned five results on each platform;
batch 6 returned five on four platforms while Toutiao run 34 failed with `structure_changed`;
batch 7 repeated only the four successful combined targets. Cancelled batch 4 remains historical,
not rewritten or continued. The PRD explicitly defines its checkmarks as fulfilled evidence/reporting
requirements, not universal platform success.

Recorded evidence supports deduplication for the 15 overlapping Weibo/Douyin/Xiaohongshu identities:
same global rows, repeated classification, preserved first-seen and advanced last-seen timestamps.
Kuaishou's zero overlap is correctly inconclusive; Toutiao was not repeated. No general relevance
benchmark or event-level deduplication is claimed.

The two rendered originals support the stated limited contrast: a local Weibo complaint dated
2024-03-06 versus a Xiaohongshu complaint naming Fuqing's namesake town. They do not verify the
allegations or establish current incidents. Title/snippet observations are distinguished from
unwatched video content. The one saved-revision synthetic text test (HTTP 200, 0.587 seconds)
was not repeated and uploaded no collected content. Media acquisition, per-post AI and summaries
remain unimplemented. Preservation uses the resumed two-tab baseline; the earlier 11-tab snapshot
is clearly historical. Live SQL/UI/tab observations remain main-session evidence.

## Findings (fixed)

- Updated this review's stale blocked/unrun conclusions to reflect the completed bounded checks.
- Main corrected the literal backup database path to sanitized runtime wording and changed
  ambiguous “negative-keyword” wording to “complaint-keyword” after review feedback.
- Main records the terminal-counter caveat and used new batches after authorization. No product
  fixes or other-file edits were made by this reviewer.

## Findings (not fixed)

- **Misleading terminal-progress copy:**
  `frontend/src/routes/collection-batch-detail.tsx:368` and
  `frontend/src/routes/collection-runs.tsx:120` label `terminal_item_count` as “已完成”.
  `backend/src/longtian_api/services/search_batches.py:441` includes completed, failed and cancelled
  items in that count. Thus “已完成 5 / 5” does not mean five successful searches, even though the
  cancelled header and per-platform failure/cancellation labels are accurate. The evidence now
  calls this out. A wording correction and regression test require separately authorized product
  work; no code or spec change was made here.
- **Recorded Toutiao combined-search failure:** run 34 remains `structure_changed`; its exact
  underlying cause has not been diagnosed. Product investigation/fixes require separate direction.
  No retry, false empty-success classification or speculative root cause was introduced.

## Verification

- Git: HEAD `d5bc49f`; no tracked source/gitlink differences; MediaCrawler worktree clean.
  Only the current task directory was untracked. `git diff --check` and task context validation
  passed after this review was written.
- Arithmetic: baseline **25 = 12 new + 13 repeated**; combined **20 = 20 + 0**;
  repeat **20 = 5 + 15**. Total **65 = 37 new + 28 repeated**; **92 + 37 = 129** global contents.
  The **5 + 5 + 4 = 14** new run snapshots match the reported run range 29–42. Observations,
  unique global contents and newly published events are correctly distinguished.
- Recorded final checks: 14 matching query/cap snapshots and serial timing; integrity OK/FK zero;
  original non-content rows and content identities/first-seen preserved; no active runs/batches;
  rules 3/4 disabled; rule 1 and AI revision unchanged. Run 39's new-zero/repeated-five filters and
  clean console are now verified by the main session, not left as untested claims.
- Lint: prior unchanged-source Centaurus baseline **PASS**, not rerun.
- TypeCheck: prior TypeScript baseline **PASS**, not rerun; no separate Python gate is configured.
- Tests: prior backend **353** / frontend **164 PASS**, not rerun under this bounded review.
  Baseline source: `archive/2026-08/08-27-monitoring-rule-combinations/verification.md` and its
  `research/check-review.md`. These automated passes are not substituted for live acceptance.
- No product/spec/template update was made or authorized. Independent evidence review is complete;
  the task remains `in_progress` for main-session handoff, without commit, push or archival.
