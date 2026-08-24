# Toutiao account-connection evidence

Date: 2026-08-24 (Asia/Shanghai)

## Prior decisions and delivered baselines

- Project session memory records the user's decision to reuse the existing user Chrome for the
  product account center rather than an application-specific Profile (Codex session
  `01a0257f-f89`).
- The delivered Weibo, Kuaishou, and Douyin tasks established the authentication-only subprocess,
  constant event protocol, global single-flight service, manual-only official challenges, online
  proof requirement, and task-owned page cleanup contract.
- The archived Toutiao adapter task
  `.trellis/tasks/archive/2026-08/08-23-research-mediacrawler-toutiao-adapter/` deliberately chose a
  different lifecycle for ordinary search: fresh standard visible context, no CDP/persistent
  Profile, optional allowlisted Cookie state, separate Auth/Search Pages, and first-page DOM-only
  search.
- That task's live evidence records a successful manual official challenge/login and a full browser
  restart whose DOM online check remained authoritative. It does not prove the borrowed user Chrome
  ownership boundary, so the present task still requires a new real acceptance.

## Current MediaCrawler gaps

- `cmd_arg/arg.py:371-417` allows auth only for `wb | dy | ks`, although the normal CLI/factory
  already recognizes `toutiao`.
- `tools/auth.py:47-51` lacks the Toutiao typed protocol member.
- `media_platform/toutiao/core.py:44-117` ignores CDP and always enters the fresh standard browser
  search lifecycle; no auth-only early return exists.
- `media_platform/toutiao/core.py:119-139` rejects every crawler type other than search.
- `media_platform/toutiao/core.py:68-105` owns optional `BrowserAuthStateStore` restore/save. The
  new auth path must structurally bypass it while leaving this normal-search behavior unchanged.
- `media_platform/toutiao/client.py:78-145` already evaluates bounded booleans for account signal,
  login entry, and challenge. It currently collapses non-positive states to `False`; the product
  connection boundary should classify explicit anonymous vs inconclusive structure drift.
- `media_platform/toutiao/login.py:84-139` navigates the official visible page, optionally opens
  the login entry, leaves official challenges to the user, tolerates only one navigation race, and
  waits with a bound. Unlike older platform flows, it does not extract QR bytes.
- Toutiao has no `CDPBrowserManager` member or launcher method. The auth path needs the shared
  manager with the same fail-closed and registered-page ownership behavior already used by the
  three delivered platforms.

## Current product gaps

- `backend/src/longtian_api/services/platform_connections.py:47-52` trusts exact
  `wb | dy | ks`; lines `412-420` keep Toutiao unavailable.
- The backend's command builder, constant-event parser, phase transition validation, global task
  lock, timeout/cancellation, and process-group cleanup are already platform-generic.
- `frontend/src/routes/platform-accounts.tsx:143-205` renders any enabled platform generically and
  lines `79-112` already produce platform-aware guidance. No new Toutiao component is needed.
- `frontend/src/routes/workbench.tsx:67-96` derives enabled names, counts, and readiness copy from
  the API, so enabling a fourth platform should be a fixture/test change rather than new product
  logic.

## Planning implications

- Keep authentication readiness and ordinary search as separate browser entry paths in the same
  crawler class; do not replace or relax the existing search isolation contract.
- Refine the current live DOM check into a fail-closed tri-state result and retain a real positive
  rollout gate. Do not introduce private-response replay merely to imitate other platforms.
- Reuse the shared protocol, backend service, account row, polling, guidance, and readiness copy;
  do not add Toutiao-specific endpoints or frontend state.
- Real evidence must cover both online-positive classification and borrowed-Chrome ownership,
  because the archived Toutiao task proved only the former in a fresh project browser context.
