# 龙田街道舆情系统

面向单机使用的舆情工具，包含 React 前端、FastAPI 后端，以及使用本机专用 Chrome
运行的微博、抖音、快手、小红书和今日头条登录、采集与文字分析能力。

## 项目结构

```text
frontend/                 React + TypeScript + Vite + shadcn/ui
backend/                  FastAPI 产品后端（独立 uv 环境）
```

产品支持微博（`wb`）、抖音（`dy`）、快手（`ks`）、小红书（`xhs`）和今日头条
（`toutiao`）。采集使用项目自有的原生浏览器边界；仅启动应用或打开页面不会启动浏览器。

## 环境要求

- Node.js 24 LTS（建议使用 mise，版本记录在 `frontend/.node-version`）
- pnpm 11
- Python 3.11
- uv
- 本机安装的 Google Chrome（平台登录与采集使用）

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

采集运行时默认选择五个平台，也可以在手动采集或自动任务中调整平台范围。后端使用项目
自有的原生浏览器采集边界；普通平台失败会记录采集缺口，登录或安全验证等人工障碍会
暂停批次，待在专用窗口完成操作后显式继续。

如需覆盖 API 地址，复制 `frontend/.env.example` 为 `.env.local` 并修改
`VITE_API_BASE_URL`。本地环境文件不会进入版本控制。

## 平台登录与专用浏览器

在“平台账号”中点击“检查状态”后，应用按需打开一个专用 Chrome 窗口。首次使用时，
请在这个窗口中登录对应平台；扫码、验证码和安全验证也由你在该窗口中完成。

- 无需在日常 Chrome 中开启远程调试或批准本应用连接。应用不会接管日常浏览器，
  也不会从中复制 Cookie。
- 专用窗口使用独立的本地目录 `runtime/browser/managed-chrome`，由 Chrome 保留登录态。
  该目录已排除在 Git 之外，不应共享或提交；平台登录过期后仍需重新登录。
- 各平台登录检查和采集中的浏览器操作共用专用窗口。单个任务结束不会关闭整个窗口；
  退出后端应用时会关闭其管理的专用浏览器，但保留登录目录。
- 若提示专用浏览器不可用，请先确认本机已安装 Chrome。若有残留的专用窗口，关闭它后
  再重新检查；不要删除浏览器目录或锁文件来强行恢复。

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
