# Real Chrome / Weibo acceptance evidence

Date: 2026-08-24 (Asia/Shanghai)

This evidence intentionally records no Cookie, QR, authorization header, page content, account
identity, browser profile path, or raw child-process output.

## Attempts

### Attempt 1 — expected approval timeout

- Observed product transitions: `checking -> action_required(enable_remote_debugging) -> failed`.
- Exit category: browser/CDP unavailable or approval timeout.
- The first macOS launch did not visibly navigate the running Chrome instance to the internal
  settings page; the user opened `chrome://inspect/#remote-debugging` manually. The launcher was
  subsequently changed to use macOS LaunchServices and covered by Darwin command/ownership tests.
  That automatic visible-open fix was not re-exercised after remote debugging was already enabled.
- Ownership result: the pre-existing Chrome instance remained usable and the harmless
  `https://example.com/` sentinel tab remained open.

### Attempt 2 — existing authenticated session

- Observed product transitions:
  `checking -> action_required(enable_remote_debugging) -> checking -> connected`.
- Terminal time reported by the API: `2026-08-23T22:53:13.192801Z`.
- Exit category: connected (`0`) after the authoritative online Weibo probe succeeded.
- No QR or manual Weibo login was required because the borrowed Chrome session was already
  authenticated.
- React terminal state: `connected`; browser console warnings/errors: `0`.

## Ownership and containment

- Debug listener count on port 9222: `1`, bound only to `127.0.0.1`.
- Harmless sentinel tabs still present after completion: `1`.
- Task-created Weibo pages still present after completion: `0`.
- Chrome remained open and usable after both timeout and success.
- Authentication-only configuration disabled search, detail, creator, comment, media, database,
  state-file, proxy, and word-cloud work. Automated failing sentinels proved that content entry
  points were not reached.
