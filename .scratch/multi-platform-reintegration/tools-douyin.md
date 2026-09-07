# 抖音单作品 URL 补全工具核查

后续更新：本文保留实测前的源码调查快照。2026-09-06 已完成独立样本试验，当前可用性、失败证据与选型调整以[实测记录](real-validation.md)为准。

核查日期：2026-09-06（Asia/Shanghai）。范围：官方仓库、固定提交源码、Release 与上游 Issue；只读下载源码进行静态检查，没有安装/导入运行这些组件，没有登录或请求抖音，没有使用仓库中附带的 Cookie。以下“支持”指代码具有对应能力，不代表已在当前平台验证成功。

## 建议顺序

| 结论 | 候选 | 判断 |
| --- | --- | --- |
| 优先做受限单作品验证 | F2 | 有明确的单作品详情与图集/视频下载代码，本地签名，字段覆盖最接近需求；但最新正式版较老，存在近期失败反馈，不能直接承诺接入成功。 |
| 备用验证 | Evil0ctal/Douyin_TikTok_Download_API | URL→详情→媒体的服务接口较完整，适合比较结果；也使用本地 a_bogus 与 Cookie，和 F2 不是完全独立的成功路径，且原服务缺少本项目所需网络/日志边界。 |
| 暂不作为开箱即用主选 | DouK-Downloader / TikTokDownloader | 功能覆盖完整，但维护者明确宣布加密参数算法已失效且不再维护；当前默认签名甚至返回固定值，需要另找签名实现。 |
| 不适合作为本次完整抖音补全主选 | yt-dlp | 视频元数据/下载基础成熟，但抖音详情长期有 open 的 Cookie 失败问题，当前 extractor 仍留有签名 Cookie 的 TODO，且不覆盖抖音图片集。 |
| 仅作为分享页替代路线参考 | zyipeng/video-downloader | 存在不走详情签名 API 的分享页脚本，但只提取页面标题/视频地址，没有正文/作者/时间/互动/图片集的完整投影，也缺少稳健预算和错误分类。 |

这是**验证优先级**，不是已选定实现。应先比较正常视频、图片集、长文案、需要登录、删除/无权限作品等样本的详情与真实媒体结果，再确定组件。不能把 README 的“支持抖音”作为验收证据。

## 1. F2

### 版本与维护证据

