# Child A backend implementation evidence

Implemented locally on 2026-08-29. Backend ownership only; no frontend, task-state,
spec, deployment, Git commit/push, account session or real provider mutations.
Read the child/parent PRD, design and implementation context and applied the
`trellis-before-dev` and `fastapi` skills. The strict shared HTTP contract was
published in `backend-contract.md` before frontend implementation.

## Implementation

- Additive SQLite v12: immutable two-stage prompt versions, explicit
  provider-revision-bound automation authorization, global discovery/ownership
  claims, independent jobs/attempts, durable request UUID replay including no-op,
  collection handoffs and unique normally-settled completion events. Genuine v11
  legacy rows remain unchanged; legacy verdicts become markers, not new generic
  understanding successes.
- New `analysis_settings`, `results`, `content_analyses` repository/service/schema
  and API families, registered through `main.py` and `api/router.py`.
  Shared `analysis_evidence` owns the unchanged saved-input representation;
  legacy imports re-export it. Existing actual-media message validation is
  shared through `build_content_messages`, not duplicated or weakened.
- One transaction admits the entire never-started library across runs/pages and
  history. Per-member source/provenance, first-entry time, provider and both
  prompt versions are frozen. Active legacy/new owners interlock in both paths.
  Explicit retry/reanalysis stays separate from first-time/all-new admission.
- New source/claim registration is atomic with origin persistence. Only new,
  never-attempted candidates can enter automatic backlog. Standalone and batch
  completion callbacks run after browser release; batch children do not trigger
  independently. A later ordinary completion recovers terminal-commit/handoff
  crash gaps without startup work or history/failed-attempt sweeps.
- Initial understanding receives accepted full text and verified actual media;
  saves neutral structured output, complete accepted input metadata/fingerprint,
  usage and constant failure codes independently. No stage-two report call.
  Reuse requires compatible input/model/provider/prompt/schema/extractor, with a
  newer known failed-input fingerprint fencing out older cached results.
- Queue waiting does not count as an attempt. Provider changes settle remaining
  claims as `configuration_blocked`; cancellation/restart preserve successes,
  drain late writes and emit no normal completion event. Successful or partially
  failed normal settlement emits exactly one durable C handoff event.
- Lifespan initialization is storage-only for this stage. The admission/empty
  queue exit race is covered with a deterministic barrier. Default automatic
  activation remains unavailable until the parent integrates the full workflow.

## Checks

Source-of-truth edits were local via `apply_patch`. The final one-way snapshot
was synced to `Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/backend`, excluding
`.venv`, Python/Ruff/pytest caches and `.env*`. The isolated remote database and
model/media workers are synthetic. No resource-intensive validation ran locally.

Final remote command:

```sh
cd /tmp/longtian-decoupling-impl.dMCxsd/backend
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m pytest -q tests --tb=short
```

Results: Ruff check passed; **95 files already formatted**;
**650 passed in 18.62s** (original baseline: 596 tests). Local `git diff --check`
also passed. No configured backend type-check gate was claimed.

New regression coverage includes real v11→v12 preservation and migration
rollback, 0/1/101/1001 bulk admission, concurrent claims, second-member
transaction rollback, durable zero-result UUID replay, new/history distinction,
legacy-active interlock, saved evidence and media validation, prompt freezing,
cache compatibility, unknown/overflow usage, cancellation/late writes/restart,
busy-resource waiting, provider-revision changes, empty-queue admission races,
strict API/local-guard/no-store errors, and collector/batch handoff integration.
The final handoff fixture corrected an old synthetic Toutiao ID/URL mismatch;
production source identity validation was preserved.

## Isolated browser-acceptance app

The stable snapshot was handed back to the main session after the final gate.
Do not resync over its running acceptance server.

```sh
cd /tmp/longtian-decoupling-impl.dMCxsd/backend
PYTHONPATH=src:tests uv run --frozen uvicorn initial_analysis_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
```

`tests/initial_analysis_smoke.py` creates a temporary on-disk database with 103
synthetic cross-run sources, including one incomplete source, and injects fake
model/media/settings. Its real browser launcher fails closed. Allowlisted UI
origin: `http://127.0.0.1:46081`. Synthetic usage counters:
`GET /api/v1/initial-analysis-smoke/counters`. Shutdown cleans up the temporary DB.
The main session owns browser acceptance and its independent reviewer gates.

## Boundary and follow-ups

No known backend implementation blocker remains. Child B scheduling and child C
report execution/consumption are intentionally not implemented here. C consumes
frozen job membership, prompt/provider intent and the completion-event interface
documented in `backend-contract.md`, and must keep report failures independent of
the already settled initial analysis. Main owns spec updates and final sign-off.
