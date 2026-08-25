# Research: Monitoring Rules Frontend UX and Architecture

- Query: How should the existing React/shadcn administration shell expose a simple, real monitoring-rule configuration page across desktop and mobile?
- Scope: mixed (project source/specs plus official library documentation)
- Date: 2026-08-25

## Findings

### Product boundary

- The page has one job: maintain reusable named rules and their alternative search terms. It must not select platforms or expose run/schedule/result controls (`prd.md:20`, `prd.md:29`, `prd.md:59`).
- Every term is searched independently. The interface should say this once in plain Chinese and must not expose Boolean controls (`prd.md:25`, `prd.md:70`).
- Render only persisted data. Do not add summary cards, readiness indicators, sample results, speculative counts, or a dependency on platform-account state (`prd.md:41`, `prd.md:53`, `prd.md:64`).
- Recommended page copy:
  - title: `监控规则`
  - description: `设置需要持续关注的搜索词。每个搜索词会分别用于搜索。`
  - primary action: `新建规则`
- Preserve the current civic palette, typography, shell width, and density; do not generate another theme for this page. The global tokens already own that visual system (`frontend/src/index.css:46`, `.trellis/spec/frontend/component-guidelines.md:34`). The UI/UX skill search supported a minimal, low-motion, medium-density utility layout, but its unrelated dark “operations landing” palette and metrics pattern do not fit this configuration-only route and should not be applied.

### Recommended layout and interaction

Use one responsive list plus one controlled editor dialog. A table is a poor fit because terms are variable-length text and would force horizontal compression on mobile; a permanent two-pane editor adds state and responsive complexity without helping a single operator.

```text
Desktop
┌─ 监控规则 ───────────────────────────── [新建规则] ─┐
│ 设置需要持续关注的搜索词……                         │
├────────────────────────────────────────────────────┤
│ 规则名称                         [已启用] [编辑][删除]│
│ [龙田街道] [龙田社区] [老坑社区] [竹坑社区] [南布社区]│
├────────────────────────────────────────────────────┤
│ 另一条规则                       [已停用] [编辑][删除]│
│ [噪音扰民] [交通事故]                               │
└────────────────────────────────────────────────────┘

Mobile
┌─ 监控规则 ─────────────────────┐
│ 设置需要持续关注的搜索词……     │
│ [新建规则                    ] │
├───────────────────────────────┤
│ 规则名称              [已启用] │
│ [龙田街道] [龙田社区]          │
│ [编辑]                 [删除] │
└───────────────────────────────┘
```

- Add `/monitoring-rules` as the third real route and navigation item. The shell currently owns both registries (`frontend/src/app/router.tsx:8`, `frontend/src/app/shell.tsx:78`) and derives the page title with a two-route ternary (`frontend/src/app/shell.tsx:170`); replace that ternary with an explicit pathname-to-title mapping or switch so later routes cannot silently appear as `工作台`.
- Keep the existing shell page-title `<h1>` and focus-on-navigation behavior (`frontend/src/app/shell.tsx:161`, `frontend/src/app/shell.tsx:203`). Inside the route, follow the existing page composition with an intro section and content card (`frontend/src/routes/platform-accounts.tsx:378`).
- Render the rules as a semantic `<ul>` with one `<li>`/`article` per rule. Show the real rule name, all terms in their persisted order as wrapping outline badges, and an explicit text state (`已启用` / `已停用`) so status is not conveyed by color alone. Do not clamp the rule name or hide all meaning behind an ellipsis.
- Use visible `编辑` and `删除` shadcn Buttons. A kebab menu saves little space for only two actions and makes the core maintenance flow less discoverable. At narrow widths, stack actions and preserve at least 44px touch targets, as the platform page already does for mobile actions (`frontend/src/routes/platform-accounts.tsx:173`).
- Use a controlled shadcn `Dialog` for both create and edit. It should have `DialogTitle`, a short `DialogDescription`, a scrollable body, and a sticky or always-visible footer. Style one dialog responsively rather than branching between Dialog and Sheet; this avoids duplicated forms and breakpoint-state drift.
- Dialog fields:
  1. `规则名称` — Input.
  2. `搜索词` — Textarea, one term per line. Helper text: `每行输入一个搜索词，粘贴多行可批量添加。系统会分别搜索这些词。`
  3. `启用这条规则` — Switch with a visible label.
- The form should translate the textarea into an ordered term array on submit. Blank lines are ignored, surrounding whitespace is trimmed, but duplicate normalized terms are rejected with a field-level message rather than silently disappearing. The backend remains authoritative for canonical normalization and limits; the design contract must define those exact rules before the frontend mirrors them.
- Use a controlled `AlertDialog` for deletion: title `删除“{规则名称}”？`, description `删除后无法恢复。`, actions `取消` and `删除`. Keep the dialog open and show the API message if deletion fails.
- Do not add a toast dependency for the MVP. Successful create/edit/delete/toggle should update the visible list and a page-level polite live region (for example `已保存“{名称}”`). Validation and mutation failures stay next to the affected field/action; do not rely on transient toast-only errors.

