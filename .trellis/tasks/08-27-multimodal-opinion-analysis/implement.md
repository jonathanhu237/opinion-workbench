# Execution Plan

Planning only. The parent owns scope and integration; start a child only after the final review is approved. Every child has its own PRD, design, checklist and curated context. No task activation, source change or provider call is part of this document.

Readiness refresh: configuration is implemented/checked and `08-27-monitoring-rule-combinations` is completed/archived. The accepted 2026-08-28 video experiment informs downstream implementation, not a new permission for live calls. See `research/product-integration-readiness.md`.

## Ordered Delivery

1. `08-27-ai-configuration`: implemented and checked, including one authorized synthetic live text test. Preserve it; no repeated paid test or unrelated code rewrite is required by this planning revision.
2. `08-27-monitoring-rule-combinations`: already delivered two input groups, empty-issue compatibility, preview and derived effective queries. Preserve the archived child's verification; do not reimplement it.
3. `08-27-platform-media-enrichment`: isolated fork protocol/adapters and backend validation/temporary-media boundary. Verify each platform independently; do not report all supported from a catch-all unavailable response.
4. `08-27-ai-opinion-summary`: one manual generation pipeline owning source/context snapshots, per-item multimodal analysis/reuse and final evidence-only composition. Depends directly on configuration + media contracts, not a standalone screening delivery.
5. Parent integration review: prove search/results remain usable without AI, then the explicitly requested text/image/video summary flow, repeated-content reuse, source integrity, no unsolicited calls, and unchanged collection.

`08-27-ai-relevance-screening` is deferred outside this first version. Its old plan is history, not an activation target or completion dependency. The delivered two-list editor generates complete queries for the existing collectors. Do not edit that editor, run live searches or generate keyword suggestions during this planning revision.

Shared `database.py`, `main.py`, dependency/router ownership and the collection-detail route are sequential integration points. Do not launch multiple implementers against them. The parent itself is not an undifferentiated implementation target.

## Before the First Start

- [ ] User approves this latest post-probe final summary, including one-action analysis/summary, single-run scope, strict results/token accounting and inherited media/credential limits. Earlier approvals of separate screening or the cost experiment do not activate this implementation.
- [ ] Confirm all children still have real spec/research entries in both JSONL manifests; validate each with `task.py validate`.
- [ ] Check local/submodule dirty state and Centaurus reachability. Preserve user edits and runtime; use local main, no invented branch or PR.
- [ ] Load Phase 2.1 for Codex and dispatch `trellis-implement` with `Active task: <child path>` first; after implementation dispatch `trellis-check`. Use fresh bounded context without conversation credentials. These roles are the project's prescribed workflow.
- [ ] Treat any required change to approved scope/limits as planning review, not silent fallback.

## Validation Commands (after implementation, on Centaurus)

Sync exact changed source/task/spec paths from the local repository to a validated isolated Centaurus checkout (the current test snapshot is `/tmp/longtian-recovery-validation.EcUhyX`); exclude runtime, credentials, `.git`, dependency environments and caches. Verify the target still belongs to this project before reuse. Git operations stay local. If Centaurus is unavailable, report it before attempting a heavy local fallback.

Backend, from `backend/`:

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

Frontend, from `frontend/`:

```bash
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

For the media child, add fork protocol/adapter tests using its isolated environment and explicit test paths in that child's checklist. Never run generic `main.py` crawling as a test.

## Integration Evidence

- [ ] New configuration tested with fake transports; real synthetic provider test only on explicit invocation with locally entered replacement key.
- [ ] One actual text/image/video fixture proves input fidelity; video evidence includes a spoken fact absent from title/cover. Log outcome/count only.
- [ ] Per-platform media gates identify supported/unsupported evidence honestly; auth/challenge requires manual action and never bypass.
- [ ] Full-scope test spans more than one UI page; API totals match frozen rows, not current filter/new-only results.
- [ ] Existing phrases remain separate ordinary platform queries; results are candidate leads and need no AI verdict to be viewed. No standalone screening action/routes are introduced.
- [ ] Repeated compatible source causes zero extra model requests; changed context/content/config/prompt and explicit force produce the correct new work.
- [ ] Refresh/restart causes zero new paid requests; interrupted work and completed results remain visible.
- [ ] One explicit generation prepares uncached item evidence then composes only real related sources, without a second media upload. Empty/oversized/incomplete cases report coverage honestly; source opening works including XHS.
- [ ] Strict plain/fenced JSON tests preserve verdict and citation validation; malformed outputs never trigger a paid repair. Completed-response usage survives local JSON/schema failure, missing/malformed usage remains unknown, reused evidence does not duplicate historical usage, and no raw diagnostic answer escapes.
- [ ] A frozen AI summary survives later collection recovery without source mutation; preserve current schema v10/recovery protocol behavior and allocate any new migration after the actual latest version.
- [ ] Desktop/narrow viewport, keyboard/focus/error/pending states, console and existing routes checked through forwarded loopback services.
- [ ] Update owning specs only after behavior is verified; archive/commit/push only when requested and following the finish-work gate.

## Risk / Rollback Points

Secret-store atomicity, worker protocol versioning, new schema versions, browser ownership and paid-call restart behavior require explicit regression tests. A future fork gitlink must reference a pushed, reachable commit before parent publication. Preserve pre-migration data if a binary rollback is needed; do not down-migrate or delete source history. Current planning changes touch only task artifacts.