- 官方仓库 [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2)，Apache-2.0。
- 核查固定提交 [`7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3`](https://github.com/Johnserf-Seed/f2/commit/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3)，默认分支最新提交时间为 2025-10-12，内容为 README 赞助信息更新。仓库 push 时间不是抖音功能最近修复时间。
- GitHub 最新正式发布是 [v0.0.1.7](https://github.com/Johnserf-Seed/f2/releases/tag/v0.0.1.7)，发布时间 2024-12-31 UTC（中国时间 2025-01-01）；发布说明已经提示动图作品接口维护。
- [Issue #281](https://github.com/Johnserf-Seed/f2/issues/281) 是使用 `one` 模式下载部分作品失败的报告；目前已关闭，不能据此断定已修复。[Issue #443](https://github.com/Johnserf-Seed/f2/issues/443) 在核查当日仍 open，反映点赞列表翻页后 403，属于维护风险旁证，不是“单作品全部失效”的证据。

### 单作品入口与字段

- `AwemeIdFetcher.get_aweme_id(url)` 处理作品 URL / 分享短链；`DouyinHandler.fetch_one_video(aweme_id)` 返回 `PostDetailFilter`；`_to_raw()` 可保留上游原始详情。官方 [单作品示例](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/docs/snippets/douyin/one-video.py) 明确要求提供自己的 Cookie。
- `handle_one_video` (`one` 模式) 还会获取/保存作者资料、写 F2 数据库、调用下载器，不能把整个 CLI 当成“仅一个详情请求”。较小的集成入口是 `DouyinCrawler.fetch_post_detail(PostDetail(...))`，再使用组件下载器并受应用边界约束。见 [handler.py L237-L310](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/handler.py#L237-L310)、[crawler.py](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/crawler.py)。
- `PostDetailFilter` 具体提供 `desc_raw` / `caption_raw`、作者 ID / 昵称、`create_time`、点赞/评论/收藏/分享统计、图集 URL、实况图片对应视频 URL、视频码率和播放 URL。播放量字段被注释，不应承诺该接口提供。发布文案不是视频音轨转录。见 [filter.py L1052-L1432](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/filter.py#L1052-L1432)。
- 下载器按视频或图集分支保存 MP4 / WebP，另有描述、封面、原声下载开关；图集还处理实况附带视频。见 [dl.py L101-L255](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/dl.py#L101-L255)。代码中字段路径存在，不代表图片张数、长文案完整性或视频声音已经验证。

### 凭据、签名与限制

- 详情请求使用调用方传入的 Cookie，与匹配的 User-Agent；签名调用仓库内本地 `ABogus` / `XBogus`。静态调用路径未发现必须购买第三方签名服务或 TikHub API Key 的要求；README 赞助链接不是技术依赖。见 [crawler.py L92-L104](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/crawler.py#L92-L104)、[utils.py](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/utils.py)。
- **导入时就可能发网**：`BaseRequestModel` 的类属性初始化调用 `TokenManager.gen_real_msToken()`；“只实例化 SDK，不执行 fetch”不是天然无网络操作。Token 生成另有向平台相关域名的请求。见 [model.py L10-L41](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/apps/douyin/model.py#L10-L41)。
- `max_tasks`、`max_connections`、`max_retries`、`timeout` 可配置；默认任务/连接 10、重试 5、超时 10 秒。业务重试用 `range(max_retries)`，底层传输还重试，所以不能简单设 `max_retries=0` 并假定“请求一次不重试”。默认 transport 显式 `verify=False`，没有应用级域名/总请求/总字节控制。见 [base_crawler.py L94-L170](https://github.com/Johnserf-Seed/f2/blob/7dab3e2ffffaa2535834d28fca99dbc2e89fa9d3/f2/crawlers/base_crawler.py#L94-L170)。
- 集成负担：受限网络桥接、分离导入期 Token 请求、专用会话 Cookie 注入、关闭 Bark 通知/默认配置副作用、避免 F2 自有数据库和额外作者请求、规范化原始字段、逐项媒体清单、失败分类。不是仅包一层 shell 就能符合现有微博组件边界。

## 2. Evil0ctal/Douyin_TikTok_Download_API

### 版本、接口和覆盖

- 官方仓库 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)，Apache-2.0；核查提交 [`42784ffc83a72a516bfe952153ad7e2a3998d16c`](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/commit/42784ffc83a72a516bfe952153ad7e2a3998d16c)，2025-10-12；最新发布 [V4.1.2](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/releases/tag/V4.1.2)，2025-03-16，发布修复重点为 TikTok 主页接口，不可当作当前抖音验证。
- 有单作品 HTTP 接口 `/api/douyin/web/fetch_one_video?aweme_id=...`，也有 URL 混合解析 `/api/hybrid/video_data?url=...&minimal=...`。底层是 `DouyinWebCrawler.fetch_one_video(aweme_id)`，本地 a_bogus → 抖音详情 API。见 [douyin_web.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/app/api/endpoints/douyin_web.py)、[hybrid_parsing.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/app/api/endpoints/hybrid_parsing.py)、[web_crawler.py L88-L110](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/douyin/web/web_crawler.py#L88-L110)。
- 混合解析 `minimal=False` 返回原始作品详情；精简输出包含 `desc/create_time/author/statistics`、视频地址或图片列表；图片类型识别包括 2、68。视频 URL 还会按 URI 拼接/替换播放地址，因此“解析返回非空 URL”和“已验证媒体成功”应分开。见 [hybrid_crawler.py L69-L207](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/hybrid/hybrid_crawler.py#L69-L207)。
- `/api/download` 会下载视频或图集，图片打成 zip，已有实际下载实现；但本项目需要逐媒体交接/哈希/完整度，不能直接把 zip 成功当作每张图片验证成功。见 [download.py](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/app/api/endpoints/download.py)。

### 维护风险与适配边界

- 官方 README 要求替换为自己的抖音 Cookie，建议已登录 Cookie，并明确 Demo 下载已关闭、Demo 抖音解析不保证可用。仓库示例配置存在非空 Cookie，不可依赖或复用。TikHub 是被推荐的独立服务，已检查的本地抖音路径不要求其 API Key。见 [README 运行说明](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/README.md#L330-L343)。
- [Issue #734](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/issues/734) 2026-07-27 报告短视频解析失效；[Issue #720](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/issues/720) 报告详情有多个视频地址、首地址 403、其他地址可用。这是未复现的用户报告，不是全站失效定论，但证明需验真实媒体而不只看 JSON。
- 基类有重试/并发/超时参数，默认重试 3、并发 50；单作品封装直接构造默认 `BaseCrawler`，没有把预算透传到公开接口。模型类属性同样会在导入时获取 msToken。见 [base_crawler.py L61-L102](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/base_crawler.py#L61-L102)、[models.py L1-L42](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/douyin/web/models.py#L1-L42)。
- `update_cookie` 会打印新旧 Cookie 并写配置；原下载实现未见应用级总字节预算。应替换凭据注入/日志和传输控制，不应直接照部署整个 API 服务。见 [web_crawler.py L351-L365](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/42784ffc83a72a516bfe952153ad7e2a3998d16c/crawlers/douyin/web/web_crawler.py#L351-L365)。
- F2 与本项目同样围绕本地 a_bogus、抖音 Cookie、详情 API 工作。换到这个候选可能解决某个适配问题，但不能假定签名失效时两个工具一定互补。

## 3. DouK-Downloader / TikTokDownloader

- 官方仓库 [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)，GPL-3.0；固定提交 [`078e0537faa6bdc11458355b1e88b9ee9f5a07e9`](https://github.com/JoeanAmier/TikTokDownloader/commit/078e0537faa6bdc11458355b1e88b9ee9f5a07e9) 为 2026-08-29 FileNotFoundError 修复；最新发布 [5.7](https://github.com/JoeanAmier/TikTokDownloader/releases/tag/5.7) 为 2025-08-19。近期通用修复不能证明抖音签名仍可用。
- 当前 [README L22-L23](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/README.md#L22-L23) 明确警告部分功能失效、计划 6.0 重构；加密参数算法过期且不再维护，使用者要自行准备生成实现。
- 静态源码印证该警告：`DouYinParams.sign()` 注释掉本地计算，当前返回固定 `a_bogus` 字符串。不是缺一个 Cookie 就完整可用。见 [douyin_params.py L16-L32](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/encrypt/douyin_params.py#L16-L32)。
- 单作品代码仍清楚：`Detail(..., detail_id=...).run(single_page=True)` 请求 `aweme/v1/web/aweme/detail/`；HTTP `POST /douyin/detail` 接受作品 ID、可选 Cookie 和代理，支持原始/处理结果模式。URL 需先提取 ID，完整下载由另外的下载流程处理。见 [detail.py](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/interface/detail.py)、[main_server.py L193-L212](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/application/main_server.py#L193-L212)。
- 提取器有描述、发布时间、作者、点赞/评论/收藏/分享统计、图集/实况图/视频码率选择，下载器支持媒体和断点续传。见 [extractor.py L285-L352](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/extract/extractor.py#L285-L352)、[extractor.py L411-L535](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/extract/extractor.py#L411-L535)、[download.py](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/downloader/download.py)。
- `max_retry=0` 在此工具中表示最后执行一次、没有额外重试；单页模式不会遍历用户主页；`max_size` 控制文件大小，`timeout` 可设。仍无涵盖签名/Token/重定向/媒体的统一总请求预算，需要包住其 curl_cffi 传输层。见 [retry.py](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/tools/retry.py)、[template.py](https://github.com/JoeanAmier/TikTokDownloader/blob/078e0537faa6bdc11458355b1e88b9ee9f5a07e9/src/interface/template.py)。
- 没有证据表明必须购买特定第三方付费服务，但**需要自行解决有效签名来源**。这直接增加维护负担，当前不应列作“现成且可直接复用”的优先组件。将来上游 6.0 或明确可复现的签名适配出现后再评估。

## 4. yt-dlp

- 官方仓库 [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)，Unlicense；最新正式版 [2026.08.19](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19)，核查源码提交 [`bbc809a1161d3bfca51fa36f59dda35556ee85a0`](https://github.com/yt-dlp/yt-dlp/commit/bbc809a1161d3bfca51fa36f59dda35556ee85a0) 为 2026-08-30。
- `DouyinIE` 只匹配 `douyin.com/video/<id>`；请求详情后使用通用视频提取，能输出完整 `description`、发布时间、作者、互动统计与可下载格式。当前 `DouyinIE` 没有抖音图片集 `/note/` 入口或图片集资产投影。见 [tiktok.py L1371](https://github.com/yt-dlp/yt-dlp/blob/bbc809a1161d3bfca51fa36f59dda35556ee85a0/yt_dlp/extractor/tiktok.py#L1371)、[字段提取 L515-L545](https://github.com/yt-dlp/yt-dlp/blob/bbc809a1161d3bfca51fa36f59dda35556ee85a0/yt_dlp/extractor/tiktok.py#L515-L545)。
- 抖音 `_real_extract` 仍只带 aweme_id 请求详情，没有当前 a_bogus 生成路径；取不到详情时提示新 Cookie，代码保留签名 Cookie TODO。[长期问题 #9667](https://github.com/yt-dlp/yt-dlp/issues/9667) 在核查日仍 open（有用户报告提供新 Cookie 后仍失败）。因此否定主选的依据来自 yt-dlp 自身源码/Issue，而不是另一下载器的营销宣称。见 [tiktok.py L1495-L1508](https://github.com/yt-dlp/yt-dlp/blob/bbc809a1161d3bfca51fa36f59dda35556ee85a0/yt_dlp/extractor/tiktok.py#L1495-L1508)。
- 已有程序化 `YoutubeDL.extract_info(url, download=...)`、CLI JSON 元数据、单条/禁止播放列表、文件大小、socket timeout、各层重试参数；可禁浏览器自动取 Cookie，注入项目专用会话。它适合作为已拿到真实视频 URL 后的下载基础备选，但这个用途不补上正文/图集，也不能解决抖音详情本身失败。见 [官方 README 参数](https://github.com/yt-dlp/yt-dlp/blob/bbc809a1161d3bfca51fa36f59dda35556ee85a0/README.md#L455-L568)。

## 5. zyipeng/video-downloader：只保留分享页路线线索

- 官方仓库 [zyipeng/video-downloader](https://github.com/zyipeng/video-downloader)，MIT；固定默认分支 [`ebdbf9e444ea4a18fab2442b50b519ed2b268615`](https://github.com/zyipeng/video-downloader/commit/ebdbf9e444ea4a18fab2442b50b519ed2b268615)，仓库 API 返回 push 时间 2026-06-02；仓库首页仅显示 6 次提交，未显示正式 Release。
- [download-douyin.sh](https://github.com/zyipeng/video-downloader/blob/ebdbf9e444ea4a18fab2442b50b519ed2b268615/scripts/download-douyin.sh) 从长/短 URL 提取 aweme_id，以 iPhone UA 访问 `iesdouyin.com/share/video/<id>/`，正则解析 `<title>` 与 `play_addr`，然后下载视频。该脚本没有使用 Cookie 或付费签名服务，是与详情 API 不同的路径。
- 但它没有结构化提取发布正文、作者、时间、互动或图片集；probe JSON 的 uploader/upload_date 直接为空。它改写播放 URL 的清晰度参数，而不是从已核验媒体中确认每档；不应继承其“原画/1080p/720p”声明作为事实。
- 下载默认 aria2c 16 路或 curl；页面/下载调用没有统一时长/字节上限，失败后还会自动换 URL；没有内容身份/媒体真实性验证。因此只能参考 SSR 解析路线，不能作为满足本项目要求的成品补全组件。将它补到满足本项目需求接近重新实现适配器。

## 与当前微博组件边界的衔接

这批工具提供了可复用的详情请求、正文投影与下载代码；它们都没有直接提供本项目现有的“单条受控网络桥接＋专用 Cookie 域隔离＋媒体清单＋人工暂停恢复＋脱敏诊断”合同。若验证通过，下一步应复用组件的请求/下载能力并施加这层合同，不应将 URL 转交外部在线解析站，也不应默认读取日常浏览器登录态。

候选依赖本地签名，不等于它永远可用；存在 TikHub 赞助，不等于必须付费。当前调查不能证明任何候选已完成四平台全链路或抖音真实媒体验收。使用者尚未选择实现前，此文只记录候选与证据，不修改运行时依赖或下载器选择。