### shadcn/Base UI components

`pnpm dlx shadcn info` reports the expected `base-nova`, Base UI, Tailwind 4, Lucide preset and resolves `@/components/ui` to `frontend/src/components/ui`. Installed primitives are only Badge, Button, Card, Input, Separator, Sheet, Sidebar, Skeleton, and Tooltip.

Add only these named consumers from `frontend/`, then review generated source/dependencies and reject theme overwrites:

- `dialog` — create/edit form and focus containment.
- `alert-dialog` — destructive delete confirmation.
- `field` — visible labels, help text, and connected validation errors.
- `textarea` — batch entry, one term per line.
- `switch` — enabled state in the editor and/or list row.

Do not add Table, Data Table, Dropdown Menu, Drawer, Tabs, Select, Sonner, Motion, or a second responsive component mode. Existing Badge/Button/Card/Input/Skeleton are enough for the list and async states. This follows the repository rule to add shadcn source only with a named feature consumer (`.trellis/spec/frontend/component-guidelines.md:15`) and avoids disallowed speculative dependencies (`.trellis/spec/frontend/quality-guidelines.md:18`).

### State and module ownership

Data flow should be:

```text
FastAPI JSON -> lib/api runtime schema -> TanStack Query cache -> route list
Dialog fields -> React Hook Form + Zod -> API mutation -> cache update/invalidation
```

- `frontend/src/lib/api/monitoring-rules.ts` owns the query key, endpoint functions, strict runtime response parsing, API error class/code mapping, and inferred API-facing types. Parse network JSON as `unknown`; do not cast it (`.trellis/spec/frontend/type-safety.md:23`).
- Prefer Zod schemas for the exact response shapes consumed by this new boundary because Zod is already a direct dependency and the PRD explicitly requires runtime response validation (`frontend/package.json:31`, `prd.md:51`). FastAPI/Pydantic remains authoritative.
- `frontend/src/hooks/use-monitoring-rules.ts` owns the reusable read query (`['monitoring-rules']`) because later collection-task UI will consume enabled rules. Use the request `AbortSignal`, set an explicit local-service retry policy (recommended `retry: false` with a visible retry button), and preserve normal cache lifetime. The singleton QueryClient already exists (`frontend/src/app/providers.tsx:4`).
- Keep create/update/toggle/delete `useMutation` instances in the route or a route-owned helper while this page is their only consumer. On success, write the returned canonical resource into the cache or invalidate the monitoring-rules query; never copy server data into component state (`.trellis/spec/frontend/state-management.md:34`). Avoid optimistic writes for the MVP so database rejection cannot briefly show a false saved state.
- Keep only editor mode, delete target, and short-lived accessible success text in React state. Model editor state as a union (`closed | create | edit(rule)`) rather than parallel booleans. React Hook Form exclusively owns field values; do not mirror them in `useState` (`.trellis/spec/frontend/state-management.md:63`).
- Keep the form Zod schema and textarea-to-terms adapter next to the editor/route, per the type-ownership rule (`.trellis/spec/frontend/type-safety.md:15`). Use `zodResolver`, validate on blur and submit, and map stable backend field errors with `setError`; unknown failures become one form-level `role="alert"`.
- The route should not call `usePlatformConnections`, inspect platform connection state, start MediaCrawler, or launch a browser. The shell's existing health request may still happen globally, but the monitoring-rule query/error is authoritative for this page.
- Respect API ordering; do not independently sort rules or terms in the browser unless the backend contract explicitly delegates ordering to the client. This keeps the future collection consumer deterministic.

### Loading, empty, error, and pending behavior

- Initial load: keep the content card height stable and render 2–3 Skeleton rows plus one visible `role="status"` message: `正在读取监控规则…`. Skeletons are loading affordances, not sample records.
- Empty: `还没有监控规则` plus `新建规则`; no fake recommendation cards or platform prompts. The initial seed normally prevents first-run emptiness, but the state remains reachable after deleting all rules.
- Initial query error: show the stable Chinese API message in `role="alert"` and a shadcn Button `重新加载`. Do not expose paths, SQLite errors, or FastAPI internals.
- Background refetch error with cached rows: retain the rows and show a non-blocking alert above them rather than replacing real data.
- Create/edit pending: disable close-affecting submit actions, label the button `保存中…`, keep the dialog open, and close only after a successful response/cache update.
- Toggle pending: disable only that rule's toggle/actions and expose `正在更新…` through a polite live region. On failure, restore the server state and show a row-level message.
- Delete pending: disable both confirmation actions and label the destructive action `删除中…`; on failure keep the confirmation visible.
- Never turn an API/protocol/service failure into a validation message such as `请填写关键词`; preserve the correct recovery path.

