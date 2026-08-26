# 多平台批量采集技术设计

## 1. 设计目标与边界

本功能把多个现有的单平台采集任务组合成一个可恢复、可取消、可暂停的批次，不把多个平台塞进同一个 `search_run`，也不让 React 页面充当后台任务队列。

```text
React 批量采集表单 / 批次总览
  -> FastAPI search-batches API
  -> SearchBatchService（批次状态机与串行调度）
  -> SearchRunService 的可复用单平台执行边界
  -> SearchBatchRepository + SearchRunRepository
  -> 产品 SQLite
  -> 现有持久化 MediaCrawler worker
  -> 用户已批准的谷歌浏览器会话
```

FastAPI 继续拥有业务状态和调度；SQLite 是批次与平台尝试的唯一事实来源；MediaCrawler 仍只执行一个平台、一次有界搜索。本任务不修改五个平台的采集协议，也不引入浏览器并发。

## 2. 聚合与状态模型

### 2.1 批次

批次状态为：

```text
queued | running | paused_for_manual_action |
completed | completed_with_failures | cancelled | internal_error
```

状态流转：

```text
queued -> running
running -> paused_for_manual_action -> running
running -> completed | completed_with_failures | cancelled | internal_error
paused_for_manual_action -> cancelled
```

- `completed`：所有平台的最新尝试均为 `completed_with_results` 或 `completed_empty`。
- `completed_with_failures`：队列已跑完，但至少一个平台的最新尝试为其他终态。
- `paused_for_manual_action`：当前平台返回 `manual_challenge_required`，批次保留当前顺序位置并等待用户继续或取消。
- `internal_error` 只表示批次调度或存储自身无法可靠继续；单个平台的 `internal_error` 是平台尝试失败，批次仍继续后续平台。

### 2.2 平台项与尝试

每个选中平台对应一个有序批次项。平台项保存固定目录顺序、当前状态和时间；真正开始平台搜索时才建立一个现有 `search_run` 作为尝试。人工验证后继续会为同一个平台项建立新的尝试，旧尝试不可变且仍可审计。

批次总览投影平台项的最新尝试：`latest_run_id`、`attempt_count`、运行状态、当前搜索词位置、新增/再次命中/总数和时间。历史尝试通过批次项读取，但不会在总览中重复堆叠。

## 3. SQLite 迁移

数据库版本从 6 升至 7，新增：

```text
search_batches(
  id, monitoring_rule_id, rule_name, max_results_per_term, status,
  current_item_position, created_at, started_at, finished_at
)

search_batch_terms(batch_id, position, value)

search_batch_items(
  batch_id, position, platform, status, created_at, started_at, finished_at
)

search_batch_attempts(
  batch_id, item_position, attempt_number, search_run_id, created_at
)
```

关键约束：

- `PRIMARY KEY search_batch_terms(batch_id, position)`；
- `PRIMARY KEY search_batch_items(batch_id, position)`；
- `UNIQUE search_batch_items(batch_id, platform)`；
- `PRIMARY KEY search_batch_attempts(batch_id, item_position, attempt_number)`；
- `UNIQUE search_batch_attempts(search_run_id)`；
- 批次源规则使用 `ON DELETE SET NULL`，规则名称和搜索词是提交时的不可变快照；
- 平台值由服务层严格校验为当前五个平台，数据库保存规范化目录顺序；
- 现有 `search_runs`、结果关系与 `(platform, platform_content_id)` 去重约束保持不变。

创建批次、词快照和平台项必须是一个短事务。创建新尝试时，插入 `search_run`、词快照、尝试关系和平台项状态也是一个短事务。浏览器与 worker 操作始终在事务之外。

启动恢复规则：

- 中断的单平台 `queued/running` 尝试按现有规则收敛为 `internal_error`；
- 对应批次把该平台视为一次普通失败并从下一个未执行平台继续；
- 尚未开始的平台项保持排队；
- 人工验证暂停的批次保持暂停，不自动创建新尝试；
- 无法确定一致状态时批次收敛为 `internal_error`，不猜测成功。

## 4. HTTP 契约

新增版本化路由：

```http
POST /api/v1/search-batches
GET  /api/v1/search-batches?limit=20&before_id=<optional-int64>
GET  /api/v1/search-batches/{batch_id}
POST /api/v1/search-batches/{batch_id}/cancel
POST /api/v1/search-batches/{batch_id}/continue
GET  /api/v1/search-batches/{batch_id}/items/{position}/attempts
```

严格开始请求：

```json
{
  "monitoring_rule_id": 1,
  "platforms": ["toutiao", "wb", "ks", "dy", "xhs"],
  "max_results_per_term": 10
}
```

- `platforms` 必须包含 1–5 个互不重复的平台；后端不信任客户端顺序，统一按产品目录排序。
- 规则、搜索词数量和每词结果上限复用现有验证。
- 创建成功返回 HTTP 202 和持久化批次详情，前端随后进入批次路由。
- `continue` 仅允许人工验证暂停的批次；它不会修改旧尝试，而是为同一平台创建下一次尝试。
- `cancel` 取消当前 worker 请求，把未开始平台项标为取消，并保留已完成尝试和结果。
- 批次列表按 `id DESC` 使用 `before_id` 游标；批次详情返回有序平台项和最新尝试投影。
- 现有 `/search-runs` 创建、读取、取消和结果 API 保持兼容。批次详情使用已有 run ID 下钻；单平台历史读取增加一个兼容的范围过滤，避免批次子任务在主历史中重复展示，API 默认行为不变。

