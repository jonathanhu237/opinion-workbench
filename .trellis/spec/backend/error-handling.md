# Error Handling

> Stable product errors across FastAPI, services, subprocess boundaries, and local storage.

## Overview

Expected failures cross the API boundary as a stable code and Chinese product message. Raw child
output, exceptions, SQL, filesystem paths, credentials, and user-entered content are never public
error details.

The public envelope is:

```json
{"detail": {"code": "stable_error_code", "message": "可执行的中文说明。"}}
```

## Error ownership

- Pydantic owns structural request validation.
- Services own semantic validation and raise feature-specific domain errors containing only a
  stable code, product message, and HTTP status.
- Repositories translate only the constraints/storage categories they can identify safely; they do
  not construct HTTP responses.
- Routes catch expected domain errors and raise `HTTPException` with the shared envelope.
- Unexpected exceptions fail closed and map to a constant internal/storage-unavailable response;
  never expose `str(error)` to the client.

## Request validation

- Request models use `ConfigDict(extra="forbid", strict=True)` unless a documented compatibility
  contract requires coercion.
- The application-level `RequestValidationError` handler returns HTTP 422 with
  `invalid_request` and the constant message `请求内容不正确。`.
- Field-specific semantic errors may use a feature code/message after the request is structurally
  valid. OpenAPI must document feature 404/409/422/503 response models.
- Changing the validation handler must preserve existing successful responses and documented domain
  errors in other routes.

## Storage and subprocess failures

- Known uniqueness and missing-resource conditions map to feature domain errors.
- Unexpected SQLite failures return a constant recoverable message. Responses and retained evidence
  contain no database path, SQL, parameters, raw exception, or rule contents.
- Authentication worker errors follow the stricter constant-only IPC rules in
  `platform-connection-guidelines.md`; do not weaken those boundaries for ordinary CRUD features.

## Logging

- Log a stable operation name and exception class only when diagnosis requires it.
- Do not log request bodies, monitoring-rule terms, database paths, SQL parameters, Cookies,
  authorization material, QR data, raw browser output, or child stderr.
- User-visible recovery guidance belongs in the product error message, not in raw exception text.

## Testing requirements

- Assert exact status, code, message, and envelope shape for every documented expected failure.
- Force storage/internal failures with a fake boundary and assert sentinel paths, SQL, secrets, and
  user-entered values do not appear in responses or captured logs.
- Test malformed JSON, wrong types, unknown fields, missing resources, conflicts, semantic
  validation, and service unavailability.
- Re-run unrelated route contract tests after adding or changing a shared exception handler.

## Common mistakes

- Returning FastAPI/Pydantic internals directly as user-facing copy.
- Catching every exception in the route and converting programmer defects into a false validation
  error.
- Using one generic 500 response for actionable not-found, conflict, and invalid-input cases.
- Logging a full exception whose message embeds SQL, a filesystem path, browser data, or product
  values.
