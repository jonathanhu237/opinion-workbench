Status: open

# ZIP 免安装交付

用户要求：默认提供解压后双击即可启动的 Windows ZIP，而不是安装向导或源码构建工具包。

## 已实现

- `windows/build.ps1` 默认输出 `dist/windows/Longtian-Windows.zip`。
- ZIP 包含完整 PyInstaller Longtian 目录及使用说明；打包前检查主程序、worker 和前端入口。
- Inno Setup 的检查、安装及安装包生成仅在 `-Installer` 时启用。
- 工具包白名单加入免安装版说明，更新 Windows 使用及验收文档。
- 保持现有 Windows 用户数据目录，不将构建机资料放入 ZIP。

## 验证

本机 Mac：`backend/.venv/bin/python -m pytest tests/test_windows_delivery_contract.py -k 'not pinned_mise_runtime' tests/test_application_paths.py -q`（在 backend 目录运行时使用 `.venv/bin/python`）。
结果：9 passed，2 skipped（无 PowerShell），1 deselected（工具链下载检查）。

## 待完成

在 Windows x64 上生成实际 ZIP，按 `windows/README.md` 验收；当前没有生成或验证 Windows 可执行产物。
