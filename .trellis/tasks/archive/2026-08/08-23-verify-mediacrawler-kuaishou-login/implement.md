# 实施计划

## Phase A: Native Baseline

- [x] 确认 submodule 源码干净、端口 9222 未监听、临时目录不覆盖项目运行数据。
- [x] 使用 `auth_validation` no-op runner 启动快手独立 Chrome，完成首次二维码扫码和 `pong()` 验证。
- [x] 完全关闭 Chrome 后以同一目录第二次启动，记录是否首次 `pong()` 直接通过且不显示二维码。
- [x] 基线未直接通过，因此按条件进入 Phase B，未执行跳过分支。

## Phase B: Conditional Integration

- [x] 仅在基线复用失败时，搜索并复用微博认证编排模式，将 `BrowserAuthStateStore` 最小接入快手 core。
- [x] 登录后增加二次 `pong()`，只保存服务端确认有效的状态；保持现有二维码和 Cookie 登录路径不变。
- [x] 新增快手认证编排测试，覆盖已有登录、扫码登录、二次校验失败和关闭开关。
- [x] 运行 targeted tests、完整 `tests/`、pre-commit、compile/type checks 和敏感信息扫描。

## Phase C: Real Regression

- [x] 使用全新隔离目录执行首次扫码，验证状态文件存在、被 Git 忽略且 POSIX mode 为 `0600`。
- [x] 完全关闭并第二次启动，验证首次 `pong()` 通过、无二维码、无内容采集。
- [x] 记录非敏感证据，确认临时配置恢复、9222 关闭、独立 Chrome 退出。
- [x] 永久删除本任务创建且包含真实登录态的临时目录，不触碰项目既有运行数据。

## Review and Delivery

- [x] 完成 Trellis full-scope check，确认范围、测试真实性、secret-safe logging 和 submodule 合同。
- [ ] 若有源码修改，以 Conventional Commit 提交并推送 MediaCrawler `main`，再更新父仓库 gitlink。
- [ ] 提交父仓库任务证据，归档任务并记录开发日志。

## Rollback Points

- 原生二维码结构失效：停止在基线阶段，记录页面/选择器问题，不进入持久化接线。
- 自动化测试失败：不运行真实账号回归，回退计划内 core/test 修改。
- 二次启动仍失败：恢复环境并停止交付，不提交未验证的 gitlink。
