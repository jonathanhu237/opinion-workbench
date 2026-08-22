# Research: MediaCrawler 微博登录态持久化

- Query: 为什么独立 CDP Chrome 重启后不能复用微博登录态；在 Playwright `storage_state`、仅持久化 Cookie、依赖浏览器会话恢复三种方案中，选择最小且稳健的修复。
- Scope: mixed（本地源码、上一次真实验证证据、Playwright 官方文档）
- Date: 2026-08-22

## Findings

### 1. 根因与现有数据流

- 上一次真实验证确认首次扫码、跳转移动端、Cookie 更新和 crawler 流程成功，但同一 `browser_data/cdp_wb_user_data_dir` 第二次启动仍进入扫码（`.trellis/tasks/08-22-verify-mediacrawler-weibo-login/research/validation-results.md:19-25`）。
- 活跃 CDP 上下文在首次登录后能读取 11 个 `m.weibo.cn` Cookie；Chrome 关闭后 Cookie 数据库只剩 8 个 `weibo.com` / `passport.weibo.com` Cookie，关键 `.weibo.cn` 会话 Cookie 未落盘（`.trellis/tasks/08-22-verify-mediacrawler-weibo-login/research/validation-results.md:27-31`）。本次只读查询 `browser_data/cdp_wb_user_data_dir/Default/Cookies` 也未发现 `.weibo.cn` 行，且未读取 Cookie 值。
- `SAVE_LOGIN_STATE=True` 目前只驱动 CDP 使用固定 Chrome 用户目录（`third_party/MediaCrawler/config/base_config.py:52-53`；`third_party/MediaCrawler/tools/cdp_browser.py:250-270`），并没有显式认证状态文件。
- 微博启动顺序是：创建上下文 → 新建页面并访问 `www.weibo.com` → 从上下文的 `m.weibo.cn` Cookie 创建 HTTP client → 首次 `pong()`（`third_party/MediaCrawler/media_platform/weibo/core.py:76-103`）。因此第二次启动在任何显式恢复发生前就已经用缺失的移动端 Cookie 判断未登录。
- `pong()` 只用 HTTP client 当前 `Cookie` header 请求 `https://m.weibo.cn/api/config`，并以响应中的 `login` 字段为准（`third_party/MediaCrawler/media_platform/weibo/client.py:118-132`）。这证明本任务无需持久化整个浏览器存储；恢复可用于 `m.weibo.cn` 的 Cookie 足以保持现有登录判定语义。
- 扫码成功后，crawler 会访问 `m.weibo.cn`，再把 URL 过滤后的 Cookie 复制进内存中的 HTTP client（`third_party/MediaCrawler/media_platform/weibo/core.py:103-121`；`third_party/MediaCrawler/media_platform/weibo/client.py:134-150`），但此处没有保存动作。这是最合适的持久化点。
- MediaCrawler 已经在所有平台的 cookie 登录中使用 `BrowserContext.add_cookies()`；微博现有实现见 `third_party/MediaCrawler/media_platform/weibo/login.py:124-132`，其他平台遵循相同模式。这是比引入另一套浏览器初始化路径更稳定的复用点。

### 2. 浏览器关闭不是可靠修复边界

- 正常 CLI 生命周期在 `crawler.start()` 返回后执行统一清理（`third_party/MediaCrawler/tools/app_runner.py:94-104`；`third_party/MediaCrawler/main.py:123-143`）。CDP 清理尝试关闭上下文和 Playwright browser，再终止其启动的 Chrome 进程（`third_party/MediaCrawler/tools/cdp_browser.py:437-505`；`third_party/MediaCrawler/tools/browser_launcher.py:255-291`）。
- CDP 连接使用 Chrome 的默认上下文（`third_party/MediaCrawler/tools/cdp_browser.py:360-398`），而 Playwright 官方文档明确默认上下文不能通过 `BrowserContext.close()` 关闭。当前清理代码会吞掉这个失败并继续关闭连接/进程；调整清理顺序可能改善 Chrome profile 落盘，但不能改变微博移动端会话 Cookie 在重启后缺失的已观测事实。
- 保持 `AUTO_CLOSE_BROWSER=False` 只能在 Chrome 不退出时延长当前会话，不满足“关闭浏览器并再次启动”的验收条件。依赖 Chrome 的会话恢复开关还会耦合浏览器版本、退出方式和恢复设置，无法做确定性的单元测试，也不能为未来平台提供清晰的数据边界。

### 3. 方案比较

