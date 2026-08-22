# 验证 MediaCrawler 微博原生登录

## Goal

在不接入项目前后端、不过早改造 MediaCrawler 登录代码的前提下，验证当前派生仓库能够在本机完成微博二维码登录，并在第二次启动时复用登录态，为后续“平台连接”功能提供可靠的技术基线。

## Background

- MediaCrawler 以 Git submodule 固定在 `third_party/MediaCrawler`；验证基线为 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，登录态修复后更新为 `be6f6beb007332734b04421377af210a285be3f3`。
- MediaCrawler 已包含微博二维码提取、系统图片窗口展示、Cookie 登录检测以及 CDP 浏览器登录态复用逻辑。
- 本机已安装 `uv` 和 Google Chrome 151，满足仓库文档中 Chrome 144+ 的要求；MediaCrawler 的 `.venv` 尚未创建，端口 9222 当前未监听。
- 默认配置会连接开启远程调试的日常 Chrome；仓库同时支持启动独立 Chrome，并在 `browser_data` 下使用专用用户数据目录。

## Requirements

- 使用 MediaCrawler 现有微博登录实现，不增加 React、FastAPI 或新的登录协议。
- 使用 `uv sync` 按 MediaCrawler 锁文件创建隔离依赖环境。
- 使用 MediaCrawler 自行启动的独立 Chrome 和专用用户数据目录，不连接用户的日常 Chrome；仅在验证期间调整 `CDP_CONNECT_EXISTING = False`，验证完成后恢复源码配置。
- 以 `wb`、`qrcode` 参数启动原生流程，并将采集量和评论采集限制到验证所需的最低程度。
- 第一次运行能够完成二维码展示、用户扫码和 MediaCrawler 登录成功判断。
- 第二次运行能够复用同一浏览器登录态，不再次要求扫码。
- 记录实际运行命令、观察结果和遇到的问题，不提交 Cookie、浏览器用户数据、采集结果或日志。
- 不覆盖或删除现有未跟踪的 `db_data/`、`logs/` 内容。

## Acceptance Criteria

- [x] `uv sync` 成功，MediaCrawler CLI 能正常启动且不出现依赖导入错误。
- [x] 首次验证中出现微博登录二维码，扫码后日志明确进入登录成功后的移动端 Cookie 更新步骤。
- [x] 登录后能够进入微博 crawler 流程；即使搜索结果为空，也不因认证失败退出。
- [x] 使用相同浏览器数据目录再次启动时，`WeiboClient.pong()` 识别为已登录，流程不再展示二维码。初始验证暴露的会话 Cookie 丢失已由子任务 `08-22-persist-mediacrawler-weibo-login-state` 修复并完成真实两次启动回归。
- [x] 验证结束后，Git 状态中没有意外的 MediaCrawler 源码修改，也没有敏感运行数据进入版本控制。

## Key Decisions

- 选择独立 Chrome 数据目录，优先保证日常浏览器 Cookie 隔离和两次运行验证的可重复性。
- 本任务允许生成本地 `.venv`、专用浏览器数据、日志和最小采集结果，但这些运行产物不得进入版本控制。
- 暂不修复运行过程中发现的 MediaCrawler 源码问题；阻断验收的问题将记录为后续任务候选。

## Out of Scope

- React 平台连接页面和 FastAPI 登录接口。
- 将二维码 Base64 或登录状态改造成结构化事件。
- 今日头条或其他平台适配。
- 长时间、批量或定时采集。
- 对 MediaCrawler 登录实现进行功能性重构或缺陷修复。

## Notes

- 本任务属于轻量验证任务，采用 PRD-only，不新增 `design.md` 和 `implement.md`。
