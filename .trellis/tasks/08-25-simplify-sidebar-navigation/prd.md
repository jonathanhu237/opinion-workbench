# 精简侧边栏导航

## Goal

Keep the application shell focused on two honest destinations: an intentionally empty workbench home page and the working platform-account page. Remove unfinished feature choices and fabricated dashboard content so future modules appear only when they are implemented.

## Background

- The original sidebar exposed `工作台`, `平台账号`, and five disabled placeholder items marked `规划中` in `frontend/src/app/shell.tsx`.
- The task initially reduced the active route tree to `/platform-accounts`, but the user later clarified that `工作台` should remain as the home page even while it has no content.
- The existing workbench component still contains speculative status cards, readiness steps, and future-module copy that must not return with the route.

## Requirements

- The primary sidebar navigation must contain exactly two destinations in this order: `工作台` and `平台账号`.
- Keep `工作台` as the application home page at `/` and mark it active only on the root path.
- Make the workbench route intentionally empty: the shell header may identify the page as `工作台`, but the route body must not render metrics, cards, setup steps, empty-state copy, or placeholder actions.
- Remove all five disabled `规划中` placeholder entries.
- Remove the redundant sidebar footer copy `单机值守模式 / 数据与浏览器操作仅留在本机` and the separator dedicated to that footer.
- Remove the persistent header service-status pill (`服务检测中` / `服务正常` / `服务异常`) because the current product does not need a decorative global health indicator.
- Preserve the underlying health check and outlet context because the platform account page still uses real backend availability for unavailable and retry behavior.
- Remove the persistent `当前操作指引` card and its always-on Chrome safety copy from the platform account page.
- Keep real failure feedback visible inside the main platform connection panel only when the backend is unavailable or a connection attempt fails; normal states must not reserve a guidance column.
- Replace technical or report-like Chinese copy (`账号接入`, `平台账号连接`, `本机浏览器通道`, `平台连接信号`, and connection-oriented status/action labels) with concise language centered on platform login status.
- Replace the `WB / DY / KS / RED / TT` letter placeholders with recognizable, locally bundled brand SVG marks for Weibo, Douyin, Kuaishou, Xiaohongshu, and Toutiao.
- Add a prominent `一键检测` action to the login-status panel. It must use the existing single-platform attempt endpoint to check every enabled platform in catalog order, one at a time, so browser operations never overlap.
- While a batch check is running, show the current platform and progress, disable individual check actions, and continue automatically after each platform reaches a terminal result.
- When a platform needs login, is disconnected, or finishes with a failed check, show concise recovery guidance in that platform row telling the user to log in through the currently opened Chrome browser and then check again.
- Opening `/` must render the empty workbench without redirecting; `/platform-accounts` remains the direct platform-account route.
- Preserve the existing Shadcn Sidebar structure, mobile navigation behavior, health-status indicator, and platform account page behavior.

## Acceptance Criteria

