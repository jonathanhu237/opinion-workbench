# Technical Design

## 1. Reference and scope boundary

本任务参考 `/Users/jonathanhu237/code/landing-customs-law-portal/frontend/admin` 的静态管理端，而不是其 `website` React Router Framework Mode 应用。当前项目继续保持单个 `frontend/` Vite SPA，不为了复制参考仓库而引入 workspace 或公共包。

参考栈与本项目映射：

| Concern | Approved owner |
| --- | --- |
| URL / route state | React Router Data Mode |
| Backend server state | TanStack Query |
| Form state and input validation | React Hook Form + Zod |
| Local UI state | React component state |
| Functional icons | Lucide React |
| UI primitives | shadcn `base-nova` / Base UI |
| Formatting | Prettier + Tailwind plugin |
| Lint | Oxlint |
| Component behavior tests | Vitest + Testing Library + jsdom |

OpenAPI client generation is a separate cross-layer task because it requires a deterministic FastAPI OpenAPI export, generated artifacts and drift checks. Installing those packages now would create unused infrastructure.

## 2. Target frontend structure

```text
frontend/
├── prettier.config.mjs
├── vitest.config.ts
├── components.json
├── package.json
├── pnpm-lock.yaml
└── src/
    ├── app/
    │   ├── providers.tsx
    │   └── router.tsx
    ├── components/ui/
    │   ├── badge.tsx
    │   ├── button.tsx
    │   └── card.tsx
    ├── lib/api/health.ts
    ├── routes/
    │   ├── home.tsx
    │   └── route-error-boundary.tsx
    ├── test/setup.ts
    ├── App.test.tsx
    ├── App.tsx
    ├── index.css
    └── main.tsx
```

The current status-page component moves from `src/app/App.tsx` to the index route. `src/App.tsx` becomes the stable composition root that mounts `AppProviders` and `RouterProvider`.

## 3. Composition flow

```text
main.tsx
  -> <StrictMode>
    -> <App>
      -> <AppProviders>
        -> <QueryClientProvider>
          -> <RouterProvider router={router}>
            -> index route <Home>
```

- `QueryClient` is created once outside render in `providers.tsx`.
- `router` is created once outside render in `router.tsx`.
- The root route owns an `errorElement`; the index route owns the existing health page.
- No form provider or global client store is created. React Hook Form and Zod are feature-level tools, not application-global state.

## 4. Health behavior compatibility

The existing `fetchHealth(signal)` boundary and exact response validation remain authoritative for this task. The page continues to own its loading/connected/unavailable/retry state. Migrating health fetching itself to TanStack Query is deferred until a server-state feature establishes query key and retry policy conventions; this keeps the foundation task from silently changing network behavior.

Tests mock the narrow `fetchHealth` module boundary rather than hitting the network or mocking TanStack Query internals. A later API-integration task may introduce MSW together with the first multi-endpoint client contract.

## 5. shadcn migration

### Current state

- `components.json` uses `new-york`.
- `button.tsx` uses Radix Slot for `asChild`; current product usage does not pass `asChild`.
- Badge and Card are repository-owned source and contain no complex primitive behavior.
- `index.css` contains project-specific civic palette, typography and connection-mark styles that must survive.

### Migration strategy

1. Record the current three component files and call sites.
2. Update shadcn configuration to the reference `base-nova` preset and Base UI base.
3. Use the current shadcn CLI to regenerate only Button, Badge and Card into a temporary/diffable state or overwrite them after the configuration is backed by Git.
4. Review component API changes and update call sites only when required.
5. Merge the minimal required shadcn/Tailwind imports and tokens into `index.css`; preserve all project-specific tokens and custom styles.
6. Search for `@radix-ui` and remove the dependency only after zero source references.

This project is still at its initial three-component stage, so the approved all-at-once migration is bounded and rollback is the single pre-task Git commit.

## 6. Tooling migration

- Replace `eslint .` with an explicit Oxlint command covering `src`, `vite.config.ts` and `vitest.config.ts`.
- Delete `eslint.config.js` and ESLint-only packages after the Oxlint gate passes.
- Prettier uses no semicolons, single quotes and `prettier-plugin-tailwindcss`; the Tailwind stylesheet points to `./src/index.css`.
- Add `test` for watch mode and `test:run` for deterministic CI/review execution.
- Keep `typecheck` separate. `build` runs Vite's production build after static checks have their own gates.

## 7. Compatibility and rollback

- Node 24 and pnpm 11.14.0 remain fixed; no root JavaScript workspace is introduced.
- React 19, TypeScript 6, Vite 8 and Tailwind 4 remain unchanged unless the package manager must make a compatible patch-level lock update.
- If shadcn regeneration overwrites brand CSS or changes visible behavior unexpectedly, restore only the task-modified UI/config files from the pre-task Git commit and repeat component migration one file at a time.
- If a dependency requires an incompatible framework downgrade, stop and report instead of weakening peer-dependency checks.
