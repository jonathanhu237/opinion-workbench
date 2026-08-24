# Frontend skill design verification

## Scope and evidence selection

The project-local `ui-ux-pro-max` and `frontend-design` skills were applied to the committed
administration-shell baseline. The accepted direction and rejected generic output are recorded in
Section 12 of `design.md`.

Accepted evidence:

- dense operator-facing layout rather than a landing-page hierarchy;
- truthful server-backed readiness plus explicit unavailable and empty states;
- the reviewed shadcn `base-nova` Sidebar composition for desktop and narrow navigation;
- one civic four-community identity mark and one ruled duty ledger as the subject-specific
  signature;
- Chinese system copy, local system fonts, visible focus, reduced motion, sticky focus clearance,
  and 44px narrow-screen targets.

Rejected output:

- dark glassmorphism, Fira or other network fonts, fluorescent CTAs, generic real-time SaaS hero
  copy, synthetic telemetry, ambient animation, and a repeated card-gallery dashboard.

## shadcn review

- `pnpm dlx shadcn info` resolved `base-nova`, Base UI, `@/` aliases, and
  `frontend/src/components/ui` correctly before generation.
- `pnpm dlx shadcn add sidebar --dry-run` and `--diff` were reviewed before applying the Sidebar
  registry item.
- Sidebar's required local primitives are `input`, `sheet`, `skeleton`, and `tooltip`; no unrelated
  product dependency was added.
- The application now composes `SidebarProvider`, `Sidebar`, `SidebarTrigger`, menu primitives, and
  the generated mobile Sheet path instead of owning a parallel desktop/mobile navigation state
  machine.
- Product-facing hidden labels in the generated Sheet/Sidebar path are localized to Chinese, while
  the generated Base UI behavior, slots, and composition remain unchanged.
- Final `pnpm dlx shadcn diff` reported `No updates found.`

## Automated verification

Run from `frontend/` with mise Node 24:

```text
pnpm format
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
pnpm dlx shadcn info
pnpm dlx shadcn diff
```

Results:

- frozen install passed with no lockfile change;
- Prettier, Oxlint, and TypeScript passed;
- Vitest passed: 2 files, 22 tests;
- Vite production build passed;
- Vite emitted its non-failing single-chunk size advisory at 502.36 kB (159.08 kB gzip), only
  2.36 kB / 0.47% above the advisory threshold. Route-level splitting is deferred because this
  local MVP has two small routes and the task does not change its loading architecture; the warning
  limit was not raised or suppressed.
- shadcn configuration resolved correctly and registry diff was clean.

## Loopback visual and console review

The user's existing loopback port 8000 was occupied by an unrelated SSH listener and was left
untouched. For this frontend-only review, FastAPI ran on `127.0.0.1:8001`, Vite on
`127.0.0.1:5173`, and a temporary loopback-only reverse proxy on `127.0.0.1:5175` routed `/api` to
the review backend. No authentication attempt endpoint was called.

Observed results:

- 375x812: mobile Sidebar opened, exposed a close trigger, closed after route navigation, and the
  workbench/account pages had no horizontal overflow; visible primary targets were at least 44px.
- 768x900 at the user's 90% Chrome zoom exposed a fractional-width boundary where rounded
  `innerWidth` selected desktop state while Tailwind had not reached `48rem`. The mobile hook was
  corrected to follow the same media query as CSS, the narrow 44px target query was aligned to
  `width < 48rem`, and the navigation then remained operable with no horizontal overflow.
- 1024x800 and 1440x900: the duty ledger, activation sequence, platform signal list, and guidance
  column used the available canvas without overflow.
- 812x375 landscape: the fixed shell remained operable; Sidebar content retained its own necessary
  navigation scroll area and the page had no horizontal overflow.
- Workbench values came only from health/platform responses or explicit `尚未配置` / `规划中` /
  empty states.
- Platform accounts preserved five accurate states, one actionable Weibo control, the existing
  polling/mutation behavior, and the manual-Chrome safety guidance.
- Route navigation and the skip link moved focus to the named main region below the sticky header;
  the mobile dialog exposed the Chinese accessible name `主导航` and closed after route navigation.
- Initial platform telemetry remained explicitly `正在读取` until a real catalog response arrived;
  connected and sidebar small-text treatments were strengthened where the prior colors fell below
  the intended contrast floor.
- Reduced motion was enabled in the review browser; the loaded stylesheet applied the global
  reduced-duration rule, and no external font or page asset was loaded.
- Backend access logs contained GET health/catalog requests only; the authentication attempt
  endpoint was never called.
- Browser console review returned zero warnings and zero errors.
- Foreground, muted text, primary controls, and the strengthened attention-text token meet at least
  WCAG AA 4.5:1 against their intended light surfaces.
