# 今日头条补全工具调查

Status: research

后续更新：本文保留实测前的源码调查快照。2026-09-06 已完成独立样本试验，当前可用性、失败证据与选型调整以[实测记录](real-validation.md)为准。

核查日期：2026-09-06（Asia/Shanghai）。只查作者仓库、公开源码、文档和发布记录；未安装或执行候选工具，未登录平台，未打开真实头条内容或下载媒体。下文的“支持”区分代码证据与本项目实测，不把维护活跃或工具退出成功当成验收。

## 结论

今日头条已经找到分别面向文章、微头条和独立视频的现成工具，不能再简单表述为“没有下载器，需要自己写”。但没有一个本次核验的候选同时完成三种内容的正文、元数据和媒体下载，并符合本项目全部运行约束。

- **文章全文：先验证 NewsCrawler 的头条文章适配，再以 Trafilatura 作为现成正文提取的对照。** 前者有明确的 `/article/` 获取及头条正文定位代码；后者有独立 HTTP 获取、HTML 正文和元数据提取，适合在已取得完整 HTML 后比较提取效果。两者均未在本项目样本上实测，不能提前判断必须自写正文解析。[NewsCrawler 文章适配](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/toutiao_news/toutaio_news.py)、[Trafilatura 下载接口](https://trafilatura.readthedocs.io/en/latest/downloads.html)。
- **微头条：HunterWangwei/ToutiaoCrawler 有真正的单条微头条实现，技术上值得优先验证。** 它把作品 ID 交给移动端 `/w/` 页面，解析微头条专用数据并能下载图片；这比仅在 README 列“微头条”更强。但仓库未提供明确 LICENSE，属于公开源码技术候选，尚不能作为许可已明确的正式依赖。[微头条实现](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_crawler.py#L164-L216)、[仓库](https://github.com/HunterWangwei/ToutiaoCrawler)。
- **独立视频：yt-dlp 2026.08.19 有头条专用获取器，可直接作为第一轮验证对象。** 它支持 `/video/{id}/`、标题、作者、时间、封面、多种格式和音视频参数；不负责文章全文或微头条正文。[发布](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19)、[对应版本源码](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/toutiao.py)。
- **haodown 是另一个真实备选。** 它具有微头条图片和独立视频的浏览器获取代码，适合媒体能力对照；微头条结果没有正文，文章 URL 也不在当前正规化范围内。该仓库同样未见明确 LICENSE。[平台路由](https://github.com/realerikk0/haodown/blob/cff6316d405c1494daf34b5832dc94e00b743614/lib/providers/toutiao/shared.ts#L48-L71)。

## 候选与职责

“优先验证”是调查排序，不表示已选定依赖。许可未明确的公开源码只列为技术候选；正式接入前必须解决依赖采用条件。

| 候选 | HTTP / 浏览器获取 | 正文与元数据 | 媒体 | 原生微头条证据 | 本轮定位 |
| --- | --- | --- | --- | --- | --- |
| NewsCrawler | `RequestsFetcher` 获取文章 HTML，可换获取策略 | 头条专用 XPath，标题、作者、时间、正文段落 | 提取图/视频 URL；该新闻链路保存 JSON，不下载媒体文件 | 未见；文章 ID 解析限定 `/article/` | 文章专用首选验证，GPL-3.0 |
| Trafilatura 2.2.0 | 自带 HTTP；JS 页面需外部渲染后传 HTML | 通用正文、标题、作者、日期等 | 可保留 HTML 中图片引用；没有头条视频解析或媒体归档 | 没有平台专用 thread 适配 | 文章正文对照，Apache-2.0 |
| HunterWangwei/ToutiaoCrawler 1.7.3 | `requests` 获取移动端 SSR HTML | 微头条正文、作者、时间、图片、部分互动量 | 有图片实际下载；未见视频实现 | 有 `articleInfo.thread.threadBase` 分支 | 微头条技术首选；许可待明确 |
| yt-dlp 2026.08.19 | HTTP + 头条 RENDER_DATA | 独立视频标题、作者、时间、封面和统计；非文章正文 | 提取视频格式，通用下载器下载文件 | 无 `/w/` 或 thread 分支 | 独立视频首选验证 |
| cv-cat/HeadlineApis | `requests` 获取文章 HTML及视频接口 | 文章全文/图片；其他 URL 仅 JSON-LD 标题与描述 | 可由嵌入视频 ID 得到 MP4 URL，不下载文件 | README 的微头条声明在用户作品列表；单条实现未见专用分支 | 文章嵌入视频参考；许可待明确 |
| realerikk0/haodown | Puppeteer 页面、播放器和响应 URL | 视频标题/部分元信息；微头条图集只有标题 | 返回图集和视频格式 URL，不归档文件 | 有 `/w/` 与 `.weitoutiao-img`，但没有微头条正文 | 媒体获取备选；许可待明确 |
| GNE 0.4.3 | 不获取 HTML；调用者提供渲染后的 HTML | 通用新闻标题、作者、时间、正文、图片 URL | 不下载媒体、不解析视频接口 | 未见专用微头条实现 | 通用文章解析对照；不是 URL 下载器 |
| Newspaper4k 0.9.6 | `requests` 获取；可通过外部浏览器供给 HTML | 通用新闻正文/标题/作者/日期 | 图片与电影链接检测；非头条媒体下载器 | 未见专用微头条实现 | 通用解析备选，优先级低于上述组合 |

各行的具体代码证据和限制见下文。

## 1. HunterWangwei/ToutiaoCrawler：真正的微头条候选

版本与来源：GitHub 最新发布为 [v1.7.3](https://github.com/HunterWangwei/ToutiaoCrawler/releases/tag/v1.7.3)，2026-08-12，提交 `411b39c886e7a90579eb920da16d6550feb26456`。README 标注的软件更新日期为 2026-08-11，和 Release 日期不同，不能混为一个日期。该发布主要修改更新代理和重试，不是对当日平台内容可用性的证明。

### 单条内容获取

`ToutiaoCrawler.article(source_url)` 接受 `/article/{id}` 或 `/w/{id}`，实际 HTTP 请求 `https://m.toutiao.com/w/{id}/`。它从返回 HTML 的 `RENDER_DATA` 中解码 JSON，明确处理 `articleInfo.thread.threadBase`，读取 `richContent/content`、用户名称、创建时间、`largeImageList/originImageList` 和点赞数；返回来源 URL、详情 URL、ID 与结构化字段。这是微头条专用路径，不是通用新闻正文识别。[源码 164–216 行](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_crawler.py#L164-L216)。

另一个 `ProfileCrawler.post(source_url)` 也可直接接受单条 URL，不必先遍历主页；它返回作者、正文、发布时间/时间戳、评论总数、图片列表。名称叫 `article` 不代表长文章支持：主要分支是微头条，所有输入仍被重写至移动端 `/w/`，普通长文须单独验证。[单条 post 实现](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_profile_crawler/crawler.py#L236-L301)。

### 下载、登录态与适配负担

- `download_images` 真正发起图片 HTTP 请求并写文件，失败图片只打印错误并继续。当前实现以 `response.content` 整体读入、据 URL 后缀选扩展名，没有本项目的字节预算、类型探测和内容哈希判定。正式接入需要转换为既有媒体缓存契约。[图片下载](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_crawler.py#L268-L281)。
- 基础单条类的请求没有内置 Cookie；`ProfileCrawler` 支持传入 Cookie，但把它放在 session 通用头上。该 session 后续也下载图片，不能直接照搬为跨域凭证边界。[ProfileCrawler 请求](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_profile_crawler/crawler.py#L63-L130)。这仅证明代码提供这些模式，不证明头条永远无需登录。
- 基础类为硬超时启动 daemon 请求线程，超时后会继续重试；线程可能尚未退出。停止、请求预算和人工暂停不能只依赖其 UI “停止”状态。[网络实现](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_crawler.py#L95-L162)。
- 原 CLI 默认抓评论，GUI 还有内容过滤、主页遍历与自动更新。应限定使用单条获取和图片下载能力；不采用评论、内容过滤、主页遍历或更新器。CLI 默认输出 TXT 会丢掉作者、时间和来源等字段，适配应读取方法返回的结构化数据。[CLI 与保存逻辑](https://github.com/HunterWangwei/ToutiaoCrawler/blob/411b39c886e7a90579eb920da16d6550feb26456/toutiao_crawler.py#L300-L345)。
- 未见需要第三方收费解析 API；发布 EXE 的自动更新器有由作者 Secret 注入的备用代理，README 明确该代理只用于更新。我们不需要这套更新器。[更新器说明](https://github.com/HunterWangwei/ToutiaoCrawler#七网络与故障排查)。

**分级：技术上值得优先验证；正式采用条件未解决。** 仓库未提供明确 LICENSE；也没有本项目真实样本、输出完整性和可停止性的验证。不要写成“已找到可以直接接入的开源包”。

## 2. 文章全文：NewsCrawler 与 Trafilatura

### NewsCrawler 是现成的头条文章专用适配

核验提交为 `25fb3b4a20186905f5ce38f7a7f854050d402253`，2026-08-08；该提交主要关联微信公众号修复，不能当成头条最近修复日期。仓库声明 [GPL-3.0](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/LICENSE)。

`ToutiaoNewsCrawler` 根据 `/article/` 取 ID，用 `//h1`、`.article-meta`、`//article/*` 读取标题、作者、时间和正文。它保留文本、图片、视频项的顺序；只处理直接正文子节点中的 `p` 文本，图片考虑 `img/div/p`，视频只检测直接 `video/@src`，因此嵌套标题、列表、其他文字块和播放器容器要列为样本缺口。没有原生微头条 `threadBase` 分支。[专用解析器](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/toutiao_news/toutaio_news.py#L47-L146)。

`BaseNewsCrawler.run(persist=False)` 包含 HTML 获取、解析和非空校验；默认 `RequestsFetcher`，默认 3 次尝试、15 秒 timeout。`FetchStrategy` 是可替换的明确接口，因此可以通过适配接入本项目受控请求，无需预设重写全部获取器。默认保存的是 JSON，媒体项为 URL，不代表已经下载图片/视频。[运行基类](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/core/base.py#L24-L118)、[获取策略](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/core/fetchers.py#L11-L85)。

头条模块与其 skill 副本包含固定 Cookie 常量，不能复制、启用或依赖其中身份值。**不要反向误报“当前 run 默认必定使用固定 Cookie”**：核查的子类未覆盖基类 `headers_model`，默认实例化的是基类 RequestHeaders；固定头条 RequestHeaders 需要显式传入才会参与这条调用链。正式接入仍应显式注入项目请求头并删去任何未采用的固定凭证值。[头条头部定义](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/toutiao_news/toutaio_news.py#L22-L45)、[基类头部选择](https://github.com/NanmiCoder/NewsCrawler/blob/25fb3b4a20186905f5ce38f7a7f854050d402253/news_crawler/core/base.py#L24-L43)。

**分级：文章专用首选验证。** 现成代码覆盖普通 article 页面，输入边界和获取策略可适配；需要验证页面确有正文、正文结构覆盖、作者时间和媒体完整性。本次调查不支持“已完整解决全部文章形态”，也不支持“必然要自写文章获取器”。

### Trafilatura 是完整 HTML 上的正文工具，不执行网页 JavaScript

当前发布 [2.2.0](https://github.com/adbar/trafilatura/releases/tag/v2.2.0)，2026-07-31；核验 HEAD `2e1d38b2dff26f1598500c7a7702755cd01e7a6e`，2026-08-28。[Apache-2.0 许可](https://github.com/adbar/trafilatura/blob/2e1d38b2dff26f1598500c7a7702755cd01e7a6e/LICENSE)。

它能自行 HTTP 获取 URL（`fetch_url` / `fetch_response`），也能只解析传入 HTML（`extract` 等），返回正文与标题、作者、日期等元数据，可保留图片引用和文档结构。因此“URL → 获取 → 正文提取”已有现成组成部分，不是仅能做模型总结的工具。[下载文档](https://trafilatura.readthedocs.io/en/latest/downloads.html)、[Python 使用](https://trafilatura.readthedocs.io/en/latest/usage-python.html)。

官方明确：遇到 JavaScript 渲染页面，应先用浏览器得到渲染后的 HTML，再交给 `extract()`。它不会从仅有空壳或未渲染脚本的原始响应中自动补出正文，也没有头条微头条、视频平台参数的专用适配。新闻正文较合适；短微头条、图集可能不适合其正文启发式规则。[官方故障说明](https://trafilatura.readthedocs.io/en/latest/troubleshooting.html#page-requires-javascript)。

**分级：许可和接口清楚的文章对照候选。** 若普通 HTTP 返回完整 article HTML，可以直接比较它与 NewsCrawler 的正文质量；若只能在浏览器中看到全文，复用项目浏览器取 HTML 仍是现成解析组合，但要明确这部分获取由应用负责。图片归档和视频获取要另接媒体组件，不能以图片 URL 清单冒充已下载。

## 3. 独立视频：yt-dlp

已核查 [2026.08.19 对应源码](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/toutiao.py)，不只查最新 master。`ToutiaoIE` URL 模式仅接受 `www.toutiao.com/video/{id}/`；从 `RENDER_DATA → data.initialVideo` 读取格式、音频/视频编码、码率、尺寸、时长、发布时间、封面、标题、作者及统计。输出没有完整文章/微头条正文。

初始化若没有 `ttwid`，会向字节的 `ttwid/union/register` 请求游客标识，失败则要求登录；已有 `ttwid` 时跳过该请求。请求是平台自身接口，未见第三方收费解析服务。该隐式游客初始化必须计入本项目请求预算和登录态边界。[初始化源码](https://github.com/yt-dlp/yt-dlp/blob/2026.08.19/yt_dlp/extractor/toutiao.py#L54-L75)。

正文与媒体职责应清楚分开：此候选可以实际下载独立视频，文章里出现视频 ID 不一定有可以直接交给它的独立 `/video/` URL；文章嵌入视频需要额外样本判断。yt-dlp 的源码和构建制品许可不同，应沿用项目实际选择的 Python/子进程制品审查，不把所有打包文件视为同一种许可。[项目许可与集成说明](https://github.com/yt-dlp/yt-dlp#license)。

**分级：独立视频首选验证。** 检验对象是标题、作者、时间、完整视频/音轨和中止行为；不是将所有头条 URL 都交给它后认定整个平台接入完成。

## 4. 另外两个有实际代码的技术备选

### cv-cat/HeadlineApis

核验 HEAD `6c8fd80e5539d1a0dbf8154185e4cc2a64dda879`，2026-08-18，提交为 README 更新；未见明确 LICENSE。虽然 README 写用户作品覆盖视频、图文、微头条，`get_work_info` 的单条逻辑只判断 URL 含不含 `article`：文章分支取 `<article>.text`、JSON-LD 图片，并把 `tt-video-box` 的视频 ID 交给 `i.snssdk.com/video/urls/...` 得到 MP4 URL；其他分支只拿 JSON-LD `name/description`，没有填充 `videos`。因此不能拿列表的微头条声明，推导单条微头条全文或独立视频已完整支持。[单条与嵌入视频代码](https://github.com/cv-cat/HeadlineApis/blob/6c8fd80e5539d1a0dbf8154185e4cc2a64dda879/tou_tiao_api.py#L127-L164)。

代码发起平台 HTTP 请求，单条详情依赖调用者 `auth.cookie`；本次检查的请求没有 timeout 参数。README 还介绍 Node 签名和服务接口，但部分包装入口未出现在当前树中，不能将 README 启动流程直接当成可执行产品。仓库 `.env` 有非空 Cookie 配置，不应读取或采用其值。**定位为文章嵌入视频的实现参考，优先级低于许可已明确、接口可控的组件。**[仓库目录及接口声明](https://github.com/cv-cat/HeadlineApis)、[请求与工具实现](https://github.com/cv-cat/HeadlineApis/blob/6c8fd80e5539d1a0dbf8154185e4cc2a64dda879/utils/tou_tiao_utils.py)。

### realerikk0/haodown

核验 HEAD `cff6316d405c1494daf34b5832dc94e00b743614`，2026-05-06；未见明确 LICENSE。它有自己的头条 provider，正规化仅支持 `/video/` 与 `/w/`。微头条图片获取器用 Puppeteer 读取图片/HTML，按 `from=post`、`gid` 过滤正文图片；只返回标题和图片，没有正文、作者和时间。[微头条图片实现](https://github.com/realerikk0/haodown/blob/cff6316d405c1494daf34b5832dc94e00b743614/lib/providers/toutiao/extract-gallery.ts#L104-L181)。

视频获取器读取页面 initialVideo 数据、video 元素、网络响应媒体 URL，并可点击播放；返回视频格式、封面、时长和部分发布时间。浏览器由 `puppeteer.launch` 在本地或 serverless Chromium 中启动，不是调用付费媒体解析 API。[视频实现](https://github.com/realerikk0/haodown/blob/cff6316d405c1494daf34b5832dc94e00b743614/lib/providers/toutiao/extract-video.ts#L246-L487)、[浏览器创建](https://github.com/realerikk0/haodown/blob/cff6316d405c1494daf34b5832dc94e00b743614/lib/browser.ts)。

其 Supabase 登录/次数/点数是外层网站功能，README 明确不配 Supabase 时提取仍可运行。我们只需要评估 provider，不需要部署收费/账号网站；它返回地址而非持久媒体文件。现有离线测试覆盖图片过滤、格式排序；live 测试为显式开启，存在测试文件不代表我们已运行成功。[README](https://github.com/realerikk0/haodown)、[可选 live 测试](https://github.com/realerikk0/haodown/blob/cff6316d405c1494daf34b5832dc94e00b743614/tests/live/toutiao.live.test.ts)。

**分级：独立视频和微头条图片技术备选。** 若采用，浏览器生命周期、项目登录态、请求预算和下载阶段都需要接入既有边界；比纯 HTTP 微头条组件的适配面更大。

## 5. 通用新闻正文工具及已排除的混淆项

### GNE 与 Newspaper4k

- [GNE 0.4.3](https://github.com/kingname/GeneralNewsExtractor/releases/tag/v0.4.3) 官方明确输入是渲染后的 HTML，输出标题、发布时间、作者、正文、图片 URL，自己不请求网页。README 有头条新闻测试声明与旧截图，但没有当前头条真实验收，也没有微头条专用处理。可以和项目浏览器组合验证文章；不能独立完成“给 URL 就补全”。[README](https://github.com/kingname/GeneralNewsExtractor)。
- [Newspaper4k 0.9.6](https://github.com/AndyTheFactory/newspaper4k/releases/tag/0.9.6)，2026-07-19，提供 HTTP 获取和新闻正文/作者/时间/图片等抽取，支持中文。默认请求不是 JS 渲染；官方对复杂页面建议另用 Playwright/Selenium。没有此次需要的微头条、头条视频原生实现，故只作通用正文备选。[功能](https://github.com/AndyTheFactory/newspaper4k)、[外部浏览器说明](https://github.com/AndyTheFactory/newspaper4k/blob/master/docs/user_guide/advanced.rst#L591-L678)。
- [Mozilla Readability](https://github.com/mozilla/readability) 也属于 DOM 正文提取器。对本轮而言，增加第三个通用解析库不会自动解决头条页面获取或微头条数据识别，因此不列为首批依赖。

### 名称接近，但不能作为独立补全能力证据

| 项目 | 实际证据 | 本轮处理 |
| --- | --- | --- |
| [you-get](https://github.com/soimort/you-get/blob/049548f3f3f35e67ba8d3181c71fdc71d11cf260/src/you_get/extractors/toutiao.py) | 旧 `videoId` 正则与 `ib.365yg.com` 接口，可下载视频；HEAD 为 2025-04-27，缺文章和微头条 | 视频低优先级历史对照，不能替代正文组件 |
| [05020050zj/toutiao-downloader](https://github.com/05020050zj/toutiao-downloader) | Android/Kivy 包装，README 指明视频引擎为 yt-dlp；核验 HEAD 为 2026-05-16 | 不算另一套独立头条解析引擎 |
| [GitLqr/LQRArticlePatch](https://github.com/GitLqr/LQRArticlePatch) | Android 文章图片/视频下载应用，最后提交为 2017-04-10 | 年代久远，非当前首选 |
| [reycrawler](https://github.com/reyxbo/reycrawler-py/blob/424798bb8613f61d80007bd1f7849709ac8e1b64/src/reycrawler/rtoutiao.py) | 头条模块只有热榜 title/url/image 等，2026-09-05 更新不等于具备全文接口 | 排除全文/媒体补全候选 |
| [tamnd/toutiao-cli](https://github.com/tamnd/toutiao-cli) | README 明确当前是 fresh scaffold，只有 version 命令框架 | 排除实际补全候选 |
| [头条号运营 MCP](https://github.com/SuperWangYuan/toutiaohao-mcp-server) | 主要面向自己创作者后台的发布、管理、运营数据和历史列表 | 不把“微头条发布/自有历史”算作任意来源 URL 获取 |
| [TikHub 头条 SDK](https://github.com/TikHub/TikHub-API-GoLang-SDK/blob/main/docs/ToutiaoWebAPIApi.md) | 文章/视频接口是 bearer 鉴权的第三方服务 SDK | 不等于本地开源获取器；本轮未选用，也未核查/购买其套餐 |

## 下一步验证边界

建议在后续明确启动实施/验证后，用少量代表性样本验证下列组合；本轮未执行：

1. **长文章**：NewsCrawler 专用适配与 Trafilatura 比较正文完整性，覆盖长段落、标题、列表、图文、嵌入视频；检验原始 HTTP 返回的是全文还是壳页面。应优先验证现成组件，观察到具体缺口后再决定是否补最小适配。
2. **微头条**：HunterWangwei 单条方法验证纯文本、多图、带表情、作者/时间和删除/限制内容；确认缺图是部分结果，不把空正文视为成功。微头条视频不在现有代码证据内，须单独判断，不要与独立视频混同。
3. **独立视频**：yt-dlp 验证不同清晰度、完整音轨、元信息、Cookie 缺失、暂停、中止和续作；haodown 作为有具体代码的对照，不默认多工具无限串联。
4. **采用门槛**：将许可明确的组件与仅公开源码的技术候选分开；补上版本固定、受控请求、对应平台登录态、完整性标记和媒体缓存适配。候选网站自身的评论抓取、主页遍历、自动更新和内容过滤均不应扩展本任务范围。

调查得到的是“有可验证的具体工具组合及剩余缺口”。当前证据既不支持承诺三种头条内容全部即插即用，也不支持以“没找到工具”为由把全文获取预先定成全部自维护。