### Accessibility and responsive acceptance

- Every control needs a visible label or an action-specific accessible name (`编辑“{规则名称}”`, `删除“{规则名称}”`, `启用“{规则名称}”`). Lucide icons, if used, are decorative and `aria-hidden` because text labels remain visible.
- Connect `FieldError` to Input/Textarea with `aria-invalid` and the generated description/error identifiers. Keep errors beside fields; add a focusable error summary only if the final form can produce multiple simultaneous failures.
- Let Base UI Dialog/AlertDialog own focus trapping, dismissal, and return focus; do not manually query/focus DOM nodes. On failed submit, focus the first invalid field or an error summary once, not on every blur.
- Status and error text use `aria-live`/`role` appropriately, matching the existing route pattern (`frontend/src/routes/platform-accounts.tsx:398`, `frontend/src/routes/platform-accounts.tsx:434`).
- Mobile layout must not horizontally scroll. Terms wrap and may break long unspaced text; buttons remain at least 44px high below `48rem`. Check 375px, the exact `48rem` boundary, 1024px, and the existing wide shell. No JavaScript breakpoint is needed for the recommended one-Dialog design.
- The existing shell already provides a skip link, accessible main label, mobile Sidebar dialog, and main-focus transfer (`frontend/src/app/shell.tsx:174`, `frontend/src/app/shell.tsx:203`); route tests must preserve them.

### Likely affected files and tests

| File | Change / ownership |
| --- | --- |
| `frontend/src/app/router.tsx` | Register `/monitoring-rules`. |
| `frontend/src/app/shell.tsx` | Add the real nav item/icon and exact page-title mapping. |
| `frontend/src/routes/monitoring-rules.tsx` | Route composition, list rows, controlled editor/delete state, mutations, form schema/adapter. Split a route-owned editor file only if this becomes difficult to review; do not put product models in `components/ui`. |
| `frontend/src/hooks/use-monitoring-rules.ts` | Shared read query for current and future route consumers. |
| `frontend/src/lib/api/monitoring-rules.ts` | Query key, response schemas/types, requests, stable errors. |
| `frontend/src/components/ui/{dialog,alert-dialog,field,textarea,switch}.tsx` | Reviewed shadcn `base-nova` source. |
| `frontend/src/App.test.tsx` | Change desktop/mobile navigation expectations from two to three; assert title, active link, focus, and no redirect. |
| `frontend/src/routes/monitoring-rules.test.tsx` | Behavior-oriented route states and CRUD/form interactions with mocked API boundary. Prefer this focused file over adding another large block to the already 1,000+ line `App.test.tsx`. |
| `frontend/src/lib/api/monitoring-rules.test.ts` | Success, malformed payload, non-JSON, status/code mapping, cancellation/service failure. |
| `frontend/src/index.css` | Prefer no feature CSS; use current tokens/Tailwind. Review shadcn generation to ensure it does not replace theme variables. |
| `frontend/package.json`, `frontend/pnpm-lock.yaml` | Change only if generated components require a new direct dependency; keep lock synchronized. |

Required behavior tests:

- real rule rendering in API order; enabled and disabled states distinguishable without color;
- initial loading, empty, error/retry, cached-data refetch error;
- create/edit payloads, textarea line parsing, blur/submit errors, whitespace, duplicate and over-limit handling;
- toggle success/failure and row-only pending lock;
- delete cancel, confirm, pending and failure;
- dialog accessible name/focus return and mobile action availability;
- `/monitoring-rules` desktop/mobile navigation, active state, page heading/main label/focus;
- no platform selector/run action, no platform connection fetch, and no browser/MediaCrawler action from this route.

Run the frozen gates in `.trellis/spec/frontend/quality-guidelines.md:40`, then a loopback browser smoke test at desktop and 375px with console/overflow inspection (`.trellis/spec/frontend/quality-guidelines.md:24`).

## Files Found

