# 舆情工作台改名验证记录

状态：待用户验收（代码与本机验证及 v0.2.0 GitHub Actions 发行草稿已完成）。

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

## 发布前未执行项（已由下述发布记录更新）

- Windows x64 原生构建与解压启动需要 Windows runner；工作流和命名契约已更新，但本机当时未冒充 Windows 验收。
- 发布前未创建标签、未推送提交、未上传或公开 Release 草稿；这些状态已由下述 v0.2.0 发布执行记录更新。
- 未验证 Finder/Explorer 双击和系统安全提示。

## v0.2.0 发布执行记录（2026-09-12）

当前发布状态：**待用户验收**。草稿保持未公开，未执行 Finder/Explorer 双击或系统安全提示验收。

- 标签 `v0.2.0` 指向提交 `fc2ca91a3ec1b66e7be9e1337f09bee68bfde353`；GitHub Actions 运行：[34704345345](https://github.com/jonathanhu237/opinion-workbench/actions/runs/34704345345)，Windows、macOS、draft 三个作业均成功。
- Release 草稿：[v0.2.0](https://github.com/jonathanhu237/opinion-workbench/releases/tag/untagged-487e9801ff745d8c1af3)，`draft=true`，目标提交为上述 SHA，`published_at=null`。
- 从草稿下载的四个资产存放于临时目录 `/tmp/opinion-workbench-v0.2.0.In3cPo`；资产名称、大小和下载文件 SHA-256：

  | 资产 | 字节数 | 下载文件 SHA-256 |
  | --- | ---: | --- |
  | `OpinionWorkbench-v0.2.0-Windows-x64.zip` | 88,788,755 | `f94a1436abfb9be22bb1b420dd0f5ef9a842ea3655e0ff3b30db7320fc1386d6` |
  | `OpinionWorkbench-v0.2.0-Windows-x64.zip.sha256` | 107 | `04a5fd1dd5a742209897875b3c86a75a85278a387f5f43bccedf24376f9970b1` |
  | `OpinionWorkbench-v0.2.0-macOS-arm64.zip` | 89,513,168 | `4db8822ae69c8a8a678be537e652920b180991fbc3a0a471f9062924638e9c34` |
  | `OpinionWorkbench-v0.2.0-macOS-arm64.zip.sha256` | 106 | `75f68dd167ff0b3d87b847388f8349b30294cf73eaef49a32c434b38cd32fd17` |

- 运行 `python3 scripts/validate_portable_release.py v0.2.0 fc2ca91a3ec1b66e7be9e1337f09bee68bfde353 --assets /tmp/opinion-workbench-v0.2.0.In3cPo`：`Portable assets verified; draft-only upload permitted.`
- 直接调用现有 `audit_archive`：Windows `383` 个成员、元数据 `version=v0.2.0` / `source=fc2ca91a3ec1b66e7be9e1337f09bee68bfde353` / `architecture=x86_64`，macOS `407` 个成员、元数据 `version=v0.2.0` / `source=fc2ca91a3ec1b66e7be9e1337f09bee68bfde353` / `architecture=arm64`；两项均通过。
- 通过现有 `validate_assets`：`VALIDATE_ASSETS: passed`。解压后二进制识别为 Windows PE32+ x86-64 与 macOS Mach-O arm64；未执行真实采集、登录或付费模型调用。

未完成项：需要用户人工检查并决定是否公开 Release；Finder/Explorer 双击、系统安全提示、真实平台采集、登录和付费模型仍未验收。CI 仅有 GitHub Actions 的 Node.js 20 弃用提示，不影响本次成功结论。
