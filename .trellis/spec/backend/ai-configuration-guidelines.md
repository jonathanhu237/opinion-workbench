# AI Configuration

## 1. Scope / Trigger

This contract owns the single local AI configuration, credential storage and explicit text-only
connection test. It applies when changing AI settings, admitting AI operations, or integrating a
future screening/summary consumer. It does not establish multimedia compatibility or authorize
automatic model requests.

The implemented manual summary consumer follows [Manual AI Summaries](./ai-summary-guidelines.md).
Its shared `AIClient.complete(...)` adds optional validated usage without changing the tiny explicit
connection test; media compatibility, request limits and strict output parsing belong to that guide.

Owners under `backend/src/longtian_api/`: `schemas/ai_settings.py`,
`repositories/ai_settings.py`, `services/ai_settings.py`, `services/ai_credentials.py`,
`services/ai_client.py`, `services/ai_errors.py` and `api/v1/ai_settings.py`.

## 2. Signatures

- `GET /api/v1/ai-settings` → `AISettings`.
- `PUT /api/v1/ai-settings` accepts `AISettingsUpdate` → `AISettings`.
- `POST /api/v1/ai-settings/test` accepts `{revision: integer > 0}` →
  `{status: "connected", revision: integer}`.
- `create_app(ai_settings_service_factory: Callable[[Database], AISettingsService] | None,
  ai_frontend_origins: tuple[str, ...] = ())` supports isolated service injection and explicit
  loopback frontend origins. It does not enable wildcard CORS.
- `AISettingsService.operation(revision)` is an async context manager yielding one stable
  `AIConfiguration`. Future AI work must use this owner rather than reading credentials directly.
- SQLite migration **v8** adds the singleton `ai_settings` row: `id = 1`, `base_url`, `model`,
  `secret_ref`, positive `revision`, and UTC `updated_at`. Collection tables are unchanged.

## 3. Contracts

### Public settings and browser state

- Public fields are exactly `base_url`, `model`, `has_api_key`, `revision`. An unconfigured response
  uses null URL/model, false key presence and revision zero. Never return a key, key prefix, key hash
  or secret-file reference.
- PUT requires string `base_url` and `model`; `api_key` is optional/null to retain an existing key.
  Pydantic rejects unknown fields and coercion. A supplied blank key is invalid, not “retain”.
- First save and normalized-endpoint changes require a newly supplied key. An unchanged save with
  no new key preserves revision; changing settings or explicitly replacing the key increments it.
- Base URL is a public HTTPS API prefix, not a full `/chat/completions` URL. Reject embedded
  credentials, queries/fragments, controls, private IPs, local hostnames, unsafe path segments and
  invalid authority. Normalize trailing slashes, host casing and the default HTTPS port.
- Model names are nonempty printable ASCII without internal spaces, at most 200 characters. Keys
  are nonempty printable ASCII without whitespace, at most 4,096 bytes.
- `AI 配置` uses RHF/Zod and existing shadcn Field/Input/Button. Submit the typed key with a direct
  API function, not TanStack mutation variables. Clear the input after a submitted attempt. Only
  non-secret projections enter Query cache; no local/session storage or persisted form drafts.
- Testing uses saved values and revision. Unsaved changes disable the test and show
  `请先保存配置`; testing never saves implicitly. Clear previous save/test feedback when the user
  edits a field so a successful result cannot appear to describe an untested configuration.

### Credential storage and operation lifetime

- Resolve credentials from `Database.path.parent / "secrets" / "ai"`. This is permission-protected
  **plaintext**, not encryption. It belongs under ignored runtime state, never source control.
- On POSIX, require an owned runtime directory that is not group/world writable, owned
  `secrets/ai` directories with mode 0700, and owned single-link regular key files with mode 0600.
  Use no-follow directory descriptors and random opaque file names; reject unsafe storage.
- Replacement order: exclusively create and fsync the new file; commit the SQLite pointer; then
  remove only the exact superseded owned file. Failed commits preserve the previous configuration.
  Failed cleanup must not undo a committed replacement or trigger broad orphan deletion.
- Missing/unreadable credentials are an explicit error, not a false “configured” result. Do not
  silently replace them with an environment variable or chat-provided key.
- One lifespan-owned service coordinates saves and an exclusive AI-operation lease. Reject saves
  or competing operations while leased; release on success, failure and cancellation. Do not hold
  a database transaction during networking or block the event loop with filesystem/SQLite I/O.
- AI client teardown must not prevent existing search-batch, search-run or browser-worker cleanup,
  even if the client's close operation raises. Preserve failure visibility while running cleanup.

### Outgoing text test

- Save, GET, startup and page load send zero model requests. One explicit test sends one tiny fixed
  synthetic prompt; never send collection data as a connection test.
