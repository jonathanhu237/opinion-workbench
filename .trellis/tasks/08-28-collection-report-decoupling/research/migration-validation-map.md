# Research: Migration, legacy compatibility, and validation map

- Query: Identify the current database baseline, safe additive ownership for independent initial analyses and reports, legacy-analysis risks, global-result provenance, and existing validation/runtime conventions.
- Scope: internal; static source inspection only. No product edits, task activation, migration, tests, browser/model requests, remote commands, synchronization, or Git operations were performed by this researcher.
- Date: 2026-08-29

## Findings

### Files found

| File | Responsibility |
| --- | --- |
| `backend/src/longtian_api/database.py` | One SQLite path, connection policy, ordered schema migrations; current version 11. |
| `backend/src/longtian_api/repositories/search_runs.py` | Global content identity, per-run observations, source-provenance proof, transactional writes. |
| `backend/src/longtian_api/repositories/ai_summaries.py` | Legacy report-owned item snapshots, canonical reuse, input metadata, startup interruption. |
| `backend/src/longtian_api/services/ai_analysis.py` | Legacy relevance-first item prompt and strict report/analysis schemas. |
| `backend/src/longtian_api/services/content_enrichment.py` | Provenance/active-source/changed-source checks before media acquisition. |
| `backend/src/longtian_api/main.py` | Application-owned shared database and lifecycle/service factories. |
| `backend/src/longtian_api/api/router.py` | `/api/v1` router registration. |
| `backend/src/longtian_api/api/dependencies.py` | Lifespan service dependency accessors. |
| `backend/src/longtian_api/api/v1/ai_summaries.py` | Legacy report endpoints and local mutation/no-store boundary. |
| `backend/src/longtian_api/api/v1/search_runs.py` | Existing result list and stored-source opening endpoints. |
| `frontend/src/app/router.tsx`, `frontend/src/app/shell.tsx` | Route registry and persistent navigation ownership. |
| `frontend/src/lib/api/ai-summaries.ts`, `frontend/src/lib/api/search-runs.ts` | Independent strict HTTP decoding, source validation/opening. |
| `backend/tests/schema_fixtures.py`, `backend/tests/test_ai_summary_repository.py` | Real historical-schema fixtures and migration/transaction/recovery tests. |
| `README.md`, `backend/pyproject.toml`, `frontend/package.json`, `frontend/vite.config.ts` | Existing commands, tooling, service entrypoints, and loopback proxy. |

### 1. Database baseline and safe additive migration

**Observed:** `CURRENT_DATABASE_VERSION = 11` (`database.py:7`). Initialization opens WAL, rejects future versions, and applies migrations sequentially (`database.py:45`). Each migration owns an explicit `BEGIN IMMEDIATE`, rechecks its source version under that lock, sets `user_version`, commits, and rolls back on failure (`database.py:99`). Connections are per operation with foreign keys and a five-second busy timeout (`database.py:33`).

The v11 migration only appends two tables:

- `ai_summary_runs`: mandatory one `source_run_id`, one platform, historical rule/terms, configuration identity, three version strings, report document/usage/status (`database.py:110`). A partial unique index permits one active legacy report (`database.py:142`).
- `ai_summary_items`: required parent report and global content FK, a frozen source JSON, input/cache hashes, analysis outcome, canonical reuse pointer, usage, and terminal-state constraints (`database.py:150`). Its position is constrained to 0–99 (`database.py:156`).

**Design recommendation, not an implemented migration:** allocate v12 or the next available version after rechecking the baseline at implementation time. Append new independently owned stage-one attempts/operations, report attempts/membership, prompt revisions, and durable admission state. Do not repurpose the legacy tables, relax their constraints in place, drop historical columns, or turn report-owned IDs into global analysis IDs. Keep references to stable `search_contents.id` and freeze the source/evidence/version actually used by each attempt.

Preserve these boundaries:

