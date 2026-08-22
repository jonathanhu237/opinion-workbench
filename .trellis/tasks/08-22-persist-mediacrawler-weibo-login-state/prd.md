# 持久化 MediaCrawler 微博登录态

## Goal

让 MediaCrawler 在独立 CDP Chrome 模式下完成一次微博扫码后，后续使用同一专用浏览器目录启动时能够直接通过微博移动端登录检查，不再重复扫码。

## Background

- 父任务已验证首次原生二维码登录、移动端 Cookie 更新和最小 crawler 流程可用。
- 第二次使用同一 `browser_data/cdp_wb_user_data_dir` 启动时，`WeiboClient.pong()` 仍判定未登录。
- 运行诊断显示首次登录上下文可读取 11 个 Cookie，但 Chrome 关闭后持久数据库只保留 8 个 `weibo.com` / `passport.weibo.com` Cookie，关键 `.weibo.cn` 会话 Cookie 未保留。
- MediaCrawler 目前只有浏览器 profile 持久化，没有针对微博移动端登录态的显式保存和恢复流程。
- 源码研究确认 `WeiboClient.pong()` 仅使用 `m.weibo.cn` Cookie 请求 `/api/config` 并读取 `login` 字段，因此无需保存完整 localStorage、IndexedDB 或浏览器状态。

## Requirements

- 使用按平台、按 URL allowlist 保存 Cookie 的机制，不使用完整 Playwright `storage_state`，也不依赖 Chrome 会话恢复。
- 保留 MediaCrawler 现有二维码登录流程和 `WeiboClient.pong()` 登录检查语义。
- 登录成功后显式保存微博认证状态；下次启动时在首次 `pong()` 之前恢复。
- 保存文件必须位于被 Git 忽略的运行数据目录，不进入父仓库或 submodule 版本控制。
- 登录态文件应按平台隔离，并为以后其他平台复用保留清晰边界，但本任务只实现微博。
- 无状态、状态过期或状态文件损坏时应安全回退二维码登录，不得导致 crawler 崩溃。
- 继续使用独立 Chrome 数据目录，不连接用户日常 Chrome。

## Key Decisions

- 默认状态路径为被 Git 忽略的 `browser_data/auth_state/wb.json`，schema 包含版本、平台和过滤后的 Cookie 列表。
- 恢复发生在创建微博 HTTP client 和首次 `pong()` 之前；保存发生在移动端 Cookie 更新完成之后。
- `pong()` 继续作为登录有效性的唯一权威；状态文件缺失、损坏、过期或恢复失败时自动回退二维码登录。
- 写入采用临时文件加原子替换，POSIX 权限为 `0600`；日志只记录状态、路径和数量，不记录 Cookie 值。
- 用户接受在本地以明文 JSON 保存认证 Cookie，并以 `0600` 文件权限限制为当前操作系统用户可读；系统钥匙串和加密存储延后处理。

## Acceptance Criteria

- [x] 首次无保存状态时展示二维码，扫码后成功保存微博登录态并完成 crawler 流程。
- [x] 关闭浏览器并使用相同运行目录再次启动后，首次 `WeiboClient.pong()` 直接通过，全程不展示二维码。
- [x] 删除、损坏或过期的登录态不会泄露敏感值，程序会记录可理解的非敏感日志并回退扫码。
- [x] 登录态文件和浏览器数据均被 Git 忽略；父仓库只记录 submodule gitlink，MediaCrawler 源码修改在派生仓库中提交后再更新父仓库指针。
- [x] 相关自动化测试通过，并完成一次真实的两次启动回归验证。

## Out of Scope

- React/FastAPI 平台连接页面。
- 登录态加密、系统钥匙串或多用户账号切换。
- 微博以外平台的登录态持久化实现。
- 修复空 `--specified_id` 回退示例 ID 的问题。

## Notes

- 本任务会修改第三方派生仓库登录基础设施，属于复杂任务；技术设计、实施步骤和回滚点分别记录在 `design.md` 与 `implement.md`。
