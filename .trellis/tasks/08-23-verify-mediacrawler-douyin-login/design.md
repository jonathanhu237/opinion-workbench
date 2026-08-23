# MediaCrawler 抖音登录验证与条件接线设计

## Scope

本任务只处理抖音认证链路，包括一处先决安全修正、原生两次启动基线，以及基线失败时的条件式登录态接线。关键词搜索、作品、评论和长期稳定性均不在范围内。

## Existing Flow and Gaps

现有流程为：

```text
创建 BrowserContext
→ 打开 www.douyin.com
→ 创建 DouYinClient
→ 读取 LocalStorage/Cookie 的 pong
→ 失败时二维码登录
→ 更新内存 client Cookie
→ 进入 crawler 分支
```

存在两个独立缺口：

1. 安全挑战路径会自动识别并拖动滑块，不符合项目规范。
2. 登录后没有二次 `pong()`；显式 Cookie 状态存储尚未接入抖音，原生 Chrome profile 能否跨重启复用尚无真实证据。

## Manual Safety Challenge

在任何真实登录前，修改 `DouYinLogin.check_page_display_slider()`：

- 最多等待 30 秒检测 `#captcha-verify-image` 是否出现；未出现则直接继续。
- 出现后记录不含页面内容或凭证的人工操作提示，并在可见浏览器中等待该元素消失。
- 人工等待设置有界超时；超时后让登录流程失败，不执行图片识别、鼠标拖动、自动刷新或重试绕过。
- 删除活动路径中的 `move_slider()` 自动实现，避免后续调用者误用。

新增单元测试验证无滑块、人工完成和超时路径，并断言没有 click/mouse 等自动挑战动作。

## Native Baseline Runner

- 使用 `PLATFORM="dy"`、`LOGIN_TYPE="qrcode"`、`CRAWLER_TYPE="auth_validation"`、`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、`CDP_HEADLESS=False`、`SAVE_LOGIN_STATE=True`、`AUTO_CLOSE_BROWSER=True`。
- 浏览器 profile 与运行状态位于任务专用临时目录；进程工作目录保持为 MediaCrawler 仓库，以满足源码相对资源路径。
- `auth_validation` 不匹配 search/detail/creator，因此 crawler 只运行认证链路。
- 第一轮完成二维码扫码和首次登录检查；完全关闭 Chrome/CDP 后，以同一 profile 启动第二轮。
- 只记录二维码是否出现、`pong()` 布尔结果、顺序和文件元数据，不记录 Cookie/LocalStorage 的键名或值。

## Conditional Authentication-State Integration

只有原生第二轮首次 `pong()` 失败或再次显示二维码时，才在 `media_platform/douyin/core.py` 接入现有 store：

1. 创建 BrowserContext 后构造 `BrowserAuthStateStore(platform="dy", urls=self.cookie_urls)`。
2. 在创建页面并导航到抖音前调用 `restore()`，让首个页面请求携带允许范围内的 Cookie。
3. 页面加载后创建 client，并执行首次 `pong(browser_context=...)`。
4. 首次检查失败时保留二维码及人工安全挑战流程。
5. 登录完成后更新 client Cookie，并再次执行 `pong()`。
6. 只有二次检查为真且 `SAVE_LOGIN_STATE=True` 时保存状态。
7. `SAVE_LOGIN_STATE=False` 时不创建 store，不执行 restore/save。

缺失、损坏、过期或平台不匹配的文件沿用通用 store 的安全回退；不修改 helper，除非测试证明存在抖音 URL allowlist 的通用缺陷。

## Tests if Integration Is Needed

新增抖音编排测试，至少覆盖：

- restore 早于页面导航、client 创建和首次 `pong()`；已有登录不进入二维码。
- 首次失败时执行 login → update cookies → second pong → save。
- 二次 `pong()` 失败不保存。
- `SAVE_LOGIN_STATE=False` 完全跳过 store。
- 事件由独立 mock 记录，避免测试由被测实现自证。

## Real Regression

若发生条件接线，使用新的隔离临时目录重新执行两轮，避免基线 profile 污染。第二轮必须在页面导航前恢复状态，首次 `pong()` 直接通过，不进入 `DouYinLogin`，不显示二维码，不采集内容。

## Security, Cleanup, and Delivery

- 认证材料只进入 Git 忽略目录，状态文件在 POSIX 上为 `0600`。
- 不输出 Cookie、LocalStorage、二维码或认证头内容。
- 若出现安全挑战，只允许用户手工完成；自动化不得操作挑战元素。
- 确认 Chrome/CDP 和端口关闭后，永久删除本任务创建的敏感临时目录；不触碰项目既有运行目录。
- 有源码修改且真实回归通过时，先在 MediaCrawler 派生仓库 `main` 提交并推送，再更新父仓库 gitlink；提交动作仍需在交付阶段单独确认。

## Rollback

- 人工滑块等待测试失败：不运行真实登录。
- 二维码结构失效或登录页无法打开：清理环境并记录阻塞，不进入持久化接线。
- 条件接线后真实第二次启动仍失败：不提交未验证的 gitlink，保留非敏感诊断并清理凭证。
