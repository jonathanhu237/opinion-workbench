# 今日头条账号连接链路

## Goal

在现有单人本机“平台账号连接中心”中接入今日头条真实账号连接闭环：用户从 React
页面发起检测，FastAPI 启动受控的 MediaCrawler 今日头条认证子进程，认证子进程只在
`auth` 模式下借用用户当前 Chrome，并以刚加载的今日头条官方页面在线 DOM 状态确认
账号是否可用。未登录或出现官方安全验证时，由用户在可见 Chrome 中人工完成；系统
只报告连接状态，不采集或保存任何内容。

## Confirmed Product Decisions

- 本任务只接入今日头条账号连接，不实现新的关键词搜索、正文、作者、评论、媒体下载、
  定时调度或舆情分析。
- 沿用现有账号中心的用户 Chrome 方案；认证模式不复制 Profile，不把 Cookie、二维码、
  LocalStorage、页面正文、账号身份或认证请求头写入前端、API、SQLite、日志或证据。
- 今日头条普通搜索保持既有隔离设计：每次运行使用全新的标准可见 Chrome
  `BrowserContext`，可选状态复用只经过 `BrowserAuthStateStore`。账号连接所用 CDP
  只存在于 `CRAWLER_TYPE=auth` 分支，两条路径不得互相降级或共享生命周期。
- 二维码、短信、滑块、CAPTCHA 和其他平台安全验证都由用户在今日头条官方可见页面
  人工完成；系统不自动识别、破解、拖动或绕过。
- `connected` 必须来自当前官方页面的一次新鲜、在线、失败关闭的登录状态检查；Cookie、
  状态文件、页面曾经登录过、登录框消失或进程退出都不能单独产生“已连接”。
- 微博、抖音和快手连接行为保持兼容；同一时刻仍只允许一个平台认证任务。
- 今日头条只有在自动化门禁和真实用户 Chrome 正向验收都通过后才从 `coming_soon`
  切换为 `enabled`；小红书继续显示“待接入”。
- 首版状态继续保存在当前 FastAPI 会话内，不为今日头条引入 SQLite 持久化。

## Current Repository Evidence

- `third_party/MediaCrawler/cmd_arg/arg.py:371-417` 当前认证白名单和强制安全覆盖仅支持
  `wb | dy | ks`；今日头条尚不能通过 `--platform toutiao --type auth` 启动。
- `third_party/MediaCrawler/tools/auth.py:47-51` 的强类型认证平台枚举尚无 `toutiao`。
- `third_party/MediaCrawler/media_platform/toutiao/core.py:44-117` 当前只有普通搜索生命周期：
  它明确忽略 CDP、启动全新标准 Chrome、恢复可选白名单 Cookie、在线检查后进入搜索；
  没有认证专用早退分支。
- `third_party/MediaCrawler/media_platform/toutiao/core.py:119-139` 当前配置校验会拒绝
  `auth`，因此需要把搜索约束与认证约束分支化，而不是放宽普通搜索边界。
- `third_party/MediaCrawler/media_platform/toutiao/client.py:78-145` 已有不返回账号身份的
  可见 DOM 登录检查，并能把官方挑战与已登录状态区分；此前真实登录与完整浏览器重启
  验收已经证明该检查在项目专用浏览器路径可用。
- `third_party/MediaCrawler/media_platform/toutiao/login.py:46-139` 已使用官方可见页面、
  有界等待和人工挑战处理，不提取二维码；认证中心可复用这条人工流程，但必须跳过
  Cookie 注入与显式状态持久化。
- `backend/src/longtian_api/services/platform_connections.py:47-52,374-421` 当前可信 worker
  平台为 `wb | dy | ks`，今日头条目录项仍为 `coming_soon`。
- `frontend/src/routes/platform-accounts.tsx:143-205` 的平台行已经按 API 目录通用渲染；
  今日头条接入主要是扩展真实目录、行为测试与工作台四平台准备度，而不是新建页面。

## Requirements

### R1 — Authentication-only MediaCrawler boundary

