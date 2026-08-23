# 验证 MediaCrawler 小红书登录与登录态复用

## Goal

验证 MediaCrawler 在本机隔离 Chrome 中能否完成小红书首次二维码登录、人工安全验证和浏览器完全退出后的登录态复用；若原生 profile 不能稳定免扫码，则最小接入现有 `BrowserAuthStateStore`，为后续本地单用户舆情工具提供可重复使用的小红书平台连接能力。

## Background

- 用户已确认小红书可以进入本轮验证，但既有约束继续有效：非商业、低频、不自动破解或绕过滑块/CAPTCHA。
- 小红书 crawler 当前使用国内站 `https://www.xiaohongshu.com` 作为首页和 Cookie URL 边界，并在页面打开后创建 HTTP client（`third_party/MediaCrawler/media_platform/xhs/core.py:62`、`:100`、`:104`）。
- 首次 `XiaoHongShuClient.pong()` 通过 `/api/sns/web/v1/user/selfinfo` 的成功字段判断服务端登录状态（`third_party/MediaCrawler/media_platform/xhs/client.py:272`、`:286`）。
- 未登录时，原生流程显示二维码，并通过“我”入口或 `web_session` 变化检测扫码结果；页面出现“请通过验证”时只提示人工处理，不存在自动拖动或破解动作（`third_party/MediaCrawler/media_platform/xhs/login.py:51`、`:71`、`:167`）。
- 当前 core 在原生登录后只更新内存 client Cookie，没有再次执行服务端 `pong()`，也没有显式恢复或保存通用认证状态（`third_party/MediaCrawler/media_platform/xhs/core.py:103`-`:117`）。
- `SAVE_LOGIN_STATE=True` 时 CDP 已使用按平台隔离的 Chrome profile，但该 profile 是否足以跨浏览器进程复用小红书登录尚无真实证据（`third_party/MediaCrawler/tools/cdp_browser.py:250`-`:271`）。
- 微博和快手已经验证通用 `BrowserAuthStateStore` 的平台/URL 隔离、安全回退、原子 `0600` 写入和两次启动验收；抖音已经验证“安全挑战只允许人工处理”的边界。

## Requirements

- 使用国内小红书 `xhs`、`qrcode`、可见的独立 Chrome 和任务专用临时用户数据目录；必须设置 `CDP_CONNECT_EXISTING=False`，不得连接用户日常 Chrome。
- 使用不会进入 search/detail/creator 分支的 `auth_validation` 模式，只运行认证链路，不采集笔记、作者、评论或媒体。
- 第一轮验证首页与二维码可正常打开；若出现官方滑块或 CAPTCHA，只允许用户在可见浏览器中人工完成，自动化只等待并检查结果。
- 原生扫码完成后更新 client Cookie，并在清理浏览器前额外调用一次 `XiaoHongShuClient.pong()`，只有服务端检查为真才把第一轮视为登录成功。
- 完全关闭第一轮 Chrome/CDP 后，以同一隔离 profile 第二次启动；首次 `pong()` 必须直接通过，且不得再次进入二维码登录。
- 先执行不修改 XHS 源码的原生两次启动基线；只有第二轮复用失败时，才在同一任务内最小接入现有 `BrowserAuthStateStore`。
- 条件接线时使用 `platform="xhs"`、`urls=self.cookie_urls`，恢复必须发生在 client 创建和首次 `pong()` 之前；登录后必须更新 client、再次 `pong()`，且仅在确认有效时保存。
- 缺失、损坏、过期或不匹配的状态文件必须安全回退原生二维码流程；`SAVE_LOGIN_STATE=False` 时不得创建 store 或读写状态文件。
- 若真实页面变化导致二维码选择器或人工挑战等待不可用，允许做有真实证据支持的最小登录健壮性修正；不得扩展到挑战识别、模拟拖动、自动刷新或绕过。
- 运行证据只记录状态、顺序、数量和文件元数据，不记录 Cookie/LocalStorage 名称和值、二维码内容、认证请求头或完整页面内容。
- 任务产物和敏感运行数据不得进入 Git；不得覆盖或删除项目既有 `browser_data/`、`db_data/`、`logs/`。

## Key Decisions

- 本轮只验证国内版小红书和二维码登录，不验证手机号、手工 Cookie 或 RedNote 国际站。
- 原生 profile 优先，显式 Cookie 状态存储仅作为基线失败后的条件式补救，避免没有证据就扩大派生改动。
- `XiaoHongShuClient.pong()` 是登录有效性的最终权威；页面入口出现、`web_session` 变化、profile 或状态文件存在都不能单独判定成功。
- 继续沿用用户已接受的本机单用户风险模型：若必须显式保存认证 Cookie，只写入 Git 忽略目录中的本地明文 `0600` 文件；系统钥匙串和加密存储延后。
- 官方安全验证可以人工完成；重复出现或人工超时只允许安全结束并报告，不允许自动绕过。
- 任务保持单任务结构：原生基线、条件式最小接线和真实复测共同组成一条可独立验收的 XHS 认证链路。

## Acceptance Criteria

- [x] 可见的独立 Chrome 和国内小红书首页正常打开，原生二维码能够展示，用户完成扫码及必要的人工官方验证。
- [x] 第一轮更新 Cookie 后的服务端 `XiaoHongShuClient.pong()` 为真，`auth_validation` 正常结束且未执行内容采集。
- [x] Chrome/CDP 完全退出后，第二轮首次服务端 `pong()` 直接为真且不展示二维码；若原生 profile 失败，则完成条件式最小接线后重新验证至通过。
- [x] 若发生条件接线，自动化测试证明 restore → client → first pong → login（按需）→ update cookies → second pong → save（仅有效）的顺序，且关闭开关时无认证状态 I/O。
- [x] 平台安全挑战未被自动操作或绕过；日志、测试输出和任务证据不包含敏感认证材料。
- [x] 临时配置恢复，Chrome/CDP 退出，调试端口关闭，本任务创建的敏感临时目录在确认无进程占用后永久删除。
- [x] 任何 MediaCrawler 源码修改均限定在 XHS 登录/认证编排及对应测试；相关自动化与全量回归通过，父仓库既有运行目录保持不变。

## Out of Scope

- 小红书关键词搜索、笔记详情、作者、评论、媒体下载和长期采集稳定性。
- 自动识别、拖动、刷新、重试或以其他方式绕过小红书安全验证。
- React/FastAPI 平台连接页面、定时任务、SQLite 舆情结果表、AI 分级和通知。
- 手机号登录、手工 Cookie 登录、RedNote 国际站和多账号管理。
- 登录态加密、系统钥匙串和跨设备同步。

## Technical Notes

- 现有 XHS 与通用认证状态的无浏览器定向基线为 29 passed；`xhshow` 依赖可正常导入。真实网页、二维码和登录态复用仍需实施阶段的可见浏览器验证。
- 本任务包含真实账号回归和条件式第三方派生仓库修改，按复杂任务管理；技术设计和执行步骤见 `design.md`、`implement.md`。
