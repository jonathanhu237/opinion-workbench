# 初始化 React + FastAPI 项目骨架

## Goal

为龙田街道舆情系统建立一个可独立启动、可相互连通的 React + FastAPI
全栈开发骨架，作为后续平台登录、采集任务、舆情列表和分析流程的应用基础。

本任务只完成工程初始化和最小端到端连通，不提前实现具体业务页面或采集逻辑。

## Requirements

- 前端使用 React、TypeScript 和 Vite。
- UI 体系后续采用 shadcn/ui，不引入 Ant Design；初始化阶段只建立必要的样式与组件目录基础。
- 后端使用 FastAPI，并组织为独立 Python 包；开发入口通过 `pyproject.toml` 声明。
- 前后端可以分别启动，并通过版本化 API 路径完成一次最小端到端请求。
- 提供 `GET /api/v1/health` 健康检查接口及明确的响应模型。
- 前端初始页面能展示后端连接成功或失败状态，验证跨层链路而非只渲染静态模板。
- 开发环境只监听本机地址；正确配置 Vite 代理或等价开发期通信方案。
- 提供最小的环境变量示例、开发命令和根目录使用说明。
- 为前端类型检查、代码检查和构建，以及后端代码检查和测试建立可执行入口。
- 保留现有 `third_party/MediaCrawler` 子模块，不修改其源码、依赖或运行方式。
- 保留用户现有的未跟踪目录 `db_data/` 和 `logs/`，不读取、删除或提交其中内容。

## Confirmed Product Decisions

- 这是部署在使用者个人电脑上的单用户工具。
- 前端选择 React，后端选择 FastAPI。
- UI 组件方案选择 shadcn/ui，不使用 Ant Design。
- 本地数据存储初步选择 SQLite，但本次初始化不创建业务表、迁移或数据库模型。
- 应用本身暂不实现传统账号登录；采集平台登录属于后续业务功能。
- 后续平台采集 MVP 优先复用用户当前 Chrome Profile：Chrome 未运行时由程序启动，
  用户按 Chrome 安全机制批准连接，后端尽量保持 CDP 连接；应用专属持久化
  Profile 仅作为未来可选的完全无人值守模式。该能力不在本次初始化任务中实现。
- 项目源码采用 `frontend/`、`backend/`、`third_party/` 平级结构。
- 后续继续使用派生版 MediaCrawler 作为平台采集引擎，通过独立子进程与产品 FastAPI
  隔离；产品后端负责任务、SQLite、结果归一化和业务流程，不复用 MediaCrawler
  WebUI/API 作为产品后端。

## Out of Scope

- 舆情看板、平台登录中心、关键词管理、采集任务和结果列表等正式页面。
- MediaCrawler 调用、子进程 worker、今日头条适配或其他平台采集逻辑。
- SQLite schema、ORM、数据库迁移和数据仓储实现。
- 定时任务、AI 分析、风险分级、通知和任务闭环。
- Docker、生产部署、远程访问和多用户权限系统。

## Acceptance Criteria

- [ ] 前端和后端可按 README 中的命令独立安装依赖并启动。
- [ ] `GET /api/v1/health` 返回通过响应模型校验的健康状态。
- [ ] 前端初始页面能请求健康检查接口，并明确显示成功或不可用状态。
- [ ] 前端类型检查、lint 和生产构建通过。
- [ ] 后端 lint 和测试通过，健康检查至少有一个自动化测试。
- [ ] 根目录文档说明项目结构、环境要求和本地开发步骤。
- [ ] `third_party/MediaCrawler` 子模块指针不发生变化。
- [ ] `db_data/` 和 `logs/` 保持未跟踪且内容不受影响。

## Open Decisions

- 暂无。

## Notes

- 该任务跨越前后端，需要在实施前补充 `design.md`、`implement.md`、
  `implement.jsonl` 和 `check.jsonl`。
- 最小跨层数据流为：React 页面 → API 客户端 → FastAPI 路由 →
  Pydantic 响应模型 → React 状态展示。
