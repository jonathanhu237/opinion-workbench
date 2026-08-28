# Child B independent review and gate evidence

Reviewed 2026-08-29 by the reused `a_frontend` agent, independently of B's
implementers. Main owns the formal Trellis gate and task/spec state. This review
used `trellis-check`, the before-development boundary checklist, FastAPI guidance
and the existing frontend/UI accessibility guidance; it did not spawn agents.

Read B's full PRD/design/implementation/check manifest, both implementation
reports and HTTP contract, parent G1/G3/G7 and scheduling/migration boundaries,
A's collection handoff and relevant backend/frontend specs. The main-owned
`collection-schedule-guidelines.md` was reread after the fixes/spec update;
no remaining factual contract drift was found.

## Findings (fixed)

1. **P2 — invalid persisted projections escaped as successful HTTP responses.**
   Schedule/occurrence output models only checked basic field types. Empty or
   reversed platform children, malformed timestamps, a dangling rule reference,
   invalid rule labels and reversed missed ranges returned 200 even though the
   frontend rejected them. A synthetic private sentinel in a timestamp was also
   returned as data. Added strict UTC-string and state/link/count/name/platform
   invariants to the owning response models, retaining the exact public fields
   and timestamp strings. Existing route/repository error boundaries now return
   constant `503 collection_schedule_storage_unavailable` with `no-store`.
   Twelve API corruption cases cover schedule list/detail and affected history;
   a positive case preserves a deleted rule's linked interrupted/manual-paused
   batch when the schedule is explicitly disabled. No repair or work is caused
   by those reads.

2. **P2 — internal timer admission bypassed the platform projection boundary.**
   Main's follow-up trace identified that `_platforms` and scheduled batch
   insertion consumed raw persisted children independently of public POST
   validation. A damaged empty/reversed set could reach the batch path. The
   same canonical validator now guards response projection, claim reads and
   the transaction's pre-link re-read. Four regressions cover empty/reversed
   children both before claim and between claim/link. Before-claim failure
   rolls back the occurrence/advance transaction; post-claim failure records a
   bounded storage skip. Both retain zero batches, zero worker calls and no
   browser owner.

3. **P2 — same-revision rule deletion stranded an open editor/confirmation.**
   Deletion uses `ON DELETE SET NULL` and does not increment the schedule
   revision. The old dialog retained its non-null rule ID while refreshed data
   had a null reference; revision-only stale detection offered no adoption
   action, so repeated disable confirmation kept submitting the removed ID.
   The shared stale-configuration predicate now compares the rule reference
   and current rule state at the same revision as well as newer revisions.
   Dirty drafts and confirmations expose explicit adoption followed by a
   separate save/confirm. Tests cover deletion and disablement, preserved dirty
   interval values, a retained deleted-rule option, occurrence-only updates
   that do not invalidate drafts, and rejection of older dependency reads as a
   rebase source. No new fields or automatic save were introduced.

The first API regression run failed all 9 initial cases with 200 instead of
503; the first frontend regression run failed the two new same-revision cases
while its 476 existing tests passed. Subsequent tests expanded the boundaries
above. A focused frontend run initially checked immediately after Query's
asynchronous notification (3 failures/107 passes); the tests now await the
visible adoption control before asserting disabled state, without relaxing the
behavior. The final gates below supersede all failed/intermediate runs.

## Reviewed scope and evidence

| Gate / boundary | Evidence checked |
| --- | --- |
| G1 migration | Genuine v12 construction from historical migrations, populated old collection/legacy rows plus A prompt/eligibility state, exact preexisting table/column projections before/after v13, reopen, WAL/FK/busy-timeout checks, actual DDL rollback, forward-version rejection and multi-platform replacement rollback. v13 only appends its three owned tables/indexes. |
| Configuration | Strict minute/hour normalization through 1–43,200 minutes; disabled creation; full-replacement CAS; same-value save increments revision; enabled saves reset future due, disabled saves clear it; timer does not change configuration revision. Deleted rules retain labels/history. |
| Current-rule execution | Current valid rule is loaded and rechecked in the link transaction, with frozen batch terms/name/platforms. Rule edit/deletion does not mutate old batch snapshots. Disabled/missing/invalid/over-limit rules have distinct skipped reasons. |
| Durable admission | Unique occurrence key and UUID, atomic claim/advance, one shared existing batch insertion owner, batch/terms/items/link in one transaction before runner creation. Link-trigger failure rolls everything back. Concurrent polls/token replay produce one batch and no second runner. |
| Browser ownership | Existing coordinator is the only lease owner. Busy standalone/account/enrichment/result-open and manual-pause tests preserve their owner; the paused batch is unchanged. Availability is no-I/O session evidence, false after backend/worker restart or failure; readiness alone is insufficient. Manual connected/disconnected checks establish browser evidence without claiming all platform logins. |
| Clock/startup | Exact due and duplicate polls, backward rollback, bounded forward range, all 101 schedules across storage pages, 100,000 missed offline rounds in one range, first future aligned due and repeated startup without catch-up calls. |
| Crash/shutdown | Before-link, after-link and after-launch-marker crashes never replay; existing linked batches retain explicit paused recovery. Disable does not cancel active work. Shutdown drains slow dispatch, blocks admission after a pending rule read, uses bounded monotonic waits and still executes later cleanup after an earlier close failure. |
| A+B handoff | A's shared fixture asserts the browser is released before one batch callback. Two platform sources create one initial-analysis job and two synthetic completions; repeating the scheduled collection adds no duplicate job/model work. Scheduler contains no direct analysis/report/model call. Existing A pause/cancel/source tests remain in the full gate. |
| G7 HTTP | Exact 201/200 schemas, strict inputs and safe IDs, local Host/Origin/JSON guard, constant domain/storage errors and no-store. Side-effect-free list/detail/history. Corrupt projections and timer reads now share bounded validation. |
| G7 frontend | 77 independent strict decoder tests; URL cursor bounds/order/identity, exact status/code/message, UTC fields, saved enablement versus rollout, pending locks, separate enable/disable confirmations, dirty CAS recovery, late GET/save ordering, history links/focus and unchanged manual collection. Final route suite has 34 tests. |

