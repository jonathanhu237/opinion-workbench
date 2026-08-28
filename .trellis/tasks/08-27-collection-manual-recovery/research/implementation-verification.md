# Implementation and verification log

## Approval and boundary

The user approved the final plan on 2026-08-28. Context validation passed (15 references per
manifest) and the task was activated before product implementation. Native Trellis implementers
own the derivative, backend and frontend in contract order; main owns coordination, evidence,
spec changes and all live runtime/Git decisions. No live batch operations or Git delivery occur
as part of the offline implementation gate.

## Baseline

- Parent main: `12df65d992240a60e4eae6f6ba83e2fb2562017d`.
- Derivative main: `8a7b620628d7447f05cf565a446eae31779f576a`, initially clean.
- Preserve pre-existing edits to frontend AI settings/monitoring rules and their tests, the
  frontend state-management spec, and AI-configuration task documents/evidence.
- Centaurus SSH is reachable. Use an isolated code-only validation snapshot at
  `/tmp/longtian-recovery-validation.EcUhyX` so tests do not change the running frontend checkout.
- Dependencies are symlinks to the existing remote environments. Backend tests explicitly set
  `PYTHONPATH=src` to import this isolated snapshot, not the existing editable installation.
- Source-only rsync excludes `.git`, `.env*`, runtime, database files, browser data, dependencies,
  logs and generated caches. No user DB, credentials or browser state is copied.
- Test-only Chromium is
  `/home/jonathanhu237/.cache/longtian-test-browsers/chrome/linux-152.0.7977.64/chrome-linux64/chrome`.
- Unchanged backend: `PYTHONPATH=src .venv/bin/pytest -q tests` — **353 passed**;
  `.venv/bin/ruff check .` — **passed**.
- Unchanged derivative: explicit test Chromium + `.venv/bin/pytest -q tests` — **589 passed**,
  zero skips; one inherited SQLAlchemy deprecation warning.
- Frontend baseline including the user's existing edits: **166 passed** in 10 test files.
- Isolated frontend must explicitly select both `node@24` and `pnpm@11.14.0` via mise;
  the first attempt selected only Node and stopped before tests because the pnpm shim had no
  version configured. No global tooling configuration was changed.

## Frozen derivative protocol

Search protocol v2 retains separate unchanged auth-v2 frames. `term_completed` carries the exact
request ID, platform, local term position and item count. `manual_page` carries request ID,
platform and `action=show|close`; its event returns the same action and one action-specific fixed
outcome. No URLs, terms, cookies or scripts enter that command. The backend run service maps
suffix-local positions once. Implementation and regression evidence will be appended below.

## First derivative gates

- Tests-only synchronization to the unchanged baseline failed collection because the new
  `tools.product_search_recovery` module did not exist. This is structural red evidence only,
  not an executed behavioral regression or live-platform test.
- First coherent patched focused suite: **170 passed, 2 failed**. Both failures were old Douyin
  assertions that a structure-failure page must close; the approved recovery contract now retains
  usable owned failure pages. The implementer is updating those assertions to prove retention
  and that failed terms do not emit completion, not discarding the assertions.
- After broader cases were added, the full derivative suite reached **629 passed, 1 failed**:
  an additional direct adapter caller in `test_toutiao_parser.py` still omitted the new mandatory
  completion callback. The fixture was updated to pass it and assert it is not awaited on cancel.
- Scoped remote Ruff reports 31 inherited diagnostics (28 in existing `cdp_browser.py`, two
  Weibo, one Kuaishou). The implementer compared against HEAD with the same checker. The newly
  touched Toutiao parser test adds four inherited findings (UP009 plus three ISC004); no new
  diagnostics were introduced. New recovery helper/tests and other modified files are clean.
- Final derivative stage gate: **630 passed**, zero skips, 16.00s, with the inherited SQLAlchemy
  deprecation warning only. The exact test-only Chromium override was active. Independent
  derivative review is now running; backend/frontend integration remains in progress.

## Independent review regression

The reviewer found an old browser's delayed disconnected callback could invalidate a newly
connected manual-page session. A tests-only remote run reproduced this at `session.is_connected()`:
**1 failed** in 0.84s. The narrow fix captures/validates the registration's session event rather than
reading the newest event on callback. It does not change the public protocol or API.

