# MediaCrawler 微博登录态持久化设计

## Scope and Boundaries

本任务在 MediaCrawler 派生仓库中新增一个通用但窄职责的浏览器认证 Cookie 状态存储，并只为微博接线。存储层不理解微博登录、二维码、`pong()` 或 crawler；微博层负责决定恢复和保存时机。

不保存 localStorage、IndexedDB 或完整 Playwright `storage_state`，不连接用户日常 Chrome，不引入数据库、系统钥匙串或多账号模型。

## Components

### `BrowserAuthStateStore`

新增 `tools/browser_auth_state.py`，构造参数：

- `platform`: 状态命名空间，本任务传入 `wb`。
- `urls`: BrowserContext Cookie URL allowlist，本任务传入 `https://m.weibo.cn`。
- `root_dir`: 可选测试注入；生产默认 `browser_data/auth_state`。

公开异步接口：

- `restore(browser_context) -> bool`
- `save(browser_context) -> bool`

返回值只表示是否完成有效恢复/保存；异常均在边界内转为不含敏感值的 warning，不阻断 crawler。

### Weibo integration

`WeiboCrawler.start()` 在 `SAVE_LOGIN_STATE=True` 时创建 store：

1. BrowserContext 创建并打开初始页面。
2. 在 `create_weibo_client()` 和首次 `pong()` 之前调用 `restore()`。
3. 从恢复后的 BrowserContext 创建 HTTP client，由现有 `pong()` 判断状态是否仍有效。
4. 若 `pong()` 失败，保持现有二维码登录、移动端跳转和 `update_cookies()` 流程。
5. 当 client 已确认有效，统一调用 `save()`。因此首次扫码成功和 profile 偶然已有有效登录两条路径都能刷新状态文件。

`SAVE_LOGIN_STATE=False` 时完全跳过 store，保持当前无状态语义。

## File Contract

默认路径：`browser_data/auth_state/wb.json`。`browser_data/` 已由 MediaCrawler `.gitignore` 忽略。

```json
{
  "version": 1,
  "platform": "wb",
  "cookies": []
}
```

- Cookie 对象沿用 Playwright `BrowserContext.cookies()` 的字段集合。
- 恢复前验证根对象、版本、平台和 `cookies` 类型。
- 仅允许与配置 URL 匹配的 Cookie 域；拒绝文件中混入的其他域。
- `expires > 0` 且早于当前时间的 Cookie 被丢弃；`expires = -1` 的会话 Cookie 必须保留。
- 日志可包含平台、路径、Cookie 数量和结果，不得包含 Cookie 名值、完整 JSON 或 HTTP Cookie header。

## Write Safety

1. 创建状态目录。
2. 在目标目录创建临时文件。
3. POSIX 系统设置权限 `0600`。
4. flush 后通过 `os.replace()` 原子替换目标文件。
5. 替换后再次确保目标权限为 `0600`。
6. 失败时清理本次临时文件并返回 `False`，不得删除已有有效状态文件。

Windows 不强制 POSIX mode，但仍使用用户本地运行目录；跨平台加密不在本任务范围内。

## Failure and Fallback

| Condition | Behavior |
| --- | --- |
| 文件不存在 | 安静返回未恢复，进入现有扫码流程 |
| JSON 截断或 schema 不匹配 | 非敏感 warning，忽略文件并扫码 |
| Cookie 全部过期或非 allowlist | 不调用 `add_cookies()`，进入扫码 |
| `add_cookies()` 失败 | 非敏感 warning，进入扫码 |
| 恢复成功但 `pong()` 失败 | 由现有逻辑扫码，成功后覆盖旧状态 |
| 保存失败 | 当前 crawler 继续运行，记录非敏感 warning；下次可能重新扫码 |

## Compatibility

- 保留现有 `SAVE_LOGIN_STATE` 开关作为唯一启用条件。
- 不改变 `LOGIN_TYPE`、Cookie 手工登录或 CDP/标准 Playwright 启动接口。
- store 的平台和 URL 参数允许以后其他平台复用，但本任务不为其他平台接线。
- 真实回归仍使用 `CDP_CONNECT_EXISTING=False` 的独立 Chrome；测试结束恢复默认配置。

## Repository and Rollback

- 源码和测试先在 `third_party/MediaCrawler` 派生仓库提交并推送。
- 父仓库随后更新 gitlink，并记录 Trellis 子任务产物。
- 回滚时父仓库可将 gitlink 指回原提交；状态文件留在被忽略的运行目录，不参与 Git 回滚。
