# 龙田街道舆情系统

面向单机使用的舆情工具。目前仓库提供 React 前端、FastAPI 后端和一次真实的健康检查
链路，业务页面、平台登录与采集能力将在后续任务中逐步接入。

## 项目结构

```text
frontend/                 React + TypeScript + Vite + shadcn/ui
backend/                  FastAPI 产品后端（独立 uv 环境）
third_party/MediaCrawler/ 平台采集引擎 submodule（独立依赖环境）
```

产品后端当前不会导入或启动 MediaCrawler。两者使用彼此独立的 Python 环境，后续通过
受控子进程集成。

## 环境要求

- Node.js 24 LTS（建议使用 mise，版本记录在 `frontend/.node-version`）
- pnpm 11
- Python 3.11
- uv

## 启动后端

```bash
cd backend
uv sync --locked
uv run fastapi dev --host 127.0.0.1 --port 8000
```

验证接口：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

预期响应：

```json
{"status":"ok","service":"longtian-public-opinion-api"}
```

## 启动前端

另开一个终端：

```bash
cd frontend
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm dev
```

打开 <http://127.0.0.1:5173>。Vite 会把 `/api` 请求代理到本机的 FastAPI 服务；页面
会显示“后端已连接”或可操作的不可用状态。

如需覆盖 API 地址，复制 `frontend/.env.example` 为 `.env.local` 并修改
`VITE_API_BASE_URL`。本地环境文件不会进入版本控制。

## 质量检查

后端：

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

前端：

```bash
cd frontend
mise x node@24 -- pnpm format:check
mise x node@24 -- pnpm lint
mise x node@24 -- pnpm typecheck
mise x node@24 -- pnpm test:run
mise x node@24 -- pnpm build
```