1. Collection rows, IDs, first-entry timestamps, rule snapshots, per-run terms/observations, batch attempts/recovery proofs, AI settings, and both legacy AI tables remain readable and unchanged by the schema migration. Existing v10 recovery data is not a migration input to reinterpret.
2. Initial-analysis success belongs to its own attempt. Report failure/retry must not update that success or force media re-acquisition. A report freezes the successful analysis IDs and text it consumed; it must not follow a mutable "latest analysis" pointer later.
3. Give new rows explicit status/finished-time, uniqueness, parent-membership, and FK constraints. Use original result IDs for source citations, not report or analysis IDs. New foreign-key deletion rules must protect historical evidence; no cascading deletion from a prompt edit or collection-task removal.
4. Seed shared prompt defaults once, with exact text/version persisted for subsequent operation snapshots. Startup must not overwrite user edits. The old `ai_summary_runs` stores version strings, not exact editable prompt text; do not claim a migrated historical prompt was captured verbatim merely from a version/hash.
5. **No upgrade-triggered historical AI sweep.** Establish a durable rollout/admission boundary: pre-existing contents are historical candidates for explicit bulk analysis; only genuinely new content insertions after the feature boundary produce new-result admission events. A startup query of "all contents without a stage-one row" would violate this boundary. Persist unprocessed new-result admissions so a restart or later collection does not lose them. SQL/schema/default initialization itself makes zero provider/browser calls.
6. Binary rollback needs a pre-migration recoverable backup or a new compatible binary. The old binary rejects a newer schema (`database.py:52`); changing `user_version` downward does not roll back tables/data safely. Do not overwrite a live database or down-migrate as routine rollback.

### 2. Legacy analyses are useful history, not automatically new-stage completion

The old prompt explicitly asks whether a source is relevant to a monitoring scope (`services/ai_analysis.py:167`); the response requires `decision`, `reason`, and a bounded `evidence_summary` (`services/ai_analysis.py:115`). The new stage one instead understands every source before stage-two relevance/reporting. Those are different instruction/schema contracts even when a legacy summary looks usable.

Concrete compatibility hazards:

- Cache identity includes observation, historical rule name/terms, configuration revision/endpoint/model, analysis prompt, model input, and extractor (`repositories/ai_summaries.py:311`). Global stage-one reuse must not assume that content ID alone proves compatibility, nor continue coupling a general understanding result to a report's scope by accident.
- Reused legacy rows intentionally have no own decision/text/input/usage; they reference one canonical completed row (`database.py:171`, `repositories/ai_summaries.py:629`). A migration/import must resolve and validate that canonical row and retain both provenance identities. Copying the reuse row's nullable fields directly would erase evidence; attributing the canonical usage to each reuse would double-count spending.
- Saved input preserves text and bounded readiness/media metadata, not image/video bytes or locators (`repositories/ai_summaries.py:62`). Old summaries cannot prove that a different new prompt was run over the original media; incomplete input is not an "irrelevant" decision.
- Reuse invalidation checks the newest known acquired fingerprint even when that newer analysis failed (`repositories/ai_summaries.py:418`). Preserve this rule in the new system; a failed refresh must not silently resurrect old evidence as current.
- Global collection fields can change on repeated observations while `first_seen_at` stays fixed (`repositories/search_runs.py:339`). Historical report text must come from frozen source/input snapshots, not a later join to the mutable current title/snippet.
- Legacy unfinished summaries are marked interrupted during repository initialization, not resumed (`repositories/ai_summaries.py:171`). Keep old startup reconciliation separate from new queue/recovery decisions; neither a GET nor importing history should restart an old paid operation.

**Recommended compatibility policy for the design review:** keep old reports and analyses in a visibly legacy/read-only history projection, with original IDs and links. Do not silently mark them successful under the new stage-one contract. A historical record can display "legacy analysis available; new initial analysis not completed"; the explicit bulk action may include it only with that status/count made clear. Migration itself performs no reanalysis. If a future compatibility import is wanted, require an explicit versioned adapter with complete provenance and regression tests, rather than guessing compatibility from non-empty text. This preserves old work without inventing new work or hiding possible repeated model cost.

