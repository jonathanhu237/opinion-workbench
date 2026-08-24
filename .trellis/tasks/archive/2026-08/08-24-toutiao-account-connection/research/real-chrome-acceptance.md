# Real Chrome/Toutiao acceptance

Date: 2026-08-24 (Asia/Shanghai)

## Data boundary

Evidence records only constant auth phases, terminal process category, tab counts, and ownership
results. No Cookie, QR payload, account identifier, profile path, debugger URL, authorization
material, challenge content, or page content was retained.

## Run result

- The borrowed-Chrome authentication-only worker ran as `--platform toutiao --type auth`.
- The user granted the visible Chrome debugger approval that the earlier post-fix attempts did not
  receive.
- Protocol phases were `waiting_for_approval -> checking -> connected`.
- Exit code was `0`, the connected terminal category, preceded by the valid terminal `connected`
  event.
- The authoritative fresh official-page DOM classification produced `connected`; no Cookie, state
  file, prior page state, or process signal was used as proof.
- The already-authenticated fast path applied, so no manual QR, SMS, slider, or other challenge
  step was required.
- No search, detail, creator, comment, media, store, database, or `BrowserAuthStateStore` entry
  point was reached.

## Browser ownership

- Post-run Chrome total open tabs: `3`.
- Remaining Toutiao task-owned tabs after cleanup: `0`.
- Chrome, the borrowed context, and the pre-existing tabs all survived the run.
- No borrowed context, browser, user page, or non-task process was closed or terminated.

## Rollout gate result

- Positive online proof: passed.
- Borrowed-browser ownership and owned-page cleanup: passed.
- Secret-free evidence boundary: passed.

The gate is satisfied, so the product catalog promotes only the Toutiao entry from `coming_soon` to
`enabled/not_checked`. Xiaohongshu remains `coming_soon`. See `live-dom-diagnostic.md` for the
preceding selector-drift diagnosis and the two approval-timeout attempts, and
`offline-validation.md` for the automated baseline.

## Cross-layer rollout smoke

- A fresh loopback frontend was served through the configured Vite `/api` proxy to the promoted
  backend catalog.
- The workbench rendered platform readiness as `0 / 4` and named exactly 微博、抖音、快手、今日头条
  as the enabled login checks; the copy reported one remaining unavailable platform.
- The account center rendered four `检测连接` actions for those enabled platforms.
- Xiaohongshu remained visible as `待接入` / `暂不可用` with no connection action.
- A fresh browser tab reported zero console errors or warnings.
- The smoke check caught an initial production-only denominator defect (`0 / 5` from total catalog
  length). The implementation and behavior test now derive both numerator and denominator from
  `availability === "enabled"` before this evidence was accepted.
