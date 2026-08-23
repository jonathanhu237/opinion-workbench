# 实施计划

## Phase 0: Safety Prerequisite

- [x] 将抖音滑块处理改为只检测、提示并有界等待人工完成，删除活动自动识别/拖动/刷新路径。
- [x] 新增单元测试覆盖无滑块、人工完成和超时，证明没有自动挑战动作。
- [x] 在任何真实浏览器运行前完成定向测试和代码检查。

## Phase A: Native Baseline

- [x] 确认 submodule 除本任务预期改动外无其他变化、端口未监听、任务临时目录不会覆盖项目运行数据。
- [x] 使用 `auth_validation` 和可见独立 Chrome 完成首次二维码扫码及登录验证，不采集内容。
- [x] 完全关闭 Chrome/CDP，以同一隔离 profile 第二次启动，首次 `pong()` 为真且二维码未出现。
- [x] 原生第二次启动直接免扫码，按条件跳过 Phase B。

## Phase B: Conditional Integration

- [x] 不适用：原生 profile 复用成功，未接入 `BrowserAuthStateStore`。
- [x] 不适用：未发生条件接线。
- [x] 不适用：未发生条件接线。
- [x] 已运行抖音定向测试以及通用 store、微博、快手认证回归测试。

## Phase C: Real Regression

- [x] 不适用：未发生显式状态接线；原生 profile 位于 Git 忽略目录。
- [x] 完全关闭后第二次启动，验证首次 `pong()` 通过、无二维码、无内容采集。
- [x] 记录非敏感证据，关闭 Chrome/CDP 和端口，永久删除本任务的敏感临时目录。

## Quality and Delivery

- [x] 运行完整 `tests/`、scoped pre-commit、compileall、`git diff --check` 和敏感信息扫描；仓库配置了 mypy，全量检查存在存量错误，本任务两个文件 scoped 检查通过。
- [x] 执行 Trellis full-scope check，核对安全挑战、认证顺序、测试真实性、secret-safe 证据和 submodule 合同。
- [ ] 若源码有修改，经一次性提交计划确认后提交并推送 MediaCrawler `main`，再提交父仓库 gitlink、任务证据和必要规范更新。
- [ ] 归档任务并记录开发日志。

## Rollback Points

- 安全修正或单元测试未通过：不启动真实浏览器。
- 原生登录失败：清理运行环境并停止，不把页面故障误判为持久化缺陷。
- 条件接线的自动化或真实回归失败：不交付源码 revision，恢复任务内临时配置并删除敏感状态。
