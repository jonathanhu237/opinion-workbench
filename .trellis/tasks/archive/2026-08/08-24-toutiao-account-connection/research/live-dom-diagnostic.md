# Toutiao live DOM diagnostic and product acceptance attempts

Date: 2026-08-24 (Asia/Shanghai)

## Data boundary

The diagnostic used the user's existing Chrome session and the official HTTPS Toutiao homepage.
It retained no identity, account name, avatar URL, page text, Cookie, storage, Profile path,
debugger URL, content link, or challenge detail. Evidence below is restricted to boolean state,
anonymous DOM shape, protocol phases, exit categories, and ownership behavior.

## Live DOM result

- Official origin: yes (`https`, trusted Toutiao hostname).
- Visible exact login entry: no.
- Legacy visible `data-e2e="user-avatar"`: absent.
- Challenge-term booleans: all false.
- Exactly one visible banner-scoped anchor matched `role="button"`,
  `aria-haspopup="true"`, and a visible image.
- The control used a same-origin account route. Its route contents were not retained.
- A separate publisher control was a `div.publisher-icon`, not an anchor, so it did not satisfy
  the account selector.

This proves the previously implemented `data-e2e`-only selector was a false negative on the
current official page. The classifier now preserves the guarded legacy selector and additionally
accepts only the observed banner/account-menu shape. Synthetic DOM tests pair the current positive
case with content-profile, missing-image, hidden, challenge, login-entry, and untrusted-origin
negative/inconclusive cases.

## Exact worker attempts

1. Pre-fix worker run:
   - Chrome debugger approval succeeded.
   - Protocol reached `checking -> waiting_for_login -> checking -> disconnected`.
   - Exit category was disconnected (`20`).
   - The task-owned Toutiao page was closed; the borrowed context/browser remained open.
   - The live diagnostic subsequently established that this was selector drift, not proof of an
     anonymous Chrome session.
2. Diagnostic rerun before the selector fix:
   - Chrome debugger approval was not granted within the 60-second connection window.
   - Exit category was browser unavailable (`21`); no fallback browser was launched.
3. Post-fix acceptance attempt:
   - Chrome debugger approval was not granted within the 60-second connection window.
   - Exit category was browser unavailable (`21`); no fallback browser was launched.

## Post-fix automated verification

- Focused Toutiao/auth parser suite: `79 passed`.
- Maintained MediaCrawler `tests/`: `336 passed`.
- Backend Ruff format and lint: passed.
- Backend pytest: `75 passed`.

## Rollout gate resolved

The post-fix exact worker run subsequently received the user-visible Chrome debugger approval and
proved `connected`, exit `0`, owned-page cleanup, and survival of the borrowed browser/context. See
`real-chrome-acceptance.md`. Toutiao is therefore promoted to `enabled/not_checked` in the backend
catalog and exposed as the fourth actionable platform in React.
