# Read-Only Preflight — 2026-08-27

## Current Revision and Services

- Local main is clean at `d5bc49f` before this task's planning docs.
- Local ports 5173, 8000 and 18000 have no application listener. Health/settings/rule reads on
  the previous 18000 API port fail to connect; no mutation or provider request was made.
- Chrome has a loopback 9222 listener. This proves only a listener, not debugger approval or login.
- Centaurus SSH is available. No frontend/backend was started during planning.

## Existing Local Data

A regular SQLite read-only attempt could not open the WAL-mode database without sidecars. After
confirming absent WAL/SHM files and stopped app listeners, an immutable read-only inspection
succeeded without creating sidecars or applying migrations. Recheck writers before any later use.

- User version: 8; `quick_check`: OK.
- One enabled existing monitoring rule, ID 1, with five ordered objects. The first object matches
  the intended locality; no source rule was modified.
- Batch totals: one cancelled, one completed, one completed-with-failures; no active/paused batch.
- Run totals: 5 browser-unavailable, 3 cancelled, 1 empty, 13 with-results and 1 structure-changed;
  no active run.
- Non-secret AI metadata: revision 1, key reference present, `qwen3.5-omni-plus`, Alibaba's configured
  compatible-mode endpoint. No credential file or secret reference value was read or printed.

## Source Contracts

- `backend/src/longtian_api/database.py`: current schema 9; startup adds issue-keyword storage to v8.
- `backend/src/longtian_api/main.py`: owns shared database, search/batch worker and AI service;
  startup reconciliation/resume makes the no-active-work precheck important.
- `backend/src/longtian_api/services/media_crawler_auth_worker.py`: launches the existing derivative
  worker using its independent frozen uv environment. Real platform operations use one borrowed
  browser owner and strict normalized protocols.
- `third_party/MediaCrawler/tools/auth_worker.py`: requires an existing default browser context and
  a local direct connection; no browser account was probed during this preflight.
- `frontend/vite.config.ts`: Vite loopback frontend proxies `/api` to a loopback backend. The proposed
  test setup can preserve this boundary with SSH forwarding without copying private runtime files.
- `.trellis/spec/backend/ai-configuration-guidelines.md`: only a bounded fixed synthetic text test
  exists; save/read/startup send no model requests. Live text success is not media quality proof.

The earlier AI-config acceptance records one real synthetic-text success, and the batch acceptance
records real three-platform results. These are historical evidence only and are not reused as the
outcome of this requested fresh live run.

## Proposed Acceptance Boundaries

Use existing platform adapters, one baseline query and one composed query on five targets, then one
repeat of successful composed targets. Five retained results per query bounds inspection. Report
small-sample relevance qualitatively; do not claim measured recall or multimedia understanding.

The scoped local-backend exception is proposed so credentials and Chrome remain on the user's Mac;
it has not yet been approved or executed. No plan-time search, provider call, migration or code edit
has occurred.
