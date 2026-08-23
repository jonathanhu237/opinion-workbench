# 抖音登录与原生登录态验证结果

日期：2026-08-23

## 安全前置

- 已从活动代码中删除滑块图片识别、轨迹生成、模拟鼠标拖动、自动刷新和重试绕过路径。
- 新流程最多等待 30 秒检测官方安全验证；出现后提示用户在可见浏览器中手工完成，并以 120 秒有界等待结束。
- 无挑战、人工完成、人工超时三个单元测试均断言没有 click、页面内容读取、元素查询或 mouse 操作。
- 在任何真实浏览器启动前，3 个定向测试、scoped pre-commit、compileall 与 `git diff --check` 均通过。

## 原生两次启动基线

运行配置为 `dy`、`qrcode`、可见独立 Chrome/CDP、`CDP_CONNECT_EXISTING=False`、`SAVE_LOGIN_STATE=True` 和不会进入采集分支的 `auth_validation`。浏览器只使用本任务的隔离 profile。

第一轮：

- 启动时首次登录检查为假。
- 二维码出现 1 次；用户扫码后登录流程确认成功。
- 内容采集入口调用 0 次。
- Chrome/CDP 正常关闭。

第二轮（同一隔离 profile，第一轮 Chrome 完全退出后）：

- 首次 `pong()` 为真。
- 二维码出现 0 次，未进入 `DouYinLogin`。
- 内容采集入口调用 0 次。
- Chrome/CDP 正常关闭。

结论：抖音原生 CDP profile 可以在本次环境中跨浏览器进程复用有效登录态，因此按设计跳过 `BrowserAuthStateStore` 条件接线。交付源码只包含安全挑战人工化修正及其测试。

## 自动化与质量检查

- 抖音安全挑战及通用认证回归：25 passed。
- 完整 `tests/`：121 passed；仅有 1 条存量 SQLAlchemy deprecation warning。
- scoped pre-commit：通过。
- compileall：通过。
- `git diff --check`：通过。
- 敏感信息模式扫描：通过。
- Git ignore：`/browser_data/` 同时覆盖本次原生 profile 路径和默认认证状态路径。
- 仓库存在 `mypy.ini`，但项目虚拟环境未直接安装 mypy；使用离线可用的 mypy 2.3.1 并指定项目虚拟环境执行全量检查，报告 346 个分布于 62 个既有/导入模块的存量错误。本任务修改的两个文件没有报错，并在 `--follow-imports=skip` 的 scoped 检查中通过。

## 清理

- 端口 9222 已确认不再监听。
- 本任务创建的敏感隔离 profile 已永久删除，不可恢复。
- 未触碰 MediaCrawler 的其他运行目录，也未触碰父仓库现有的 `db_data/` 和 `logs/`。

## 最终复核

- 活动抖音认证代码中不存在滑块图片分析、缺口计算、轨迹生成、鼠标拖动、自动刷新或挑战重试；只保留可见性检测、人工提示、有界等待与安全超时。
- 三项安全挑战测试以独立 mock 记录调用，验证没有 click、页面内容读取、元素句柄查询或 mouse 操作，不依赖被测实现生成自证事件。
- submodule 仅有批准的登录文件和测试文件发生变化；父仓库 gitlink 仍指向已推送的 `3b5421f`，临时全新 clone 可递归初始化并检出同一 revision。
- 定向测试 25 项、完整测试 121 项、scoped pre-commit、compileall、`git diff --check`、敏感信息扫描和本任务两文件 scoped mypy 均通过；全量 mypy 仍因 62 个范围外文件的 346 个存量问题未通过。
