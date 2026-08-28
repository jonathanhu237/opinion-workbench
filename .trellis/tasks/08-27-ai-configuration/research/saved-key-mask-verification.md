# Saved API Key Mask — 2026-08-27

## Scope and Behavior

User requested asterisks when an API Key is already configured, then clarified that they should
be literal normal-color text and more numerous. This revision supersedes the eight-character
placeholder. The existing shadcn password input now has a display-only overlay of 20 literal
asterisks in normal foreground color, shown for `has_api_key` with an empty/unfocused input. Focus
or typing hides it; empty blur restores it. The overlay is aria-hidden and pointer-events-none,
with matching input padding/font and disabled opacity. RHF's actual value stays empty until the
user types a replacement. No real key/length, sentinel form value, provider request, backend change,
global style or shared-component change was introduced.

Colocated tests now cover literal text rather than a placeholder, saved/unconfigured display,
focus/empty-blur, replacement typing/clearing, first save and reopen, failed-save clearing,
pending opacity state, unchanged dirty state, same-endpoint model-only key omission and
endpoint-change rejection even when the mask is visible. The frontend state-management
contract records why the mask must never become form data.

## Main-Session Checks

- Formatted only the two locally edited frontend files with Prettier; both were already formatted.
- Synchronized changed source and task/spec records one-way to Centaurus. Runtime data, credentials,
  browser profiles and Git metadata were not synchronized.
- Centaurus frozen frontend gates all passed under mise Node 24 and pnpm 11.14.0: frozen install,
  format check, lint (zero warnings/errors), TypeScript, **10 test files / 165 tests**, and Vite build.
  AI settings contributes **13 component tests**. No backend gate was rerun for a frontend-only
  display change. All gates were rerun after this 20-star revision, not reused from the first mask.
- Non-saving UI smoke on the existing running app at `/ai-settings` confirmed the API Key label
  and help remain visible, input type is `password`, placeholder is absent, and the rendered overlay
  contains exactly 20 asterisks with the foreground token. Actual value is empty, Save is disabled
  and there is no dirty hint. Clicking API Key hides the overlay without changing the value or Save
  state; clicking Base URL without typing restores the mask and leaves the form clean. Screenshot
  inspection confirms ordinary dark asterisks aligned within the input. Console: zero warnings/errors.
  A new owned in-app tab is retained for the user; prior owned tabs were already absent at discovery.
- No real key was entered or read; no Save or Test action was invoked, so saved settings were not
  changed and no model call was made. Persistence/replacement/failure cases use isolated component
  tests and fake API responses, not live credential mutation.
- Local diff/context checks passed. No commit, push or archive was requested or performed.

Independent source/evidence review is recorded separately in `saved-key-mask-check.md`; remote
gates and browser smoke are main-session evidence, not an independent live replay by the reviewer.
