# Research: 今日头条网页搜索与官方能力可行性

- Query: 截至 2026-08-23，今日头条是否能以合规、低频、可维护的方式，为本地非商业舆情项目提供通用公开内容关键词搜索，并如何映射到 MediaCrawler 的平台架构？
- Scope: mixed（本地源码、官方文档、一次低频匿名公开页面观察）
- Date: 2026-08-23（Asia/Shanghai）

## Findings

### Executive conclusion

**当前结论是“技术上可读取，项目内不应直接实现”。** 今日头条公开桌面搜索页在本次观察中无需交互式登录即可显示标题、摘要、来源、时间和跳转链接，也暴露了明确的页码参数；但是：

1. 官方开放平台公开文档中没有找到可检索任意公众内容的通用关键词搜索 API。可确认的头条 OpenAPI 主要围绕经用户授权的帐号视频发布、视频列表和数据管理，并不满足“搜索所有用户/媒体公开内容”的舆情发现需求。
2. `https://so.toutiao.com/robots.txt` 当前对所有 user-agent 声明 `Disallow: /`；`https://www.toutiao.com/robots.txt` 也明确声明 `Disallow: /search`。MediaCrawler 源码要求遵守目标平台的 robots.txt（例如 `base/base_crawler.py:10-15`）。因此，可见浏览器 DOM 解析和浏览器上下文内网络响应读取这两条自动化路线，均应在当前项目中停止，而不是进入适配实现。
3. 推荐顺序是：**先申请/确认官方授权能力或书面许可；否则使用有明确授权条款的第三方搜索数据服务发现链接；在此之前只保留人工搜索流程。** 不应把当前网页结构、未公开网络接口或签名机制写进 MediaCrawler。

这不是法律意见；它是按当前官方公开信号和本仓库既有合规约束作出的工程准入判断。

### 1. 官方 Toutiao / ByteDance 开放能力

#### 官方文档直接支持的事实

