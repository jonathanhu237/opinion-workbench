# 小红书登录与登录态复用验证记录

日期：2026-08-24

## 结论

小红书原生 CDP profile 可以完成首次二维码登录，但 Chrome 完全退出后，同一 profile 的第二次启动首次服务端 `pong()` 仍为假并再次显示二维码。按批准的条件式方案接入现有 `BrowserAuthStateStore` 后，真实两次启动回归通过：首次扫码后的二次 `pong()` 为真并保存状态；第二次启动先恢复状态，首次 `pong()` 直接为真，未进入登录类、未显示二维码、未采集内容。

## 隔离与安全边界

- 平台与站点：国内小红书 `xhs`、`https://www.xiaohongshu.com`
- 登录方式：`qrcode`
- 运行模式：`auth_validation`
- 浏览器：MediaCrawler 启动的独立可见 Google Chrome 151
- CDP：`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、端口 9222
- 登录态：`SAVE_LOGIN_STATE=True`
- 清理：`AUTO_CLOSE_BROWSER=True`
- 内容采集保护：runner 将 search/detail/creator 入口替换为失败哨兵；全部真实运行的 `collection_calls=0`
- 二维码只在可见浏览器中展示；runner 抑制终端二维码正文，只记录是否出现
- 本次没有观察到或收到官方安全挑战提示；若出现，runner 和产品代码均只允许用户在可见浏览器中人工处理

浏览器 profile 与显式认证状态只写入任务专用 `/tmp/mediacrawler-xhs-*` 目录。日志和记录未包含 Cookie/LocalStorage 名值、二维码内容、认证 header、状态 JSON 或完整页面内容。

## 原生两次启动基线

第一轮：

1. 独立 Chrome、CDP 9222 和国内小红书首页正常启动。
2. 首次服务端 `pong()` 为假，进入原生 `XiaoHongShuLogin` 并显示二维码。
3. 用户扫码后，原生 UI 检查确认登录成功。
4. runner 在 `start()` 返回后额外执行服务端 `pong()`，结果为真。
5. `login_entered=1`、`qrcode_shown=1`、`collection_calls=0`，Chrome 和 9222 正常关闭。

第二轮使用同一隔离 profile，并在第一轮 Chrome 完全退出、9222 无监听后启动：

1. 首次服务端 `pong()` 仍为假。
2. 再次进入原生登录类并显示二维码。
3. 基线失败已经成立，因此没有要求用户重复扫码；runner 被安全取消并完成 Chrome/CDP 清理。
4. `login_entered=1`、`qrcode_shown=1`、`collection_calls=0`。

结论：本次环境中单靠 XHS CDP profile 不能满足跨进程免扫码，触发批准的条件式接线。

## 条件式最小接线

- 在 XHS BrowserContext 创建后构造 `BrowserAuthStateStore(platform="xhs", urls=self.cookie_urls)`。
- restore 发生在首个页面、首页导航、client 创建和首次服务端 `pong()` 之前。
- 首次 `pong()` 失败时保留原生二维码和人工验证流程。
- 登录完成后更新 client Cookie，并增加第二次服务端 `pong()`。
- 只有服务端确认有效时才保存状态；`SAVE_LOGIN_STATE=False` 时不构造 store、不 restore、不 save。
- 登录后二次 `pong()` 仍失败时记录非敏感 warning 并结束本轮，不保存状态，也不进入 search/detail/creator。
- 通用认证 helper、XHS 登录选择器、人工挑战处理、其他平台和采集逻辑均未修改。

## 接线后的真实两次启动回归

使用全新隔离目录，避免原生基线 profile 污染。

第一轮：

1. 无已有显式状态，首次 `pong()` 为假，进入二维码登录。
2. 用户扫码后，更新 client Cookie，第二次服务端 `pong()` 为真。
3. store 保存 16 个 URL allowlist 内的 Cookie；状态文件 POSIX mode 为 `0600`，默认路径命中 MediaCrawler `/browser_data/` Git ignore。
4. runner 额外服务端 `pong()` 仍为真。
5. `login_entered=1`、`qrcode_shown=1`、`collection_calls=0`，Chrome 和 9222 正常关闭。

第二轮：

1. store 在页面导航和 client 创建前恢复 16 个 allowlisted Cookie。
2. 首次服务端 `pong()` 直接为真。
3. `login_entered=0`、`qrcode_shown=0`、`collection_calls=0`。
4. runner 额外服务端 `pong()` 仍为真，Chrome 正常关闭。

## 自动化与质量检查

- XHS 编排、XHS 既有错误语义和通用认证 store：33 passed，1 条存量 SQLAlchemy deprecation warning。
- 项目主测试目录 `uv run pytest -q tests`：198 passed，1 条存量 SQLAlchemy deprecation warning。
- 全仓 `uv run pytest -q`：207 passed、8 skipped、4 subtests passed；另有 6 项旧 `test/` 集成测试因本机 `127.0.0.1:6379` 未运行 Redis 而失败。失败仅位于 `test_proxy_ip_pool.py` 和 `test_redis_cache.py`，不经过 XHS 代码。
- scoped pre-commit（XHS core 与新测试）：全部通过。
- scoped compileall：通过。
- `git diff --check`：通过。
- scoped mypy 2.3.1 使用项目 Python 解析依赖后，新测试无错误；XHS core 报告 7 个位于既有代理、采集参数和返回值代码的存量错误，均不在本任务修改行。
- diff 与任务证据敏感信息检查：未发现认证值、二维码正文、状态 JSON 或认证 header。
- Trellis full-scope 复核补充了登录后二次 `pong()` 失败时的早退保护，并以 `CRAWLER_TYPE="search"` 的独立哨兵证明不会保存无效状态或进入采集；复核后的定向测试仍为 33 passed，主 `tests/` 仍为 198 passed。该保护不改变真实两次启动回归已经覆盖的成功路径，因此未重新打开浏览器或重建凭据。

## 清理与工作树

- 所有真实运行结束后，端口 9222 均确认无监听，未发现任务 Chrome 或 runner 进程。
- 在向主会话报告准确目标后，任务创建的两个敏感 `/tmp/mediacrawler-xhs-*` 目录已永久删除且验证不存在；不可恢复。
- 未触碰项目现有 `browser_data/`、父仓库 `db_data/` 或 `logs/`。
- MediaCrawler 仍位于 `main`；当前仅修改 `media_platform/xhs/core.py` 并新增 `tests/test_xhs_auth_state.py`。
- 尚未 commit、push 或更新父仓库 gitlink。
