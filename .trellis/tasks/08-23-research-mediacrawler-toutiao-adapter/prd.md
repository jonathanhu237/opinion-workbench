# MediaCrawler 今日头条最小适配

## Goal

在 MediaCrawler 派生仓库中新增 `toutiao` 平台，使本地非商业舆情项目能够使用项目专用浏览器低频搜索“龙田街道、4 个社区和辖区地址”等关键词，并把今日头条公开搜索结果的标题、摘要片段和可打开的原文链接保存为 JSONL 或 SQLite 线索。

## Background

- 甲方 JD 明确包含今日头条，核心价值是每天发现涉及辖区的公开内容并生成原文链接。
- 当前派生仓库支持抖音、快手、微博等平台，但没有今日头条 crawler、CLI 平台值、配置或 store。
- 2026-08-23 调研未发现官方通用公众内容关键词搜索 API；公开网页搜索无需强制登录即可显示标题、摘要、来源、时间和跳转链接。
- 当前 `so.toutiao.com/robots.txt` 禁止 `/`，`www.toutiao.com/robots.txt` 禁止 `/search`；这与 MediaCrawler 源码声明的 robots 遵循原则存在明确冲突。
- 2026-08-24 用户在知悉上述准入和维护风险后，明确拒绝将直接适配标记为 `blocked`，决定继续实现直接站内搜索。本决策改变实施范围，不把网页结构或未公开接口描述为官方稳定合同。

## Requirements

- 在 `main.py` crawler factory、`cmd_arg/arg.py` 平台枚举与帮助、`config/base_config.py` 和 `config/toutiao_config.py` 中注册稳定平台 ID `toutiao`。
- 第一版仅支持 `CRAWLER_TYPE=search`；`detail`、`creator`、正文、评论、媒体下载必须明确报“不支持”或安全跳过，不能静默触发其他采集链路。
- 每次运行只新建项目专用的标准可见 Chrome `BrowserContext` 正常导航访问桌面搜索页，并从当前页面 DOM 读取结果；今日头条适配不得进入任何 CDP 分支、连接既有浏览器或创建持久化 profile，不得调用或重放未公开搜索 API，不逆向签名，不注入 stealth。
- 默认每个关键词只读取第一页、串行执行、遵守 `CRAWLER_MAX_NOTES_COUNT` 和固定 `CRAWLER_MAX_SLEEP_SEC`；不得自动滚动扩量或并发打开详情页。
- 搜索结果必须离线解包最多两层 `search/jump?url=`，只接受 HTTP(S) 且最终 host 属于 `toutiao.com` 的链接；不点击跳转链接，不打开正文，不保存 `jtoken` 等跟踪参数。
- 最小线索字段为：`content_id`、`content_type`、`title`、`snippet`、脱敏后的 `publisher_name`、`published_at_text`、`content_url`、`source_keyword`、`discovered_at`；禁止保存原始用户 ID、头像、主页、IP 位置、Cookie、LocalStorage、认证头或二维码内容。
- 搜索本身不强制登录；新增 `TOUTIAO_REQUIRE_LOGIN` 配置用于项目专用账号。开启后支持可见浏览器人工首次登录、在线 DOM 状态确认和现有 `BrowserAuthStateStore(platform="toutiao")` 的登录态复用；它是唯一允许的跨重启认证持久化边界，文件存在不能替代在线确认，LocalStorage/profile 数据不得跨运行保留。
- 首页认证检查和关键词搜索必须使用同一临时 `BrowserContext` 内的两张不同 Page：认证/人工登录/状态保存完成后创建一张从未导航过的空白搜索 Page，关闭认证 Page，再在搜索 Page 上执行唯一一次官方搜索入口导航；不得复用首页 Page、重试导航或吞掉 `ERR_ABORTED`。
- 搜索阶段遇到 CAPTCHA、滑块、安全验证、登录墙、403/429 或无法识别的页面结构时必须停止当前平台运行并输出非敏感提示。只有用户明确发起的人工登录等待可以在可见浏览器中把官方安全挑战视为待人工处理状态，继续低频在线登录检查直至成功或超时；不得自动检查挑战细节、处理、绕过或重试页面导航。
- 第一版正式存储仅支持 JSONL 与 SQLite。SQLite 按 `content_id` 幂等更新；其他 save option 必须给出清晰的不支持错误。
- 完成全离线 parser、URL、crawler 编排、认证编排、store 幂等、隐私和平台注册测试，再进行一个关键词、单页、可见浏览器的真实回归。
- MediaCrawler 改动必须先提交并推送到派生仓库 `main`，父仓库再更新 submodule gitlink；不修改 MediaCrawler 自带 API/Web UI。