| 方案 | CDP 兼容性 | 过期/损坏回退 | 安全范围 | 测试性 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 完整 Playwright `storage_state` | `storage_state()` 可从现有上下文导出；项目锁定 Playwright 1.61.0，也有 `set_storage_state()`。但 CDP 是官方标注的 lower-fidelity 连接，且恢复到已存在默认上下文不能使用 `browser.new_context(storage_state=...)` 的常规入口 | JSON 损坏可捕获；服务端过期仍需 `pong()` 判断 | 包含所有上下文 Cookie 和 localStorage；`set_storage_state()` 会清空/替换现有 Cookie、localStorage、IndexedDB 等。如果误连日常 Chrome，影响面过大 | 可 mock，但必须验证 CDP 默认上下文的 `set_storage_state()` 真实兼容性 | 当前需求过宽，不作为首选 |
| 按平台、按 URL 保存 Cookie，并用 `add_cookies()` 恢复 | `cookies(urls=...)` / `add_cookies()` 是 BrowserContext 基础 API，当前仓库也已在各平台使用；合并写入，不会清空默认上下文 | 缺失、JSON 损坏、schema 错误或 Cookie 过期均可忽略并回退；最终仍由现有 `pong()` 判真 | 只保存 `m.weibo.cn` 可用 Cookie，敏感面最小；可做域名 allowlist | 文件 I/O、过滤、恢复顺序和回退均可独立单测 | **推荐** |
| 通过优雅关闭/恢复 Chrome 会话 Cookie | 依赖 Chrome profile、关闭方式和版本，不是稳定的 Playwright 认证接口 | profile 损坏或会话未恢复时缺少清晰回退边界 | 状态散落在整个浏览器 profile | 很难可靠自动化 | 不推荐 |

Playwright 官方说明 `BrowserContext.cookies(urls=...)` 只返回适用于指定 URL 的 Cookie，且其返回字段可由 `BrowserContext.add_cookies()` 重新添加；这与现有 `cookie_urls=["https://m.weibo.cn"]`（`third_party/MediaCrawler/media_platform/weibo/core.py:60-65`）直接吻合。

### 4. 推荐设计

新增一个与 crawler/平台实现解耦的小型 `BrowserAuthStateStore`（名称可调整），职责限定为本地 Cookie 状态文件：

1. 构造参数包含 `platform`、允许的 URL 列表和可选根目录；默认路径为 `browser_data/auth_state/<platform>.json`。
2. 文件采用带版本和平台标识的窄 schema，例如 `{ "version": 1, "platform": "wb", "cookies": [...] }`。不得在日志、异常信息或测试输出中记录 Cookie 值。
3. `restore(context)` 在首次 `pong()` 之前读取文件：
   - 文件不存在时安静返回“未恢复”；
   - JSON/schema/平台不匹配时记录不含内容的 warning 并返回；
   - 丢弃已到期 Cookie，并用 URL/domain allowlist 拒绝不属于微博的 Cookie；
   - 有有效 Cookie 时调用一次 `context.add_cookies(cookies)`；任何 Playwright 错误均记录非敏感 warning 并回退。
4. `save(context)` 使用 `context.cookies(urls=["https://m.weibo.cn"])` 获取最小状态；写入同目录临时文件后 `os.replace()` 原子替换，POSIX 下权限设为 `0600`。保存失败只告警，不中断本次 crawler。
5. 在 `WeiboCrawler.start()` 中，上下文创建后、创建 HTTP client/首次 `pong()` 前调用 `restore()`。页面访问可保持现状，只要恢复发生在 `create_weibo_client()` 前即可。
6. 登录分支完成移动端跳转并调用 `update_cookies()` 后保存；初始 `pong()` 已通过时也保存一次，以便把偶然由 profile 提供的有效会话引导进显式状态文件。最简单的控制流是登录分支结束后统一 `save()`。
7. 仅在 `config.SAVE_LOGIN_STATE` 为真时读写；否则保持现有无状态语义。`pong()` 仍是登录有效性的唯一权威：状态文件过期但可解析时，`pong()` 失败后照常二维码登录，成功后覆盖旧文件。

该边界对未来平台可复用，但本任务只在微博接线。以后平台只需提供自己的 platform key 和 URL allowlist；不要把微博域名、`pong()` 或二维码逻辑放进通用 store。

### 5. 受影响文件

- 新增 `third_party/MediaCrawler/tools/browser_auth_state.py`：窄 schema、URL/domain 过滤、过期过滤、原子安全写入、恢复和非敏感日志。
- 修改 `third_party/MediaCrawler/media_platform/weibo/core.py`：创建微博 store；在首次 client/`pong()` 前恢复；确认登录后保存。
- 新增 `third_party/MediaCrawler/tests/test_browser_auth_state.py`：store 单元测试。
- 新增或扩展微博 core 测试（建议 `third_party/MediaCrawler/tests/test_weibo_auth_state.py`）：验证调用顺序和登录分支。
- `.gitignore` 通常无需改动：submodule 根的 `/browser_data/` 已被忽略（`third_party/MediaCrawler/.gitignore:165-167`）。实现后仍需用 `git check-ignore -v browser_data/auth_state/wb.json` 明确验证。
- 这是派生 MediaCrawler 仓库的源码变更；按 `.trellis/spec/infra/submodule-guidelines.md`，必须先在派生仓库提交并推送，再更新父仓库 gitlink。

### 6. 测试与真实回归

自动化测试至少覆盖：