- HTTPX is a direct runtime dependency. Resolve the configured host, reject any non-public answer,
  and pin the validated IP while preserving original TLS SNI and Host. Disable redirects,
  environment proxies, automatic retries and cross-host keep-alive reuse.
- Append `/chat/completions` once; send `stream: true`, `modalities: ["text"]`, and
  `max_tokens: 32`. The test has a 30-second overall deadline, with bounded network phases.
- Decode SSE and fragmented UTF-8 incrementally. Require valid final text, `finish_reason: "stop"`
  and `[DONE]`; reject partial, empty, malformed, refused, tool/audio, truncated or oversized output.
  Retain at most 64 KiB of text and cap total stream bytes at 1 MiB.
- Excessively nested JSON is invalid model output: map decoder recursion/depth failure to
  `ai_invalid_response`, never leak the exception or misclassify it as service unavailability.
- Provider responses and raw exceptions are never public error messages. A successful text test
  does not prove image/video/audio support, account model access beyond that request, or free usage.

## 4. Validation & Error Matrix

All errors use `{detail: {code, message}}`; `AI_ERROR_CONTRACTS` is the constant-message owner.

| Condition | HTTP / code |
| --- | --- |
| Wrong type or extra request field | 422 `invalid_request` |
| Invalid URL / model / supplied key | 422 `invalid_ai_base_url` / `invalid_ai_model` / `invalid_ai_api_key` |
| First save or changed endpoint without key | 422 `ai_api_key_required` |
| No configuration / stale test revision / busy lease | 409 `ai_configuration_required` / `ai_configuration_changed` / `ai_operation_active` |
| Credential safety/read failure / SQLite failure | 503 `ai_credentials_unavailable` / `ai_settings_storage_unavailable` |
| Invalid Host, cross-site Origin or fetch-site | 403 `ai_request_forbidden` |
| Mutation without JSON content type | 415 `ai_json_required` |
| Resolved destination is not public | 422 `ai_destination_forbidden` |
| Provider rejects key / missing model or endpoint | 502 `ai_authentication_failed` / `ai_model_not_found` |
| Provider rate limit / unavailable / deadline | 429 `ai_rate_limited` / 503 `ai_provider_unavailable` / 504 `ai_timeout` |
| Invalid stream / incompatible request / too large | 502 `ai_invalid_response` / 502 `ai_unsupported_input` / 413 `ai_request_too_large` |

Mutations require a loopback Host and, when Origin exists, matching origin or an explicitly allowed
loopback origin. Cross-site browser requests are rejected; local non-browser JSON clients may omit
Origin. Do not add wildcard CORS to work around this gate.

## 5. Good / Base / Bad Cases

- **Good:** save a key once; change only the model without re-entering it; test that saved revision;
  reload and see settings plus key presence, never the key value.
- **Base:** a new installation reads an unconfigured projection; Save does not call a provider.
- **Bad:** change the endpoint while retaining the previous key, accept a 200 partial stream as
  success, expose a raw provider error, or classify a failed connection as multimedia validation.

## 6. Tests Required

- Temporary on-disk SQLite plus temporary secret roots: v8 migration/reopen, singleton projection,
  no-op revisions, replacement, file modes, symlink/hardlink rejection, missing files and rollback.
- Fake transports: exactly one explicit request, no calls on reads/saves, bounded timeout, public
  DNS pinning, no redirects/retries, fragmented/multiline SSE, optional usage, terminal markers,
  malformed/truncated/oversized output and sanitized provider errors.
- API: strict schemas, Host/Origin/content-type rejection, stale revision, concurrent edit/test
  exclusion, cancellation release, cleanup after client-close failure and sentinels absent from
  reads/errors/captured logs.
- UI: labelled controls, required key rules, dirty/pending state, key clearing on success/failure,
  reload persistence, missing-key replacement recovery, no secret in Query or mutation caches, and
  truthful connection feedback including success → edit → invalid-save clearing.
- Run complete backend/frontend gates on Centaurus. Browser QA uses an injected fake client and
  temporary database; live provider acceptance remains a separate explicit user action.

## 7. Wrong vs Correct

```python
# Wrong: user-supplied requests bypass the shared owner and leak a secret in errors.
return {"error": str(provider_error), "api_key": settings.api_key}

# Correct: a stable lease, non-secret projection, and constant-only error mapping.
async with service.operation(saved_revision) as configuration:
    await client.test_connection(configuration)
```

```typescript
// Wrong: mutation variables can keep the submitted key in a shared cache.
saveMutation.mutate({ ...values, api_key: typedKey })

// Correct: direct transient submission; only safe settings become server state.
const saved = await saveAISettings(payload)
form.reset({ base_url: saved.base_url, model: saved.model, api_key: '' })
```
