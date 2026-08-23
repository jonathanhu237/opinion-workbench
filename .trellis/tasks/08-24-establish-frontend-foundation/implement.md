# Implementation Plan

## Phase 0: Preflight

- [x] Confirm `main` is clean and record the MediaCrawler gitlink and ignored user data paths.
- [x] Run the current frontend lint, typecheck and build to establish a passing baseline.
- [x] Read the task research and relevant Trellis frontend/spec thinking guides.

## Phase A: Install the approved foundation

- [x] Under mise Node 24, add React Router, TanStack Query, React Hook Form, resolvers, Zod and Lucide React using pnpm.
- [x] Add Oxlint, Prettier, Tailwind Prettier plugin, Vitest, jsdom and Testing Library development dependencies.
- [x] Add shadcn and `tw-animate-css` as required by the approved Base UI preset; allow the CLI to add its direct primitive dependency.
- [x] Remove ESLint-only dependencies only after the replacement lint command works.

## Phase B: Migrate shadcn foundation

- [x] Update `components.json` to the `base-nova` / Base UI configuration used by the reference admin app.
- [x] Regenerate/migrate only Button, Badge and Card; review every diff and preserve current public usage.
- [x] Merge required Tailwind/shadcn imports and tokens into `src/index.css` without replacing brand palette, typography or connection-mark styles.
- [x] Search for remaining `@radix-ui` imports, then remove Radix Slot if no source reference remains.

## Phase C: Compose providers and routing

- [x] Add `src/app/providers.tsx` with a stable QueryClient and QueryClientProvider.
- [x] Add `src/app/router.tsx` with root error boundary and `/` index route.
- [x] Move the current status page to `src/routes/home.tsx`; create `route-error-boundary.tsx`.
- [x] Make `src/App.tsx` the Provider/Router composition root and keep `main.tsx` limited to root validation and mounting.
- [x] Preserve the exact health API contract and loading/connected/unavailable/retry behavior.

## Phase D: Quality tooling and tests

- [x] Add `prettier.config.mjs`, `vitest.config.ts` and `src/test/setup.ts`.
- [x] Add an application behavior test that renders through Router/Provider with a mocked health boundary and asserts visible state.
- [x] Replace package scripts with `format`, `format:check`, `lint`, `typecheck`, `test`, `test:run`, `build` and existing dev/preview commands.
- [x] Delete `eslint.config.js` after Oxlint passes.

## Phase E: Verification

- [x] Run Node 24 `pnpm install --frozen-lockfile`.
- [x] Run `pnpm format`, then `format:check`, `lint`, `typecheck`, `test:run` and `build`.
- [x] Start FastAPI and Vite on loopback and verify direct health plus Vite proxy behavior.
- [x] Visually verify desktop and narrow connected/unavailable/retry states and check browser console.
- [x] Stop all temporary services; verify ports, Git status, ignored data paths and submodule pointer.

## Review and knowledge capture

- [x] Run full-scope Trellis check and fix in-scope findings.
  - Evidence: frozen install, format, Oxlint, typecheck, Vitest and build passed under Node 24 / pnpm 11.14.0; direct/proxied health plus desktop, narrow, unavailable and retry recovery browser paths passed after adding the root route outlet.
- [x] Use `trellis-update-spec` to replace relevant placeholder frontend conventions with the established stack and quality gates.
  - Evidence: established single-SPA structure, state ownership, Base UI component rules, runtime-validated type boundaries, the shadcn alias gotcha, and executable quality-gate contracts across six frontend spec documents.
- [x] Re-run affected checks after spec/review changes and present results for commit approval.
  - Evidence: frozen install, Prettier check, Oxlint, TypeScript, Vitest (2/2), and Vite production build all passed after review/spec updates.

## Rollback Points

- Peer dependency requires a framework downgrade: stop before changing React/Vite/TypeScript major versions.
- shadcn CLI modifies files outside the three components, `components.json`, package metadata or required CSS: revert only those task-generated changes and migrate manually from reviewed generated output.
- Brand styles or health behavior regress: restore the pre-task UI files and repeat after isolating the component/config change.
- MediaCrawler or user runtime data changes: stop immediately; do not clean or reset unrelated state automatically.
