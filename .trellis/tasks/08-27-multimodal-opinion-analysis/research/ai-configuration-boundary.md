# AI Configuration: Existing Boundaries and Planning Notes

## Repository Evidence

- `frontend/src/app/router.tsx` defines the workbench, platform accounts, monitoring rules, collection runs, and batch detail routes. There is no AI settings route.
- `frontend/src/app/shell.tsx` owns the sidebar items and page titles. A new settings entry can use the same navigation structure without restoring the previously removed placeholder sections.
- `frontend/package.json` already includes React Hook Form, Zod, the resolver integration, TanStack Query, and shadcn/Base UI. `frontend/src/components/ui/` already contains Field, Input, Label, Button, and Card primitives.
- `backend/src/longtian_api/api/router.py` has no AI settings or model API route. Inspection of `backend/src` found no API-key credential store or OS-keychain integration. Do not claim that secret persistence is already implemented.
- `.trellis/spec/backend/database-guidelines.md` defines backend-owned SQLite persistence and forbids network/model work inside database transactions. It does not define an API-key encryption or secret-storage contract.

## Minimal UI Direction

The page's single job is to let this application's local operator save and check a model endpoint. Preserve the current palette, typography, and layout conventions. Use clear labels for API Key, Base URL, and model name, plus direct action labels such as `保存` and `测试连接`. Do not add a hero, decorative metric cards, provider marketing, or a general system-settings dashboard.

The `ui-ux-pro-max` search for `form field validation` in the `shadcn` stack returned React Hook Form/Controller plus Field primitives and associated FieldError feedback. This matches the installed stack; the separate TanStack Form recommendation does not apply. `frontend-design` reinforces the user's request for purposeful controls and concise copy, not a palette redesign.

No rendered UI or product implementation has been created during this planning work.

## Contract and Safety Items for Design

- Keep API calls and secret ownership in the backend. Read responses can contain Base URL, model name, and key-presence state, but not the saved key.
- The browser may hold a newly typed key only while submitting it; do not persist it in local/session storage or query caches. Decide replacement/reset semantics explicitly before implementation.
- Save configuration separately from network testing. Testing must be a deliberate user action with a bounded synthetic request, never an automatic post/media upload on page load or save.
- A successful text connection test is not proof that images, video, or audio were understood. Model capability checks and media acceptance tests belong to the downstream analysis contract.
- Bind a saved credential to the user's intended endpoint. Do not silently forward it after a host change or across a redirect to another host. Validate URL structure and keep secrets out of URL fields and error text.
- Choose a backend-only at-rest credential mechanism before implementation; do not claim ordinary SQLite storage is encrypted or put the key in a committed environment file.
- The user approved one active configuration shared by assessment and summary, with explicit save and connection-test actions. Multiple provider profiles and separate per-stage settings are outside the approved first-version configuration scope.

## Potential Delivery Boundary

AI configuration can be verified without real platform media: save/read/update/restart behavior, secret non-disclosure, bounded connection testing, and truthful error handling. Downstream analysis depends on this configuration contract and on a separate content-enrichment contract. If split into child tasks, these dependencies must be written into their artifacts rather than inferred from task order.