### 3. Global results and source-opening provenance

`search_contents` is already globally deduplicated on `(platform, platform_content_id)` (`database.py:1200`); `search_run_contents` is the per-run relation (`database.py:1222`). The repository looks up that global identity before insertion (`repositories/search_runs.py:301`), never resets first entry on repeat (`:339`), and stores `new`/`repeated` on the observation relation (`:383`). These are collection facts, not analysis status.

There is presently no global results HTTP endpoint in the registered routers (`api/router.py:13`); results list under `/search-runs/{run_id}/results` (`api/v1/search_runs.py:72`). A new global results repository/route should query the global source once and project its collection origins separately, rather than unioning visible result pages and double-counting duplicates.

Source proof cannot be discarded when introducing that global endpoint:

- `get_result_source(run_id, result_id)` proves the stored relation, matching platforms, ordered historical matched terms, and source activity within one read snapshot (`repositories/search_runs.py:555`). It returns the active flag; enrichment is the caller that rejects active/paused or changed frozen sources before worker navigation (`services/content_enrichment.py:222`).
- The existing XHS action is `POST /search-runs/{run_id}/results/{result_id}/open`, with no caller-supplied URL (`api/v1/search_runs.py:91`). `SearchRunService.open_result` reuses proven historical terms, admits one shared browser owner, and invokes the existing worker (`services/search_runs.py:251`). It is XHS-only, not a generic open-URL endpoint.
- Non-XHS sources render a previously validated canonical URL; XHS uses the stored-result action (`frontend/src/routes/collection-ai-summary.tsx:107`). The decoder rejects unexpected URLs/tokens (`frontend/src/lib/api/search-runs.ts:245`), and the HTTP client requires both result ID and source-run ID (`:436`).

**Recommended contract:** each global result/analysis/report citation retains an application-selected valid origin tuple `(source_run_id, result_id)` plus frozen source identity. If several origins exist, choose deterministically under a documented policy and retain the chosen provenance; do not invent a current rule or trust a URL generated by the model. Keep historical origin lists discoverable. New report citation resolution must validate against that report's complete frozen membership, independent of the currently visible page.

### 4. API, service, and frontend ownership

- API registration: `backend/src/longtian_api/api/router.py:13`; lifespan services/state/factories: `main.py:26`; common dependency accessors: `api/dependencies.py:14`. The legacy summary accessor is currently route-local (`api/v1/ai_summaries.py:24`). These are shared integration files: edit them sequentially, not with competing implementers.
- The main app currently constructs shared database, search/batch, AI settings, enrichment and summary services before exposing state (`main.py:75`); shutdown drains summary, enrichment, AI, batch, search and platform owners (`main.py:112`). New independent queues must fit this ownership chain and retain settled database writes under cancellation.
- Preserve legacy `GET /search-runs/{id}/ai-summaries`, `GET /ai-summaries/{id}`, and item-history decoding (`api/v1/ai_summaries.py:87`). New global result/stage-one/report contracts should use separate resources, not change the meaning of those legacy response fields. Retirement/retention of the legacy creation action is a design decision; never redirect its UUID to a different automatic workflow without explicit compatibility handling.
- New AI mutations should reuse the existing local Host/Origin/JSON guard; success and all error paths need no-store and bounded errors (`api/v1/ai_summaries.py:40`, `:60`, `:70`). GET remains read-only, including history/progress polling.
- `frontend/src/app/router.tsx:8` owns route registration and lazy loading; `app/shell.tsx` owns navigation/title. New narrow clients belong in `lib/api/` with independent strict decoders. Existing legacy code checks one source run/platform (`routes/collection-ai-summary.tsx:269`) and positions/report membership (`lib/api/ai-summaries.ts:541`); do not just rename that component for cross-run reports.

### 5. Existing validation commands and Centaurus conventions

These are command contracts for later implementation, **not results of this research pass**.

Backend commands from `backend/` are documented in `README.md:24` and `:62`; the frozen-lock variant is used by previous integration plans. A consistent future gate is:

```sh
uv sync --locked
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests
```

`backend/pyproject.toml:19` declares pytest and Ruff; `:29` restricts discovery to `tests`. No separate backend mypy/pyright dependency or type-check script is configured. Do not report a nonexistent Python type-check gate as passed. A previous isolated run used `.venv/bin/ruff` and `PYTHONPATH=src .venv/bin/pytest -q tests/ --tb=short` (`.trellis/tasks/08-27-ai-opinion-summary/research/commit-gate.md:52`); these are equivalent environment-specific historical commands, not proof of current environment readiness.

Frontend frozen gates, from `frontend/`, are specified in `.trellis/spec/frontend/quality-guidelines.md:40`, with exact script bodies in `frontend/package.json:6`:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

Run formatting locally for actual frontend edits before the frozen gate; installation/tests/builds belong on Centaurus under the user's standing workflow. A prior gate uses the explicit mise pnpm selector above (`.trellis/tasks/08-27-ai-opinion-summary/research/commit-gate.md:64`).

Deployment/validation constraints:

- Local files are the source of truth; one-way `rsync` only exact source/test/task/spec/manifest/lock changes to a separately verified project or isolated test directory on Centaurus. `rsync -a --relative` and before/after hash comparison are established evidence practices (`.trellis/tasks/08-27-ai-opinion-summary/research/commit-gate.md:18`). Never copy runtime SQLite/WAL, credentials, browser profiles, staged media, `.git`, dependency environments, or caches. Do not synchronize while validation is running against that snapshot.
- Prior isolated directories and remote ports are historical evidence, not reusable targets without checking current ownership. The planning-doc copy is not a runnable code checkout. This researcher did not inspect SSH configuration, secret stores, runtime databases, or remote availability.
- Documented backend dev command is `uv run fastapi dev --host 127.0.0.1 --port 8000` (`README.md:29`), with `longtian_api.main:app` entrypoint (`backend/pyproject.toml:26`). Default startup can initialize the default runtime database (`database.py:22`), so isolated smoke acceptance must inject a temporary on-disk database/fake services through `create_app`, not run against the user's live database by accident.
- Frontend `pnpm dev` binds loopback (`frontend/package.json:7`); Vite proxies `/api` to fixed `http://127.0.0.1:8000` and preserves the original Host (`frontend/vite.config.ts:14`). Forward both frontend and API loopback ports to the local machine for validation, check collisions, and keep Origin/Host allow-list alignment. Changing an alternate API port alone does not change Vite's proxy target. Use only owned service/tunnel processes and do not expose CDP/API publicly.
- Browser acceptance must cover affected routes, progress/history, source links, keyboard/narrow layout and console. Use isolated fixtures and mocks; a previous live-browser task's local-backend exception was explicitly scoped and is not blanket authority to use the production database, Chrome session, or provider now (`.trellis/tasks/08-27-live-search-ai-acceptance/design.md:13`).
- If Centaurus is unavailable, report it before resource-intensive local fallback. New tools, if needed later, use mise. No new external queue/database/ORM is needed merely to follow the current persistence pattern.

### 6. Proposed regression matrix

| Area | Required evidence |
| --- | --- |
| Schema upgrade | Genuine populated v11 fixture to next version; every old table/ID/relationship/JSON/usage value unchanged; new defaults only in new structures; `foreign_key_check` clean; initialize twice; deleted/edited defaults remain deleted/edited. |
| Failure/rollback | Fail after first new DDL/DML under a real transaction; no half-created schema/version/admission state; future-version rejection still fails startup. |
| Startup boundary | Upgrade/reload/GET creates zero AI/browser calls and no historical bulk job; pre-existing rows remain explicit bulk candidates; new pending admissions survive restart without reconstructing work from collection `new/repeated` labels. |
| Legacy compatibility | Completed/reused/incomplete/failed/cancelled/interrupted legacy cases remain readable; canonical reuse and usage are not duplicated; no old semantic outcome silently satisfies the new prompt/schema. |
| Independence | Report failure/cancel/retry preserves saved stage-one success, prompt snapshots and media counters; source edits/new observations cannot mutate previous report membership or text. |
| Identity/provenance | One source observed across runs/rules has one global row; first entry remains stable; valid source-run tuples work; missing/mismatched origins fail without navigation; XHS still uses original stored-source opening. |
| HTTP/frontend | Strict new-resource decoding, legacy response decoding, no-store on validation errors, mutation guards, UUID replay, full-set versus visible-page behavior, mixed provenance and complete citation membership. |
| Cancellation/concurrency | Short SQLite writes settle before releasing ownership; active attempt checks reject late callbacks; one canonical result is not re-enqueued by simultaneous automatic/manual admissions. |

