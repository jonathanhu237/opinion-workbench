# Kuaishou connection evidence

## Existing reusable boundaries

- The product already has a five-platform API contract, one global authentication-task lock,
  bounded subprocess cleanup, strict constant-only child events, TanStack Query polling, and a
  real Weibo borrowed-Chrome acceptance baseline.
- `KuaishouCrawler` already supports `CDPBrowserManager`, registers its created page, performs a
  login attempt only when the first check fails, refreshes Cookies in memory, and checks again.
- `KuaiShouClient.pong()` calls the signed `visionProfileUserList` operation and accepts only
  `result == 1`. This is stronger evidence than the login helper's local `passToken` check and must
  remain the only route to the product-level `connected` state.
- The existing product platform ID, response decoder, status enum, and button rendering already
  include `ks`; no API shape or new route is required.

## Gaps that block product use

1. `cmd_arg/arg.py:371-388` rejects every auth platform except `wb` and overwrites the selected
   platform with `wb`.
2. `KuaishouCrawler.start()` does not return an auth terminal phase or emit the versioned child
   events expected by FastAPI.
3. `KuaishouCrawler.launch_browser_with_cdp()` falls back to a standard browser after a CDP
   failure; borrowed-Chrome authentication must fail closed.
4. `KuaishouLogin.login_by_qrcode()` extracts QR image material, launches an extra image viewer,
   and exits through `sys.exit()` on failure. The connection center must keep only the official
   visible page and return a bounded, testable timeout outcome.
5. FastAPI hard-codes `--platform wb` and validates child events with `platform: Literal["wb"]`.
6. The React guidance panel always selects Weibo and contains hard-coded Weibo copy, so enabling
   the existing Kuaishou row alone would show the wrong operator instructions.

## Design conclusions

- Extend the existing version-1 authentication protocol; do not create a Kuaishou-specific event
  format or endpoint. `waiting_for_login` covers QR scan, slider, CAPTCHA, and any other official
  manual challenge without exposing challenge details.
- Build the FastAPI command from a trusted enabled-platform catalog and validate every event
  against the attempt's expected platform. Do not loosen event validation to arbitrary strings.
- Add a `visible_page_only`/authentication-only branch to the Kuaishou login helper while retaining
  its current viewer behavior for normal crawler modes.
- Choose frontend guidance from the active connection, otherwise the connection with the newest
  `last_checked_at`, and fall back to the first enabled platform. This avoids introducing parallel
  client state and remains correct after polling reaches a terminal result.
- Keep `auth` globally single-flight. A platform-specific lock would allow two processes to compete
  for the same borrowed Chrome and would violate the established ownership boundary.

## Real-world unknowns requiring acceptance

- Kuaishou's login entry and QR selectors may have drifted.
- The official page may present a slider or other security challenge before or after QR scan.
- The signed online probe must be verified against the user's actual authenticated Chrome session.

These are acceptance unknowns, not reasons to add automatic challenge handling or private-response
inspection. The real run should record only event transitions, result category, owned-page counts,
and whether a pre-existing sentinel tab survives.