No additional architecture, dependency, scheduler algorithm, platform support,
model transport, report, rollout or visual design change was made. Existing
civic tokens, Base UI controls and labelled error/focus behavior remain.

## Files changed by this review

Backend:

- `backend/src/longtian_api/schemas/collection_schedules.py`
- `backend/src/longtian_api/services/collection_schedules.py`
- `backend/src/longtian_api/repositories/collection_schedules.py`
- `backend/src/longtian_api/repositories/search_batches.py`
- `backend/tests/test_collection_schedule_api.py`
- `backend/tests/test_collection_schedules.py`

Frontend:

- `frontend/src/hooks/use-collection-schedules.ts`
- `frontend/src/routes/collection-schedules.tsx`
- `frontend/src/routes/collection-schedule-editor.tsx`
- `frontend/src/routes/collection-schedules.test.tsx`

Plus this evidence file. All other A/B implementation, fixture, spec and task
changes were preserved. Main owns the corresponding spec clarification.

## Final verification

All source edits and allowed formatting were local. The review respected the
main's read-only browser-QA freeze; source sync/testing began only after main
reported owned QA services/tunnels stopped and released both snapshots. No
source synchronization occurred while a test/build was running.

Remote root: `Centaurus:/tmp/longtian-decoupling-impl.dMCxsd`. Backend commands,
run from its `backend` directory:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests --tb=short
```

Frontend commands, run from its `frontend` directory:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

| Gate | Observed final result |
| --- | --- |
| Backend locked dependencies | Passed; 54 resolved, 52 checked |
| Backend Ruff | All checks passed; 110 files already formatted |
| Backend complete suite | **740 passed in 28.64s**, no skipped tests |
| Frontend frozen dependencies | Passed; already up to date, pnpm 11.14.0 |
| Frontend format/lint | Passed; 0 warnings/0 errors, 92 files |
| Frontend TypeScript | Passed |
| Frontend complete suite | **481 passed in 20 files, 8.87s** |
| Frontend production build | Passed; 2,353 modules transformed |
| Local whitespace | `git diff --check -- backend frontend` passed |
| Post-gate parity | Both checksum-only `rsync -rnci` dry runs returned empty output |
| Python type checker | Not configured; no type-check pass claimed |

Focused post-fix evidence: 84 scheduling/API/repository/session/smoke tests
passed in 6.90s with Ruff; 110 frontend schedule decoder/route tests passed in
4.06s before the final older-read regression was added. The review adds 17
backend and 5 frontend tests to the handed-off 723/476 baseline.

One-way synchronization used `rsync -a`, never `--delete`. Backend exclusions:
`.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.env*`, `*.pyc`,
`runtime`, `profiles`, `media`. Frontend exclusions: `.git`, `node_modules`,
`dist`, `.env*`, `*.local`, `.vite`, `.cache`, `coverage`, `*.tsbuildinfo`,
`runtime`, `profiles`, `media`. Dry runs used the same exclusions.

Final SHA-256 manifest hashes match locally and remotely:

| Manifest | Files | SHA-256 |
| --- | --- | --- |
| Backend Python sources/tests plus `pyproject.toml`/`uv.lock` | 111 | `17a68f59f98f2cdae5055fbffa57208f1dbd9591337ba160e748835548a6b64a` |
| Frontend source/config/assets, excluding dependencies/runtime/build/cache | 109 | `960de658334675a083a72a6f0d46682275518bb51b8794a3bd9d89d1d7a0e8d1` |

Manifests use locally discovered `rg --files --hidden` paths in `LC_ALL=C sort`
order, then `xargs shasum -a 256 | shasum -a 256`. Since remote `rg` is absent,
the same local sorted path list was piped to remote `xargs sha256sum | sha256sum`
from the isolated root; failed empty-list probe output was not used as parity
evidence. Only this task evidence document was written after the final source
parity check.

## Browser acceptance and remaining boundaries

Main's [isolated browser acceptance](./browser-acceptance.md) passed on the
stable pre-review UI: disabled creation, explicit enable, enabled interval edit,
disable, multi-page history/reload/focus, linked interrupted/manual-pause
controls, 390px form and non-overflowing narrow history, and no console warnings
or errors. Fake collection/model/media counters stayed **2/0/0** throughout.
The review's later changes retain output shape/layout; their dependency-race
and corruption behavior is covered by the final regression gates above, not a
new claimed browser pass. Main closed the owned services/tunnels; this reviewer
started none.

No known B blocker remains. Main still owns the formal child acceptance and C
activation. C owns automatic text reports and final rollout; both production
automation gates remain off by default. Tests do not establish live browser
availability, platform/account quality, provider quality or production-data
migration safety. No live account/provider call, production database mutation,
real schedule activation, deployment, commit/push or task archive occurred.
