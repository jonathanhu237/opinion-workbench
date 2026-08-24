# XHS account-connection planning evidence

Date: 2026-08-24

## Prior decisions recovered from project history

- The five JD platforms are Weibo, Douyin, Kuaishou, Xiaohongshu, and Toutiao.
- XHS was deliberately deferred until the other platforms because its risk controls are stricter.
- The user later approved working on XHS and selected the shared account-center model: borrow the
  user's visible Chrome, require human handling of official challenges, and do not automate bypasses.
- The product is single-user and local; account-center connection state is ephemeral and credentials
  do not belong in the application database.

Sources: current Codex conversation and local `trellis mem search "小红书"` results for project
session `01a0257f-f892-7730-b626-9037f2c73e69`.

## Previously proven XHS behavior

The archived `08-24-verify-mediacrawler-xhs-login` task proved on the domestic XHS site that:

- visible official QR login can succeed;
- login completion is authoritatively confirmed by `XiaoHongShuClient.pong()` against the official
  self-info endpoint;
- no content collection is required to validate authentication;
- official challenges remain manual-only;
- an isolated Chrome Profile alone did not survive the two-run baseline, while the explicit
  `BrowserAuthStateStore` fallback did.

That acceptance used MediaCrawler's own isolated Chrome and therefore does not prove the current
product's borrowed-user-Chrome orchestration, task-page ownership, fixed event protocol, FastAPI
state, or React flow.

Source: `.trellis/tasks/archive/2026-08/08-24-verify-mediacrawler-xhs-login/research/validation-results.md`.

## Current implementation gaps

- `cmd_arg/arg.py:371-418` excludes XHS from auth-only mode, although it already forces the correct
  fail-closed no-storage/no-collection settings for supported platforms.
- `tools/auth.py:47-51` has no constant XHS platform event value.
- `media_platform/xhs/core.py:71-153` has no early auth-only path; it can create/register a Page and
  call `pong()`, but continues through ordinary state-store and crawler lifecycle.
- `media_platform/xhs/login.py:167-211` extracts and re-renders QR image data, which violates the
  visible-page-only account-center boundary used by the delivered platforms.
- `media_platform/xhs/client.py:272-304` already supplies the strongest available success proof: a
  signed official self-info call reduced to boolean success.
- `backend/src/longtian_api/services/platform_connections.py:47-53,375-422` omits XHS from trusted
  workers and keeps it `coming_soon`.
- `frontend/src/routes/platform-accounts.tsx:143-205` is already generic; Workbench readiness in
  `frontend/src/routes/workbench.tsx:67-93` is data-derived and only needs new expectations.

## Planning conclusion

The minimum viable change is a fifth shared auth-protocol platform, not a new XHS subsystem. Add a
borrowed-Chrome auth-only branch, keep the official QR/UI inside Chrome, treat UI/Cookie changes only
as wake-up hints, and gate success on a fresh `pong()`. Reuse the existing FastAPI service and React
row, promote the catalog only after real positive acceptance, and preserve the ordinary XHS crawler.
