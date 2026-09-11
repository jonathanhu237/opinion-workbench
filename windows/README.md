# Windows ZIP 免安装版

## 给使用者

获取 `Longtian-Windows.zip`，右键选择“全部解压”，打开 `Longtian` 文件夹，
双击 `Longtian.exe`。不要在压缩包预览里运行，也不要单独移走 EXE。
无需安装 Python、Node 或开发工具；支持 Windows 10/11 x64。
程序使用默认浏览器打开本地页面，平台登录和采集需要本机 Google Chrome。
Chrome 缺失时仍可查看设置和历史页面。

数据库、AI 配置、DPAPI 保护的凭据、专用 Chrome 登录目录和诊断日志保存在
解压目录内的 `data\` 文件夹；整目录移动时请连同该文件夹一起移动。
升级时关闭所有应用页面，等待服务退出，将新版解压到新文件夹运行即可保留资料。
不要同时运行不同版本；删除程序目录不会删除用户数据。
凭据受 Windows 用户保护，不能直接通过复制文件夹跨电脑迁移。

`Longtian-Windows-Build-Toolkit.zip` 是维护者构建工具包，**不是可直接运行的免安装版**。

## 给维护者

必须在 Windows x64 上构建；Mac 构建不能代替 Windows EXE 的生成和验收。
工具包不包含运行时数据库、AI 密钥、Chrome 登录资料或日志，不需要 Codex 或插件。

双击 `windows\build.cmd`，或在项目根目录的 Windows PowerShell 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build.ps1 -InstallTools
```

默认只生成 `dist\windows\Longtian-Windows.zip`，不要求 Inno Setup。
`-InstallTools` 在需要时通过 winget 安装 mise，再由根目录 `mise.toml`
准备锁定的 Node.js、pnpm、Python 和 uv。网络、代理和安装确认需要维护者处理。
已准备好工具链时可省略该开关。

构建会安装锁定的依赖、构建静态前端、生成 PyInstaller 完整目录，再压缩为 ZIP。
ZIP 包含主程序、采集辅助程序、内部依赖和使用说明，不包含构建机的用户资料。
采集使用本机 Chrome，不额外下载 Playwright Chromium。
日志位于 `windows\build\logs\`。

可选参数：

- `-Installer`：额外生成 `dist\windows\Longtian-Setup.exe`；仅此模式需要 Inno Setup。
- `-PackageToolkit`：额外生成 `dist\windows\Longtian-Windows-Build-Toolkit.zip`。

例如，同时生成全部产物：

```powershell
.\windows\build.ps1 -InstallTools -Installer -PackageToolkit
```

## Windows 验收清单

1. 在没有 Python、Node、pnpm、源码或 Inno Setup 的干净 Windows 用户环境中，
   解压 ZIP 到含中文和空格的目录，双击 `Longtian.exe`。
2. 确认默认浏览器打开本地页面，刷新页面不停止服务，无需安装向导或管理员权限。
3. 确认缺少 Chrome 的提示；安装 Chrome 后登录平台，重启后登录资料仍在。
4. 保存 AI 配置，检查报告生成、平台人工验证后的显式继续，以及关闭最后一个
   应用页面后约 10 秒退出。
5. 再次打开后，未完成任务显示为已中断，不自动恢复，手动重试可用。升级请完全退出旧版本、备份旧 `data`，把旧 `data` 复制到新版目录后再启动；不要复制正在写入的数据库。旧版 `%LOCALAPPDATA%\LongtianPublicOpinion` 资料需在同一用户退出应用后手工备份复制。
6. 关闭程序并将新版解压到另一目录启动，确认历史内容、报告、配置和登录资料保留。
7. 若生成安装包，另行验收安装、覆盖升级和卸载保留用户资料。

浏览器冻结、网络断开、进程强制结束或系统休眠时，精确十秒的退出体验必须在
目标 Windows 机器实际验收，不能由 Mac 测试结果替代。
