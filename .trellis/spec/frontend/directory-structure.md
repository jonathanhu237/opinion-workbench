# Directory Structure

> How frontend code is organized in this project.

---

## Overview

All JavaScript tooling and browser code live under `frontend/`. The application is a static SPA: FastAPI remains a separate process, and Vite proxies `/api` only during local development. Do not introduce a root JavaScript workspace, SSR runtime, or shared UI package without a separately approved architecture task.

---

## Directory Layout

```text
frontend/
├── components.json
├── prettier.config.mjs
├── vitest.config.ts
├── package.json
├── pnpm-lock.yaml
└── src/
    ├── app/
    │   ├── providers.tsx
    │   └── router.tsx
    ├── components/
    │   └── ui/
    ├── lib/
    │   ├── api/
    │   └── utils.ts
    ├── routes/
    ├── test/
    │   └── setup.ts
    ├── App.tsx
    ├── index.css
    └── main.tsx
```

---

## Module Organization

- `main.tsx` validates `#root`, applies `StrictMode`, and mounts `App`; it owns no providers or routes.
- `App.tsx` is the composition root for application-wide providers and `RouterProvider`.
- `app/providers.tsx` owns singleton provider instances such as `QueryClient`.
- `app/router.tsx` owns the browser router, root `<Outlet />`, route error boundary, and route registry.
- `routes/` owns route-level page composition. Reusable generic primitives do not live here.
- `components/ui/` contains reviewed shadcn source copied into this repository. Add one component only with the feature that consumes it.
- `lib/api/` owns narrow HTTP boundaries, response validation, and environment-aware base URLs.
- `test/setup.ts` contains global Vitest/jsdom setup only; feature fixtures stay next to their tests.

---

## Naming Conventions

- Use lowercase filenames for routes, helpers, and app infrastructure: `home.tsx`, `router.tsx`, `providers.tsx`.
- Use PascalCase for exported React component names.
- Use `@/` imports for modules under `src/`; keep both root and application TypeScript path mappings synchronized.
- Use `import type` when an import is erased at runtime.

---

## Established Examples

- Composition root: `frontend/src/App.tsx`
- Provider ownership: `frontend/src/app/providers.tsx`
- Router ownership: `frontend/src/app/router.tsx`
- Route page: `frontend/src/routes/home.tsx`
- HTTP boundary: `frontend/src/lib/api/health.ts`

> **Warning**: shadcn resolves aliases through the root TypeScript configuration. If `@/*` exists only in `tsconfig.app.json`, the CLI can create a literal `frontend/@/` directory. Run `pnpm dlx shadcn info` after alias changes and require the resolved UI path to be `frontend/src/components/ui` before adding components.
