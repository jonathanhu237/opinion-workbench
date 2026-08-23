# MediaCrawler 快手登录验证与条件接线设计

## Scope

本任务只验证快手认证链路，不验证搜索、详情、评论或长期采集稳定性。执行分为“原生基线”和“条件接线”两阶段：只有基线第二次启动仍要求扫码，才修改 MediaCrawler 快手 crawler。

## Existing Authentication Flow

快手当前顺序：

```text
创建 BrowserContext
→ 打开 www.kuaishou.com
→ 从浏览器 Cookie 创建 KuaiShouClient
→ GraphQL pong
→ 失败时点击登录并显示二维码
→ 轮询 passToken
→ 更新内存中的 client Cookie
→ 进入 crawler 分支
```

现有缺口是扫码后没有再次 `pong()`，也没有显式认证状态保存。Chrome profile 是否足以跨重启必须先通过真实基线判断。

## Baseline Runner

- 使用临时工作目录和独立 Chrome profile，不接触日常 Chrome。
- 运行时覆盖 `PLATFORM="ks"`、`CRAWLER_TYPE="auth_validation"`、`LOGIN_TYPE="qrcode"`、`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、`SAVE_LOGIN_STATE=True`、`AUTO_CLOSE_BROWSER=True`。
- 直接调用 `KuaishouCrawler.start()`；`auth_validation` 不匹配任何采集分支，因此只运行认证。
- 第一轮扫码成功并完全清理 Chrome 后，以同一临时目录启动第二轮。
- 记录二维码是否出现、`passToken` 检测结果、首次 `pong()` 结果及 Cookie 数量；不记录 Cookie 名称和值。

## Conditional Integration

仅当基线第二轮未能免扫码时，在 `media_platform/kuaishou/core.py` 接入现有 `BrowserAuthStateStore`：

1. BrowserContext 和页面准备完成后创建 `BrowserAuthStateStore(platform="ks", urls=self.cookie_urls)`。
2. 在 `create_ks_client()` 和首次 `pong()` 前调用 `restore()`。
3. 首次 `pong()` 失败时保持现有 `KuaishouLogin` 二维码流程。
4. 登录完成后更新 client Cookie，并再次调用 `pong()`。
5. 仅在 `pong()` 为真且 `SAVE_LOGIN_STATE=True` 时调用 `save()`。
6. `SAVE_LOGIN_STATE=False` 时不创建 store、不读写状态文件。

通用 store、schema、allowlist、过期过滤、原子 `0600` 写入和非敏感日志语义保持不变；除非真实证据发现通用 helper 缺陷，否则不修改 helper。

## Tests if Integration Is Needed

新增 `tests/test_kuaishou_auth_state.py`，至少验证：

- restore 早于 client 创建和首次 `pong()`；已有有效登录直接 save，不进入二维码。
- 首次 `pong()` 失败时执行 login → update cookies → second pong → save。
- 二次 `pong()` 失败时不保存无效状态。
- `SAVE_LOGIN_STATE=False` 时完全跳过 store。
- 事件序列断言基于独立 mock 事件，不能由被测实现自证。

## Real Regression After Integration

条件接线后使用新的隔离临时目录重新执行两轮，避免基线 profile 污染结果。第二轮必须在首次 `pong()` 前恢复状态，首次 `pong()` 直接通过，且不进入 `KuaishouLogin`。

## Security and Cleanup

- 认证状态是可冒充账号的敏感凭证，只能保存在 Git 忽略目录；POSIX mode 必须为 `0600`。
- 日志和任务证据不得包含 Cookie 名称、值、序列化 JSON 或 Cookie header。
- 真实验证结束后，在确认 Chrome 和端口 9222 均已退出后，永久删除包含测试登录态的临时目录；该目录不可恢复。
- 不删除项目现有 `browser_data/`、`db_data/` 或 `logs/`。

## Delivery and Rollback

- 无源码修改：只提交 Trellis 验证证据。
- 有源码修改：自动化测试和真实两次启动都通过后，先在 MediaCrawler `main` 提交并推送，再更新父仓库 gitlink。
- 真实回归失败：恢复临时配置、保留诊断证据，不提交未经验证的 gitlink。
