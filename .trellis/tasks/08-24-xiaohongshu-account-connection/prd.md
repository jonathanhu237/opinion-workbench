# 小红书账号连接链路

## Goal

在现有单人本机“平台账号连接中心”中接入国内小红书真实账号连接闭环：用户从 React
页面发起检测，FastAPI 启动受控的 MediaCrawler 小红书认证子进程，子进程只在
`auth` 模式下借用用户当前 Chrome。未登录或遇到官方安全验证时，由用户在可见的小红书
官方页面中人工完成；系统只有在新的小红书官方在线账号检查通过后才显示“已连接”，且
整个流程不采集或保存笔记内容。

## Confirmed Product Decisions

- JD 的首期范围是微博、抖音、快手、小红书、今日头条五个平台；前四个连接链路已经
  交付，小红书是最后一个仍显示 `coming_soon` 的平台。
- 沿用用户已经确认的账号中心方案：认证时复用用户现有的可见 Chrome，而不是启动应用
  专属 Profile；用户本人处理二维码、短信、滑块、CAPTCHA 和其他官方安全验证。
- 认证自动化不得破解、模拟拖动或绕过平台挑战，也不得读取用户输入、提取或转发二维码。
- 本任务只证明当前账号连接可用，不承诺小红书关键词采集的长期稳定性、全量覆盖或零风控。
- 账号连接状态继续保存在当前 FastAPI 会话内；不把 Cookie、LocalStorage、二维码、
  账号身份或认证请求头写入 SQLite、前端、日志或任务证据。
- 国内站 `https://www.xiaohongshu.com` 是首版唯一目标；RedNote 国际站、多账号、手机号
  自动填充和手工 Cookie 导入均不在本任务范围内。

## Current Repository Evidence

- 已归档的底层验证证明：国内小红书二维码登录后，
  `XiaoHongShuClient.pong()` 可以从官方 `/api/sns/web/v1/user/selfinfo` 得到有效的在线
  登录结论；同时证明原生隔离 Profile 单独重启不足以稳定复用状态，显式状态存储才通过
  两次启动验收。该验证使用应用启动的隔离 Chrome，不等于当前账号中心的借用 Chrome
  路径已经接入（`08-24-verify-mediacrawler-xhs-login/research/validation-results.md`）。
- XHS 普通 crawler 已能连接 CDP、登记任务 Page、创建 HTTP client、执行首次与登录后二次
  `pong()`，并在服务端检查失败时阻止采集；但没有 `auth` 专用早退和事件协议分支
  （`third_party/MediaCrawler/media_platform/xhs/core.py:71-153`）。
- `pong()` 只有在官方自查响应 `data.result.success` 为真时才返回真；异常失败关闭
  （`third_party/MediaCrawler/media_platform/xhs/client.py:272-304`）。
- 当前 XHS 二维码流程会读取二维码图片并调用终端展示工具，不能直接用于账号中心；其 UI
  和 `web_session` 判断也只能作为人工操作完成的提示，不能作为产品“已连接”的最终证明
  （`third_party/MediaCrawler/media_platform/xhs/login.py:51-85,167-211`）。
- MediaCrawler `auth` 白名单、固定事件平台枚举和 FastAPI worker 平台联合类型均只包含
  `wb | dy | ks | toutiao`，尚不接受 `xhs`
  （`third_party/MediaCrawler/cmd_arg/arg.py:371-418`、
  `third_party/MediaCrawler/tools/auth.py:47-51`、
  `backend/src/longtian_api/services/platform_connections.py:47-53`）。
- FastAPI 目录中小红书仍为 `coming_soon`；React 平台行和工作台准备度已经按 API 数据
  通用渲染，不需要小红书专用页面
  （`backend/src/longtian_api/services/platform_connections.py:375-422`、
  `frontend/src/routes/platform-accounts.tsx:143-205`、
  `frontend/src/routes/workbench.tsx:67-93`）。