新增产品错误至少包括：批次不存在、批次不可取消、批次不可继续、平台集合无效和存储不可用。所有错误沿用固定中文消息与 `detail.code/message`，不包含规则词、数据库路径、worker 输出或平台原始异常。

## 5. 调度与浏览器所有权

`SearchBatchService` 和 `SearchRunService` 共享数据库、worker 与 `BrowserOperationCoordinator`。单平台搜索的“创建 run、执行 worker、持久化事件、形成终态”提取为一个内部可复用执行器；批次不得复制平台协议或结果入库逻辑。

一个批次在开始前原子声明浏览器操作所有权，并在平台之间保持所有权，确保账号检查、结果打开或另一个采集任务不能插入队列。人工验证暂停时仍保留批次所有权，保护可见验证页面不被产品中的其他操作清理；继续复用该批次所有权，取消或批次终止后释放。

每个平台流程：

```text
读取持久化批次快照
  -> 创建新的单平台尝试
  -> 执行现有单平台 worker 搜索
  -> 将尝试终态投影到批次项
  -> manual_challenge_required：暂停
  -> 其他终态：继续下一平台
  -> 全部完成：计算 completed / completed_with_failures
```

批次取消只取消当前尝试并停止后续调度。关闭页面不会取消批次。FastAPI 关闭时安全取消内存任务；下次启动依据 SQLite 恢复规则继续。

## 6. 前端体验

### 6.1 页面任务与视觉方向

页面服务于单人值守人员，唯一任务是“一次发起多个平台并看清每个平台执行到哪里”。保留当前 Shadcn/Base UI、现有语义色、字体与平台 SVG，不新增主题、不重写配色、不添加虚构指标。

只有五个固定平台，因此使用可见的 Shadcn Checkbox 平台卡片组，而不是隐藏在自定义多选下拉中：

```text
采集平台
[✓ 今日头条] [✓ 微博] [✓ 快手] [✓ 抖音] [✓ 小红书]
```

- 初始全选；每项同时显示复选框、Logo 和中文名称；
- 组使用 `fieldset/legend` 或等价 Shadcn Field 语义，键盘、焦点和屏幕阅读器可完整操作；
- 手机端自然换行，不产生横向滚动；
- 表单由 React Hook Form + Zod 拥有平台数组，错误显示在控件附近。

### 6.2 批次总览

新增 `/collection-batches/:batchId`。页面的识别性元素是一条有真实含义的“平台执行轨道”，按固定顺序展示平台 Logo、状态、尝试次数和结果数量：

```text
已完成 2 / 5 个平台                      [取消批次]

✓ 今日头条   采集完成       新增 8 / 再次命中 2   [查看]
✓ 微博       采集完成       新增 3 / 再次命中 1   [查看]
● 快手       正在采集       第 2 / 5 个搜索词     [查看]
○ 抖音       等待中
○ 小红书     等待中
```

顺序线和图标编码真实流程，不作为装饰。状态始终有文字，不能只靠颜色。进度显示已形成终态的平台数量和当前平台搜索词位置，不伪造时间百分比。只保留现有轻量加载旋转，遵守 reduced motion。

人工验证暂停时，页首显示当前平台和明确动作：“请在谷歌浏览器完成验证”，并提供 Shadcn `继续采集` 与 `取消批次` 按钮。继续处于请求中时禁止重复提交；若浏览器或存储冲突，保留暂停状态和可操作错误。

批次历史成为新提交的主入口；旧单平台历史继续可读。批次项点击进入现有 `/collection-runs/:runId`，旧尝试可从“尝试记录”查看。TanStack Query 仅在批次为 `queued/running` 时每秒轮询；暂停和终态依赖普通缓存与显式刷新/变更失效。

## 7. 兼容性、隐私与回滚

- 不修改现有五个平台 worker 搜索帧和适配器；MediaCrawler 派生仓库原则上无需变更。
- 数据库迁移只新增批次表，不重写现有运行或结果；旧代码遇到更高 schema 版本应按现有规则拒绝启动，不删除用户数据。
- 旧单平台 API、历史深链接、结果打开和账号检测继续工作。
- 前端只接收批次/运行 ID、平台枚举、状态、数量与时间；搜索词仅沿用已有安全快照边界，不新增日志或遥测。
- 若批次调度导致两个 worker 搜索重叠、关闭用户原有标签页、丢失既有运行数据或把失败表示成成功，立即停止真实验收并回滚代码；不得回滚或删除用户 SQLite、浏览器数据或历史结果。

## 8. 关键权衡

- 选择持久化批次聚合而非 React 临时队列：增加一次数据库迁移和 API 面，但满足刷新/重启恢复与权威取消。
- 保留单平台 run 而非一个多平台 run：数据结构更多，但失败、结果、重试和现有详情契约保持清晰。
- 人工验证后创建新尝试而非复活终态 run：历史更诚实，也保持现有 run 终态不可变；代价是同一平台可能有多个尝试，需要总览明确展示最新状态。
- 使用可见复选框组而非自制多选下拉：占用更多横向空间，但五个平台数量固定、默认全选，操作与可访问性更直观。
