# Run 47 Follow-up Verification — 2026-08-28

## Scope and observed evidence

See `run47-followup-plan.md` for the approved one-term boundary and sanitized browser predicates.
The unchanged production snapshot on the owned exact-query page returned one main container,
zero candidates, no empty marker and no login/challenge. Nine real title headers pointed through
ordinary official jump links to external HTTP(S) destinations. One separate known anchorless
related-search header and one visible main pagination were also present; no loading marker was
visible. No external target was followed. The historical failed run has no captured DOM, so this
proves the current query's defect, not an exact reconstruction of run 47.

## Tests-first red gate

Only the test file was changed before the red gate; the unchanged client was explicitly synchronized
with it into the isolated Centaurus source snapshot. The existing verified test Chromium executed
the real production DOM script against synthetic fixtures, with no real-site requests.

Command (derivative working directory):

```sh
TEST_CHROMIUM_EXECUTABLE=/home/jonathanhu237/.cache/longtian-test-browsers/chrome/linux-152.0.7977.64/chrome-linux64/chrome \
  .venv/bin/python -m pytest -q tests/test_toutiao_parser.py \
  -k external_only_completed_dom_returns_zero
```

Result: **2 failed, 96 deselected**, 2.51 seconds, one inherited SQLAlchemy deprecation warning.
Both one- and two-wrapper fixtures failed at the behavioral `await client.search(...) == []`
assertion with `ToutiaoStructureChangedError`: no recognized results or empty state after the
existing 21 reads. This was not a missing-field, fixture, import or browser setup failure.
The implementer was then authorized to modify only the client and its parser regression tests.

## Private runtime preflight

Both search-run and batch APIs showed no active work before the backup. A fresh SQLite online
backup was created under ignored `runtime/toutiao-fix-backup.YCHL2G/before.sqlite3`, with directory
mode 0700 and file mode 0600. It remains on the Mac and is not included in remote synchronization.
Formal rule 1 and all existing run/batch/content records remain untouched at this checkpoint.

## Fixed-code offline gates

- Parser suite: **98 passed**, 9.81 seconds, zero skips, one inherited SQLAlchemy warning.
- Maintained derivative suite: **655 passed**, 18.79 seconds, zero skips, same inherited warning.
- Backend suite: **408 passed**, 8.62 seconds.
- Backend Ruff check and format: passed (51 files). Both edited derivative files are formatted;
  parent and derivative `git diff --check` pass.
- Scoped derivative Ruff reports five inherited diagnostics: two `UP009` coding headers and three
  `ISC004` preexisting fixture concatenations. Checking both exact HEAD versions via Ruff stdin
  reproduces the same five; no new lint finding. The first invocation found no Ruff in the
  derivative venv; the actual check used existing backend Ruff 0.16.4, without installing tools.
- The exact patched DOM script on the same owned real page now returns
  `external_only_complete=true`, with unchanged trusted origin, main count 1, candidate count 0,
  `empty=false`, `challenge=false`, `mandatory_login=false`. This is predicate validation, not yet
  a normal product run.

Frozen local and remote SHA-256 values agree:

```text
74c4a85b158295d432ee12f2a076f6477db6c0c7f6ee3443ce08b9c6128289a3  client.py
64da4f14cff29e721ed2cda98c80b43e91b45f68c5550b5b862b0a2dd961ed9c  test_toutiao_parser.py
```

## Independent review

The existing Trellis check agent independently reviewed the exact frozen diff/hashes, specs and
regression cases. No introduced defect or spec drift was found; no source change was requested.
Safety/origin/error precedence, final-read-only completion, bounded URL handling and the three
preexisting manual-recovery callback additions were verified. It distinguished predicate evidence
from product acceptance and did not claim the historical cause was known. Tests were run by main;
the reviewer did not independently rerun them. No separate type-check gate is claimed.

## Normal product verification

After confirming no active runs, batches or connection attempts, main gracefully stopped only the
owned idle backend/worker and restarted the same lightweight local service on port 18000. The
remote Vite/forwarding setup stayed available; no user Chrome process was closed. A fresh worker
then loaded the exact remotely validated source through the normal product service.

One temporary task rule (ID 6) contained only the failed seventh query. One normal API-created
Toutiao run (ID 53) used a maximum of five results and completed successfully:

- Started `2026-08-27T19:18:09.674457Z`; finished `2026-08-27T19:18:21.214212Z` (11.54 seconds).
- Status `completed_empty`, one term, zero new/repeated/total results.
- Position 0 has explicit `worker_term_completed` proof with `result_count=0` and a completion
  timestamp. No historical or next-term-inferred proof was substituted.
- The actual application route `/collection-runs/53` displayed normal completion / no matching
  content and all three counts at zero. This is the expected result for the demonstrated
  external-only page, not a claim that no discussions exist elsewhere on the web.
- No login/CAPTCHA restriction was observed, no such UI was acted on, and no additional platform,
  query, pagination, original-batch continuation or model call was made.

## Cleanup and preservation

Only temporary rule 6 was deleted through the normal API (HTTP 204) after completion. Run 53 and
its term/proof/history remain; its rule FK is now null. The original formal rule 1 remains the only
rule. Comparing every original row against the fresh backup found **zero changed/missing rows**
in all 14 monitoring/search relations: rules, object terms, issue terms, runs, run terms, contents,
run contents, content-term matches, completion proofs, batches, batch terms, items, attempts and
recoveries. This also preserves original content identities and first-seen values.

Content count remains 486; runs changed from 49 to 50 solely for run 53; batches remain 8. Integrity
is `ok`, FK errors are zero, and no run/batch is active. Original run 47 remains `structure_changed`
with its data intact; the other 14 uncompleted Toutiao queries were not automatically resumed.

The owned diagnostic tab was closed and the product's owned search page was released. All 12
original Chrome tab IDs remained. Two new unrelated user tabs were left untouched. The application
remains available on the run-53 result page. The ignored private backup remains local and recoverable.

The scoped repair and bounded live verification are complete. Git delivery was deferred at this
checkpoint; the user's subsequent commit/push request and exact-candidate checks are recorded in
`run47-delivery.md`. Archival and broader full-batch acceptance are not included.
