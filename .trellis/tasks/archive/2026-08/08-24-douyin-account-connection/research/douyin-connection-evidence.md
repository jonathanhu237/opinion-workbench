# Douyin connection evidence

Date: 2026-08-24 (Asia/Shanghai)

## Prior product decisions

- Project session memory records the user's explicit decision to reuse the existing user Chrome
  rather than an application-specific profile (`codex` session `01a0257f-f89`).
- Earlier Douyin work established that official slider verification is manual-only. The current
  implementation and tests preserve that decision.
- The delivered Weibo and Kuaishou tasks established the shared auth-only subprocess protocol,
  online-proof requirement, single-flight product state, and task-owned-page cleanup boundary.

## MediaCrawler current state

- `media_platform/douyin/core.py:67-125` supports CDP, creates/registers one page, checks login, and
  then immediately enters normal crawler branches; there is no `auth` early return.
- `media_platform/douyin/core.py:360-392` falls back to a standard browser when CDP fails. That
  remains valid for normal crawler mode but violates the fail-closed borrowed-Chrome auth contract.
- `media_platform/douyin/core.py:394-402` delegates CDP cleanup to the shared manager, which already
  has task-page ownership support used by Weibo and Kuaishou.
- `media_platform/douyin/client.py:150-159` calls the method `pong()` but returns true solely from
  LocalStorage `HasUserLogin` or Cookie `LOGIN_STATUS`; it is not a fresh online proof.
- `media_platform/douyin/login.py:54-105` waits for local Cookie/LocalStorage markers and can exit
  from inside the helper; auth-only mode needs typed bounded results instead.
- `media_platform/douyin/login.py:120-133` extracts and displays QR image bytes in the normal
  crawler flow. Auth-only mode must keep the official page visible and skip this branch.
- `media_platform/douyin/login.py:167-197` already detects a slider and waits for manual completion
  without solving it; `tests/test_douyin_manual_slider.py` covers no-slider, manual completion, and
  timeout behavior.
- `cmd_arg/arg.py:371-405` currently allows `--type auth` only for `wb | ks`, while
  `tools/auth.py:47-49` has the same two-platform typed enum.

## Product current state

- `backend/src/longtian_api/services/platform_connections.py:47-51` trusts only `wb | ks` as child
  platforms, and lines `385-391` keep Douyin `coming_soon`.
- The backend already validates exact platform-tagged events, owns one global subprocess slot, and
  has bounded timeout/cancellation/process-group cleanup. Douyin should extend these shared paths.
- `frontend/src/App.test.tsx:63-92` models Douyin as coming soon and tests only two actionable rows.
- `frontend/src/routes/workbench.tsx:84-88` hard-codes Weibo/Kuaishou readiness copy even though the
  counts themselves are derived from enabled catalog entries.
- The account-center row and guidance implementation are already platform-generic; enabling
  Douyin should not require a new route or a duplicated card component.

## Planning implications

- The first implementation gate is a fresh read-only official-page online-auth probe. Local state
  may wake the probe but never decide the terminal result.
- Reuse and extend the protocol/command/catalog/UI path; do not create a Douyin-only backend API or
  frontend flow.
- Real Chrome acceptance remains required because official-page selectors and challenge behavior
  cannot be proven solely with mocks.