- [x] Desktop and mobile sidebars display exactly two navigation links in order: `工作台` and `平台账号`.
- [x] `采集任务`, `舆情信息`, `监控关键词`, `舆情日报`, `系统设置`, and `规划中` remain absent from the primary navigation.
- [x] Opening `/` stays on `/`, marks only `工作台` active, labels the shell content as `工作台`, and renders none of the previous dashboard metrics, cards, readiness steps, speculative copy, or placeholder actions.
- [x] Opening `/platform-accounts` marks only `平台账号` active and preserves the complete platform login and batch-detection behavior.
- [x] The sidebar no longer displays `单机值守模式` or `数据与浏览器操作仅留在本机`, and no orphaned footer separator remains.
- [x] The application header no longer displays the service-status pill or its status labels in loading, connected, or unavailable states.
- [x] Real backend health state remains available to the platform account page, including its service-unavailable guidance and retry behavior; after an initial health and catalog failure, the page-level retry must recheck both and recover without a full reload.
- [x] The platform account page no longer renders `当前操作指引`, `系统只会打开官方页面并检测登录状态`, or the always-on Chrome authorization/safety note.
- [x] The main platform connection panel uses the released width without an empty right column, while backend-unavailable and connection-attempt failure messages remain visible as conditional alerts.
- [x] The page uses the natural Chinese copy `平台账号`, `在这里查看各平台账号的登录状态。需要登录、扫码或安全验证时，请在打开的 Chrome 浏览器中完成。`, `登录状态`, and `为避免浏览器操作相互影响，每次只能检查一个平台。` without the removed technical labels.
- [x] Platform rows consistently use `待检查`, `检查中`, `已登录`, `未登录`, `检查失败`, `尚未检查`, `上次检查`, `检查状态`, and `重新检查` while preserving the existing backend status contracts and behavior.
- [x] Each of the five platform rows renders its correct brand mark, and the letter placeholders `WB`, `DY`, `KS`, `RED`, and `TT` no longer appear.
- [x] Brand marks are bundled as reviewed local SVG assets with no runtime image request or new icon dependency; the adjacent Chinese platform name remains the accessible identity and the decorative logo is hidden from assistive technology.
- [x] The login-status panel provides one `一键检测` button that checks all enabled platforms in catalog order through the existing per-platform API, never starts two browser operations at once, and remains disabled when the backend or platform catalog is unavailable.
- [x] During batch detection, the UI exposes meaningful progress such as the current platform and `1/5`, disables competing row actions, and announces the changing status without moving keyboard focus.
- [x] `需要操作`, `未登录`, and `检查失败` rows display actionable Chinese guidance beside that platform: the user should log in through the currently opened Chrome browser and retry when necessary; connected and untouched rows do not show this warning.
- [x] Individual platform checks continue to work exactly as before when no batch detection is active.
- [x] Selecting either real destination from the mobile sidebar closes the sidebar as before.
- [x] Frontend formatting, lint, type checking, tests, build, and loopback browser smoke checks pass without new console errors or horizontal overflow.

## Out of Scope

- Implementing collection tasks, public-opinion records, keywords, reports, or system settings.
- Adding workbench widgets, statistics, empty-state cards, explanatory copy, or shortcuts before those features have real behavior.
- Changing backend APIs, MediaCrawler integration, the visual theme, or platform connection behavior.
- Running platform attempts concurrently, adding cancellation controls, or persisting batch progress across page reloads.

## Technical Notes

- Keep the navigation model explicit in `frontend/src/app/shell.tsx` rather than hiding entries with CSS. Derive the shell page title and active state from the current route.
- Remove the unused `SidebarFooter` composition and its adjacent `SidebarSeparator` from `frontend/src/app/shell.tsx`.
- Remove the `LocalServiceStatus` presentation from `frontend/src/app/shell.tsx` without removing the health reducer, fetch lifecycle, or `ShellContext` contract.
- Expose a non-visual health retry action through `ShellContext` and invoke it together with the platform catalog refetch from the page-level `重新读取` control.
- Remove the `guidanceFor` / `relevantConnection` presentation path and the right-hand guidance card from `frontend/src/routes/platform-accounts.tsx`; retain only conditional, actionable failure feedback in the main card.
- Update only user-facing copy and display labels in `frontend/src/routes/platform-accounts.tsx`; do not rename backend enums, API payloads, or platform connection state contracts.
- Store the reviewed brand assets under `frontend/src/assets/platforms/`, record their sources, and map them by `PlatformId` in the platform account page without changing API data.
- Implement the batch as route-owned ephemeral UI state that sequences the existing asynchronous attempt mutation and the polled platform catalog; do not add a second server-state store or a new API endpoint.
- Keep failure recovery guidance contextual to the affected row. Use the existing Shadcn `Button` and status primitives, preserve 44 px mobile targets, and keep the batch progress available to assistive technology through one polite live region.
- Restore `Workbench` as the root index element in `frontend/src/app/router.tsx`; keep `/platform-accounts` as a sibling child route.
- Reduce `frontend/src/routes/workbench.tsx` to an intentionally empty route component without retaining unused data fetching, fake status derivation, or decorative imports.
- Update behavior-oriented assertions in `frontend/src/App.test.tsx` to cover both real navigation destinations, the non-redirecting root, the empty workbench, and mobile sidebar closure.