- `--type auth` 的精确平台白名单扩展为 `wb | dy | ks | toutiao`，继续强制可见借用
  Chrome、loopback CDP、无代理、无 Cookie 参数、无显式认证状态持久化、无数据库/文件
  存储、无关键词/业务 ID、无评论/媒体/词云。
- 今日头条认证流程继续发送版本 1 常量事件：等待浏览器、等待批准、检测中、等待人工
  登录、已连接或未连接；所有事件的 `platform` 必须恒为 `toutiao`。
- 认证模式在任何搜索、正文、作者、评论、媒体、store、数据库或
  `BrowserAuthStateStore` 入口前终止，并以失败哨兵测试证明不可达。
- 正常 `search` 模式必须继续使用全新标准可见 Chrome、独立 Auth/Search Page、可选
  `BrowserAuthStateStore` 和现有单页搜索合同；不得因新增认证模式而进入 CDP。

### R2 — Borrowed Chrome ownership

- 认证模式只连接用户现有 Chrome 与 loopback CDP，不启动标准浏览器、专属 Profile
  或备用浏览器。
- CDP 不可用、用户未批准连接或连接失败时返回稳定的浏览器不可用类别，不得回退到
  普通搜索浏览器。
- 认证任务创建今日头条 Page 后立即登记归属；成功、失败、超时和取消都只关闭本任务
  创建的 Page，不关闭用户原有标签页、BrowserContext、Chrome 或非本任务进程。

### R3 — Fresh online DOM proof

- 认证 Page 必须先新鲜导航到受信的今日头条官方首页，再运行登录状态检查；不得从旧
  标签页、Cookie 文件或本地标记推断结果。
- 登录检查输出应收敛为 `connected | disconnected | inconclusive` 三态：只有稳定账号
  DOM 信号存在且登录入口缺失时为 `connected`；明确匿名页为 `disconnected`；挑战、
  导航失败、来源不受信、选择器矛盾或结构漂移为 `inconclusive`。
- 三态检查只返回分类，不返回账号昵称、头像、用户 ID、页面文本或原始 DOM。
- 初次检查非 `connected` 时进入人工登录；人工完成或等待结束后必须重新执行同一在线
  检查。复检非 `connected` 一律不得发送成功事件。
- 自动化覆盖正向、匿名、挑战和结构漂移；产品目录启用前还必须在真实已登录用户
  Chrome 中观察到正向结果。无法稳定证明时保持 `coming_soon`。

### R4 — Manual official login

- 未登录时只打开/保留今日头条官方可见登录界面，允许用户选择页面提供的扫码、手机
  或其他官方方式。
- 认证模式不得注入 Cookie、提取或转发二维码、读取用户输入、检查挑战细节或自动处理
  滑块/CAPTCHA。
- 人工等待有界；官方挑战期间允许低频重复普通登录状态检查，但不得刷新、重新导航、
  操作挑战或绕过。
- 只有已知的页面导航竞态可视为一次不确定检查后继续等待；其他 Playwright 错误失败
  关闭且不得输出可能包含页面或凭据的异常细节。

### R5 — FastAPI orchestration and protocol

- 后端可信认证平台扩展为精确的 `wb | dy | ks | toutiao`，仍从固定参数向量和受信平台
  映射构造 worker 命令，不使用 shell 或用户提供的任意平台字符串。
- 每个 attempt 只接受与当前平台完全一致的事件；四个平台共 12 个有向跨平台组合均
  必须失败关闭，不回显原始子进程行，也不改变任何错误平台的状态。
- 今日头条复用现有 202 启动、全局单任务锁、轮询、状态映射、超时、取消、进程组清理
  和安全错误结构。
- 只有 MediaCrawler 正向验收通过后，今日头条目录才改为
  `enabled/not_checked`；否则保持 `coming_soon` 且 POST 返回 409。

### R6 — React connection center

- 今日头条启用后提供与微博、抖音、快手一致的“检测连接/重新检测”操作，复用现有
  TanStack Query mutation、轮询、重复操作禁用、状态徽标和 live-region 指引。
