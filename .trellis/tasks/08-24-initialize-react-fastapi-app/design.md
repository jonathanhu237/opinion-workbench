# React + FastAPI 项目骨架设计

## Scope and Boundary

本任务建立产品自己的前端和后端，并证明一次最小端到端请求能够工作。它不实现舆情
页面、SQLite 业务模型、平台登录、MediaCrawler 进程、定时任务或 AI 分析。

现有 `third_party/MediaCrawler` 保持独立 submodule 和独立依赖环境；本任务不得修改
其源码、gitlink 或运行数据。用户现有的 `db_data/`、`logs/` 只通过 Git ignore
保护，不读取、不删除、不迁移。

## Repository Layout

```text
longtian-public-opinion-management/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   └── App.tsx
│   │   ├── components/
│   │   │   └── ui/
│   │   └── lib/
│   │       └── api/
│   │           └── health.ts
│   ├── .env.example
│   ├── .node-version
│   ├── components.json
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   └── longtian_api/
│   │       ├── api/
│   │       │   ├── router.py
│   │       │   └── v1/
│   │       │       └── health.py
│   │       ├── schemas/
│   │       │   └── health.py
│   │       └── main.py
│   ├── tests/
│   │   └── test_health.py
│   ├── .python-version
│   ├── pyproject.toml
│   └── uv.lock
├── third_party/
│   └── MediaCrawler/
├── .gitignore
└── README.md
```

不创建 `apps/`、`runtime/`、`scripts/`、根级 pnpm workspace 或根级 uv workspace。
未来运行数据存放位置在数据库任务中决定，不用空目录提前表达未实现的架构。

## Toolchain

### Frontend

- Node 24 LTS，通过 `frontend/.node-version` 表达项目基线；实施时用 mise 运行该版本。
- pnpm 11，并在 `package.json` 固定 package manager 元数据。
- Vite + React + TypeScript 的 `react-ts` 模板。
- Tailwind CSS 和 shadcn/ui，使用 `@/* -> src/*` alias。
- ESLint、TypeScript project build 和 Vite production build 作为质量入口。

不引入路由、全局状态库、数据请求库或表单库。初始化只有一个页面和一个请求，使用
React 本地状态与窄 API client 足够。

### Backend

- Python 3.11 和 uv，backend 拥有独立 `.venv` 与 `uv.lock`。
- packaged application + `src/longtian_api`，避免从仓库工作目录偶然导入源码。
- FastAPI 应用入口由 `[tool.fastapi] entrypoint = "longtian_api.main:app"` 声明。
- Ruff 负责 lint/format，pytest + FastAPI TestClient 负责接口测试。

backend 不声明 MediaCrawler 为 dependency，也不 import `third_party`。

## Backend Design

`longtian_api.main` 提供 `create_app() -> FastAPI`，再创建模块级 `app`。应用只注册一个
版本化 router，不添加数据库、lifespan、CORS、认证或全局异常中间件。

健康检查契约：

```http
GET /api/v1/health
```

```json
{
  "status": "ok",
  "service": "longtian-public-opinion-api"
}
```

- HTTP 200 表示 API 进程可用。
- `status` 为字面值 `ok`，`service` 为稳定服务标识。
- 路由声明明确的 `HealthResponse` Pydantic 返回类型。
- 不查询 SQLite、Chrome 或 MediaCrawler；这是进程健康检查，不是依赖就绪检查。

开发命令只监听 `127.0.0.1:8000`，不使用 `0.0.0.0`。

## Frontend Design

初始页面是一个克制的本地系统状态页，标题为“龙田街道舆情系统”，使用 shadcn/ui
的 Card、Badge 和 Button。页面只表达工程已连通，不伪造舆情统计或业务数据。

状态机：

```text
initial/loading
  ├── 200 + valid body → connected
  └── network/non-2xx/invalid body → unavailable
                                 └── retry → loading
```

`src/lib/api/health.ts` 拥有 API boundary：

- base URL 从 `VITE_API_BASE_URL` 读取，默认 `/api/v1`。
- 请求 `/health`，检查 HTTP 状态和最小 payload shape。
- 接收 `AbortSignal`，组件卸载时取消请求。
- 不把 fetch、JSON 解析或错误消息散落在 UI 组件中。

页面区分“正在连接”“后端已连接”“后端不可用”，失败时提供重新检测按钮。错误详情
保持适合本地开发，不显示堆栈或环境路径。

## Frontend ↔ Backend Boundary

开发期 Vite 将 `/api` 代理到 `http://127.0.0.1:8000`：

```text
Browser http://127.0.0.1:5173
  → GET /api/v1/health
  → Vite dev proxy
  → FastAPI http://127.0.0.1:8000/api/v1/health
  → HealthResponse JSON
  → frontend payload validation
  → status card
```

因此初始化不需要允许任意 origin 的 CORS。未来生产是由 FastAPI 托管静态文件、独立
端口还是桌面壳层，必须在部署任务中明确后再设计 CORS。

## Repository Hygiene

根 `.gitignore` 至少覆盖：

- frontend `node_modules/`、`dist/`、Vite cache 和本地 `.env*`，但保留 example。
- backend `.venv/`、Python cache、pytest/Ruff cache、coverage 和本地 `.env*`。
- 用户既有 `db_data/`、`logs/` 运行目录。

提交 pnpm 和 uv lockfiles。不得提交虚拟环境、构建产物或本地运行数据。

## Failure Handling

| Condition | Behavior |
| --- | --- |
| FastAPI 未运行 | 前端显示不可用并允许 retry |
| API 非 2xx | API client 抛出窄错误，页面显示不可用 |
| JSON shape 不匹配 | 视为契约错误，不把未知 payload 当成功 |
| 请求在卸载时取消 | 不更新已卸载组件，不显示误导性错误 |
| 子模块有变化 | 停止交付并确认不是本任务造成 |
| `db_data/`/`logs/` 出现改动 | 停止并保留用户数据，不清理 |

## Validation

- Backend: Ruff lint、Ruff format check、pytest、直接 health 请求。
- Frontend: ESLint、TypeScript、Vite production build。
- Cross-layer: 通过 Vite proxy 请求 health；停止 backend 后验证 unavailable 和 retry。
- Visual: 在本机浏览器检查 loading、connected、unavailable 三种状态及窄屏布局。
- Repository: `git diff --check`、submodule status、用户运行目录未进入版本控制。

## Deferred Decisions

- SQLite ORM、迁移和应用数据目录。
- MediaCrawler 子进程协议和规范化结果 schema。
- 用户 Chrome CDP 连接管理和平台登录中心。
- 路由、导航、完整设计系统、暗色模式和正式舆情页面。
- 生产打包、后台服务、自启动、定时唤醒和端口策略。
