# 验证 MediaCrawler 快手原生登录

## Goal

验证 MediaCrawler 在本机独立 Chrome 中能否完成快手首次扫码登录、有效登录检查和第二次启动免扫码，并判断现有通用认证状态存储是否需要接入快手。

## Background

- 快手 crawler 使用 `https://www.kuaishou.com` 作为页面、HTTP client 和 Cookie URL 边界。
- 首次 `KuaiShouClient.pong()` 通过 GraphQL `visionProfileUserList` 的 `result == 1` 判断登录是否有效。
- 未登录时，原生流程点击“登录”，提取 `//div[@class='qrcode-img']//img` 二维码，并轮询浏览器中的 `passToken` Cookie；代码实际最多等待约 10 分钟。
- 扫码成功后，现有流程只把浏览器 Cookie 更新到内存中的快手 HTTP client，没有显式写入认证状态文件。
- 微博任务已经提供通用 `BrowserAuthStateStore`，支持平台/URL 隔离、过期过滤、原子 `0600` 文件和安全回退，但目前只在微博 crawler 中接线。
- 历史决策继续有效：使用独立 Chrome，不连接日常 Chrome；允许在 Git 忽略目录中以明文 `0600` 文件保存本地认证 Cookie。

## Requirements

- 使用 `ks`、`qrcode` 和隔离的专用 Chrome 数据目录运行快手原生登录流程。
- 使用不会进入 search/detail/creator 分支的认证验证模式，避免采集任何快手内容或评论。
- 第一次运行验证二维码展示、用户扫码、`passToken` 检测和 `KuaiShouClient.pong()` 登录结果。
- 完全关闭 Chrome 后以相同隔离目录第二次启动，观察是否直接通过首次 `pong()` 且不再展示二维码。
- 若任务范围允许接入通用状态存储，则使用 `platform="ks"`、`urls=["https://www.kuaishou.com"]`，并保持文件损坏/过期时自动回退扫码。
- 运行证据只记录状态、数量和文件元数据，不记录 Cookie 名称或值。
- 测试和运行产物不得进入 Git；不覆盖或删除既有 `db_data/`、`logs/`。

## Key Decisions

- 先在不改快手源码的条件下执行两次启动基线，避免把“可能需要”当成“必须修改”。
- 用户允许在基线第二次仍要求扫码时，于同一任务把现有 `BrowserAuthStateStore` 最小接入快手，并补齐编排测试。
- 接线时登录态使用 `platform="ks"`、`urls=["https://www.kuaishou.com"]`，默认文件为被 Git 忽略的 `browser_data/auth_state/ks.json`。
- `KuaiShouClient.pong()` 是登录有效性的最终权威；二维码流程检测到 `passToken` 后，还必须更新 client Cookie 并再次通过 `pong()` 才能保存状态。

## Acceptance Criteria

- [x] 独立 Chrome、快手登录页和二维码能够正常打开，扫码后原生流程检测登录成功。
- [x] 登录成功后 `KuaiShouClient.pong()` 通过，认证验证模式正常结束且未采集内容。
- [x] 完全关闭后第二次启动首次 `pong()` 通过且不展示二维码；若原生 profile 不能满足，则完成最小接线后重新验证至通过。
- [x] 临时配置全部恢复，端口 9222 和独立 Chrome 均已关闭。
- [x] MediaCrawler 源码保持在批准范围内，认证状态和浏览器数据被 Git 忽略且无敏感值进入日志或任务记录。

## Out of Scope

- 快手搜索、详情、评论质量和长期稳定性验证。
- React/FastAPI 平台连接页面。
- 抖音、小红书、今日头条或其他平台登录。
- 登录态加密、系统钥匙串和多账号管理。

## Notes

- 本任务包含条件式源码修改和真实账号回归，按复杂任务管理；设计、执行步骤和回滚点分别记录在 `design.md` 与 `implement.md`。
