# 微博登录态持久化真实回归

## Scope

在隔离临时目录中运行两次 `WeiboCrawler.start()`，验证首次扫码保存状态以及 Chrome 完全关闭后第二次启动免扫码。记录只包含状态、数量和文件元数据，不包含 Cookie 名称或值。

## Runner

- 临时根目录：`/private/tmp/mediacrawler-wb-auth-regression.c8Du0m`
- 通过 `uv run --project <MediaCrawler>` 启动内联 Python。
- 运行时配置：`PLATFORM="wb"`、`CRAWLER_TYPE="auth_validation"`、`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、`CDP_HEADLESS=False`、`SAVE_LOGIN_STATE=True`、`AUTO_CLOSE_BROWSER=True`、`LOGIN_TYPE="qrcode"`。
- 直接执行 `WeiboCrawler.start()`，并在 `finally` 中调用 `cdp_manager.cleanup(force=True)`。
- `auth_validation` 不匹配 search/detail/creator 分支，因此两轮均未采集任何内容。

## First Run

- 初始 `pong()` 未通过，进入现有二维码登录。
- 23:21:59 生成二维码；23:22:16 检测到扫码登录成功。
- 移动端跳转和 Cookie 更新完成后，再次 `pong()` 通过。
- 日志仅记录保存 11 项 allowlist Cookie，不包含名称或值。
- `browser_data/auth_state/wb.json` 相对于临时根目录存在且非空，大小 1950 字节，POSIX mode 为 `0600`。
- crawler 正常结束，Chrome 正常关闭，端口 9222 不再监听。

## Second Run

- 使用同一临时根目录和专用 Chrome 数据目录。
- 在创建微博 client 和首次 `pong()` 前恢复 10 项未过期 Cookie。
- 首次 `pong()` 直接通过；未进入 `WeiboLogin`，未生成或展示二维码。
- 状态文件刷新为 10 项有效 Cookie，crawler 正常结束且未采集内容。
- Chrome 正常关闭，端口 9222 不再监听。

## Cleanup

- 确认无进程占用临时目录且端口 9222 无监听。
- 包含明文测试登录态和专用 Chrome profile 的临时目录已永久删除，不可恢复。
- `config/base_config.py` 没有差异；MediaCrawler submodule 只保留四个计划内源码/测试变更。
