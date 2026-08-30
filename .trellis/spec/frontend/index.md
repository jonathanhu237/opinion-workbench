# Frontend Development Guidelines

> Project-specific standards for the local React administration application.

---

## Overview

The frontend is a single static Vite SPA under `frontend/`. React Router owns routes, TanStack Query is available for server state, React Hook Form with Zod owns future form state, and shadcn `base-nova` components use Base UI primitives. There is no frontend workspace, SSR process, or shared UI package.

## Pre-Development Checklist

- Read [Directory Structure](./directory-structure.md) before adding routes, providers, or top-level folders.
- Read [State Management](./state-management.md) before adding data fetching, forms, URL state, or a client store.
- Read [Component Guidelines](./component-guidelines.md) before adding shadcn components, icons, or global styles.
- Read [Quality Guidelines](./quality-guidelines.md) before changing dependencies, scripts, test setup, or build configuration.
- Read [Type Safety](./type-safety.md) before adding request/response types or Zod schemas.

## Guidelines Index

| Guide | Description | Status |
| --- | --- | --- |
| [Directory Structure](./directory-structure.md) | Vite SPA module ownership and route/provider boundaries | Established |
| [Component Guidelines](./component-guidelines.md) | Base UI shadcn ownership, styling, icons, and accessibility | Established |
| [Hook Guidelines](./hook-guidelines.md) | Custom-hook conventions beyond the current foundation | To fill |
| [State Management](./state-management.md) | Server, URL, form, and local-state ownership | Established |
| [Quality Guidelines](./quality-guidelines.md) | Package, format, lint, type, test, build, and smoke gates | Established |
| [Type Safety](./type-safety.md) | Strict TypeScript and runtime-validation boundaries | Established |
| [Results and Initial Analysis](../backend/initial-analysis-guidelines.md) | Cross-layer result library, prompt drafts, frozen bulk intent, history and progress | Active |
| [Unified Opinion Automation](../backend/automation-workflow-guidelines.md) | Fixed-stage task forms, run-now, retry/cancel, history, strict decoding and workbench integration | Active |
| [Automatic Text Reports](../backend/topic-report-guidelines.md) | Saved-evidence relevance/report projections, strict decoding, frozen citations and report history | Active |
| [Homepage Workbench](../backend/workbench-guidelines.md) | Read-only duty signal, typed deep links, adaptive polling, stale/unknown semantics, and report-first layout | Active |

## Quality Check

Run every frozen gate in [Quality Guidelines](./quality-guidelines.md). Route-entry, rendering, component-primitive, or Vite changes also require a loopback browser smoke check covering the affected state and the browser console.

---

**Language**: All documentation should be written in **English**.
