# 实施计划

## Phase A: Preflight and Native Baseline

- [x] 确认父仓库和 MediaCrawler submodule 仅有预期任务文件变化，保留未跟踪的 `db_data/`、`logs/`，并确认调试端口未监听。
- [x] 建立任务专用临时根目录和可见独立 Chrome profile；以 `xhs`、`qrcode`、`auth_validation`、`CDP_CONNECT_EXISTING=False` 启动第一轮，不连接日常 Chrome。
- [x] 用户完成二维码扫码；运行器在 Cookie 更新后额外执行服务端 `XiaoHongShuClient.pong()`，确认第一轮真实有效且没有内容采集。本次未出现官方挑战。
- [x] 完全关闭 Chrome/CDP 后，以同一隔离 profile 启动第二轮；首次 `pong()` 仍为假并再次进入二维码，证明原生 profile 复用失败。
- [x] 保存非敏感原生基线结论并按条件进入 Phase B。

## Phase B: Conditional Minimal Integration

- [x] 仅在原生复用失败后，将现有 `BrowserAuthStateStore` 最小接入 XHS core：首次页面/client/`pong()` 前 restore，登录后 update + second pong，仅有效时 save；二次校验失败时安全结束，不进入内容采集。
- [x] `SAVE_LOGIN_STATE=False` 保持无状态行为；缺失、损坏、过期和平台/URL 不匹配沿用通用 helper 的安全回退。
- [x] 新增 XHS 认证编排测试，覆盖已有登录、首次登录、二次检查失败和关闭开关；通用 helper 未修改。
- [x] 真实页面不需要选择器或人工挑战代码修正，未扩大登录自动化范围。
- [x] 使用全新临时根目录重新执行两次启动，验证状态文件 Git ignore、POSIX `0600`、第二轮 restore 后首次 `pong()` 通过且无二维码。

## Phase C: Validation and Evidence

- [x] 运行 XHS 与通用认证定向测试（含新增编排测试）：33 passed。
- [x] 运行主测试目录：198 passed；全仓测试另有 6 项因本机 Redis 未运行而失败。scoped pre-commit、compileall、`git diff --check` 通过；scoped mypy 仅报告 XHS core 既有行错误。
- [x] 扫描 diff、日志和任务记录，确认没有 Cookie、二维码、认证 header、状态正文或个人信息进入版本控制。
- [x] 将真实运行的状态顺序、两次启动结论、无采集证明、文件权限和清理结果写入 `research/validation-results.md`，只保留非敏感证据，并加入 `check.jsonl`。
- [x] 恢复所有临时配置，确认 Chrome/CDP 退出、调试端口关闭，再永久删除本任务创建的敏感临时目录；未触碰既有运行目录。

## Quality and Delivery

- [x] 使用 Trellis full-scope check 核对 PRD、人工挑战边界、认证顺序、测试真实性、secret-safe 证据和 submodule 合同；复核补充了二次 `pong()` 失败时禁止采集的保护和测试。
- [ ] 若 MediaCrawler 有源码修改，向用户汇报准确文件、测试与真实回归结果；交付获批后以 Conventional Commit 提交并推送派生仓库 `main`，再更新父仓库 gitlink。
- [ ] 提交父仓库任务证据、归档任务并记录开发日志；不创建 PR 或 Codex 分支。

## Rollback Points

- 二维码页面无法打开或 DOM 变化无可靠只读证据：清理环境并停止，不猜测选择器。
- 官方安全验证重复出现或人工超时：安全结束本轮，不自动破解、拖动、刷新或规避。
- 条件接线测试或登录后二次 `pong()` 失败：不保存状态、不运行后续采集、不提交未验证 revision。
- 第二次启动仍未直接通过：保留非敏感诊断，恢复临时配置并停止交付。