## Acceptance Criteria

- [x] `python main.py --platform toutiao --type search --keywords 龙田街道 --crawler_max_notes_count 10 --get_comment no --headless no --save_data_option jsonl` 能启动专用可见浏览器，并在无安全挑战时完成一次单页搜索。
- [x] 每条有效结果至少包含非空 `content_id`、`title`、`content_url`、`source_keyword` 和 `discovered_at`；`content_url` 为解包、去跟踪后的 HTTP(S) 今日头条链接，缺失的摘要/来源/时间保持为空而不是伪造。
- [x] 综合搜索中的站外链接、非法 scheme、无法安全解包的跳转和重复链接不会进入 Toutiao store；单层/双层跳转、旧/新文章 URL 及无数字 ID URL 均有离线测试。
- [x] `detail`、`creator`、评论和媒体采集不会执行；第一版每个关键词最多一页、串行处理且有硬数量上限和固定间隔。
- [x] `TOUTIAO_REQUIRE_LOGIN=False` 时不要求账号即可搜索；设为 `True` 时支持人工完成官方登录/验证，只有在线登录检查成功才保存 allowlist Cookie，并能在浏览器完全退出后的第二次启动复用有效状态。
- [x] CAPTCHA、滑块、403/429、强制登录或未知页面结构会立即结束搜索；人工登录等待中的官方挑战只提示用户手动处理并在超时后失败，未在线确认前不保存状态；任何阶段均不读取网络私有响应、不自动重试或绕过，日志不包含凭证、二维码、原始 HTML 或动态 token。
- [x] JSONL 能写入最小合同；SQLite 能自动建表并以 `content_id` 幂等新增/更新，不持久化禁止的个人信息字段。
- [x] targeted tests、完整 `tests/`、pre-commit、Python compile 检查和敏感信息扫描通过；真实回归只记录非敏感结果数量、字段完整性和停止状态。
- [ ] 派生仓库提交已推送且父仓库 gitlink 指向可达的干净 revision。
- [x] 父仓库既有 `browser_data/`、`db_data/`、`logs/` 和其他用户运行数据未被修改或删除；任务创建的临时验证目录和认证态已完成清理。

## Out of Scope

- 今日头条详情、正文、评论、作者主页、媒体文件或第二页及以后结果。
- 未公开移动端/API 响应、签名算法、请求头重放、设备指纹伪造、stealth、验证码或滑块自动化。
- MediaCrawler 自带 FastAPI/Web UI、父项目 React/FastAPI 页面、定时任务、AI 舆情分类和通知。
- CSV、MySQL、PostgreSQL、MongoDB、Excel 等额外 store。
- 对搜索覆盖率、排序稳定性、长期 selector 稳定性或零遗漏作保证。

## Key Decisions

- 用户选择直接适配，并接受当前 robots 冲突、网页结构可能随时变化和功能可能被平台阻断的风险。
- MVP 选择可见浏览器 DOM，而不是浏览器网络响应或第三方私有 API，因为 DOM 与用户可见结果一致、无需复现签名，且停止边界更清楚。
- 搜索能力与账号认证解耦：匿名页面可用时不强制登录，但保留项目专用账号的人工登录和状态复用开关。
- MVP 只做第一页线索发现和 JSONL/SQLite；正文、评论、翻页以及父项目消费链路后续单独规划。
