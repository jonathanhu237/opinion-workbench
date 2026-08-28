# Execution Plan — Manual Collection Recovery

## Approval gate

- [x] User approved an independent Trellis task.
- [x] User approved pausing the entire batch on a platform failure until continue/skip.
- [x] Research covers checkpoint evidence, browser-page ownership and UI consumers.
- [x] PRD convergence rewrite and technical design completed for final review.
- [x] User explicitly approves the latest final planning summary (2026-08-28, “ok”).
- [x] Context validation passed (15 entries per manifest), then `task.py start` activated this task on 2026-08-28.

The approval gate is complete. Product implementation and isolated validation are authorized;
live migration/restart, continuation of batch 8, and model/platform requests are not implied.
Prior approvals for the Toutiao repair do not authorize unrelated actions. No commit/push/archive
is included until the user requests it.

### Subsequent live-validation approval — 2026-08-28

The user replied “好的哦” to the explicit proposal to upgrade the application and validate the
original paused batch. This authorizes a private local backup, coordinated backend/worker upgrade,
frontend startup, and one bounded manual-page/continue attempt for the current paused item in
batch 8. Preserve all historical attempts and successful platforms. Stop on a new restriction;
do not automatically retry, skip/cancel, recover the earlier failed Toutiao item, invoke models,
or commit/push/archive. Lightweight backend/browser work stays local; frontend execution stays
on Centaurus with loopback forwarding and no private runtime synchronization.

The later “ok” separately confirmed the current Chrome remote-debugging permission. On resume
that dialog was already absent; the product page-show succeeded without main clicking permission.
The one authorized suffix continuation completed successfully; no further live search is implied.

## Ownership and order

One vertical task, implemented in ordered stages with Trellis sub-agents. Main owns requirement
decisions, docs/spec changes, all live browser/runtime data, environment coordination and Git.
Native Codex context injection preferred; child-side spec loading is the fallback. Every
dispatch begins with the active task path and warns that others' changes must be preserved.

1. **Protocol/browser implementer:** owns derivative search protocol, persistent worker/CDP
   narrow page helpers, five product adapters and their tests. No unrelated crawler/client,
   auth CLI, store, credentials or global config changes. Keep auth-v2 frames unchanged.
2. **Backend implementer:** after the protocol is frozen, owns backend migration, repositories,
   services/coordinator integration, API/schemas/worker client and tests for recovery. Follow the
   canonical design rather than alternative endpoint names in research.
3. **Frontend implementer:** after API contracts are frozen, owns recovery controls, decoders,
   hooks/presenters, reused result presentation and tests. Preserve existing theme and all
   unrelated AI-settings and monitoring-rule changes. Do not create a new frontend dependency.
4. **Independent checker:** reviews the complete cross-layer change and tests after all stages;
   fixes only scoped issues under Trellis check rules, then main verifies any changed files and
   full regression evidence. Do not treat a single layer's green tests as integration success.

Do not run concurrent edits against shared protocol/schema/fixture files. Add context/checklist
updates after each stage without changing product scope silently.

## Ordered implementation checklist

- [x] Record parent/submodule dirty baselines and source revisions. Confirm Centaurus is reachable
  before execution-heavy work; do not run heavy tests locally when it is unavailable.
- [x] Add offline regression coverage: ordinary-failure pause, six completed terms plus failed
  seventh, empty completed term, partial A/B then B/C retry, all-terms-completed but final failure,
  stale controls and official page show without any search/probe.
- [x] Freeze search-v2 suffix-local frames, term completion counts/order, manual-page action/outcome
  enums and exact backend position mapping. Update every serializer/decoder/fake worker fixture.
- [x] Add completion emission at all five safe post-term locations, including XHS has-more and
  Douyin continuation-ID checks. Preserve each adapter's hard request limits and failure mapping.
- [x] Retain usable trusted owned failure pages; implement show/close, cancellation, disconnect
  generation handling and fallback to fixed official homepage only on explicit show.
- [x] Add SQLite v10 migration, proof-tagged completion ledger, immutable run
  execution offset/version, skipped/pause/completion metadata, batch revision and recovery audit.
  Derive progress and aggregate counts from source relations, not independent mutable counters.