## Requirements

### R1 — Authentication-only MediaCrawler boundary

- `--type auth` 的精确平台白名单扩展为 `wb | dy | ks | xhs | toutiao`；继续强制可见的
  借用 Chrome、loopback CDP、无代理、无 Cookie 参数、无显式认证状态持久化、无数据库/
  文件存储、无关键词/业务 ID、无评论/媒体/词云。
- 小红书认证流程使用现有版本 1 常量事件：等待浏览器、等待批准、检测中、等待人工登录、
  已连接或未连接；所有事件的 `platform` 必须恒为 `xhs`。
- 认证模式必须在 search/detail/creator/comment/media/store/database 和
  `BrowserAuthStateStore` 入口前终止，并用失败哨兵测试证明这些入口不可达。
- 普通小红书 search/detail/creator、隔离 Profile 和 `BrowserAuthStateStore` 行为必须保持
  兼容，不得因新增账号中心认证分支而改用借用 Chrome。

### R2 — Borrowed Chrome ownership

- 认证模式只连接用户现有 Chrome 与 loopback CDP，不启动标准浏览器、专属 Profile 或
  备用浏览器。
- CDP 不可用、用户未批准连接或连接失败时返回稳定的浏览器不可用类别，不得回退到普通
  crawler 的浏览器启动路径。
- 认证任务创建小红书 Page 后立即登记归属；成功、失败、超时和取消都只关闭本任务创建的
  Page，不关闭用户原有标签页、BrowserContext、Chrome 或非本任务进程。

### R3 — Authoritative online proof

- 认证 Page 必须新鲜导航到受信的国内小红书官方首页，再从当前 BrowserContext 更新 client
  Cookie 并执行官方在线 `pong()`；不得从旧页面、Cookie 存在、Profile 或本地标记推断结果。
- `pong()` 对产品层只输出 `connected | disconnected` 分类，不输出账号昵称、头像、用户
  ID、原始响应或页面正文；挑战、网络失败、响应漂移和不明确状态一律失败关闭。
- 初次检查未连接时进入人工登录；人工操作产生 UI/Cookie 变化后必须再次更新 client Cookie
  并执行同一在线检查。复检未通过时不得发送成功事件。
- UI 中“我”入口、二维码消失、登录框变化或 `web_session` 变化只能唤醒在线复检，不能单独
  产生 `connected`。

### R4 — Manual official login

- 未登录时只打开或保留小红书官方可见登录界面，允许用户在页面内使用官方扫码、手机号或
  其他当前提供的方式。
- 认证模式不得调用二维码图片提取/展示工具，不得填手机号、验证码或密码，不得注入 Cookie，
  也不得识别、点击、拖动、刷新或绕过挑战。
- 系统可以点击普通的官方“登录”入口以展示登录面板，并以有界、低频方式等待用户完成；
  页面已显示面板时不得重复操作。
- 人工操作完成后只有在线 `pong()` 为真才算成功；超时、页面漂移或挑战未完成时安全返回
  未连接，并给出“请在 Chrome 中完成登录或验证”的现有平台化指引。

### R5 — FastAPI orchestration and protocol

- 后端可信认证平台扩展为精确的 `wb | dy | ks | xhs | toutiao`，继续从固定参数向量和受信
  映射构造 worker 命令，不接受任意平台字符串或 shell 拼接。
- 每个 attempt 只接受与当前平台完全一致的事件；五个平台共 20 个有向跨平台错误组合均须
  失败关闭，不回显原始子进程行，也不改变错误平台的状态。
- 小红书复用现有 202 启动、全局单任务锁、轮询、状态映射、超时、取消、进程组清理和安全
  错误结构。
- 只有 MediaCrawler 自动化门禁和真实用户 Chrome 正向验收通过后，小红书目录才从
  `coming_soon` 改为 `enabled/not_checked`；否则继续返回 409。

### R6 — React connection center

