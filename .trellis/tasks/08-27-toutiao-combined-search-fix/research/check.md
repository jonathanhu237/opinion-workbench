# Independent Bounded-Readiness Review — 2026-08-27

Reviewed production changes are limited to the derivative's
`media_platform/toutiao/client.py` and `tests/test_toutiao_parser.py`.
The reviewer also checked the main-owned product-search and browser-search-adapter spec
updates. Unrelated work was not changed. The reviewer performed source/diff inspection,
not local/remote test execution or live browser/API/runtime operations.

## Findings (fixed)

No additional production defect was found or fixed by the reviewer.

The implementer/main corrected the new routed HTML fixture to declare UTF-8 after the
first patched run reached the title assertion but decoded Chinese fixture text incorrectly.
The reviewer verified this correction in source. This fixture correction is separate from
the readiness fix and is not evidence about a live site's character encoding.

## Findings (not fixed)

- The main session reports five existing Ruff diagnostics on the two files: two `UP009`
  encoding-header findings and three `ISC004` concatenations in old DOM fixtures. Main
  compared the same remote lint command against the committed baseline and confirmed
  all five already existed. They remain unchanged as instructed; they are not new patch
  regressions. Do not describe the raw derivative lint command as completely clean.
- The maintained suite reports one existing SQLAlchemy warning. No warning-producing
  dependency or unrelated source was changed in this bounded task.
- Historical run 34's underlying cause remains unknown. The synthetic delayed-render
  regression proves the one-snapshot readiness gap; it cannot establish the cause of an
  uncaptured historical failure. The already successful unmodified live run 43 returned
  two results and must not be described as a post-fix success.

No unresolved behavior or design finding was identified in the reviewed patch.

## Contract Checks

- Exactly one `goto` remains; navigation aborts propagate without reload, retry, private
  endpoint fallback or extra search requests. HTTP 403/429 still stop before DOM reads.
- The initial 1,500 ms wait is retained. `range(21)` permits at most 21 snapshots and
  20 additional 250 ms waits. This is a bounded read/wait budget, not a 6.5-second
  wall-clock guarantee: browser reads and scheduling also consume time.
- Every read has trusted-origin checks immediately before and after evaluation. Unsafe
  navigation stops without interpreting its snapshot or making another read.
- Only valid boolean flags, integer container count 0/1, an empty candidate list and no
  explicit empty marker can remain pending. Zero containers with candidates or an empty
  marker, non-dictionary snapshots, malformed field types and ambiguous containers stop.
- Recognized results/empty return immediately; challenge/login stop immediately when
  observed. Exhausted pending state remains `ToutiaoStructureChangedError`, never empty.
  The unchanged DOM script still scopes candidates and empty evidence to the main column.
- Awaitable delays and evaluation propagate cancellation. The new cancellation test uses
  the real product wrapper and CDP owned-page cleanup, verifies no next term or item,
  and preserves the unrelated page, borrowed context and browser.
- Mocked tests cover first/last permitted success, both pending container states, exact
  exhaustion, immediate terminal/invalid stops before and after a pending read, origin
  changes before/after reads, and cancellation during initial wait, readiness wait/read.
- The delayed-render regression runs the unchanged snapshot script in an actual Chromium
  page with routed synthetic official HTML. It captures a real pending snapshot before
  releasing rendering, aborts non-fixture requests, and asserts one navigation and correct
  main-column results. `TEST_CHROMIUM_EXECUTABLE` is test-only and requires an existing
  executable file; production browser discovery is unchanged.
- Both updated specs match these boundaries and explicitly distinguish synthetic proof
  from the unresolved historical cause. No additional spec change is requested.

## Verification Evidence

Execution evidence below is supplied by the main session, not independently replayed by
this reviewer:

- Red baseline: both new delayed-render browser cases failed against the old one-snapshot
  client at structure interpretation, before candidate/title assertions.
- Initial patched focused run: 75 passed and two fixture-encoding failures; UTF-8 correction
  was then made openly rather than weakening result assertions.
- After UTF-8 correction: focused parser suite **77 passed (7.33s)**; maintained derivative
  suite **589 passed (15.89s), zero skipped**, with the one existing warning noted above.
- Final frozen-source rerun after wrapping-only formatting: derivative format check
  passed for both changed files; the maintained suite passed **589 tests (15.86s), zero
  skipped**. Exact local/remote source SHA matches were recorded by the main session.
- Final backend gate: Ruff lint and format passed (47 files); **353 tests passed
  (5.66s), zero skipped**, as reported by the main session.
- TypeCheck: no separate Python type-check gate is configured for these derivative files;
  no TypeScript source changed in this task.
- Final main-run live acceptance: combined run 44 and identical repeat run 45 each
  completed with **0 new / 1 repeated** result. Both reused global content 137 and its
  original `first_seen` from unmodified run 43. Object-only baseline run 46 completed
  with **0 new / 5 repeated** results. Run 43 returned two results while runs 44/45
  returned one; this observed live variation establishes neither completeness nor a
  historical root cause, and is not attributed to the patch.
- Run 44 initially waited for ordinary Chrome remote-debugging consent before term
  progress. Main accepted that existing consent prompt under the user's prior explicit
  same-session authorization. This was not a platform login/challenge, a credential or
  security-setting change, or evidence of the readiness loop's duration.
- Main deleted only temporary rule 5 after all runs were terminal. Formal rule 1 was
  unchanged. Backup comparisons preserved every pre-existing row exactly across eight
  history tables; global content grew from 129 to 131 with all previous identities and
  `first_seen` values preserved and zero duplicate identities. Schema version remained
  9, integrity was OK, foreign-key violations were zero, and no active run/batch/item
  remained. Historical run 34 was untouched.
- Main closed the owned diagnostic tab and verified the original two tab IDs/URLs were
  unchanged, with exactly two tabs remaining. Final frontend and backend health checks
  returned HTTP 200. The frozen client/test hashes in `verification.md` match the tested
  remote copies. No source change followed those gates.

The final evidence was reconciled against main-owned `verification.md` and
`live-acceptance.md`. Independent static review and main-run verification are complete;
there is no remaining patch-specific finding or requested source/spec correction. The
five inherited derivative lint findings remain the explicit baseline exception above.

Product source is frozen from this reviewer's side. The reviewer wrote only this report;
no runtime/credential reads, remote mutations, browser operations, API/model requests,
Git writes, commit, push, parent gitlink movement or archival were performed.