- [x] Implement transactional progress/provenance validation, legacy backfill with null historical
  completion timestamps, single-snapshot reads and safe unavailable-recovery behavior for corruption.
- [x] Generalize pause behavior; add guarded continue, skip, manual-page and explicit historical
  failed-item recovery. Preserve success/cancel terminal history and old batch finish timestamps.
- [x] Handle no-work continue without creating a run or calling a worker. Distinguish item
  completion from latest attempt success explicitly in API and frontend decoders.
- [x] Fence stale requests by item/run/revision; drain DB threads, runner and page-show tasks on
  cancellation/shutdown; keep ownership until settled. Pause startup/interrupted work without
  launching a worker or automatically advancing to later platforms.
- [x] Add platform aggregate results/counts, ordered matched terms, supporting run ID for XHS
  opening, existing filters/pagination and all-history links without changing publication sorting.
- [x] Implement compact cause-specific Shadcn recovery card, locked/loading buttons, nearby live
  feedback, explicit old-failure action and merged results on the existing batch-detail route.
- [x] Update batch/search contract specs after successful checks; preserve unrelated spec edits.

Final offline gates: backend 408 tests, derivative 634 tests, frontend 215 tests and all frontend
type/lint/build/format checks passed. Main's synthetic HTTP and browser acceptance also passed.
Initial derivative red was structural; behavior-level tests-only red for independent-review bugs
is recorded explicitly rather than claiming every acceptance case was red before implementation.
See `research/implementation-verification.md` and `research/recovery-boundary-analysis.md`.
The bounded live acceptance below also passed for the selected existing Xiaohongshu item.
No actual platform CAPTCHA appeared; that conditional branch is not claimed as live-tested.
Task/Git delivery remains pending.

## Offline acceptance matrix

Use temporary on-disk SQLite files and fake/routed browser/worker fixtures only. Required tests:

1. Exact v9 migration, fresh init, repeat init, rollback on partial DDL, foreign keys/indexes,
   forward-version rejection, unchanged old IDs/terms/timestamps/content/attempt relations.
2. Each of the five adapters: nonempty and empty success, bounded caps, preflight failure,
   partial failure, completion ordering, cancellation and no extra search while paused/showing.
3. Strict v2 frames: wrong version/UUID/platform/action/count, duplicate keys/completions,
   out-of-order start/item/completion/result, extra fields, oversize and privacy sentinels.
4. Failure at term 7 resumes only terms 7..N, two successive resumes preserve the completed
   prefix, original term positions survive suffix mapping, and A/B plus B/C unions to A/B/C.
5. Last completion committed but result lost: continue performs no request/new attempt while
   retaining the failed run. Last completion missing: last term is retried, never skipped.
6. All ordinary failure categories pause; skip is distinct and advances; cancel halts remaining
   work. Legacy paused items and explicit old failed-item recovery do not rerun successful items.
7. Concurrent/stale continue/skip/recover/cancel, restart before attempt creation, delayed
   to-thread commits, cleanup failure and late callbacks: one owner, no orphan run or mis-target.
8. Show reuses owned page with no navigation/probe, missing-page fallback opens once, repeated
   show does not leak tabs, unsafe origins fail, absent close does not launch/reconnect, user tabs
   survive. API challenge with normal homepage never displays a false verified/visible-CAPTCHA claim.
9. UI strict schemas cover new paused causes, skipped, queued-with-previous-attempt, no-work
   completion and legacy proof. Verify counts, history, filters, source-run result opening,
   mutation errors, keyboard/focus, narrow layout and no changes to global color/font tokens.
10. Refresh/restart/GET launch no browser or model work; old successful/cancelled histories are
    untouched. Any mocked scenario remains labelled synthetic rather than live platform proof.

## Environment and commands

Local repository is source of truth. After local source edits, synchronize only source/tests/docs
one-way to Centaurus using reviewed rsync excludes. This implementation uses the isolated snapshot
`/tmp/longtian-recovery-validation.EcUhyX`, not the running checkout at
`/home/jonathanhu237/code/longtian-public-opinion-management`. Never sync runtime, keys, profiles,
`.git`, dependencies or build caches; do not use `--delete` against a broad directory. Install
additional tools only through mise if needed. Existing remote dependency environments are reused
by symlink; backend commands explicitly use `PYTHONPATH=src` to avoid the old editable installation.

