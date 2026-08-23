# MediaCrawler 小红书登录验证与条件接线设计

## Scope

本任务只处理国内小红书认证链路：原生二维码与人工安全验证、原生 profile 两次启动基线，以及基线失败时的条件式认证状态接线。搜索、详情、评论、媒体和长期风控稳定性均不在范围内。

## Existing Flow and Gaps

当前小红书认证顺序为：

```text
创建 BrowserContext
→ 打开 www.xiaohongshu.com
→ 从浏览器 Cookie 创建 XiaoHongShuClient
→ 服务端 pong
→ 失败时显示二维码并等待“我”入口或 web_session 变化
→ 更新内存 client Cookie
→ 进入 crawler 分支
```

存在两个待验证点：

1. CDP 独立 profile 能否在 Chrome 完全退出后保留小红书所需认证材料。
2. 原生登录完成只经过 UI/Cookie 变化检测，core 没有再次执行服务端 `pong()`，因此第一轮真实验证必须额外确认服务端状态。

现有挑战路径只读取页面文本并提示“请通过验证”，然后继续原有有界重试，不会识别图像、计算轨迹或操作滑块。此边界保持不变。

## Native Baseline Runner

- 在任务专用临时根目录中运行；进程导入和资源读取仍指向 MediaCrawler 仓库，浏览器 profile 与可能的认证文件只写入临时根目录。
- 运行时覆盖 `PLATFORM="xhs"`、`XHS_INTERNATIONAL=False`、`LOGIN_TYPE="qrcode"`、`CRAWLER_TYPE="auth_validation"`、`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、`CDP_HEADLESS=False`、`SAVE_LOGIN_STATE=True`、`AUTO_CLOSE_BROWSER=True`。
- `auth_validation` 不匹配 search/detail/creator，crawler 只执行认证部分。
- 第一轮由用户扫码并人工完成官方挑战；`start()` 返回后、浏览器清理前，由 runner 再调用一次 `crawler.xhs_client.pong()`，把服务端结果作为第一轮结论。
- 完全清理 Chrome/CDP 和调试端口后，以同一临时 profile 启动第二轮。
- 第二轮必须在原生登录类开始前由首次 `pong()` 直接通过。runner 只记录登录类是否进入、二维码是否出现、`pong()` 结果和清理状态，不记录凭证。

## Conditional Authentication-State Integration

仅当原生第二轮首次 `pong()` 失败或重新出现二维码时，修改 `media_platform/xhs/core.py`：

1. BrowserContext 创建后构造 `BrowserAuthStateStore(platform="xhs", urls=self.cookie_urls)`。
2. 在创建 client 和首次 `pong()` 前调用 `restore()`；优先在首个页面导航前恢复，让页面请求也携带已恢复的认证 Cookie。
3. 创建页面并导航后，从 BrowserContext 创建 `XiaoHongShuClient`，执行首次服务端 `pong()`。
4. 首次检查失败时保持原生二维码、页面检测和人工安全验证流程。
5. 登录完成后更新 client Cookie，并再次执行服务端 `pong()`。
6. 只有服务端确认有效且 `SAVE_LOGIN_STATE=True` 时调用 `save()`。
7. `SAVE_LOGIN_STATE=False` 时不构造 store，不调用 restore/save。

通用 store 的 schema、URL/domain allowlist、过期过滤、原子 `0600` 写入和非敏感日志语义保持不变。国内站使用 `urls=self.cookie_urls`，即当前 `https://www.xiaohongshu.com`；设计不硬编码 Cookie 名称。

## Evidence-Driven Login Robustness

若基线在进入二维码或人工挑战阶段前因真实 DOM 变化失败，只允许最小修改 XHS 登录代码：

- 选择器修正必须来自可见页面的只读证据。
- 人工挑战只能检测、提示并有界等待消失；超时抛出非敏感错误。
- 不读取挑战图片做识别，不计算缺口/轨迹，不调用 mouse 拖动，不自动刷新或循环规避挑战。
- 正常登录按钮、二维码提取和登录状态检查可以继续使用 Playwright，但不得记录二维码或认证数据。

如果现有原生流程可用，则不为“以后可能变化”提前修改登录代码。

## Automated Tests

若发生认证状态接线，新增 `tests/test_xhs_auth_state.py`，至少覆盖：

- restore 早于 client 创建和首次 `pong()`；已有有效登录直接保存且不进入二维码。
- 首次 `pong()` 失败时执行 login → update cookies → second pong → save。
- 二次 `pong()` 失败时不保存无效状态。
- `SAVE_LOGIN_STATE=False` 时完全跳过 store。
- store 使用 `platform="xhs"` 与 crawler 的 `cookie_urls`，不硬编码或记录 Cookie 名称和值。
- 事件序列由独立 mock 记录，避免测试由被测实现自证。

若修改人工挑战处理，再增加无挑战、人工完成和人工超时测试，并断言挑战路径没有 click/mouse/刷新等自动动作。

## Real Regression After Conditional Integration

条件接线后使用全新的隔离临时目录重新执行两轮，避免原生基线 profile 污染结果：

```text
第一轮：first pong false → manual login → update → second pong true → save
完全关闭 Chrome/CDP
第二轮：restore → first pong true → no login/no QR
```

状态文件必须命中 MediaCrawler `/browser_data/` ignore，POSIX mode 为 `0600`。文件存在不能代替服务端 `pong()`。

## Security and Cleanup

- 认证 Cookie 是可冒充账号的 bearer credential，只能存在于任务专用、Git 忽略的本地目录。
- 日志和任务证据不得包含 Cookie/LocalStorage 名值、二维码、状态 JSON、Cookie header、authorization header 或完整页面内容。
- 官方挑战只允许人工完成；无法完成时安全结束，不扩大自动化行为。
- 先确认任务 Chrome、CDP 连接和调试端口均已关闭，再永久删除本任务创建的敏感临时目录；该删除不可恢复。
- 不删除项目现有 `browser_data/`、`db_data/` 或 `logs/`。

## Compatibility, Delivery, and Rollback

- 不改变 CLI 登录类型、搜索逻辑、数据模型、存储格式或其他平台认证流程。
- 无 MediaCrawler 源码修改时，只交付 Trellis 验证记录。
- 有源码修改时，在用户确认交付后先提交并推送 MediaCrawler 派生仓库 `main`，确认 revision 可从配置 remote 获取，再更新父仓库 gitlink；父仓库继续直接使用 `main`，不创建 PR 或 Codex 分支。
- 二维码 DOM 失效、人工挑战无法完成、服务端二次 `pong()` 失败或第二次启动仍需扫码时，不提交未验证的 gitlink；恢复环境并保留非敏感诊断。
