# 改名复修记录 — Fix 1

基线：`bf4b6ba964d8fabdcc1a711e6abca46a11d192ef`。本次针对 `review-1.md` 的 R1–R4 均为第一次修复尝试；未提交、未推送、未创建 Release。

## R1

- 删除改名前遗留的 `backend/.venv`，在新目录执行 `cd backend && uv sync --locked` 重建 Python 3.11 环境。
- 重建后的 `.venv/bin/fastapi` shebang 指向当前 `opinion-workbench` 路径；扫描 `.venv/bin` 可执行入口未发现旧绝对路径。
- `uv run fastapi dev --help`、`uv run pytest -q tests/test_health.py`（1 passed）和直接 `.venv/bin/fastapi --help` 通过；不依赖 `PYTHONPATH` 或旧路径兼容。

## R2

- 同步根 README、`windows/README.md`、`windows/portable-readme.txt`、`macos/README.txt` 和 portable Release body。
- 明确本次改名是空白切换，不复制或导入旧 `data/`、凭据或浏览器登录资料；旧目录需在停止后另行保留，删除已使用便携目录会删除其内嵌数据。
- 未来同产品兼容升级仅在明确标注时适用，不作为本次切换的导入指引。

## R3

- 源代码运行根测试在 Windows 跳过 macOS/Linux 的 `runtime/opinion-workbench` 断言。
- 新增隔离平台 seam 测试 Windows 默认 `LOCALAPPDATA/OpinionWorkbench` 分支，不修改生产 Windows 路径行为。

## R4

- 新增空白数据库中性默认提示词、无规则测试。
- 新增跨两个合成采集批次显式选材的 API/执行测试，验证总结提示词和报告提示词分别进入各自阶段，报告系统指令不追加采集对象。
- 新增合成旧数据库、凭据和 Chrome Cookie 的保留/新数据根隔离测试。
- 重建最终 macOS ZIP，解压到含中文和空格的临时目录，以解压副本的 `启动.command`（不是 `macos/build/app` 原程序）执行 portable smoke：启动、worker、HTTP、空白数据库和页面关闭退出均通过。

## 结果

- 后端完整套件：`1294 passed, 2 skipped`。
- 后端 Ruff 检查与格式检查通过；前端 typecheck、format、lint、577 tests 通过；macOS arm64 构建及最终 ZIP 启动检查通过。
- Windows x64 原生构建/解压启动、Finder/Explorer 双击和系统安全提示仍需对应环境或人工验收，未在本机冒充完成。
