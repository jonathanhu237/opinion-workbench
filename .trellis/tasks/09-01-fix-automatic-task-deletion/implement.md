# 实施计划

该缺陷是一个顺序集成的跨层修改。实施只使用临时 SQLite 数据库和模拟服务，不删除或改写 `runtime/longtian.sqlite3`，不触发真实平台采集或模型调用。

## 0. 实施前准备

- [x] 重新读取当前任务与 `git status --short`，确认无新增冲突。
- [x] 加载 `trellis-before-dev` 以及 `implement.jsonl` 中全部规范。
- [x] 核对当前数据库版本、迁移测试夹具、自动工作流错误表和查询键，禁止修改历史 v15/v16 迁移。

## 1. 先冻结后端契约

- [x] 增加 v16→v17 迁移测试：历史行默认可见、删除列/触发器规范、重复初始化、失败回滚和前向版本保护。
- [x] 增加仓储测试：软删除原子字段、历史外键图不变、同名复用、同请求幂等、陈旧修订、活动运行和删除/调度竞争。
- [x] 增加服务/API/OpenAPI 测试：DELETE 204 空体、严格请求、稳定 404/409/503、本机 mutation guard、no-store 和 run 历史独立读取。
- [x] 增加工作台测试：删除任务不再产生任务/失败提醒或下一次计划，历史报告保持可读。

## 2. 实现数据库与后端

- [x] 新增 v17 迁移并更新 `CURRENT_DATABASE_VERSION` 与顺序迁移入口。
- [x] 在自动工作流 schema 中增加删除请求模型。
- [x] 在仓储中实现软删除、名称墓碑、活动运行/修订竞争保护，并在任务、调度和工作台读取边界过滤删除行。
- [x] 在服务层翻译仓储错误；在 FastAPI 路由增加受本机写保护的 DELETE 204 端点。
- [x] 运行自动工作流、工作台和迁移相关定向后端测试与 Ruff，修复后再进入前端。

## 3. 冻结并实现前端契约

- [x] 增加 API 边界测试：DELETE JSON 修订体、仅接受空 204、精确错误契约和网络失败。
- [x] 增加任务页行为测试：删除入口、确认取消、pending 防重、活动运行禁用、成功移除/反馈/焦点、冲突与服务失败保留任务。
- [x] 实现 `deleteAutomationTask` 与删除后的 TanStack Query 缓存协调，包含工作台失效。
- [x] 在现有任务卡和受控 AlertDialog 中增加 destructive 删除交互，复用现有组件、token 和反馈区。
- [x] 运行前端格式化及自动任务相关定向测试、类型检查，修复后再做全量检查。

## 4. 全量质量与本地验收

- [x] 后端：`cd backend && uv run ruff check src tests`。
- [x] 后端：`cd backend && uv run pytest`。
- [x] 前端：`cd frontend && mise x node@24 -- pnpm install --frozen-lockfile`。
- [x] 前端：`mise x node@24 -- pnpm format:check && mise x node@24 -- pnpm lint && mise x node@24 -- pnpm typecheck && mise x node@24 -- pnpm test:run && mise x node@24 -- pnpm build`。
- [x] 使用临时数据库启动本地后端和前端：浏览器验证创建→删除→列表消失→刷新仍消失、取消确认、移动宽度和控制台无错误；自动化集成测试验证历史运行详情与活动运行保护；停止测试服务。
- [x] 运行 `trellis-check` 全范围复核，并将确认过的新删除契约更新到自动工作流 spec。

## 5. 交付

- [x] 汇总变更、测试与任何未验证项供用户复核。
- [x] 按 Conventional Commits 创建本地提交，标题 `fix(automation): allow deleting obsolete tasks`。
- [ ] 完成 Trellis wrap-up；不执行 Centaurus 同步或远端推送。
