# AI Configuration Verification

Status: implementation, independent review, automated gates and isolated browser acceptance passed
on 2026-08-27. No real provider or user runtime data was used.

## Isolation

- All source changes are local; tests, build and the smoke API run on Centaurus.
- Use temporary databases and credential directories only. Do not inspect or migrate the user's running database for QA.
- Inject a fake model client into the real API service for browser checks. No provider request, chat-disclosed key, collected post or browser profile is used.
- Use unused loopback ports with local SSH forwarding. Do not stop existing frontend/backend services or unknown listeners.

## Browser Acceptance Results

All steps passed against the real API/service with the injected fake client in
`verification/serve_fake.py`. The app ran on Centaurus and was forwarded to local loopback.

1. Opened `AI 配置` and navigated via the application sidebar; three labelled fields and shadcn controls use the existing shell/theme.
2. Empty configuration: required-field errors appeared beside their inputs; focus moved to the key field; testing stayed disabled.
3. Saved a synthetic key, public HTTPS example endpoint and test model: success, cleared password input and saved-key indicator.
4. Reloaded: non-secret settings survived; key input remained empty. GET returned only the four documented projection fields.
5. Changed the model: `请先保存配置` and disabled testing; saved without replacing the key; explicit fake test reported `连接成功，仅验证文本响应。`.
6. Changed Base URL without a replacement key: validation blocked saving and testing. After the fix, no stale successful-test message remained.
7. Controlled fake authentication failure showed the constant Chinese error and left the form usable. No raw provider response appeared.
8. Default-viewport screenshot showed no overflow or overlap; labels/focus and sidebar navigation worked. Browser warning/error logs were empty.

Three explicit test clicks produced exactly three fake-client calls (two success, one controlled
failure); save/read/reload produced none. No external model client was instantiated by the harness.
Cache/secret assertions belong to unit tests; browser inspection did not read hidden application state.

## Automated Gates

All final gates passed on Centaurus after independent fixes:

| Package | Gate | Result |
| --- | --- | --- |
| Backend | `uv sync --frozen` | Pass |
| Backend | `uv run ruff format --check .`, `uv run ruff check .` | Pass |
| Backend | `uv run pytest -q` | 308 passed |
| Frontend | mise Node 24 / pnpm 11.14.0, `pnpm install --frozen-lockfile` | Pass |
| Frontend | `pnpm format:check`, `pnpm lint`, `pnpm typecheck` | Pass |
| Frontend | `pnpm test:run` | 136 passed / 9 files |
| Frontend | `pnpm build` | Pass |
| QA harness | Remote Ruff check and format check | Pass |
| Repository | `git diff --check`, child context validation | Pass |

Independent review fixed stale UI feedback, excessive SSE JSON nesting classification and AI
teardown interrupting existing cleanup; it added regression and missing-key-recovery coverage.
Details are in `research/check-review.md`; owning code-specs record all three contracts.

## Out of Scope

No live provider or multimodal acceptance is claimed by a passing synthetic text test. Media enrichment, AI screening and summary remain separate child tasks. No commit, push or archive was requested for this implementation turn.

Credential permissions were exercised on Centaurus/Linux temporary files, not a macOS/Windows
runtime. Storage remains permission-protected plaintext, not encryption. At implementation
acceptance, existing local services were not restarted and the user database was not migrated.
The temporary smoke services and forwarding were stopped after acceptance.

## Requested Live Test: Configuration Required

After implementation acceptance, the user explicitly requested a real-model call. The live local
backend still returned 404 for AI settings and the product database had no `ai_settings` table.
Read-only checks confirmed that all collection runs/batches were terminal and no account check was
active. The old backend was shut down gracefully, and its database was backed up under ignored
`runtime/ai-config-backup.OFUVkC/longtian.sqlite3`; SQLite integrity checking passed.

The updated local backend now runs on port 18000 with the existing loopback frontend explicitly
allowed. Startup applied migration v8, health passed, and GET AI settings returned the unconfigured
projection (`has_api_key: false`, revision zero). The user-facing AI configuration page was opened
at `http://127.0.0.1:5173/ai-settings` and its empty fields were verified.

At that preparatory step, no real provider call had occurred and local configuration entry was
still required. The chat-disclosed key was not copied or used. No user collection content was sent
to any provider. The local backend remained running for configuration entry.

## Requested Live Test: Passed

The user subsequently confirmed saving the configuration. The non-secret settings projection showed
`has_api_key: true`, revision 1, model `qwen3.5-omni-plus`, and Base URL
`https://dashscope.aliyuncs.com/compatible-mode/v1`.

One explicit `POST /api/v1/ai-settings/test` with revision 1 returned HTTP 200 and
`{"status":"connected","revision":1}` in approximately 0.915 seconds. It used the running
production service and its real model client, not the earlier fake harness. The client validated a
complete nonempty text stream. There was no retry or second test request.

Only the fixed synthetic connection-test prompt was sent; no collected text, image or video was
uploaded. The user-saved credential was accessed by the backend, not exposed in tool output or
task artifacts. This confirms live text connectivity for the saved configuration, not multimedia
input support or quality. Those later child-task acceptance steps remain outstanding.