- `.trellis/tasks/08-25-keyword-settings/prd.md` — confirmed configuration-only rule model, OR semantics, persistence, and acceptance criteria.
- `.trellis/spec/frontend/{directory-structure,state-management,component-guidelines,type-safety,quality-guidelines}.md` — module, state, shadcn, validation, accessibility, and test contracts.
- `.trellis/spec/guides/{code-reuse-thinking-guide,cross-layer-thinking-guide}.md` — reuse and API-boundary ownership checks.
- `frontend/package.json` — React 19, TanStack Query 5.102, React Hook Form 7.86, Zod 4.4, Base UI 1.7, shadcn 4.19, and the existing test/toolchain versions.
- `frontend/components.json` — `base-nova`/Base UI/Lucide/Tailwind variable preset and aliases.
- `frontend/src/app/router.tsx` — current two-route child registry.
- `frontend/src/app/shell.tsx` — current shadcn Sidebar navigation, title mapping, skip link, and focus transfer.
- `frontend/src/routes/platform-accounts.tsx` — established route composition, shadcn Button/Card/Badge usage, async and responsive action patterns.
- `frontend/src/hooks/use-platform-connections.ts` — existing reusable TanStack Query hook pattern.
- `frontend/src/lib/api/platform-connections.ts` — existing exact-shape runtime parsing and stable API error pattern.
- `frontend/src/App.test.tsx` — router/provider harness, desktop/mobile navigation assertions, accessible async-state testing; currently over 1,000 lines.
- `frontend/src/test/setup.ts`, `frontend/vitest.config.ts` — jsdom, Testing Library cleanup, and `matchMedia` setup.
- `frontend/src/components/ui/` — installed shadcn primitives; Dialog, AlertDialog, Field, Textarea, and Switch are not present.

## Code Patterns

- Router and shell own navigation: `frontend/src/app/router.tsx:8`, `frontend/src/app/shell.tsx:74`.
- Route content belongs under `src/routes`, HTTP/runtime validation under `lib/api`, and reusable queries under `hooks`: `.trellis/spec/frontend/directory-structure.md:43`.
- Singleton QueryClient: `frontend/src/app/providers.tsx:4`.
- Query functions accept TanStack's abort signal and opt out of retry in the current local-resource hook: `frontend/src/hooks/use-platform-connections.ts:15`.
- Raw JSON stays `unknown` until exact consumed shape validation: `frontend/src/lib/api/platform-connections.ts:196`, `frontend/src/lib/api/platform-connections.ts:254`.
- Async route state uses visible status/alert semantics and actionable retry: `frontend/src/routes/platform-accounts.tsx:420`, `frontend/src/routes/platform-accounts.tsx:434`.
- Tests render the real route tree with a per-test QueryClient and mock the narrow API boundary: `frontend/src/App.test.tsx:107`, `frontend/src/App.test.tsx:230`.

## External References

- shadcn/ui Base [Dialog](https://ui.shadcn.com/docs/components/base/dialog) — official responsive modal composition, scrollable content, and sticky footer examples.
- shadcn/ui Base [Alert Dialog](https://ui.shadcn.com/docs/components/base/alert-dialog) — official destructive confirmation composition.
- shadcn/ui Base [Field](https://ui.shadcn.com/docs/components/base/field), [Textarea](https://ui.shadcn.com/docs/components/base/textarea), and [Switch](https://ui.shadcn.com/docs/components/base/switch) — labels, descriptions, errors, invalid/disabled state, and toggle composition.
- shadcn/ui [React Hook Form](https://ui.shadcn.com/docs/forms/react-hook-form) — `useForm`, `Controller`, Field, Zod resolver, error, switch, and reset patterns for current shadcn.
- TanStack Query v5 [Invalidations from Mutations](https://tanstack.com/query/latest/docs/framework/react/guides/invalidations-from-mutations) — invalidate related server-resource queries after successful mutation.
- Installed versions verified locally: `@base-ui/react` 1.7.0, `@tanstack/react-query` 5.102.0, `react-hook-form` 7.86.0, `zod` 4.4.3, `shadcn` 4.19.0 (`frontend/package.json:19`).

## Related Specs

- `.trellis/spec/frontend/directory-structure.md`
- `.trellis/spec/frontend/state-management.md`
- `.trellis/spec/frontend/component-guidelines.md`
- `.trellis/spec/frontend/type-safety.md`
- `.trellis/spec/frontend/quality-guidelines.md`
- `.trellis/spec/guides/code-reuse-thinking-guide.md`
- `.trellis/spec/guides/cross-layer-thinking-guide.md`

## Caveats / Not Found

- No monitoring-rule route, API client, query hook, fixtures, or tests exist yet.
- The task does not yet define exact name/term length limits, Unicode/case normalization, duplicate rule-name policy, API error codes, or server ordering. These must be fixed in the cross-layer design before form messages and runtime schemas are implemented.
- The existing shell always performs its health request, even on configuration routes. “Independent of platform account state” can be guaranteed; eliminating the shell health request is a separate shell architecture decision and is not required here.
- The initial seed means a fresh database is non-empty, but the product still needs an empty state after the operator deletes every rule.
- `pnpm dlx shadcn info` resolved the correct UI path. Adding components may still propose global CSS or dependency changes; review the diff and preserve the current theme rather than accepting unrelated generated changes.
