# React + FastAPI 初始化资料结论

## Local Toolchain

- Node.js: `v26.7.0`（Current，不作为项目推荐版本）
- pnpm: `11.14.0`
- uv: `0.12.3`
- Python: `3.14.6`
- mise: `2026.8.9`
- MediaCrawler 固定 Python `3.11`，`requires-python = ">=3.11"`

## Decisions

### Frontend

- 使用 Vite 的 `react-ts` 模板，不使用 React Compiler 模板。
- 项目声明 Node 24 LTS；实施时通过 mise 使用 Node 24，避免以 Node 26 Current 生成
  锁文件。
- 使用 pnpm，并在 `package.json` 声明 `packageManager`。
- 按 shadcn/ui 官方 Vite 现有项目流程配置 Tailwind CSS、`@/*` alias 和
  `components.json`；只添加初始状态页实际需要的少数组件。
- 不建立 pnpm workspace，也不添加根级 JavaScript package。

### Backend

- 使用 Python 3.11，与 MediaCrawler 的既有 Python 基线一致，但 backend 保持独立
  uv 环境和锁文件。
- 使用 uv packaged application 和 `src/longtian_api` 布局。
- 在 `pyproject.toml` 的 `[tool.fastapi]` 中声明 `longtian_api.main:app` 入口，开发使用
  `uv run fastapi dev`。
- 使用 Ruff 和 pytest；健康检查通过 FastAPI TestClient 验证。
- 不建立 uv workspace，不把 `third_party/MediaCrawler` 加入 backend 环境。

### Cross-layer

- 开发期使用 Vite `/api` proxy 指向本机 FastAPI，避免为初始化添加宽泛 CORS。
- 前后端只共享书面化的健康检查 JSON 契约；当前单个契约不引入 OpenAPI 客户端生成。
- 生产部署、静态资源托管和跨域策略留待部署任务决定。

## Primary Sources

- Node.js releases: https://nodejs.org/en/about/previous-releases
- Vite getting started: https://vite.dev/guide/
- shadcn/ui Vite: https://ui.shadcn.com/docs/installation/vite
- FastAPI CLI: https://fastapi.tiangolo.com/fastapi-cli/
- uv project init: https://docs.astral.sh/uv/concepts/projects/init/
- uv project layout: https://docs.astral.sh/uv/concepts/projects/layout/