- 小红书启用后提供与其他平台一致的“检测连接/重新检测”操作，复用现有 TanStack Query
  mutation、轮询、重复操作禁用、状态徽标和 live-region 指引。
- `action_required` 时明确提示用户在已打开的小红书官方 Chrome 页面中人工登录或完成安全
  验证，不暗示系统会自动处理挑战。
- 平台页展示五个可检测平台，不再显示待接入平台；工作台从 API 动态显示 `0..5 / 5`，不得
  新增小红书专用组件或硬编码五平台组合。
- 保持现有 shadcn 组件、键盘操作、可见焦点、移动端 44 px 操作目标和响应式无横向溢出。

### R7 — Real acceptance and evidence

- 真实验收前只记录非敏感的既有 Chrome 标签页数量/存活哨兵。
- 优先验证已登录快速路径；若未登录，用户在小红书官方页面中人工完成登录和必要挑战。
- 真实运行必须证明 MediaCrawler 在线 `pong()`、FastAPI 和 React 都达到 `connected`，worker
  正常结束，且没有采集、存储或显式认证状态写入。
- 运行结束后验证 Chrome 与全部既有标签页存活、本任务 Page 已清理、监听仍只在 loopback；
  证据只记录常量阶段、终态、时间和资源数量。

## Acceptance Criteria

- [x] `uv run --frozen ... main.py --platform xhs --type auth ...` 借用用户现有 Chrome，发出
      合法 `xhs` 事件，并只在新的官方在线 `pong()` 成功后以连接退出码结束。
- [x] 未登录时，用户可以在小红书官方可见页面人工扫码或处理挑战；系统不提取二维码、不读取
      输入、不注入 Cookie，也不自动处理安全验证。
- [x] Cookie/UI/Profile/旧页面状态不能单独产生 `connected`；网络失败、挑战和结构漂移保持
      失败关闭。
- [x] 认证模式哨兵证明 search/detail/creator/comment/media/store/database 与
      `BrowserAuthStateStore` 不可达；普通 XHS 认证状态与 crawler 回归通过。
- [x] CDP 失败、用户未批准、人工超时、取消、子进程协议错误和全部 20 个跨平台事件组合安全
      失败，不影响用户 Chrome。
- [x] `GET /api/v1/platform-connections` 仍按五平台固定顺序返回，门禁通过后五个平台均为
      `enabled/not_checked`。
- [x] React 能启动小红书 attempt、轮询到终态、显示人工指引，并动态展示 `0..5 / 5` 可用平台
      准备度。
- [x] MediaCrawler 定向/维护测试、FastAPI 测试、React 行为测试、静态检查和生产构建全部通过。
- [x] 真实用户 Chrome 验收达到在线证明的 `connected`，既有标签页全部存活，任务 Page 正确
      清理，且证据不含 Cookie、二维码、账号身份、Profile 路径或页面内容。

## Out of Scope

- 小红书关键词搜索、笔记详情、作者、评论、媒体下载、结果入库和长期采集稳定性。
- 自动化滑块、CAPTCHA、短信、扫码或其他平台安全验证。
- Cookie 导入导出、账号身份展示、二维码转发、专属 Profile、SQLite 连接状态持久化。
- RedNote 国际站、多账号、产品登录/权限系统、定时采集、AI 分类和预警通知。
- 把账号连接成功解释为小红书采集长期可用、全量覆盖或零风控。

## Risks and Rollout Gate

- 小红书风控和页面结构变化较快。真实已登录用户 Chrome 的正向 `pong()` 未通过前，产品目录
  必须继续保持 `coming_soon`。
- 现有普通二维码实现会提取图片，认证中心必须走单独的可见页面等待路径；任何回退到旧二维码
  展示函数都视为阻断交付的安全回归。
- 借用 Chrome 与普通 crawler 的显式状态存储是两套认证来源；账号中心检测成功不写入
  `BrowserAuthStateStore`，也不改变后续普通采集的状态。
