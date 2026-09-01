# 实施计划

该任务跨越 SQLite、提示词版本仓储、三类准入 API、自动运行快照和多个前端表单。按后端契约 → 自动流程 → 手工流程 → 前端 → 全量验证顺序实施，不拆成可独立上线的子任务。

## 0. 实施前准备

- [x] 读取 `prd.md`、`design.md`、本任务 research 与全部注入 spec，确认 `main` 上已有两处按钮文案改动属于本任务。
- [x] 核对当前 v17 结构、默认提示词常量、历史 snapshot 解码、请求证明哈希和缓存键，禁止改写 v12–v17 历史迁移。
- [x] 冻结 PromptChoice、任务投影、手工准入和历史来源标签的后端/前端测试契约。

## 1. 数据库与共享提示词模型

- [x] 增加 v18 迁移测试：固定默认版本、旧共享自定义、现有/已删除任务填充、历史不改写、触发器/FK、重开、回滚和前向版本。
- [x] 实现固定内置模板解析与不可变自定义版本复用助手，验证完整文本而非只信任哈希。
- [x] 扩展自动任务 prompt mode/version 字段与约束；复位运行时默认指针但保留全部旧版本和历史引用。
- [x] 更新数据库版本与迁移入口，运行迁移/仓储定向测试和 Ruff。

## 2. 自动任务两阶段配置

- [x] 增加严格 PromptChoice、已解析 PromptSnapshot、任务 create/replace/read 与新版/旧版 run snapshot schema。
- [x] 在任务创建/替换事务中解析并保存两阶段选择；迁移后的 `analysis_goal` 仅作为第二阶段私有镜像。
- [x] 自动运行冻结并向初步分析/报告 child 传递正确的两份提示词；重试沿用 snapshot，缓存按实际第一阶段哈希复用。
- [x] 覆盖默认/自定义组合、编辑并发、调度/立即运行、删除墓碑、历史运行和报告读取。

## 3. 手工分析与报告

- [x] 手工初步分析请求只接收第一阶段 PromptChoice，在准入/请求证明事务内解析版本并冻结来源。
- [x] 手工报告创建统一为第二阶段 PromptChoice；技术重试保留原提示词，“其他提示词重新生成”明确创建新的 default/custom 意图。
- [x] 删除全局 prompt PUT 路由/服务写入口，`GET /analysis-settings` 只返回固定模板和自动分析授权；保留历史版本读取。
- [x] 覆盖严格 payload、无提示词 CAS、UUID replay/conflict、不同提示词缓存隔离、历史 legacy 来源和稳定错误。

## 4. 前端交互

- [x] 扩展 API Zod 契约和 fixtures，删除全局 prompt 保存客户端，增加 PromptChoice/PromptSnapshot 严格解码。
- [x] 实现可复用 PromptChoiceField：默认预览、自定义复制/草稿、字数、关联错误、pending 和无 placeholder-only 语义。
- [x] 自动任务编辑器改为两个阶段区块；任务卡/运行详情显示摘要与冻结来源；保留“创建自动任务”按钮改动。
- [x] 手工初步分析确认只配置内容理解要求；手工报告配置相关性与报告要求；移除 ResultsSettings 全局 prompt editors。
- [x] 增加自动/手工默认与自定义、切换、关闭重开、含糊提交、历史来源和移动布局测试。

## 5. 质量、规范与交付

- [x] 后端：`cd backend && uv run ruff check src tests && uv run pytest`（Ruff 与全量 pytest 均通过）。
- [x] 前端：使用现有本地 Node 依赖运行 Prettier check、oxlint、TypeScript build、全量 Vitest 与 Vite build；仓库声明的 pnpm 版本与当前安装版本不一致，未改动 lockfile。
- [x] 使用临时数据库、本地后端和本地浏览器验收自动任务两阶段、手工初步分析、手工报告、历史详情、移动宽度和控制台；不提交真实模型/采集。
- [x] 运行 `trellis-check`，将最终默认/自定义、缓存兼容、迁移和历史契约同步到相关 spec。
- [ ] 汇总结果，按 Conventional Commits 在本地 `main` 提交并完成 Trellis wrap-up；不创建分支、不推送远端。
