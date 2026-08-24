# Real Chrome/Douyin acceptance

Date: 2026-08-24 (Asia/Shanghai)

## Run result

- The borrowed-Chrome authentication-only worker emitted `checking -> connected`.
- The authoritative official online probe classified the existing session as connected.
- The worker exited normally after the terminal connected event.
- No manual QR, SMS, slider, or other challenge step was required on this already-authenticated
  fast path.

## Browser ownership

- Pre-run Chrome tab count: `22`.
- Post-run Chrome tab count: `22`.
- Missing pre-existing baseline tabs: `0`.
- New task-owned tabs remaining after cleanup: `0`.
- Chrome remained available and the borrowed-browser ownership boundary was preserved.

## Data boundary

- Evidence records only constant auth phases, terminal process category, and tab counts.
- No Cookie, QR payload, account identifier, profile path, authorization material, challenge
  content, or page content was retained.
- The run used `--platform dy --type auth`; the delivered auth branch terminates before collection
  and store entry points.
