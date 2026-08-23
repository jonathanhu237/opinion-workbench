# 小红书认证源码与历史证据

日期：2026-08-24

## Historical Decisions

- 当前会话历史曾因小红书风控较严格而将其排在微博、快手、抖音和今日头条之后；这些平台验证完成后，用户明确表示“小红书可以碰”。
- 既有平台认证共同边界继续适用：本机单用户、独立可见 Chrome、二维码优先、官方挑战人工处理、不自动绕过、认证材料不写入业务数据库或 Git。
- 用户此前接受本机明文 Cookie 状态文件风险，条件是平台/域隔离、Git ignore、POSIX `0600` 和非敏感日志。
- 会话来源：Codex session `01a0257f-f892-7730-b626-9037f2c73e69`，通过本地 `trellis mem` 恢复；当前项目文件和源码仍是技术事实的权威来源。

## XHS Crawler

- `XiaoHongShuCrawler.__init__()` 在国内模式使用 `https://www.xiaohongshu.com`，`cookie_urls` 只有该首页 URL：`third_party/MediaCrawler/media_platform/xhs/core.py:62`-`:65`。
- 启动流程先创建 CDP/Playwright context、导航首页、创建 client，再执行首次 `pong()`；失败时进入 `XiaoHongShuLogin`，完成后只更新 client Cookie：`third_party/MediaCrawler/media_platform/xhs/core.py:77`-`:117`。
- `auth_validation` 不属于 search/detail/creator，能够复用 crawler 启动认证逻辑而不触发任何采集分支：`third_party/MediaCrawler/media_platform/xhs/core.py:119`-`:130`。
- 当前 XHS core 未导入或调用 `BrowserAuthStateStore`，登录后也没有第二次 `pong()`。

## Native Login

- `check_login_state()` 最多重试 600 次、每次间隔 1 秒；优先检测“我”入口，随后识别页面文本“请通过验证”并提示人工处理，最后以 `web_session` 是否相对登录前变化作为兼容判断：`third_party/MediaCrawler/media_platform/xhs/login.py:51`-`:85`。
- 二维码流程查找 `//img[@class='qrcode-img']`；若首页未自动弹窗，则点击登录入口后再次查找：`third_party/MediaCrawler/media_platform/xhs/login.py:167`-`:188`。
- 流程展示二维码后调用同一登录状态轮询；日志写“120s”，但装饰器实际允许约 600 秒：`third_party/MediaCrawler/media_platform/xhs/login.py:190`-`:211`。
- 挑战分支没有图像识别、鼠标拖动、自动刷新或绕过动作；现有普通登录按钮点击和二维码读取不属于挑战自动化。
- 失败分支使用 `sys.exit()`，不适合作为未来服务层 API，但本任务不预先重构；只有真实验证证明其阻碍认证验收时才做最小健壮性修正。

## Authoritative Live Check

- `query_self()` 请求 `/api/sns/web/v1/user/selfinfo`：`third_party/MediaCrawler/media_platform/xhs/client.py:272`-`:284`。
- `pong()` 只有在响应 `data.result.success` 为真时才返回真，异常被转为失败并进入登录回退：`third_party/MediaCrawler/media_platform/xhs/client.py:286`-`:304`。
- 因此 UI 元素、`web_session` 变化、profile 目录或状态文件存在只能作为过程信号，最终验收必须以 `pong()` 为真。

## Existing Persistence Building Blocks

- CDP 启动器在 `SAVE_LOGIN_STATE=True` 时使用 `browser_data/cdp_xhs_user_data_dir` 一类平台专用 profile：`third_party/MediaCrawler/tools/cdp_browser.py:250`-`:271`。
- 通用 `BrowserAuthStateStore` 默认写入 `browser_data/auth_state/<platform>.json`，只接受构造 URL 对应域，恢复时过滤 schema/域/过期值，保存时原子替换并在 POSIX 使用 `0600`：`third_party/MediaCrawler/tools/browser_auth_state.py:56`-`:80`、`:82`-`:164`、`:166`-`:241`。
- MediaCrawler `.gitignore` 使用 `/browser_data/`，覆盖原生 profile 和条件式认证状态文件。
- 微博与快手已经接入该 store；快手真实基线证明 profile 可能不足，接线后两次启动通过。抖音真实基线证明 profile 也可能直接满足，因此 XHS 必须先实测，不能预判。

## Repository and Test Baseline

- 父仓库位于 `main`，MediaCrawler submodule 位于其派生仓库 `main`，当前 HEAD 为 `815ce9332c74097914c61899a0e37ea1b60e0af3`；submodule 无源码改动。
- 父仓库既有未跟踪 `db_data/`、`logs/`，任务必须原样保留。
- `xhshow` 在当前 MediaCrawler `uv` 环境可导入。
- 规划阶段运行以下不启动浏览器的测试，结果为 29 passed、1 条既有 SQLAlchemy deprecation warning：

```text
tests/test_xhs_core_access_error.py
tests/test_xhs_raw_response_errors.py
tests/test_browser_auth_state.py
```

## Planning Conclusion

最小可靠方案是“原生两次启动基线优先，失败才接线”。无论 profile 还是显式状态文件，第一轮登录后和第二轮启动时都必须由服务端 `pong()` 证明有效；官方安全验证始终由用户人工完成。
