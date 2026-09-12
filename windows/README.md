# Windows ZIP 免安装版

## 给使用者

获取 `OpinionWorkbench-Windows.zip`，右键选择“全部解压”，打开 `OpinionWorkbench` 文件夹，
双击 `OpinionWorkbench.exe`。不要在压缩包预览里运行，也不要单独移走 EXE。
无需安装 Python、Node 或开发工具；支持 Windows 10/11 x64。
程序使用默认浏览器打开本地页面，平台登录和采集需要本机 Google Chrome。
Chrome 缺失时仍可查看设置和历史页面。

数据库、AI 配置、DPAPI 保护的凭据、专用 Chrome 登录目录和诊断日志保存在
解压目录内的 `data\` 文件夹；整目录移动时请连同该文件夹一起移动。
本次改名版本是全新空白切换：首次启动会在新版目录创建空白 `data\`，不要从旧产品或旧版本
复制、导入旧 `data\`，也不要复用旧凭据或浏览器登录资料。请在旧应用及专用浏览器完全停止
后，把旧程序目录（含其中的 `data\`）单独保留或备份；删除已经使用过的便携程序目录会删除
其内嵌的用户数据。不要同时运行不同版本。
未来若同一产品的某个版本明确标注为兼容升级，才按该版本说明在完全退出并备份后迁移资料；
这不适用于本次改名切换。凭据受 Windows 用户保护，不能直接通过复制文件夹跨电脑迁移。

`OpinionWorkbench-Windows-Build-Toolkit.zip` 是维护者构建工具包，**不是可直接运行的免安装版**。

## 给维护者

必须在 Windows x64 上构建；Mac 构建不能代替 Windows EXE 的生成和验收。
工具包不包含运行时数据库、AI 密钥、Chrome 登录资料或日志，不需要 Codex 或插件。

双击 `windows\build.cmd`，或在项目根目录的 Windows PowerShell 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build.ps1 -InstallTools
```

默认只生成 `dist\windows\OpinionWorkbench-Windows.zip`，不要求 Inno Setup。
`-InstallTools` 在需要时通过 winget 安装 mise，再由根目录 `mise.toml`
准备锁定的 Node.js、pnpm、Python 和 uv。网络、代理和安装确认需要维护者处理。
已准备好工具链时可省略该开关。

构建会安装锁定的依赖、构建静态前端、生成 PyInstaller 完整目录，再压缩为 ZIP。
ZIP 包含主程序、采集辅助程序、内部依赖和使用说明，不包含构建机的用户资料。
采集使用本机 Chrome，不额外下载 Playwright Chromium。
日志位于 `windows\build\logs\`。

可选参数：

- `-Installer`：额外生成 `dist\windows\OpinionWorkbench-Setup.exe`；仅此模式需要 Inno Setup。
- `-PackageToolkit`：额外生成 `dist\windows\OpinionWorkbench-Windows-Build-Toolkit.zip`。

例如，同时生成全部产物：

```powershell
.\windows\build.ps1 -InstallTools -Installer -PackageToolkit
```

## Windows 验收清单

1. 在没有 Python、Node、pnpm、源码或 Inno Setup 的干净 Windows 用户环境中，
   解压 ZIP 到含中文和空格的目录，双击 `OpinionWorkbench.exe`。
2. 确认默认浏览器打开本地页面，刷新页面不停止服务，无需安装向导或管理员权限。
3. 确认缺少 Chrome 的提示；安装 Chrome 后登录平台，重启后登录资料仍在。
4. 保存 AI 配置，检查报告生成、平台人工验证后的显式继续，以及关闭最后一个
   应用页面后约 10 秒退出。
5. 再次打开后，未完成任务显示为已中断，不自动恢复，手动重试可用。本次改名版本必须以空白状态
   启动：不要把旧版本的 `data` 复制或导入新版，也不要复制正在写入的数据库；旧 `data` 请在同一
   Windows 用户退出相关应用后单独保留或备份。
6. 关闭程序并将新版解压到另一目录启动，确认新目录创建空白数据库、规则列表为空且不会读取旧资料。
7. 删除已经运行过的便携程序目录，确认其内嵌 `data` 也会随目录删除；这不是旧资料保留方式。
8. 若生成安装包，另行验收安装、覆盖升级和卸载保留用户资料；该验收属于未来同产品升级场景，
   不代表本次改名版本导入旧资料。

浏览器冻结、网络断开、进程强制结束或系统休眠时，精确十秒的退出体验必须在
目标 Windows 机器实际验收，不能由 Mac 测试结果替代。