- 抖音开放平台将“运营头条号”描述为发布视频、获取视频数据/用户数据/榜单等能力，而不是全站公开内容检索。官方概述见 [开发者平台概述](https://developer.open-douyin.com/docs/resource/zh-CN/developer/introduction/overview)（访问：2026-08-23）。
- 头条 OAuth 文档要求先创建并审核应用；涉及视频发布、视频数据、视频列表的接口需要用户授权。`client_access_token` 操作应用数据，`user_access_token` 操作用户数据。见 [头条帐号 OAuth 2.0 授权](https://open.douyin.com/platform/resource/docs/develop/permission/toutiao-or-xigua/OAuth2.0/)（访问：2026-08-23）。
- 可确认的“查询授权帐号的视频列表”接口是 `GET /toutiao/video/list/`，需要 `toutiao.video.data` scope 和用户授权，语义是列出该授权帐号的视频，并不是按关键词搜索任意公开帐号内容。见 [查询授权帐号的视频列表](https://open.douyin.com/platform/resource/docs/openapi/video-management/toutiao/search-video/account-video-list/)（访问：2026-08-23）。
- 官方头条发布方案只支持向今日头条发布小视频，且明确暂不支持头条文章、微头条发布；它也只覆盖授权帐号内容管理。见 [头条内容发布接入方案](https://open.douyin.com/platform/resource/docs/ability/content-management/toutiao-publish-solution)（访问：2026-08-23）。

#### 调研结论

- **未发现**适合本项目的、官方文档化的“通用公开内容关键词搜索”接口。
- 官方 API 路线不能用“授权帐号视频列表”替代，因为它只返回授权主体自己的内容，会系统性漏掉公众投诉、媒体报道和其他帐号提及。
- “未发现”不等于证明官方内部或定向合作能力不存在；若甲方能获得政务/媒体合作接口或书面许可，应重新核对控制台实际可申请 scope 和合同，不应根据网页端网络请求猜测官方合同。

### 2. 当前公开网页搜索观察

#### 观察边界

- 只访问一次公开关键词页面：`https://www.toutiao.com/search/?keyword=龙田街道`，浏览器最终跳转到 `https://so.toutiao.com/search/?dvpf=pc&keyword=...`。
- 未登录、未扫码、未提交凭证；未读取 Cookie、LocalStorage 或认证请求头；未点击翻页；未检查或复现网页网络接口；未采集正文或评论。

#### 直接观察事实

- 页面标题为“龙田街道 - 头条搜索”。页面显示“登录”入口，但没有登录弹窗或登录前置阻断；搜索结果直接可见。因此，本次浏览器上下文中**基本结果不要求交互式登录**。由于未检查浏览器存储，不能进一步声称服务端完全不使用匿名状态。
- 顶部结果类型包含“综合、资讯、视频、图片、用户、小视频、微头条、音乐”；页面还提供“全网内容 / 只看头条”和“不限时间”。“综合”结果会混合今日头条内容、百科、政府网站和其他站外来源，不能默认把所有结果标记为 `platform=toutiao`。
- 可见结果字段包括：
  - 标题；
  - 摘要/命中片段（关键词高亮）；
  - 来源名称；
  - 发布时间或日期文本（部分结果缺失）；
  - 可选图片；
  - 跳转链接。
- 搜索结果外层链接通常为 `https://sou.toutiao.com/search/jump?url=<URL-encoded target>&aid=4916&jtoken=...`；存在嵌套两层 `search/jump` 的旧结果。解码后的目标既可能是站外 URL，也可能是：
  - `https://www.toutiao.com/article/<numeric-id>`；
  - 旧式 `http://www.toutiao.com/a<numeric-id>/`；
  - `https://www.toutiao.com/trending/<numeric-id>/...`。
- 桌面页面提供显式页码 `1` 到 `10` 和“下一页”，URL 使用零基 `page_num=0,1,2...`，并携带当次页面生成的 `search_id`。这说明当前桌面 UI 是页码式导航，而不是只能靠无限滚动；本次没有点击第二页，故不把 `search_id` 的长期有效性视为稳定合同。
- 本次单页加载没有看到 CAPTCHA、滑块、安全验证遮罩或 401/403 提示。一次未出现不代表未来或自动化运行不会触发。

#### 官方抓取规则

- [so.toutiao.com/robots.txt](https://so.toutiao.com/robots.txt)（访问：2026-08-23）返回：

  ```text
  User-agent: *
  Disallow: /
  Allow: /$
  ```

- [www.toutiao.com/robots.txt](https://www.toutiao.com/robots.txt)（访问：2026-08-23）明确包含 `Disallow: /search`，同时禁止 `/item/`、`/group/`、`/trending/` 等路径。
- MediaCrawler 每个核心模块的许可证声明要求遵守目标平台服务条款和 robots.txt，并控制频率（`third_party/MediaCrawler/base/base_crawler.py:10-15`）。因此，虽然人工观察证明页面“能打开”，它并不构成项目自动化采集的准入依据。

### 3. 三条候选路线与取舍

| 路线 | 技术可行性 | 合规/维护判断 | 结论与停止条件 |
| --- | --- | --- | --- |
| 官方 API | 当前公开能力可做授权帐号视频管理，但未找到全站公众内容关键词搜索 | 稳定性和合规性最好；需要审核应用、scope 和授权，覆盖范围却不符合舆情发现 | **优先但当前不可用。** 只有获得文档化的通用搜索 scope、政务合作接口或书面许可后才进入实现；不能以授权帐号列表冒充全站搜索 |
| 可见浏览器 DOM 解析 | 本次匿名页面可直接看到字段和页码，纯技术上可做最小解析 | hashed CSS class、混合结果类型、嵌套跳转链接、搜索会话参数、个性化排序都会造成维护成本；更关键是搜索域 robots 禁止自动访问 | **当前禁止实现。** robots 保持 `Disallow: /` 或 `/search` 时立即停止；出现登录墙、CAPTCHA、滑块、403/429、结构大面积缺失时同样停止，不自动重试绕过 |
| 浏览器上下文内低频读取网络响应 | 推测响应会比 DOM 更结构化，但本次按约束没有检查请求端点、响应体、签名或头信息 | 未文档化接口随时变化；可能绑定动态参数/签名/匿名会话；网络层自动调用仍是对被禁止搜索路径的自动化访问 | **当前禁止实现，且不作为 DOM 失败后的绕行。** 不逆向签名，不重放认证头，不尝试绕过 401/403/安全挑战；只有官方许可明确覆盖相关端点后才重新调研 |

#### 推荐可行替代

1. 向今日头条/字节跳动申请适合政务舆情或媒体合作的搜索能力，并让接口范围、频率、保存字段和链接再分发权落到书面材料中。
2. 若官方没有适用接口，选用**合同明确允许关键词检索和结果链接使用**的第三方舆情/网页搜索服务，由该服务负责发现 `toutiao.com` 链接；本项目只做去重、AI 分类和通知。具体服务仍需单独调研条款、覆盖率和费用。
3. 过渡期采用人工打开头条搜索、人工提交链接的方式。自动化系统可处理人工录入后的摘要、分级、查重和通知，但不要自动访问头条搜索页。
4. NanmiCoder 另有 [NewsCrawler](https://github.com/NanmiCoder/NewsCrawler) 支持对**已知** `toutiao.com/article/<id>` 链接做文章提取；它解决的是“已有 URL 后读取详情”，不是关键词发现。若未来确需正文，还要另行核对当时 robots/服务条款和最小化存储边界。

### 4. 若未来获得许可：最小数据合同

许可或官方接口是实施前置门槛。满足门槛后，第一版只保留线索发现字段，不采集评论和完整正文：

```text
platform           固定 "toutiao"（仅直接头条内容）；站外结果必须标记 external
content_id          头条内容数字 ID；没有稳定 ID 时使用 canonical_url 的确定性哈希
content_type        article | video | micro_post | image | external
title               可空但优先保存
snippet             搜索结果可见摘要片段，可空
source_name         结果页显示来源，可空；不扩展抓取作者档案
published_at_text   原始可见日期文本，可空；无法可靠解析时不伪造时间戳
canonical_url       解包跳转链接后的 HTTP(S) 目标
source_keyword      命中的监控关键词
discovered_at       本地发现时间
```

契约要求：

- 递归解包 `search/jump?url=` 时设置最大层数（建议 2）、只接受 `http`/`https`，拒绝 `javascript:`、`data:` 和缺少 host 的目标；不保存 `jtoken` 等跟踪参数。
- “全网内容”结果必须区分站外来源；若任务目标严格是今日头条平台内容，只接收解包后 host 为 `toutiao.com` 或经许可确认的官方子域结果。
- 使用 `(platform, content_id)` 或规范化 URL 的哈希去重；不依赖标题去重。
- 不收集原始用户 ID、头像、主页、IP 位置、Cookie 或认证头；这与现有 ORM 的隐私最小化说明一致（`third_party/MediaCrawler/database/models.py:20-25`）。
- 页面结构只是 fixture 输入，不是稳定 API 合同；任何 selector 或响应字段必须容忍缺失。

### 5. 若未来获得许可：MediaCrawler 影响面

#### Files found

- `third_party/MediaCrawler/main.py` — 平台 crawler 工厂和进程入口；需导入并注册 `toutiao`（`main.py:39-59`, `main.py:100-114`）。
- `third_party/MediaCrawler/cmd_arg/arg.py` — CLI 平台枚举和帮助文本；需新增平台值（`cmd_arg/arg.py:40-49`, `cmd_arg/arg.py:161-168`）。
- `third_party/MediaCrawler/api/schemas/crawler.py` — FastAPI 请求模型独立维护一套平台枚举；需同步新增（`api/schemas/crawler.py:27-35`, `api/schemas/crawler.py:63-77`）。
- `third_party/MediaCrawler/config/base_config.py` — 默认平台、关键词、登录、频率、数量和 store 配置（`config/base_config.py:20-32`, `config/base_config.py:46-53`, `config/base_config.py:89-102`, `config/base_config.py:136-137`）；如有头条专属开关，应新增 `config/toutiao_config.py` 并在文件末尾导入。
- `third_party/MediaCrawler/base/base_crawler.py` — `AbstractCrawler`、`AbstractLogin`、`AbstractStore` 合同（`base/base_crawler.py:26-64`, `base/base_crawler.py:67-100`）。
- `third_party/MediaCrawler/media_platform/weibo/core.py` — 可参考的浏览器初始化、授权检查、搜索循环和 store 调用编排（`weibo/core.py:70-148`, `weibo/core.py:150-203`），但不能复制其已登录 API 路线来访问被 robots 禁止的头条搜索。
- `third_party/MediaCrawler/media_platform/weibo/client.py` — 可参考 client 的 `request`、`pong`、`update_cookies`、关键词搜索方法边界（`weibo/client.py:49-172`）；官方匿名接口方案不应伪造 `pong` 或无必要引入登录态。
- `third_party/MediaCrawler/store/weibo/__init__.py` — store 工厂与平台响应到统一字段的转换层（`store/weibo/__init__.py:35-52`, `store/weibo/__init__.py:70-107`）。
- `third_party/MediaCrawler/store/weibo/_store_impl.py` — CSV/JSONL/SQLite 等实现模式及 ORM 字段过滤（`store/weibo/_store_impl.py:61-65`, `store/weibo/_store_impl.py:68-136`）。
- `third_party/MediaCrawler/database/models.py` — SQLite/Postgres ORM；未来需新增最小 `ToutiaoContent` 表，并保持不持久化可识别用户信息（`database/models.py:20-31`, `database/models.py:158-173`）。
- `third_party/MediaCrawler/database/db_session.py` — `Base.metadata.create_all` 自动建表路径（`database/db_session.py:77-84`）。
- `third_party/MediaCrawler/tools/async_file_writer.py` — JSON/JSONL/CSV 输出按平台和 crawler type 分目录（`tools/async_file_writer.py:30-60`）。
- `third_party/MediaCrawler/tools/browser_auth_state.py` — 若许可接口最终要求网页登录，可复用平台域名 allowlist、原子 `0600` Cookie 状态文件（`tools/browser_auth_state.py:35-80`, `tools/browser_auth_state.py:82-164`）；必须遵守“恢复后仍以在线检查为准”的既有规范，而不是把文件存在当作登录成功。
- `third_party/MediaCrawler/tests/` — 现有 registry、store、隐私和认证态测试模式；未来应新增完全离线的头条 fixture/链接规范化/编排测试。

#### Conditional module shape

```text
media_platform/toutiao/
├── __init__.py       # export ToutiaoCrawler
├── core.py           # keyword orchestration, limits, stop conditions
├── client.py         # only documented/permission-covered transport
├── help.py           # result extraction and jump-link normalization
├── field.py          # content/result type enums if needed
└── exception.py      # typed access/challenge/data errors

store/toutiao/
├── __init__.py       # response -> minimal content contract
└── _store_impl.py    # JSONL/SQLite first; other stores only if required
```

`login.py` 不应为了目录对称而空建：只有未来许可方案确实要求交互式帐号登录时才引入，并复用 `.trellis/spec/backend/auth-state-guidelines.md` 的登录态合同。若官方 API 使用 OAuth，凭证生命周期应单独设计，不能把 OAuth token 当浏览器 Cookie 保存。

### 6. 条件式后续实施计划

1. **准入门（必须先完成）：** 获取官方文档化搜索接口/书面许可，或选定明确允许搜索结果使用的第三方服务；保存能力范围、速率和数据保留条件。未通过则任务结束，不写平台代码。
2. 固化最小字段合同、来源分类和 URL 解包规则；用本次观察手工制作的脱敏 fixture，不保存原始页面、token 或动态搜索会话 ID。
3. 先实现纯函数 `normalize_result_link` 和 `extract_result_cards`，测试单层/双层跳转、站外链接、非法 scheme、字段缺失、旧/新头条 URL 形态。
4. 只接入许可覆盖的 transport。官方 API 优先；不得把未公开网页响应“包装成 client API”。
5. 接入 `toutiao` CLI/API 枚举和 crawler factory；第一版仅 `search`，对 `detail`/`creator` 明确报“不支持”，不静默空跑。
6. 接入 JSONL 和 SQLite 最小 store，唯一键做幂等；不采集评论、作者档案、媒体文件或完整正文。
7. 离线测试覆盖：注册、参数、每关键词单页上限、零结果、重复链接、字段缺失、挑战/403/429 立即停机、日志无凭证、store 幂等和无可识别用户字段。
8. 获得明确批准后才能做一次可见、低频真实回归：一个关键词、一页、不翻页、不登录；记录字段/停止结果，不记录响应头或认证状态。
9. 若出现 CAPTCHA/滑块/登录强制、签名要求、403/429、robots 或条款收紧、连续两次结构无法解析，立即关闭该平台功能，不做重试洪泛、隐身强化或绕过。

### 7. Related specs

- `.trellis/tasks/08-23-research-mediacrawler-toutiao-adapter/prd.md` — 本次调研目标、只读边界和验收条件。
- `.trellis/spec/backend/auth-state-guidelines.md` — 浏览器认证态最小化、域名 allowlist、在线验证、人工安全挑战和无敏感日志合同；仅在未来被许可方案确实需要网页登录时适用。
- `.trellis/spec/infra/submodule-guidelines.md` — MediaCrawler 派生仓库应先提交并推送，再由父仓库更新 gitlink。
- `third_party/MediaCrawler/base/base_crawler.py:10-15` — 项目自身声明必须遵守目标平台服务条款和 robots.txt。
- `third_party/MediaCrawler/LICENSE:12-18` / `LICENSE:42-48` — 仅限非商业学习研究，不得大规模爬取或影响平台运营。用户“不商用”满足其中一项，但不会取消 robots/平台规则和频率约束。

## Caveats / Not Found

- 官方开放平台目录可能对已审核应用显示额外 scope；本次没有登录控制台，也没有应用凭证，因此没有核对定向/灰度能力。
- 未找到官方文档化的通用公开内容关键词搜索 API；该结论基于截至 2026-08-23 的公开官方文档和检索结果，未来需要重新验证。
- 未查看网页网络请求、响应体、签名参数、Cookie、LocalStorage 或认证头；关于“网络响应更结构化、可能绑定动态参数”的表述是工程推断，不是直接观察。
- 没有点击“只看头条”、结果类型 tab 或第二页；类型参数和分页链接是页面直接暴露的 UI/URL 形态，不代表长期稳定或覆盖完整。
- 本次没有出现安全挑战，仅能说明一次人工低频访问未触发；不能据此估计自动化风控概率。
- `so.toutiao.com/robots.txt` 的 `Disallow: /` 是本任务最关键的当前停止信号。除非官方文档/书面许可明确改变准入边界，不应继续做 DOM 或网络接口适配。
