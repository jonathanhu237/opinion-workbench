# 抖音账号连接链路

## Goal

让单人本机舆情系统能够在“平台账号”页面检测抖音账号是否仍可在用户现有 Chrome
中使用；未登录或遇到官方安全验证时，把可见页面交给用户人工处理，只有通过新的在线
登录检查后才显示“已连接”。

## Background and confirmed facts

- 微博和快手已经通过同一套 React → FastAPI → MediaCrawler `auth` 子进程链路交付。
- 用户此前明确选择复用本机现有 Chrome，而不是创建应用专属 Profile。
- 用户此前接受所有二维码、短信、滑块和安全验证均由本人在官方可见页面完成。
- 抖音现有 CDP 启动和任务页登记能力可以复用，现有滑块代码也已经改为只等待人工完成。
- 抖音当前 `pong()` 只读取 `HasUserLogin` 或 `LOGIN_STATUS`，属于本地状态提示，不是可靠的
  在线登录证明；当前普通二维码流程还会提取二维码图片。
- 产品目录当前只启用微博和快手，抖音仍为 `coming_soon`。

## Requirements

### R1 — Product connection flow

- 抖音必须接入现有平台账号连接 API、全局单任务锁、状态机和轮询 UI。
- 抖音启用后，微博、抖音和快手为可检测平台；小红书与今日头条继续显示待接入。
- 后端重启后状态仍可回到 `not_checked`；本任务不引入 SQLite 持久化。

### R2 — Borrowed Chrome ownership

- 认证仅连接用户现有的可见 Chrome 与 loopback CDP，不启动专属 Profile 或备用浏览器。
- CDP 不可用或用户未批准连接时必须失败关闭，不得回退到标准 Playwright 浏览器。
- 只关闭本次任务创建的抖音页面，不关闭用户原有标签页、BrowserContext、Chrome 或非本任务进程。

### R3 — Manual official authentication

- 未登录时打开抖音官方可见登录界面，允许用户选择官方页面提供的扫码、短信或其他方式。
- 认证模式不得提取、复制、显示或转发二维码图片，也不得读取用户输入的手机号、验证码或密码。
- 滑块、CAPTCHA 和其他安全验证只提示并等待用户人工完成；不得自动拖动、模拟或绕过。
- 人工等待必须有界，并通过现有 `waiting_for_login` / `action_required` 状态提供操作指引。

### R4 — Authoritative online proof

- `connected` 必须来自一次新鲜、只读、网络驱动的抖音官方页面登录检查。
- Cookie、LocalStorage、二维码消失、页面跳转或进程退出只可作为触发在线复检的提示，不能单独证明登录。
- 在线检查必须只返回连接分类，不读取或持久化账号身份、页面正文或认证材料。
- 登录态不明确、选择器漂移、官方挑战未完成或在线复检失败时不得返回 `connected`。
- 在可靠探针通过自动化回归和真实 Chrome 验收前，产品不得把抖音作为已交付平台启用。

### R5 — Authentication-only boundary

- 抖音 `auth` 模式必须强制无代理、无显式 Cookie/Profile 持久化、无数据库初始化、无关键词和平台业务 ID。
- 运行必须在任何搜索、详情、创作者、评论、媒体下载、store 或数据库入口前终止。
- 正常抖音 crawler 模式的搜索、登录 UI、二维码查看器和浏览器生命周期必须保持兼容。

### R6 — Typed cross-platform protocol

- MediaCrawler 认证平台白名单扩展为准确的 `wb | dy | ks`。
- 子进程事件继续只允许 `version`、`platform`、`phase` 三个常量字段，抖音事件必须标记 `dy`。
- FastAPI 必须要求事件平台与当前 attempt 完全一致；三平台任一交叉事件都失败关闭且不得污染其他平台状态。
- worker 命令继续使用固定参数和 `create_subprocess_exec`，不得使用 shell 或传递任何凭据。

### R7 — React UX and readiness

- 抖音行提供“检测连接/重新检测”操作，并复用现有状态徽标、禁用策略和实时指引。
- 当前操作指引必须显示抖音名称，并明确扫码、短信和安全验证需要人工完成。
- 工作台必须根据 API 中 `enabled` 平台动态计算三平台准备度，不能继续写死“微博与快手”。
- 页面继续满足键盘、live region、44 px 移动端操作目标、无横向溢出和控制台无错误要求。

### R8 — Real acceptance and evidence

- 真实验收前记录一个非敏感的既有标签页存在信号。
- 优先验证已登录快速路径；否则由用户在抖音官方页面完成人工登录或挑战。
- 真实运行必须证明在线探针与 React 都达到 `connected`，且没有采集或存储入口运行。
- 成功、失败、超时和取消后均验证用户 Chrome 与既有标签页存活，任务页按归属边界清理。
- 证据只记录状态、时间、数量和页面归属，不记录 Cookie、二维码、账号身份或页面内容。

## Acceptance Criteria

- [ ] `uv run ... main.py --platform dy --type auth ...` 使用现有 Chrome，发出合法 `dy`
      事件，并在在线证明成功后以连接退出码结束。
- [ ] 未登录时，用户可在官方可见页面手工完成扫码/短信/滑块；系统不提取二维码或自动处理挑战。
- [ ] 本地登录标记存在但在线检查失败时，MediaCrawler 与产品均不得显示 `connected`。
- [ ] 认证模式的测试哨兵证明 search/detail/creator/comment/media/store/database 均不可达。
- [ ] CDP 失败、在线结果不明确、超时、取消和跨平台事件全部安全失败且不影响用户 Chrome。
- [ ] `GET /api/v1/platform-connections` 仍按五平台固定顺序返回，其中 `wb | dy | ks`
      为 `enabled`，`xhs | toutiao` 为 `coming_soon`。
- [ ] React 可启动抖音 attempt、轮询到终态、显示平台化指引，并动态展示 `0..3 / 3`
      的可用平台准备度。
- [ ] 微博、快手和抖音普通 crawler 回归通过；前后端与 MediaCrawler 的冻结质量门通过。
- [ ] 真实 Chrome 验收达到在线证明的 `connected`，既有标签页存活，任务页正确清理，且证据不含敏感信息。

## Out of Scope

- 抖音关键词搜索、定时采集、结果入库、舆情分析或预警。
- 自动化滑块、CAPTCHA、短信或其他平台安全验证。
- Cookie 导入导出、账号身份展示、二维码转发、专属浏览器 Profile 或 SQLite 登录态持久化。
- 小红书、今日头条账号连接，以及产品登录/权限系统。
- 对普通抖音采集流程进行与认证连接无关的重构。

## Risks and deferred items

- 抖音页面结构可能变化。实现阶段必须先验证只读在线探针的正向、匿名和不明确三类结果；
  无法稳定区分时保持抖音 `coming_soon`，不以 Cookie/LocalStorage 降级替代。
- 真实页面可能出现不同的官方挑战；这些挑战只允许人工处理，无法在有界时间内完成即返回未连接。
- 本任务只证明账号连接，不等同于后续关键词采集链路可用。
