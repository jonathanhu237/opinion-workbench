# Saved-Key Mask Follow-up Review

Date: 2026-08-27. Independent source review by the existing Trellis check role.
Scope: the approved display-only saved-key mask follow-up, not the historical
configuration implementation or unrelated live-search acceptance work.
This review covers the clarified 20-star normal-foreground overlay and supersedes
the earlier eight-star placeholder review in this file.

## Findings (fixed)

None. No product or test correction was needed; the reviewer changed only this
review record.

## Findings (not fixed)

None found in the follow-up. No design change or scope expansion is recommended.

## Review Evidence

- Read `check.jsonl`, its referenced specifications/research, and the child PRD,
  design and execution follow-up. Reviewed the complete current product/test diff
  and its surrounding form and Input implementation.
- The display is a span containing exactly 20 literal asterisks with
  `text-foreground`, not a placeholder or browser password dots. It appears only
  when `saved.has_api_key` is true, the actual input is empty, and local focus
  state is false. The fixed text has no relationship to the real key or its
  length. RHF defaults/reset values and the actual password input are unchanged.
- Focus hides the display; empty blur restores it; nonempty blur leaves it
  hidden. The composed blur handler still calls `field.onBlur()`, preserving RHF
  behavior. Local focus state is not form or server data.
- The overlay is `aria-hidden`, `pointer-events-none` and non-selectable. It does
  not replace the visible label/help or intercept editing. Its font sizes and
  left padding follow the existing Input. During pending operations its opacity
  follows the disabled input while the existing fieldset remains disabled; the
  overlay creates no new interactive control.
- Dirty state still derives from RHF values. Merely showing the mask cannot
  enable Save or disable testing. Typing then clearing a replacement restores
  the empty value and unchanged-state controls.
- Save still conditionally includes `api_key` only when the typed value is
  nonempty. Model-only updates omit the key, so the display text cannot be sent as
  a replacement. The existing direct API boundary/cache policy is unchanged.
- Endpoint-change validation still checks the actual value, not the overlay.
  The regression explicitly shows the mask while an empty key prevents saving a
  new endpoint. Successful saves, failed-save clearing and reopening are covered.
- Tests cover configured/unconfigured display, literal text/color, no placeholder,
  unchanged initial controls, focus/blur with empty and typed values, replacement
  clearing, save/reopen and failed-save clearing, pending/restored disabled state,
  key omission/no-mask payload, and unchanged endpoint-change validation.
- The updated frontend state-management specification matches the source and
  regression coverage. Product edits remain limited to the route and its tests;
  no shared Input/global styling, backend, dependency, route-registration or
  provider-call changes were introduced.

## Verification

- Reviewer-run `git diff --check`: pass.
- Main-session-reported Centaurus gates, not independently replayed by this
  reviewer: frozen install, format check, lint (zero warnings/errors), TypeCheck,
  tests (165 passed / 10 files, including 13 AI settings form tests) and production
  build all passed using `mise x node@24 pnpm@11.14.0 -- pnpm ...`.
- These are the main session's latest gate results for the clarified overlay,
  not the superseded placeholder implementation.
- Main-session-reported browser smoke: 20 literal normal-foreground stars, no
  placeholder, password type, actual input empty and Save disabled. Clicking the
  API Key input hides the overlay without changing its value or dirty state;
  moving focus to Base URL without editing restores the 20 stars. Console had
  zero warnings/errors. No key was typed/read and no save, connection test or
  provider call was made. This reviewer did not operate or independently inspect
  that browser.
- The reviewer did not access runtime data, real keys, browsers, APIs or providers,
  modify remote files, run local heavy checks, commit, push, archive, or edit the
  historical `check-review.md`.

Applied `trellis-check` for contract/coverage review and `ui-ux-pro-max` for the
existing shadcn/RHF label, value and validation boundaries. No product changes
resulted from the review.
