# Type Safety

> Type safety patterns in this project.

---

## Overview

The frontend uses TypeScript project references with unused-symbol and fallthrough checks enabled. Compile-time types describe trusted application code; runtime validation remains mandatory at external or user-input boundaries. FastAPI/Pydantic is authoritative for backend responses, while the frontend validates the parts it consumes until generated OpenAPI types are introduced in a dedicated contract task.

---

## Type Organization

- Keep component-only props and reducer actions next to their component.
- Keep HTTP response types and runtime guards in the owning `lib/api/` module.
- Keep future form schemas next to the form/feature that owns the input contract.
- Keep Vite/Vitest configuration included through `tsconfig.node.json`.
- Use the `@/` alias only for source modules under `frontend/src/`.

---

## Validation

- Use Zod with `@hookform/resolvers` for user-entered form values.
- Do not duplicate every FastAPI response as a Zod schema. Add runtime response validation where the browser crosses an untrusted or version-drift boundary.
- The current `fetchHealth()` implementation is the reference: parse JSON as `unknown`, check HTTP status, validate the exact consumed shape, and throw `HealthCheckError` for protocol or payload failures. Network and cancellation errors may still originate from `fetch`.
- Generated TypeScript types, when introduced later, will not replace runtime validation by themselves.
- When an API publishes stable product error codes, validate the complete `(HTTP status, code)` pair
  before mapping the failure to a field or product message. A known code on the wrong status is
  protocol drift, not an actionable field error, and must become the boundary's `invalid_response`
  equivalent.
- Some existing boundaries validate the exact `(HTTP status, code, message)` triple. Treat the
  message in those contract tables as wire data, not editable UI copy. Humanize it only after the
  response has passed validation, using the validated error code in the route or presenter. Editing
  only the frontend contract message makes an unchanged backend response look like
  `invalid_response`.

```ts
// Wrong: changes the decoder's expected wire value without changing the backend.
productErrorContracts.search_batch_not_paused.message =
  '这次采集不需要继续。'

// Correct: preserve the exact wire contract, then choose plain UI copy by validated code.
const copy =
  error.code === 'search_batch_not_paused'
    ? '这次采集不需要继续。'
    : error.message
```

---

## Common Patterns

- Use `import type` for erased imports.
- Model reducers and state machines with discriminated unions.
- Accept `AbortSignal` at HTTP boundaries so React lifecycles can cancel in-flight work.
- Prefer inference from Zod schemas and library APIs over handwritten duplicate types.

```ts
type HealthState =
  | { status: 'loading' }
  | { status: 'connected'; data: HealthResponse }
  | { status: 'unavailable'; message: string }
```

---

## Forbidden Patterns

- Do not use `any`, unchecked non-null assertions, or broad casts to bypass the compiler.
- Do not cast raw JSON directly to an application response type.
- Do not exclude new source/configuration files from TypeScript to make a gate pass.
- Do not maintain handwritten frontend copies of future generated OpenAPI types.

```ts
// Wrong: no runtime evidence supports the cast.
const payload = (await response.json()) as HealthResponse

// Correct: retain unknown until a narrow guard validates it.
const payload: unknown = await response.json()
if (!isHealthResponse(payload)) {
  throw new HealthCheckError('Unexpected health payload')
}
```
