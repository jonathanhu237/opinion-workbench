# Live Product Acceptance — 2026-08-27

Main executed these bounded searches through the existing FastAPI product endpoints and borrowed
Chrome worker. This is product acceptance, not a standalone substitute crawler or direct diagnostic
DOM result. Each run used the one temporary task rule 5 and a per-term result limit of five.

## Outcomes

| Run | Code / query | Outcome | New | Repeated | Total |
| --- | --- | --- | --- | --- | --- |
| 43 | Unmodified client / `龙田街道 投诉` | completed_with_results | 2 | 0 | 2 |
| 44 | Patched client / `龙田街道 投诉` | completed_with_results | 0 | 1 | 1 |
| 45 | Patched client / identical repeat | completed_with_results | 0 | 1 | 1 |
| 46 | Patched client / object-only `龙田街道` | completed_with_results | 0 | 5 | 5 |

The owned idle backend was restarted after the offline gates; matching local/remote SHA-256 values
confirm the client and tests are the versions validated remotely. Run 44 spent most of its elapsed
time waiting for the repeated Chrome remote-debugging prompt before term progress. Main accepted
that expected prompt using Computer Use under the user's existing explicit same-session permission.
It was not a platform login/challenge and involved no new setting or credential. Do not treat the
run's total elapsed time as the DOM-readiness wait. Runs 45 and 46 took approximately 2.29 and 3.02
seconds respectively.

The current official search result set varied across calls: unmodified run 43 found two recognized
items, whereas runs 44/45 found one. These bounded live samples do not prove complete coverage or
that the patch caused this variation. They prove successful product execution and reuse of the
overlapping item; the deterministic delayed-DOM red/green tests establish the repaired defect.
Historical run 34 remains unchanged and its exact cause is not established.

## Observed Deduplication

- Run 43 first introduced global content rows 136 and 137.
- Runs 44 and 45 both reference global row 137, both classify it as `repeated`, and retain exactly
  the same `first_seen_at` as run 43. No second row was inserted for that identity.
- Run 46 found five existing items and inserted no new content rows.
- Across all stored content, duplicate `(platform, platform_content_id)` groups: **0**.

## Cleanup and Preservation

After all runs were terminal, main deleted only temporary rule 5 through the product API. The
original formal rule 1 and its five object terms are byte-for-byte equivalent at the row-value
level to the private pre-test backup; issue terms remain empty. Only that one formal rule remains.
The backup stays private, local and ignored; no database/profile/key was synchronized to Centaurus.

Read-only SQLite comparisons against the backup confirmed:

| Table / data | Before | After | Preservation |
| --- | --- | --- | --- |
| Search runs | 39 | 43 | Every original row exactly unchanged |
| Run terms | 131 | 135 | Every original row exactly unchanged |
| Run-content observations | 209 | 218 | Every original row exactly unchanged |
| Run-content-term observations | 215 | 224 | Every original row exactly unchanged |
| Search batches | 7 | 7 | Exactly unchanged |
| Batch terms | 19 | 19 | Exactly unchanged |
| Batch items | 28 | 28 | Exactly unchanged |
| Batch attempts | 23 | 23 | Exactly unchanged |
| Global content | 129 | 131 | All original IDs, platform identities and first-seen times retained |

New run history 43–46 is retained after rule deletion, with its rule references null and its
snapshotted terms/results intact. SQLite schema remains version 9; integrity check is `ok`, foreign
key errors are zero, and active runs/batches/batch items are all zero.

Only the owned diagnostic Chrome tab was closed. The two pre-existing user tab IDs and URLs were
preserved; no product search tab remained after terminal cleanup. The application remains running.
No model calls, other-platform searches, broad pagination, safety bypass, Git writes, gitlink
movement, commit, push or archival were performed in this task.
