# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

Frontend dependencies are managed only under `frontend/` with pnpm 11.14.0 and Node 24. Prettier owns formatting, Oxlint owns linting, TypeScript owns static correctness, Vitest with Testing Library owns component behavior, and Vite owns the production build.

---

## Forbidden Patterns

- Do not create another frontend lockfile, root JavaScript workspace, or production Node service.
- Do not commit `node_modules/`, `dist/`, caches, local environment files, or development-server output.
- Do not disable TypeScript, Oxlint, or tests to hide a defect.
- Do not mock TanStack Query internals. Test product behavior through visible roles/text and mock the narrow application boundary when isolation is required.
- Do not install Zustand, Motion, MSW, TanStack Table, Query Devtools, or shadcn components without a named consumer and acceptance criteria.
- Do not depend on a transitive package that source imports directly; every direct import requires a direct dependency.

---

## Required Patterns

- Run package commands from `frontend/` through mise Node 24.
- Change dependencies through pnpm and commit the synchronized `pnpm-lock.yaml`.
- Run `pnpm format` after changing frontend source/configuration, then run every frozen gate below.
- Keep tests behavior-oriented and independent of a live FastAPI process.
- For route entry, rendering, UI primitive, or Vite proxy changes, serve the app on loopback and inspect the browser console.

---

## Scenario: Frozen frontend quality gate

### 1. Scope / Trigger

Run this scenario after any frontend source, dependency, script, route, component primitive, TypeScript, test, or Vite configuration change.

### 2. Signatures

```bash
cd frontend
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```

Script contracts in `frontend/package.json`:

- `format:check` -> Prettier check with Tailwind class ordering.
- `lint` -> Oxlint over `src`, `vite.config.ts`, and `vitest.config.ts`.
- `typecheck` -> TypeScript project references with no emit.
- `test:run` -> one deterministic Vitest run under jsdom where configured.
- `build` -> Vite production output in `frontend/dist/`.

### 3. Contracts

- Required runtime: Node 24 from `frontend/.node-version`.
- Required package manager: pnpm 11.14.0 from `packageManager`.
- Required lockfile: exactly `frontend/pnpm-lock.yaml`.
- Local API proxy: `/api` targets `http://127.0.0.1:8000` only in Vite development.
- Test contract: unit/component tests must not require a listening backend.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Manifest and lock disagree | Frozen install exits non-zero |
| Formatting or Tailwind ordering drifts | `format:check` exits non-zero |
| Oxlint violation exists | `lint` exits non-zero |
| Import/type/project-reference is invalid | `typecheck` exits non-zero |
| Visible behavior assertion fails or a test reaches real network | `test:run` exits non-zero |
| Production graph cannot bundle | `build` exits non-zero |
| Changed UI logs warnings/errors or overflows at an affected breakpoint | Browser acceptance fails |

### 5. Good / Base / Bad Cases

- Good: dependency change updates the manifest and lockfile, all gates pass, and the affected UI state is smoke-tested.
- Base: a documentation-only change runs `format:check`; source gates are rerun when executable snippets or commands change.
- Bad: `pnpm install` repairs lock drift locally, but the frozen command is never run and CI later fails.

### 6. Tests Required

- New route: render through the router and assert its visible heading/content or error behavior.
- New provider: render through `App` and assert its consumer behavior, not provider implementation details.
- New async state: assert loading/success/error/retry as applicable using accessible queries.
- New form: assert labels, validation messages, dirty/submission behavior, and the validated payload.
- API boundary: assert status/error behavior without requiring a real backend in unit tests; reserve live loopback checks for integration acceptance.

### 7. Wrong vs Correct

#### Wrong

```bash
pnpm install
pnpm build
```

This can rewrite the lockfile and skips format, lint, types, and tests.

#### Correct

```bash
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```

---

## Code Review Checklist

- The dependency graph contains only approved foundations and feature-consumed packages.
- Source imports have matching direct dependencies; old framework/linter residues are absent.
- Router/provider instances are stable and module-owned.
- Tests fail if the intended user-visible behavior is removed.
- Formatting, lint, typecheck, tests, and build pass without project warnings.
- Browser smoke checks cover changed states and leave no servers or ports running.
- MediaCrawler, backend code, and ignored runtime data remain outside frontend-only task scope.
