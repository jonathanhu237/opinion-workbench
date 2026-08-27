# AI Configuration Design

Use section A and the API/transport contracts in `../08-27-multimodal-opinion-analysis/design.md`. Parent research `ai-configuration-boundary.md` establishes current routes and form dependencies; `model-transport-contract.md` owns outgoing protocol/error bounds.

## Ownership

- Backend: new `schemas/ai_settings.py`, `repositories/ai_settings.py`, `services/ai_settings.py`, `services/ai_credentials.py`, `services/ai_client.py`, `api/v1/ai_settings.py` under `backend/src/longtian_api/`. Keep credential access separate from the public projection.
- Shared backend integration: `database.py` additive settings migration, `main.py` lifespan/client teardown and injectable factories, `api/dependencies.py`, `api/router.py`.
- Frontend: `routes/ai-settings.tsx`, `lib/api/ai-settings.ts`, optional narrow reusable query hook; register in `app/router.tsx` and `app/shell.tsx`. No global CSS or shadcn preset changes.
- Direct runtime HTTP dependency declaration/lock under `backend/` only. Keep existing dev dependency semantics intact rather than migrating unrelated tests.

## Contract

GET/PUT `/api/v1/ai-settings` return only Base URL/model/key-presence/revision. Input key is optional for same-endpoint updates; a first save or endpoint change requires it. POST `/ai-settings/test` names the saved revision and reports bounded synthetic-text connectivity. Pydantic rejects unknown fields and wrong types; errors use the existing status/code/message envelope without secret values.

Settings storage is one SQLite row plus a permission-protected file addressed by an opaque random reference. Atomic replacement and missing-file behavior follow the parent. Do not persist key-derived cache identities. Configuration serialization cannot carry the secret even in error paths.

Introduce only a small shared AI-operation lease so tests and subsequent screening/summary can hold a stable configuration while preventing edits. This is not a task scheduler. Settings writes and lease admission must use the same owner; test releases on every outcome.

Use HTTPX async streaming with no redirects/retries, explicit deadlines and sanitized failure mapping. The first test asks for a short text reply; screening-specific JSON interpretation comes in its child. No arbitrary tool/function/search execution.

The form uses RHF, Zod and shadcn Field/Input/Button. Save submits the sensitive value through a direct API function, clears it afterwards and invalidates only the non-secret GET query. Testing unsaved edits is disabled with `请先保存配置`; testing never implicitly saves.

## Migration and Rollback

At current baseline settings adds the next migration after v7; verify the actual version at implementation. Temporary database/secret roots are mandatory for tests. Removing this feature must not mutate collection tables. Older binaries need a pre-migration backup, not a down-migration. No platform submodule changes.
