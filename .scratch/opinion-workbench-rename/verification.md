# 舆情工作台改名验证记录

状态：代码与本机验证完成；未提交、未推送，未创建或上传 Release。

## 已完成

- 当前代码包、入口、健康服务身份、环境变量、运行文件名、浏览器所有权锁、冻结程序和发行脚本已统一为 `opinion-workbench` / `OpinionWorkbench`。
- 产品页面、说明和规则术语使用“舆情工作台”“采集对象”“舆情词”“总结提示词”“报告提示词”。
- 新鲜数据库不创建任何监控规则；默认两阶段提示词不包含地域或龙田限定。旧数据库、凭据和浏览器资料不由新默认数据根读取。
- 源码开发运行时的数据根改为 `runtime/opinion-workbench/`；原 `runtime/` 下的旧资料未删除。
- GitHub 仓库已重命名为 `jonathanhu237/opinion-workbench`，本地 `origin` 已更新；没有向远端推送工作区改动。
- R1：删除并通过 `uv sync --locked` 在改名后的目录重建 `backend/.venv`；`fastapi` shebang 指向当前目录，所有重建入口均无旧绝对路径。
- R2：Windows/Mac 打包说明、Windows 内置说明和 Release body 统一记录本次是空白切换，不导入旧 `data/`；明确旧目录需另行保留，删除使用过的便携目录会删除其内嵌数据；未来同产品兼容升级另行说明。
- R3：源代码运行根测试按平台分支断言，并以隔离的路径 seam 覆盖 Windows `LOCALAPPDATA/OpinionWorkbench` 默认分支。
- R4：新增中性默认提示词和空规则回归、跨批次/跨对象显式选材与两阶段操作者提示词独立执行回归，以及合成旧数据库/凭据/Chrome Cookie 保留和新状态隔离回归。

## 命令证据

- `cd backend && uv run --locked pytest -q`：`1294 passed, 2 skipped`（完整后端套件）。
- 文档入口复核：`cd backend && uv run fastapi dev --help`、`uv run pytest -q tests/test_health.py`（`1 passed`）和直接执行 `.venv/bin/fastapi --help` 均通过；重建 `.venv/bin/fastapi` 首行仅指向当前 `opinion-workbench` 路径。
- `cd backend && uv run ruff check .`：通过。
- `cd backend && uv run ruff format --check .`：通过。
- `cd frontend && mise x node@24 -- pnpm install --frozen-lockfile`：通过。
- `cd frontend && mise x node@24 -- pnpm typecheck`：通过。
- `cd frontend && mise x node@24 -- pnpm test:run`：`40 files / 577 tests passed`。
- `cd frontend && VITE_LIFECYCLE_ENABLED=1 mise x node@24 -- pnpm build`：通过。
- `bash macos/build.sh`：生成 `dist/macos/OpinionWorkbench-dev-macOS-arm64.zip` 及 SHA-256 文件；构建平台为 macOS arm64。
- 最终 ZIP 解压启动（不是 `macos/build/app` 原程序）：`unzip -q dist/macos/OpinionWorkbench-dev-macOS-arm64.zip -d "$CHECK_ROOT/含 中文 空格"` 后，`python3 scripts/portable_smoke.py "$CHECK_ROOT/含 中文 空格/OpinionWorkbench/启动.command" --cwd "$CHECK_ROOT/含 中文 空格/OpinionWorkbench"`：`Packaged startup, portable data, HTTP and page-close shutdown passed.`
- macOS ZIP 发行审计：包内 478 个成员，无 `data`、`runtime`、`logs`、`secrets`、`browser`、数据库或日志成员；`BUILD-METADATA.txt` 为 `version=dev`、固定基线 `bf4b6ba964d8fabdcc1a711e6abca46a11d192ef`、`architecture=arm64`。当前本机 SHA-256：`e0e9a2aab7bec809a9ffcf178a3b43cb28d8b3c429d2c066ec9d92fbde515748`。
- 独立临时目录隔离检查：模拟旧 `longtian.sqlite3`、凭据和 Chrome Cookie 后启动新应用，新规则列表为空，旧文件内容未改变；同一场景已有 `test_new_data_root_keeps_synthetic_legacy_material_isolated` 可复现。

## 尚未执行

- Windows x64 原生构建与解压启动需要 Windows runner；工作流和命名契约已更新，但本机未冒充 Windows 验收。
- 未创建标签、未推送提交、未上传或公开 Release 草稿；这些发布动作留给父会话审核。
- 未验证 Finder/Explorer 双击和系统安全提示。
