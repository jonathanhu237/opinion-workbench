# Reference frontend stack findings

## Inspected source

Reference repository: `/Users/jonathanhu237/code/landing-customs-law-portal`

The comparable application is `frontend/admin`, a static Vite SPA. The sibling `frontend/website` uses React Router Framework Mode for a public pre-rendered site and is not the architectural model for this single-user desktop-like management tool.

## Established reference choices

From `frontend/admin/package.json` and the reference Trellis frontend specs:

- React Router Data Mode owns URL and route state.
- TanStack Query owns backend server state.
- React Hook Form + Zod own form state and input validation.
- React component state owns ephemeral local UI state.
- Lucide is restricted to functional UI icons.
- shadcn uses the `base-nova` Base UI preset, Tailwind CSS 4, CSS variables and `tw-animate-css`.
- Oxlint owns linting; Prettier with its Tailwind plugin owns formatting.
- Vitest + Testing Library + jsdom own component behavior tests.
- Zustand, Motion, TanStack Table and Query Devtools are intentionally absent without a named consumer.

## Current project differences

- The current project already matches React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Node 24 and pnpm 11.14.0.
- It currently uses ESLint instead of Oxlint/Prettier.
- It has no router, query provider, form stack or test runner.
- Its shadcn config is `new-york` / Radix and Button imports `@radix-ui/react-slot`.
- Only Button, Badge and Card have been copied, which bounds the approved Base UI migration.

## External verification

- The current shadcn Vite guide supports existing Vite projects and adding individual components through the CLI: <https://ui.shadcn.com/docs/installation/vite>.
- The current CLI exposes a `--base` choice and supports presets/component reinstallation: <https://ui.shadcn.com/docs/cli>.
- shadcn now recommends Base UI for new projects while keeping Radix supported, and documents progressive migration for existing components: <https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default>.

## Decision

Adopt the reference admin foundation without copying its workspace topology. Migrate the three existing shadcn components now because the user explicitly approved alignment and the surface is still small. Defer OpenAPI generation/client packages until a dedicated backend/frontend contract task can establish deterministic generation and drift checks.
