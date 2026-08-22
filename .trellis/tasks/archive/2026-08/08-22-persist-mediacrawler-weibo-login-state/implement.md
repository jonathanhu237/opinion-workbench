# 实施计划

## Implementation

- [x] 在 MediaCrawler 中搜索现有 Cookie 序列化、原子文件写入和权限处理工具，避免重复实现。
- [x] 新增 `BrowserAuthStateStore`，实现窄 schema 校验、URL/domain allowlist、过期过滤、原子 `0600` 写入以及非敏感错误回退。
- [x] 在微博 crawler 中接线：首次 `pong()` 前恢复，确认登录有效后保存，`SAVE_LOGIN_STATE=False` 时跳过。
- [x] 保持现有二维码登录、Cookie 登录、CDP/标准模式和 crawler 分支行为不变。

## Automated Validation

- [x] 为 store 添加单元测试：文件缺失、有效会话 Cookie、过期 Cookie、损坏 JSON、错误版本/平台/schema、非 allowlist 域、Playwright 恢复异常、原子写入和 `0600` 权限。
- [x] 为微博编排添加测试：restore 早于 client/`pong()`、首次登录后 save、已有登录后 save、关闭开关时无读写、无效状态回退扫码。
- [x] 运行新增测试及 MediaCrawler 相关测试集。
- [x] 运行仓库格式、lint、类型检查中现有且适用于改动文件的命令；记录不存在或项目基线失败的检查。
- [x] 扫描日志和测试产物，确认不存在 Cookie 值或认证 header。

## Real Regression

- [x] 确认状态文件和浏览器目录为空或不存在，临时使用 `CDP_CONNECT_EXISTING=False` 启动独立 Chrome。
- [x] 第一次启动扫码，确认 `browser_data/auth_state/wb.json` 创建、被 Git 忽略且 POSIX mode 为 `0600`。
- [x] 完全关闭第一轮浏览器和 crawler，使用同一目录第二次启动。
- [x] 确认恢复发生在首次 `pong()` 前、首次 `pong()` 通过且不展示二维码。
- [x] 使用不会执行 search/detail/creator 的临时 no-op crawler 配置进行认证回归，避免采集示例内容；测试后恢复配置。

## Review and Delivery

- [x] 恢复所有临时配置，确认 9222 无监听且无独立 Chrome 残留。
- [x] 确认 MediaCrawler 仅包含计划内源码和测试变更，父仓库现有 `db_data/`、`logs/` 未被覆盖或删除。
- [x] 完成 Trellis full-scope check。
- [x] 以 Conventional Commit 提交并推送 MediaCrawler 派生仓库，再更新父仓库 gitlink。
- [x] 在父任务中重新核对“第二次免扫码”验收项；任何真实回归失败均停止归档并保留诊断证据。

## Rollback Points

- store 单测失败：只回退 helper 和对应测试，不运行真实账号验证。
- 微博编排测试失败：回退 `core.py` 接线，保留研究和 store 单测证据。
- 真实回归失败：恢复配置并停止交付，不提交未经验证的父仓库 gitlink。
