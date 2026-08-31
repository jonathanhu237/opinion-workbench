# One-Rule Cleanup and Next-Step Audit — 2026-08-27

## Scope and Exact Targets

The user asked to retain one rule group and continue. The main session re-read the real product
API and confirmed the original enabled rule 1 (`龙田街道及四个社区`) and exactly two disabled
task-created rules: 3 (`验收0827·基础搜索`) and 4 (`验收0827·投诉组合`). No other rule existed.
All stored runs/batches were terminal. No product rule-count restriction was introduced.

The original five objects remain unchanged: `龙田街道`, `龙田社区`, `老坑社区`, `竹坑社区`,
`南布社区`. Its issue list remains empty; cleanup did not invent search terms.

## Execution and Preservation

- Inspected the live schema: the two rule-term tables use `CASCADE`; `search_runs` and
  `search_batches` use `SET NULL`. The existing repository deletes only the selected rule.
- Created a new SQLite backup in a task-owned, ignored local runtime directory with private
  permissions. Verified its integrity, foreign keys and exact three-rule state before deletion.
  The backup was not synchronized and no credential file was read.
- Existing `DELETE /api/v1/monitoring-rules/3` and `/4` each returned HTTP 204.
- Compared every row of all nine search tables with the fresh backup in stable row order. The
  only allowed differences were rule references changing from 3/4 to null: 16 runs and 4 batches.
- Compared all fields of original rule 1 and its ordered object/issue rows exactly; unchanged.
- Final rule IDs: `[1]`; database integrity: `ok`; foreign-key violations: `0`.
- Post-cleanup GET requests for run 35 and batch 6 both returned HTTP 200, retaining the historical
  rule name, `龙田街道 投诉` query and terminal status, with only the live rule reference null.

| Preserved table | Rows |
| --- | ---: |
| search_runs | 39 |
| search_run_terms | 131 |
| search_contents | 129 |
| search_run_contents | 209 |
| search_run_content_terms | 215 |
| search_batches | 7 |
| search_batch_terms | 19 |
| search_batch_items | 28 |
| search_batch_attempts | 23 |

History snapshots and results are still available. The private backup enables recovery of the
removed definitions; any future recovery must be separately approved and selective, not a blind
replacement of the live database. This follow-up did not change AI settings or call a provider.

## Toutiao Source Audit — Not a Root-Cause Claim

The previous combined query `龙田街道 投诉` ended in `structure_changed` (run 34), while the
baseline succeeded (run 29). No new search or live page inspection was performed for this audit.

Current source behavior:

- `third_party/MediaCrawler/media_platform/toutiao/client.py:180` builds a normal URL-encoded
  keyword query. There is no local Boolean parser rejecting a space-combined phrase.
- `client.py:194` waits a fixed 1.5 seconds after DOM content load before taking its only result
  snapshot. `client.py:213` checks for exactly one visible `.s-result-list` container.
- An untrusted post-navigation URL, unknown DOM/candidates, or a page exposing neither recognized
  results nor a known empty state raises `ToutiaoStructureChangedError`. Normalization failure can raise the same
  exception in `product_search.py:69`.
- `product_search.py:101` maps these different causes to the same `structure_changed` outcome.
  The stored outcome alone therefore cannot distinguish loading timing, an empty-state variant,
  an unsupported result type/link or a genuine changed layout.

The root cause is unresolved. A bounded proposed repair task should reproduce only this query,
capture sanitized structure/readiness evidence without page content or authentication material,
then add the smallest demonstrated adapter fix and regression test. Do not assume a longer sleep
or broad fallback selector fixes it; do not relabel failure as empty success. Such product work
requires its own reviewed Trellis scope; it has not started here.

## Downstream Scope Reminder

The current parent PRD supersedes the earlier separate AI screening workflow. The remaining
sequence is actual text/image/video acquisition, then one manual `生成汇总` flow with reusable
per-item evidence and an evidence-only final composition call. Do not reactivate the deferred
standalone screening child or silently implement media/summary work during rule cleanup.

Existing uncommitted API-key-mask and rule-placeholder frontend edits were preserved. No
product/submodule code, services, credentials, Git commits, pushes or archives changed here.

## Quality and Spec Review

- Local `git diff --check` and task context validation passed; the MediaCrawler worktree is clean.
- Sanitized task documents were synchronized one-way to Centaurus; task validation also passed
  there. Runtime data, backup and credentials were not synchronized.
- Re-read the final rules API projection: exactly one enabled rule, with the original five objects
  and empty issue list. Confirmed ignored backup directory mode 700 and database mode 600.
- No application source changed in this follow-up, so no source build/test rerun was needed.
  Earlier frontend checks are separate evidence, not a test of the database cleanup.
- Spec review found no new API/schema/behavior contract: rule-reference nulling and immutable
  snapshots are already documented in backend product-search and batch-search guidelines. Keep
  the unproven Toutiao timing/structure hypotheses in task research, not as established spec facts.
- Independent sanitized-evidence review passed after correcting source citations, narrowing
  navigation wording and updating the task resume notes. It did not independently replay live
  operations. See `rule-cleanup-check.md`; Toutiao's root cause remains unresolved.