Run from the relevant remote package directory using its managed runtime:

```text
backend:
  .venv/bin/ruff check src tests
  .venv/bin/ruff format --check src tests
  PYTHONPATH=src .venv/bin/python -m pytest -q tests

third_party/MediaCrawler:
  .venv/bin/pytest -q tests/test_product_search.py tests/test_weibo_product_search.py tests/test_kuaishou_product_search.py tests/test_douyin_product_search.py tests/test_xhs_product_search.py tests/test_auth_worker.py tests/test_auth_worker_protocol.py
  .venv/bin/pytest -q tests
  run the existing Ruff checker against the changed derivative files and record baseline findings separately

frontend:
  mise x node@24 pnpm@11.14.0 -- pnpm format:check
  mise x node@24 pnpm@11.14.0 -- pnpm lint
  mise x node@24 pnpm@11.14.0 -- pnpm typecheck
  mise x node@24 pnpm@11.14.0 -- pnpm test:run
  mise x node@24 pnpm@11.14.0 -- pnpm build
```

Run frontend formatting on scoped edited files locally; do not bulk-reformat unrelated dirty work.
Resolve any new focused test filenames against the final source before running. Parser/browser
fixtures must use the existing verified test-only Chromium executable on Centaurus, not silently
skip because a browser is missing. Record exact checked source hashes and commands/results.
Forward needed service ports to local loopback for UI acceptance.

Local lightweight gates: `task.py validate`, `git diff --check` for parent/derivative, review
manifest paths and scoped secret sentinels. No test touches the user's actual database or browser.

## Bounded live acceptance after offline gates

- [x] Inspect current batch/owner state without changing it; preserve existing work and original
  user tabs. Obtain the user's explicit choice before replacing or cancelling active work.
- [x] Privately back up local SQLite before approved migration/restart; no runtime data enters
  repository, remote host, console or task research. Upgrade backend/worker together.
- [x] Load the browser-control skill at validation time and inspect the actual recovery UI over
  forwarded loopback. Follow existing lightweight local backend/borrowed-browser architecture.
- [x] Use one user-approved small task or the explicitly selected existing failed/paused item.
  Verify page show, real user handling when a challenge exists, one bounded continue, persisted
  progress/results and unchanged successful platforms. No forced challenge, automatic repeated
  retries, broad five-platform reruns or model calls merely for testing.
- [x] If a real challenge does not appear, report that branch as not triggered; offline fixtures
  establish deterministic behavior but never substitute for claimed live CAPTCHA acceptance.
- [x] Record only status, counts, positions, timestamps, ownership and test outcomes. Preserve
  old attempts/data, stop at a new restriction and explain any external blocker honestly.

Live checkpoint: upgrade and same-origin UI startup passed on 2026-08-28. The first page-show
timed out awaiting native browser permission; after the user's next confirmation, page-show
succeeded and one continuation created run 52 for positions 16..19 only. Xiaohongshu completed
20/20 with 126 merged results (+18); old attempts/results and successful platforms were preserved.
Earlier Toutiao remains failed, so the batch correctly ends with failures. No CAPTCHA appeared
or was solved. No model request or additional retry was issued. See
`research/live-upgrade-verification.md` for exact preservation checks and validation limits.

## Risks / rollback / finish

- Highest-risk files: database migration/repositories, worker client state machine, CDP ownership,
  and frontend strict batch projection. Their tests must cover mixed old/new histories and races.
- New schema and v2 worker form one rollout unit. Never edit user_version backwards or silently
  restore a backup that discards new discoveries. Rollback needs explicit user direction.
- Browser fallback can open an official homepage, not guarantee a login/CAPTCHA action exists.
  Parser repair and platform restrictions remain separate concerns.
- After implementation/check, run Trellis finish/spec steps. Commit/push only when requested:
  derivative first, reachable clean commit, parent gitlink second, reproducibility checks and
  Conventional Commits on the user's existing main branch. No new PR/branch without request.
