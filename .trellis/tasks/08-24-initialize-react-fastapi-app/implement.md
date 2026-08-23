# 实施计划

## Phase 0: Preflight

- [x] 确认父仓库现有状态，记录并保护用户未跟踪的 `db_data/`、`logs/`。
- [x] 确认 `third_party/MediaCrawler` 工作树干净、父仓库 gitlink 为当前固定 revision。
- [x] 使用 mise 的 Node 24 LTS 执行前端生成命令；不以本机 Node 26 Current 生成锁文件。
- [x] 读取实施清单中的 Trellis specs/research，不修改 placeholder specs。

## Phase A: Backend Scaffold

- [x] 在 `backend/` 初始化 Python 3.11 uv packaged application 和 `src/longtian_api`。
- [x] 添加 FastAPI 运行依赖及 Ruff、pytest/TestClient 开发依赖，生成并提交 `uv.lock`。
- [x] 在 `pyproject.toml` 配置 FastAPI entrypoint、Ruff 和 pytest。
- [x] 实现 `create_app()`、版本化 router、`HealthResponse` 和
  `GET /api/v1/health`。
- [x] 添加健康检查测试，验证状态码和完整 JSON 契约。

## Phase B: Frontend Scaffold

- [x] 在 `frontend/` 使用 Vite `react-ts` 模板初始化 React + TypeScript。
- [x] 使用 pnpm、Tailwind CSS 和 shadcn/ui 配置 `@` alias、`components.json` 和主题基础。
- [x] 只添加状态页实际需要的 Card、Badge、Button 组件。
- [x] 实现窄职责 health API client，覆盖非 2xx、无效 payload 和 AbortSignal 语义。
- [x] 实现 loading、connected、unavailable 和 retry 状态页；不添加虚构业务数据。
- [x] 配置 Vite `/api` → `127.0.0.1:8000` proxy 和前端 `.env.example`。
- [x] 添加明确的 `lint`、`typecheck`、`build` scripts 并生成 pnpm lockfile。

## Phase C: Repository Documentation and Hygiene

- [x] 建立根 `.gitignore`，忽略依赖、构建、cache、环境文件以及 `db_data/`、`logs/`，
  但不删除或读取用户目录。
- [x] 编写根 README，说明项目结构、Node/Python/pnpm/uv 前置条件、两个开发服务器的
  安装启动命令和 health 验证方法。
- [x] 明确说明本次不运行 MediaCrawler，产品 backend 和 submodule 使用独立环境。

## Phase D: Automated Validation

- [x] Backend: `uv sync --locked`、`ruff check`、`ruff format --check`、`pytest`。
- [x] Frontend: 在 Node 24 下 `pnpm install --frozen-lockfile`、`lint`、`typecheck`、`build`。
- [x] 运行 `git diff --check`，确认没有构建产物、虚拟环境或本地 `.env` 被跟踪。
- [x] 验证 `git submodule status` 和 MediaCrawler HEAD/gitlink 均未改变。

## Phase E: Cross-layer and Visual Validation

- [x] 在 `127.0.0.1` 启动 FastAPI 和 Vite，直接请求 health endpoint。
- [x] 通过 Vite proxy 打开状态页，确认 connected 状态和 JSON 契约。
- [x] 停止 backend，确认 unavailable 状态；重启并点击 retry，确认恢复 connected。
- [x] 在桌面和窄屏检查 loading、connected、unavailable 页面，无横向溢出或模板残留。
- [x] 停止两个开发进程，确认没有端口或后台进程残留。

## Review and Delivery

- [x] 调度 Trellis implementation check，核对 PRD、跨层契约、工具链、质量命令和范围。
- [x] 修复 review 发现的问题并重新运行受影响检查。
- [x] 向用户汇报文件结构、启动方式、测试结果和任何剩余限制；未经单独批准不提交、
  不推送、不归档任务。

## Rollback Points

- 官方 scaffold 与 Node 24/当前 pnpm 不兼容：停止并记录命令，不切换到未确认模板。
- shadcn 生成超出最小组件范围：删除本任务新生成且尚未提交的冗余文件，保留官方
  必需配置；不得清理用户文件。
- health 契约在前后端不一致：停止视觉验收，先修复 API boundary 和测试。
- submodule 或用户运行目录出现非预期变化：停止交付，不自动回退或删除。
