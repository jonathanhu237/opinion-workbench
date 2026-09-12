# 开发与排障说明

产品能力及成品下载见 [README](../README.md)。

## 项目结构与环境

- 前端：React、TypeScript、Vite、shadcn/ui，位于 `frontend/`。
- 后端：FastAPI，独立 uv 环境，位于 `backend/`。
- 工具链：Node.js 24、pnpm 11、Python 3.11、uv，使用 mise 管理。
- 采集：本机 Google Chrome，支持微博、抖音、快手、小红书和今日头条。

开发、浏览器登录与应用验证默认全部在本机进行。

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
{"status":"ok","service":"opinion-workbench-api"}
```

## 启动前端

另开一个终端：

```bash
cd frontend
mise x node@24 -- pnpm install --frozen-lockfile
mise x node@24 -- pnpm dev
```

打开 <http://127.0.0.1:5173>。Vite 将 `/api` 请求代理到本机后端。

如需覆盖 API 地址，复制 `frontend/.env.example` 为 `.env.local` 并修改
`VITE_API_BASE_URL`。本地环境文件不进入版本控制。

仓库目录移动或改名后，重建后端虚拟环境；已有命令入口可能包含旧绝对路径。

## 平台登录与专用浏览器

应用启动或页面打开不会自动启动专用浏览器。在“平台账号”中点击“打开专用浏览器”，
再点击对应平台的“打开平台”，在专用窗口完成登录、扫码或安全验证。
完成后，点击“检查全部”或对应平台的“检查状态”。

登录检查会在时间预算内等待页面恢复登录态，但不会一直等待扫码或验证码；完成登录后需
重新检查。检查通过不代表已暂停的采集恢复，仍需显式点击继续。

- 应用不接管日常 Chrome，也不从中复制 Cookie，无需在日常 Chrome 开启远程调试。
- macOS 源码运行使用 `runtime/opinion-workbench/browser/managed-chrome` 保存专用浏览器资料；
  便携版使用程序旁的 `data/browser/managed-chrome`。
- 浏览器资料不应提交或共享，平台登录过期后需要重新登录。
- 任务结束不会关闭整个专用窗口；退出后端应用时会关闭其管理的浏览器，保留登录资料。
- 暂停或取消采集会停止应用后续的搜索、翻页和内容处理，不会冻结正在操作的登录页面。
  浏览器仍会正常加载网站所需的脚本、样式和认证请求。

若专用浏览器打开失败，先确认已安装 Chrome；若有残留的专用窗口，关闭后再重新打开。
不要删除浏览器目录或锁文件来强行恢复。

## 数据与空白切换

macOS 源码运行默认数据根为 `runtime/opinion-workbench/`，Windows 源码运行默认使用
`%LOCALAPPDATA%\OpinionWorkbench`；便携版的数据位于程序旁的 `data/`。

v0.2.0 是空白切换，不导入旧产品的数据库、规则、提示词、模型配置、凭据或浏览器资料。
旧资料应在旧应用及专用浏览器完全停止后单独保留或备份，不复制到新目录。
删除已使用的便携目录会一并删除内嵌的 `data/`。

未来同产品升级是否兼容，以对应版本的发布说明为准。

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

测试与打包检查使用合成资料，不需要真实平台账号或付费模型调用。

## 便携包构建

- Windows：参阅 [Windows 构建与使用说明](../windows/README.md)。
- macOS Apple Silicon：在项目根目录运行 `bash macos/build.sh`。
- 推送版本标签后，GitHub Actions 在原生 Windows 与 macOS runner 构建并检查最终解压包，
  两个平台通过后上传到同版本 Release 草稿，不自动公开。

CI 启动检查不能替代 Finder/Explorer 双击和系统安全提示的人工验收。
