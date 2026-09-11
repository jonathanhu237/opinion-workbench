# Review 1

Baseline: cda5fa20bfe4a5e4da39b180c0be43b8e7359651 + all current working-tree/untracked implementation files.
Status: changes-requested

## Standards

1. **[P2] S1 — 构建工具没有按仓库约定由 mise 管理。** Windows 构建脚本目前优先 winget 安装 Node/uv/Git，只有已有 mise 时才用于 Node；用户的 AGENTS 指令要求新增开发工具使用 mise。请通过 mise 管理可支持的 Node、pnpm、Python/uv，锁定项目需要的版本；只有 mise 无法提供的安装器组件采用明确说明的系统安装方式。

## Spec

1. **[P1] R1 — 干净 Windows 的构建入口不能完成依赖准备。** 构建脚本安装后不刷新 PATH，pnpm 只在存在 corepack 时尝试启用，ISCC 只从 PATH 查找（常规 Inno Setup 安装并不保证提供 PATH），因此用户照入口执行仍会缺少工具。双击 build.cmd 也未默认启用依赖准备。请补齐一键入口及工具定位、精确 x64 检查和可重试错误；不要仅让用户自己配 PATH。验证一份干净工具包的第一轮及重复执行逻辑。
2. **[P1] R2 — PyInstaller 仍从错误工作目录执行。** build.ps1 的最终 uv run 调用没有传 backend WorkingDirectory，Invoke-Tool 默认在无 pyproject 的根目录运行。此前手工在 backend 成功的构建并不能证明该脚本可行。显式在后端项目环境执行，并固定 Python 3.11（工具包未含后端 .python-version）；对实际命令/工作目录做测试。
3. **[P1] R3 — 微博解析子进程不能沿用无控制台 exe。** 当前冻结模式复用 console=False 的主 exe，但 gallery_worker 使用 stdin/stdout JSON 协议。Windows PyInstaller 无控制台模式的这些流为 None；且子进程环境只有 LANG，丢失 Windows 必需的 SystemRoot 等。提供适合管道协议的 worker（例如隐藏启动的 console worker）并保留最小必需系统环境；通过打包后的 worker 协议验证。依据：https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html 与 Python subprocess 官方文档。
4. **[P1] R4 — 启动失败不可见，首次页面未连上时后台永不退出。** launcher.run 仅写日志返回，console=False 用户看不到错误；webbrowser.open 返回成功但网页脚本没有连上 WebSocket 时没有任何租约/超时，关闭网页也不会触发 release。增加用户可见的启动失败提示、首个页面就绪超时和可靠进程清理；检查端口被占、页面未加载、日志目录错误及无控制台运行。已有无控制台日志修复需有回归测试。
5. **[P2] R5 — 生命周期 WebSocket 接受任意网站来源。** TestClient 以 Origin=https://example.com、Host=127.0.0.1:8765 连接会收到 ready。其他网页可维持租约，使关闭系统页面不退出。新增入口需校验本地同源 Host/Origin，并测试拒绝外站来源。
6. **[P2] R6 — macOS 专用浏览器路径检查被削弱。** 原来对 profile 及所有父目录的 symlink 检查移入 Windows 分支；Mac 现在只检查末级 profile，允许 runtime/browser 等父级跳到其他资料位置。恢复现有 Mac 边界，并用 lstat 检测 Windows reparse points，避免跟随链接后检查目标属性。
7. **[P2] R7 — 新行为尚无约定的高层自动验收覆盖。** 新增测试目前仅覆盖路径投影和生命周期对象方法，没有启动入口、静态页面/API、重连、真正的任务中断/重开，以及 Windows 构建命令契约。补充少量通过应用入口的集成测试，复用现有临时数据库及浏览器/AI替身；前端打包开关下的 WebSocket 行为应有回归。顺便修正 README 产物目录与脚本输出不一致，并排除生成目录进入源码清单。

## Evidence / limits

- Parent 独立相关后端回归：66 passed。
- Parent 实际 uvicorn + 临时空白库 + WebSocket 探测：就绪成功，最后连接关闭后 launcher 退出 0。
- PowerShell 两个脚本语法通过，工具包约 1 MB、版本文件存在、无 pycache。
- 冻结无控制台环境原先存在 uvicorn formatter 失败，已见 log_config=None 修复，需锁定测试。
- 原始提交隔离副本复现全部 31 后端既有失败；完整前端基线为相同的 3 failed / 567 passed。
- Windows 安装及真实采集仍待用户执行，不作为本轮可在 Mac 声称通过的项目。

## Summary

Standards: 1 finding (P2). Spec: 7 findings (worst P1). No commits; return to same implementer for first formal fix attempt.
