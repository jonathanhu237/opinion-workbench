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