- `action_required` 时明确提示用户在已打开的今日头条官方 Chrome 页面完成人工登录或
  安全验证，不暗示系统会自动通过挑战。
- 平台页展示四个可检测平台和一个待接入平台；工作台从 API 动态计算
  `0..4 / 4` 可用平台准备度，不新增今日头条专用组件或硬编码平台组合。
- 保持现有 shadcn 组件、键盘操作、可见焦点、移动端 44 px 操作目标和响应式无横向
  溢出要求。

### R7 — Real acceptance and evidence

- 真实验收前只记录一个非敏感的既有 Chrome 标签页存在/数量信号。
- 优先验证已登录快速路径；否则由用户在今日头条官方页面完成人工登录或挑战。
- 真实运行必须证明 MediaCrawler 在线检查与 React 状态都达到 `connected`，worker
  正常结束，且没有搜索、存储或显式认证状态写入。
- 运行结束后验证 Chrome 与全部既有标签页存活、本任务 Page 已清理、监听仍只在
  loopback；证据只记录常量阶段、终态、时间和资源数量。

## Acceptance Criteria

- [ ] `uv run --frozen ... main.py --platform toutiao --type auth ...` 借用现有 Chrome，
      发出合法 `toutiao` 事件，并只在新鲜在线 DOM 证明成功后以连接退出码结束。
- [ ] 未登录时，用户可以在官方可见页面人工扫码/使用手机/处理挑战；系统不提取
      二维码、不读取输入、不注入 Cookie，也不自动处理安全验证。
- [ ] Cookie、状态文件、旧页面状态或模糊 DOM 存在时均不能单独产生 `connected`；
      挑战和结构漂移保持失败关闭。
- [ ] 认证模式测试哨兵证明 search/detail/creator/comment/media/store/database 和
      `BrowserAuthStateStore` 均不可达；普通 Toutiao search 的隔离浏览器合同回归通过。
- [ ] CDP 失败、用户未批准、在线结果不明确、人工超时、取消、子进程协议错误和全部
      12 个跨平台事件组合都安全失败，不影响用户 Chrome。
- [ ] `GET /api/v1/platform-connections` 仍按五平台固定顺序返回；正向门禁通过后
      `wb | dy | ks | toutiao` 为 `enabled`，只有 `xhs` 为 `coming_soon`。
- [ ] React 能启动今日头条 attempt、轮询到终态、显示平台化人工指引，并动态展示
      `0..4 / 4` 的可用平台准备度。
- [ ] MediaCrawler 定向/维护测试、FastAPI 测试、React 行为测试、静态检查和生产构建
      全部通过。
- [ ] 真实用户 Chrome 验收达到在线证明的 `connected`，既有标签页全部存活，任务 Page
      正确清理，且证据不含 Cookie、二维码、账号身份、Profile 路径或页面内容。

## Out of Scope

- 修改或扩展今日头条关键词搜索、正文、详情、作者、评论、媒体下载或存储模型。
- 自动化滑块、CAPTCHA、短信、扫码或其他平台安全验证。
- Cookie 导入导出、账号身份展示、二维码转发、专属 Profile 或 SQLite 连接状态持久化。
- 小红书账号连接、产品登录/权限系统、定时采集、AI 分类和预警通知。
- 把账号连接成功解释为今日头条搜索必然长期可用或零风控。

## Risks and Rollout Gate

- 今日头条 DOM 结构可能变化。实现必须先证明已登录、明确匿名、挑战和结构漂移四类
  结果；真实已登录用户 Chrome 的正向结果未通过前，目录继续保持 `coming_soon`。
- 借用 Chrome 与普通搜索的项目专用状态是两套独立认证来源；账号中心检测成功不自动
  写入 `BrowserAuthStateStore`，也不改变普通搜索的 Cookie 状态。
- 官方页面可能要求不同挑战；只能等待用户在总超时内人工完成，不能以自动化扩大范围。

## Blocking Open Questions

None.