After the fix, recovery/auth-worker suites: **63 passed**, 1.26s; both files pass Ruff and format
check. Added offline sentinels also cover actual session-level manual disconnect/cancel/shutdown,
owned-page cleanup and preserving the borrowed browser/context.

Full derivative suite after independent review: **634 passed**, zero skips, 15.95s. The scoped
inherited Ruff baseline remains 35 diagnostics; no new diagnostics were introduced.

## Initial backend and legacy gates

- New backend focused recovery suite: **15 passed**, 0.79s. Full regression/hardening is pending.
- Before syncing new backend code, main seeded a separate synthetic database using the actual v9
  implementation: one failed Toutiao item at term position 6, three completed-empty platforms,
  one paused XHS item at position 16, and one partial XHS result. This resembles the relevant old
  history shape but contains no copied user data.
- After migration to v10, all nine pre-existing search relations have **identical row counts and
  SHA-256 hashes of old columns**, preserving IDs, terms, observations, relationships and timestamps.
  Foreign-key errors: **0**. Inferred completion proofs: **82**, all with null historical completion time.
- Projected checkpoints are 6/20 for failed Toutiao, 20/20 for each successful platform and 16/20
  for paused XHS. The current pause stays on item4, next XHS position16; no work was executed.
- One initial inspection command used an API field name on the internal record and stopped with
  AttributeError after migration. Correcting it to `item.checkpoint` verified the values above;
  this was a harness typo, not a migration failure.

## First complete cross-layer gates

- Backend full regression initially exposed six historical-fixture mismatches after the schema and
  proof contracts changed. Those fixtures now create actual historical schemas and compare old
  columns separately from v10 defaults. A subsequent run was **386 passed, 1 failed**: one v8 fixture
  still invoked the current repository. It was corrected using historical SQL, not weakened assertions.
- With expanded concurrency/strict-body/legacy checks: backend **395 passed**, 8.41s;
  `ruff check src tests` and `ruff format --check src tests` passed (50 files).
- Frontend: typecheck, lint (0 warnings/errors), **209 tests in 11 files**, production build and
  format check all passed. Existing unrelated AI-settings and monitoring-rule edits remain preserved.
- All checks run in the Centaurus isolated snapshot; no live application/database was upgraded.

## Synthetic HTTP and UI acceptance

`research/preview_app.py` uses the real API/service/repositories but a synthetic worker whose process
launcher raises if browser launch is attempted. It requires a database under the isolated remote
directory and serves the actual built frontend. No credentials, models or real platform requests.

- `verify_api_recovery.py` independently proved a failed seventh term after six confirmations,
  exact suffix `(对象 7, 对象 8)` on continue, two immutable attempts, partial A/B then B/C union to
  three results, earliest supporting run IDs, stale continue/skip rejection, show-only behavior,
  explicit skip and restart persistence. **PASS** on a fresh synthetic database. An initial harness
  assumption about ascending history order was corrected to the existing descending API contract.
- The in-app browser exercised the built frontend through local port 18009 forwarded to that isolated
  server. The page is explicitly labelled `人工恢复界面验收（模拟）`; no existing production tab was used.
- Clicked `打开平台`: fixed homepage outcome feedback appeared, with no attempt/progress advance.
- Clicked `继续采集`: Toutiao changed from 6/8 paused to 8/8 complete, retaining two attempts; Weibo
  then paused with login-specific guidance. The interface did not pretend a login/CAPTCHA was solved.
- Opened merged results: three distinct synthetic records with source attempts 1/1/2. Attempt history
  preserved both the structure failure and later success. `再次命中 0` displayed the honest empty filter.
- Clicked `跳过此平台`: Weibo became `已跳过`; batch showed `部分平台未完成` and 2/2 ended. Three
  Toutiao results remained visible. Rendered screenshots retained the existing Shadcn theme/layout.
- Keyboard activation/focus, wrapping action rows, pending-show cancellation and source-run opening
  are covered by frontend interaction tests. This is not a claim of real mobile-browser or CAPTCHA QA.

## Final independent-review regression evidence

Before source fixes, tests-only synchronization reproduced:

- Backend **4 failed / 2 passed**: deleting the completion tail still yielded a trusted v2 checkpoint;
  deleting all child-run term rows made batch detail/skip/cancel fail with 503.
- Frontend **5 failed / 27 passed**: unreadable damaged child snapshots (0/1 term rows) and the valid
  short `item=running` / `latest run=terminal` commit window were rejected by the batch decoder.

Fixes preserve the frozen public fields: strict proof/current consistency, a batch-only truthful
read projection for damaged child terms, and explicit recognition of the run/item commit window.
Independent run validation remains strict. Final post-fix gates are recorded below when complete.

An additional tests-only run reproduced **3 backend failures**: missing final proof on an already
successful v2 run, a failed result write leaving an active child behind, and a failed item write
misclassifying an already successful child as failed. The expanded frontend set reproduced
**6 failures / 27 passes**, including an out-of-range historical position that should remain readonly
and recovery-unavailable rather than hide the entire batch. Normal independent-run validation is not
relaxed. Browser error/warning logs for the synthetic UI acceptance were **empty**.

## Final frozen-source gate

- Backend: **408 passed**, 9.47s; Ruff check and format check passed (50 files).
- Frontend: **215 passed in 11 files**, 7.80s; typecheck, lint (0 errors/warnings), build and
  formatting all passed.
- Frozen-install gate also passed: removed only the isolated frontend dependency symlink (not its
  shared target), then `pnpm install --frozen-lockfile` installed 447 packages in 8.6s into that test
  directory. Repeated all frontend gates with these fresh dependencies: **215 passed**, 7.72s,
  plus format/lint/typecheck/build. Local and remote package/lockfile hashes match; neither file
  changed. The running shared checkout's dependencies were not modified.
- Derivative: **634 passed**, zero skips; source unchanged since its reviewed full gate. The
  35 inherited Ruff diagnostics remain baseline findings, not newly introduced or suppressed.
- Independent synthetic HTTP acceptance repeated against the final backend on a fresh isolated
  database: **PASS** for suffix-only retry, union counts/provenance, stale controls, show-only, skip
  and restart persistence.
- Restarted **only the synthetic preview server**, loaded final frontend assets and rechecked the
  persisted result page: Toutiao 8/8, three results, two attempts; Weibo skipped; truthful partial
  completion. Browser warning/error log remained empty. This is not a production restart.
- Parent and derivative `git diff --check` passed. Both context manifests validate (15 entries each).
- The following SHA-256 hashes match locally and in the final Centaurus snapshot:

```text
a7f295cbd17eb7ac44b60b7ef37e80a092cae196dc4351d5fbaba77af29bdd26  backend/src/longtian_api/search_checkpoints.py
e1d001ba5d24f70b6c648d1901b437d795509da9e41b0402aab8e46312d279b0  backend/src/longtian_api/repositories/search_runs.py
b7174774e9b4d29310979ed31a63d2b5d62ff53b11d5c3f3afe96e4e2a0ec793  backend/src/longtian_api/repositories/search_batches.py
f7c16116f2061338102a4d484fdac1620837ed7e541178017079edf4c5f88923  backend/src/longtian_api/services/search_batches.py
70976873469401ff1a27bb7e4a457ecd40288b2a20d84596302d31a82256c951  backend/tests/test_search_recovery.py
d3fc5eb1caaeca9f7c74ce51347eca60675a5d6ac4a8b28a335375829e8079d6  frontend/src/lib/api/search-batches.ts
29bae075f6d45c184b7d3dd17d00c87992b8d294e7c95e408b9eda5ca3c96ae7  frontend/src/lib/api/search-batches.test.ts
```

## Remaining boundary

Implementation/offline checks are complete. The user's existing runtime database and batch 8 have
not been migrated, restarted, continued, skipped or cancelled. Real official-page/CAPTCHA handling
and real collection continuation remain pending the user's explicit choice of a bounded task.
No model API call, commit, push, gitlink update, archive or journal auto-commit occurred. The task
stays active; Git delivery and live acceptance are not represented as completed by these tests.

Cleanup closed only this turn's synthetic browser tab and stopped its isolated preview server and
port-18009 SSH forward. Existing application services and user browser tabs remain untouched. The
code-only validation snapshot and synthetic fixtures are retained remotely for reproducible checks.