Reuse the real fixture pattern `backend/tests/schema_fixtures.py:7` rather than relabelling a current schema as v11. The existing v10→v11 test captures full old projections and checks preservation (`test_ai_summary_repository.py:31`), and the trigger-based admission test exercises an actual second-child insertion failure (`:69`). Existing `test_startup_interrupts_unfinished_only_without_reanalysis` (`:164`), cancellation/write settlement (`:226`), `test_forward_database_version_fails_application_startup` (`test_monitoring_rules.py:99`), and migration rollback cases (`test_search_recovery.py:634`) are useful test patterns. The v11 test currently asserts `CURRENT_DATABASE_VERSION == 11` (`test_ai_summary_repository.py:54`); update version-sensitive assertions deliberately while retaining historical preservation coverage.

## External References / Versions

No external documentation was fetched or required for this static repository pass. Versions here describe local declared/locked dependencies, not latest upstream recommendations: Python `>=3.11` (`backend/pyproject.toml:7`); locked FastAPI 0.141.1 (`backend/uv.lock:104`), Pydantic 2.13.4 (`:597`), httpx 0.28.1 (`:384`), pytest 9.1.1 (`:755`), Ruff 0.16.4 (`:1004`); frontend Node 24 (`frontend/.node-version:1`) and pnpm 11.14.0 (`frontend/package.json:17`). SQLite is the standard-library runtime dependency; its actual runtime version was not inspected.

## Related Specs

Final planning reconciliation: the parent design keeps legacy completed/reused
and failed/interrupted attempts outside the ordinary all-never-started action.
They have labelled explicit reanalysis/retry instead. This selects the
conservative compatibility option without certifying legacy evidence or hiding
repeat model work; the earlier optional bulk-import suggestion is not the
chosen implementation plan.

- `.trellis/workflow.md`: research-only Phase 1 and final planning review before activation.
- `.trellis/spec/backend/database-guidelines.md`: per-operation connections, ordered locked migrations, append-only preservation, real historical fixtures, settled writes.
- `.trellis/spec/backend/ai-summary-guidelines.md`: preserve legacy evidence/privacy/usage/citation/compatibility boundaries; its manual single-run trigger is the old product contract, not authority to reject the newly agreed automatic workflow.
- `.trellis/spec/frontend/directory-structure.md`: app/router/shell/client ownership; no placeholder navigation.
- `.trellis/spec/frontend/quality-guidelines.md`: all frozen frontend gates and loopback browser acceptance.
- `.trellis/spec/backend/quality-guidelines.md` is still a placeholder; the concrete backend command contracts are in the manifest/README and domain-specific specs.

## Caveats / Not Found

- Migration/table names, exact legacy-action retirement, and new API paths are recommendations for the parent's design review, not implemented or independently user-approved choices.
- No live database contents were inspected. There is no claim that a specific user's legacy row is compatible, that a backup exists, or that any migration/remote/test passed today.
- The current first-stage contract differs from the legacy relevance prompt. A safe automatic migration of those outputs was **not found**; preserve history and explain compatibility rather than infer success.
- No dedicated global-results API, independent stage-one/report persistence, or configured backend Python type checker exists in the inspected source. Capacity/scheduling algorithms are intentionally left to the other task research.
