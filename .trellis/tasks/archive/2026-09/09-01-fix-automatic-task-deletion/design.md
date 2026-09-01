# 自动任务删除技术设计

状态：规划评审。`prd.md` 是产品行为的权威来源。

## 1. 方案概述

采用不可恢复的软删除，而不是级联物理删除。给 `automation_tasks` 增加可空的 `deleted_at`；删除事务同时清空调度字段、设置 `enabled=0`、递增修订号并写入删除时间。运行、阶段、内容归属、幂等请求、采集/分析产物和报告表均不删除、不改写。

本任务保持为一个跨层任务，不拆成前后端子任务。数据库可见性、调度竞争、HTTP 契约、查询缓存和界面行为共享同一个删除语义，需要按顺序集成验证。

## 2. 数据库与仓储

### v17 迁移

- 保持已发布 v15/v16 迁移不变，新增前向 v16→v17 迁移。
- `ALTER TABLE automation_tasks ADD COLUMN deleted_at TEXT`，历史行默认 `NULL`。
- 新增触发器约束：一旦 `deleted_at` 非空，任务必须同时为停用且 `next_due_at`/`anchor_at` 均为空；已删除行不得恢复或继续编辑。
- 迁移在现有 `BEGIN IMMEDIATE`、版本复核、回滚和 `PRAGMA user_version` 契约内运行。

### 删除事务

`AutomationWorkflowRepository.delete_task(task_id, expected_revision, now)` 在一个 `BEGIN IMMEDIATE` 事务内：

1. 读取任务，包括已删除行；未知 ID 返回 not-found。
2. 若任务已经由同一 `expected_revision` 删除，作为相同请求的幂等重放成功返回。
3. 比较当前修订；不匹配返回 task-changed。
4. 检查该任务是否存在 `queued/collecting/analysing/reporting` 运行；存在则返回 run-active。
5. 原子写入 `enabled=0`、空调度锚点、`deleted_at/updated_at`、`revision+1`。
6. 将私有 `normalized_name` 改为包含 NUL 前缀和任务 ID 的不可由合法用户名称生成的墓碑值，使原名称可被新任务复用；公开 `name` 和历史快照保持不变。

数据库写锁让删除与 `advance_due/create_run` 串行：删除先提交时后续调度看不到可用任务；调度先创建运行时删除看到活动运行并拒绝；若只创建了 occurrence claim，随后的任务读取会失败并把 claim 安全终结，不会产生运行。

### 读取边界

- `_task_row`、`get_task`、任务列表、任务范围的 occurrence/run 列表、编辑和立即运行均把 `deleted_at IS NOT NULL` 视为任务不存在。
- 所有 due/claim 查询显式要求 `deleted_at IS NULL`，即使删除事务已将 `enabled` 设为 0，形成第二道调度围栏。
- `GET /automation-runs/{id}` 和报告/子产物读取不依赖活动任务投影，因此已保存历史继续可读。
- 工作台不再为已删除任务展示任务配置提醒、终态失败提醒或下一次计划；全局最新可读报告仍按既有规则保留。

## 3. 服务与 HTTP 契约

新增严格请求模型：

```json
{"expected_revision": 3}
```

新增端点：

```text
DELETE /api/v1/automation-tasks/{id} -> 204 No Content
```

- 使用现有本机写操作保护与 `Cache-Control: no-store`。
- 未知/已被其他操作删除的任务为 404 `automation_task_not_found`；陈旧修订为 409 `automation_task_changed`；活动运行为 409 `automation_run_active`。
- 服务层将仓储错误翻译为现有稳定产品错误，意外存储错误仍为常量 503。
- DELETE 成功体必须为空；OpenAPI 明确 204 与既有错误响应。

## 4. 前端交互

- 每张任务卡增加带 `Trash2` 图标的 `destructive` 按钮，沿用现有至少 44px 的触控目标和可见焦点样式。
- 使用受控 `AlertDialog`，标题与说明明确：任务将停止未来计划并从列表移除，已有运行和报告保留，操作不可恢复。
- 活动运行时删除按钮不可用，易访问名称说明需先取消；后端仍保留竞争保护。
- 确认期间锁定对话框按钮并显示“正在删除…”，取消不发请求。
- API 客户端严格发送任务修订号并只接受空的 204；错误继续校验精确 `(status, code, message)` 契约。
- 成功后先从所有任务列表缓存移除任务、清除该任务详情缓存，再失效自动任务和工作台查询；分页由服务端重新读取校正。显示简短成功反馈，并在触发按钮随任务消失后把焦点移到稳定的“刷新任务”按钮。
- 失败时保留任务、关闭或解锁确认状态，失效任务缓存并显示原因明确的反馈；不以本地状态假装删除成功。
- 运行详情的返回入口统一回到 `/automation-tasks`，不再依赖已删除任务的任务范围运行记录路由；运行详情本身仍通过独立运行 ID 保持可读。

UI/UX 检索结果支持此方案：删除使用 AlertDialog 二次确认、语义化 destructive 变体、完整标题/描述、可见 pending/成功反馈和对话框焦点管理；不增加自定义配色或新的弹窗原语。

## 5. 兼容、回滚与风险

- v17 为加列与触发器迁移，不改写历史外键图。旧数据库升级后所有任务保持未删除。
- 回滚到只理解 v16 的应用会因前向版本保护拒绝打开数据库，不会误读软删除数据；代码回滚需配套恢复 v16 数据库备份，不能简单降低 `user_version`。
- 名称墓碑只存在私有列，禁止输出到 API 或日志。
- 不删除实际 `runtime/longtian.sqlite3`；自动测试仅使用临时数据库。

## 6. 验证策略

- 迁移：真实 v16→v17、空/有历史任务、重复初始化、前向版本拒绝、失败回滚、触发器约束和 FK/integrity 检查。
- 仓储/服务：无历史与有终态历史删除、名称复用、幂等重放、未知/陈旧修订、活动运行、删除与调度交错、所有列表过滤及历史 run 保留。
- HTTP/OpenAPI：204 空体、严格 JSON、Host/Origin、404/409/503、no-store 和公开 schema。
- 工作台：删除后的配置提醒、失败提醒和下一次计划消失，历史报告仍可读。
- 前端 API/交互：确认与取消、pending 锁、活动运行禁用、缓存移除、成功/错误反馈、焦点恢复和移动宽度布局。
- 完整执行本地后端 Ruff/pytest 与前端 format/lint/typecheck/Vitest/build；涉及路由渲染，最后使用本地临时数据库与本机浏览器做无真实采集/模型调用的 smoke check。