1. 状态文件不存在：不调用 `add_cookies()`、不抛错。
2. 有效的微博持久/会话 Cookie：恢复一次，`expires=-1` 的会话 Cookie不得被误删。
3. 已过期 Cookie：被过滤；没有有效项时不调用 `add_cookies()`。
4. JSON 截断、schema 版本错误、platform 不匹配、`cookies` 非列表：非敏感 warning 后回退。
5. 文件中混入非 allowlist 域名：拒绝注入该 Cookie。
6. `add_cookies()` 抛 Playwright 错误：回退，不阻止二维码流程。
7. 保存只调用 `context.cookies(urls=["https://m.weibo.cn"])`；输出不包含其他域 Cookie，临时文件原子替换，POSIX 权限为 `0600`。
8. `WeiboCrawler` 调用顺序：restore 在 `create_weibo_client()` / 首次 `pong()` 前；扫码登录、移动端 Cookie 更新后 save；初始 pong 通过时也 save；`SAVE_LOGIN_STATE=False` 时都跳过。
9. 日志断言只检查状态、路径和计数，不得包含测试 Cookie 值。

真实两次启动回归应使用 `CDP_CONNECT_EXISTING=False` 和同一专用运行目录。为避免再次触发默认示例微博采集，建议使用只把 `config.CRAWLER_TYPE` 设为未知/no-op 值的临时验证入口直接调用 `WeiboCrawler.start()`；不要修改本任务范围外的 `--specified_id` 行为。验收记录只写是否展示二维码、首次 `pong()` 结果、状态文件权限/忽略状态和 Cookie 数量，不写任何 Cookie 值。

## Files Found

- `.trellis/tasks/08-22-verify-mediacrawler-weibo-login/research/validation-results.md` — 首次扫码与第二次失败的真实证据。
- `third_party/MediaCrawler/media_platform/weibo/core.py` — 微博浏览器、client、`pong()`、登录和移动端 Cookie 更新编排。
- `third_party/MediaCrawler/media_platform/weibo/client.py` — 以 `m.weibo.cn/api/config` 为权威的登录检查及内存 Cookie 更新。
- `third_party/MediaCrawler/media_platform/weibo/login.py` — 二维码状态轮询和现有 `add_cookies()` 登录模式。
- `third_party/MediaCrawler/tools/cdp_browser.py` — 独立 Chrome profile、CDP 默认上下文及清理生命周期。
- `third_party/MediaCrawler/tools/browser_launcher.py` — Chrome `--user-data-dir` 启动和进程终止实现。
- `third_party/MediaCrawler/tools/crawler_util.py` — URL 过滤的 BrowserContext Cookie 转换工具（`third_party/MediaCrawler/tools/crawler_util.py:138-156`）。
- `third_party/MediaCrawler/tests/test_cdp_browser.py` — 现有 CDP 连接单测，尚未覆盖认证状态（`third_party/MediaCrawler/tests/test_cdp_browser.py:10-95`）。
- `third_party/MediaCrawler/test/test_utils.py` — 已有 URL 过滤 Cookie 转换测试（`third_party/MediaCrawler/test/test_utils.py:37-49`）。
- `third_party/MediaCrawler/.gitignore` — 已忽略整个运行时 `browser_data`。

## External References

- [Playwright Python BrowserContext API](https://playwright.dev/python/docs/api/class-browsercontext) — `cookies(urls=...)`、`add_cookies()`、`storage_state()`、`set_storage_state()` 语义；默认 BrowserContext 不能关闭。
- [Playwright Python BrowserType API](https://playwright.dev/python/docs/api/class-browsertype) — `connect_over_cdp()` 暴露默认 context，且官方注明 CDP 连接相较 Playwright protocol 为 lower fidelity。
- [Playwright Python Authentication](https://playwright.dev/python/docs/auth) — 认证文件含可冒充用户的敏感 Cookie，不应提交仓库；完整状态可包含 Cookie、localStorage、IndexedDB 等。

## Related Specs

- `.trellis/spec/infra/submodule-guidelines.md` — 派生仓库先提交/推送、父仓库后更新 gitlink，且保持 submodule 工作树干净。
- `.trellis/spec/guides/code-reuse-thinking-guide.md` — 新 helper 前先复用现有 Cookie/BrowserContext 模式；通用 store 只拥有重复的持久化职责。
- 当前任务 PRD：`.trellis/tasks/08-22-persist-mediacrawler-weibo-login-state/prd.md`。

## Caveats / Not Found

- 尚未用真实微博会话验证 `add_cookies()` 恢复后首次 `pong()` 必然通过；这是实现后的核心两次启动验收项。
- 没有发现 MediaCrawler 现有的通用 auth-state store、`storage_state` 使用或登录态持久化测试；当前只有 Chrome profile 和手工 Cookie 字符串注入。
- 没有读取、复制或记录任何真实 Cookie 值。运行目录中现有浏览器 profile 和用户生成数据必须保留。
- Cookie 方案不会保存 localStorage/IndexedDB；当前微博 `pong()` 仅依赖 Cookie，因此这是有证据的最小范围。若未来平台的认证检查依赖其他存储，再以同一 store 接口新增平台能力，而不是提前扩大微博状态文件。
