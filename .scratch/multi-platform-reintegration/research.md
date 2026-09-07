# 多平台接入事实核查

Status: researched

核查日期：2026-09-06。只读本地代码、Git 历史、官方仓库与源码；未安装或运行下载器，未登录或访问真实平台内容。下列候选未完成真实样本验证，不是最终选型。

用户要求先认真核查现成补全工具后，调查已扩展到单 URL 调用链和具体返回字段。首轮名单不完整，尤其不能根据当时只找到 NewsCrawler 和 yt-dlp 就推断头条需要从零实现。优先阅读[候选与验证顺序](tool-shortlist.md)，扩展调查分别见：

- [小红书与快手专用工具](tools-xhs-ks.md)
- [抖音候选比较](tools-douyin.md)
- [头条文章、微头条与视频候选](tools-toutiao.md)
- [跨平台解析器比较](tools-common.md)

这些记录区分“源码存在能力”“值得优先验证”和“实际 URL 已成功”，不以 README 或仓库活跃度代替原站验收。

## 当前应用的复用基础与限制

- 微博流程是浏览器发现并去重入库，选材生成报告时按需补全，随后逐条理解和报告汇总。依据：`services/native_weibo.py`、`services/search_runs.py`、`services/manual_content.py`、`services/content_analyses.py`、`services/report_generations.py`。
- `gallery-dl==1.32.10` 在子进程中执行微博获取器，应用通过请求桥接控制网络、凭据、预算和缓存。现有版本校验、获取器选择、域名限制、Cookie 读取与媒体投影均包含微博专属行为，不能扩枚举后直接使用。依据：`backend/pyproject.toml`、`gallery_worker.py`、`services/gallery_component.py`、`services/native_chrome.py`、`services/weibo_enrichment.py`。
- `EnrichedContent` 目前承接正文和媒体及完整度/问题记录，不承担作者、时间和互动统计的完整补全。需要扩展结果投影，不能把“沿用现有互动字段”解释成现有下载链路已自动更新它们。
- 当前每条内容总媒体预算为 6 MiB，最多 24 图、1 视频；就绪媒体限定为 JPEG/PNG/WebP 及含音轨 MP4。视频平台是否真实可用不能只用正文成功验证。依据：`services/enrichment_models.py`。
- 视频还限定 30 秒以内、1080p 以内、单 H.264 视频流及 AAC 音轨；经 ffprobe 校验和实际解码计数后，完整 MP4 以 base64 video_url 进入模型，音轨留在容器中。现有媒体路径要求指定的 DashScope Omni 模型，AI 客户端另限制请求体小于 9,000,000 字节；不能只提高下载大小。依据：`services/video_probe.py`、`services/ai_analysis.py`、`services/ai_client.py`。
- 手动报告禁止仅靠搜索摘要兜底；一些其他分析分支仍允许摘要兜底，因此五平台自动流程的验收不能依赖摘要假成功。部分条目成功可以继续汇总，零成功总结不能生成正常报告。
- 人工暂停占用全局浏览器租约，恢复入口还包含微博专属调用；保留整批暂停规则也必须将恢复目标改为实际受阻平台。
- 目前搜索批次将一般非成功尝试也转为人工暂停，普通平台失败自动继续是新增行为。自动任务已有 completed_with_failures 后继续分析的基础，可保留失败/跳过前取得的发现；目前报告覆盖说明只描述已选条目的处理和媒体缺口，没有平台/关键词采集缺口快照。若确认普通失败继续且报告列明缺口，需要同时扩展批次状态分流及报告中的采集范围证据，不能只改文案。依据：`repositories/search_batches.py`、`services/automation_workflows.py`、`repositories/automation_workflows.py`、`services/topic_report_engine.py`、`schemas/topic_reports.py`。
- 当前没有手工粘贴 URL 入库产品入口。`manual_content.py` 中 manual 指手动报告流程。

## 数据与平台约束

- 删除提交为 `b427094 feat(platform): narrow product to native Weibo`，父版本平台目录列出 `wb/dy/ks/xhs/toutiao`。
- v26 清理非微博业务图，并将六张平台表收紧为仅微博，增加对应写入保护；新接入需要前向迁移，不能改写历史迁移来跳过已完成的清理。
- 当前批次平台数量和条目位置、自动任务平台、采集能力目录、前端选项和校验均限定微博。相关文件：`search_platforms.py`、`schemas/search_batches.py`、`schemas/automation_workflows.py`、`services/collector_contracts.py`、`migrations/weibo_only_v26.py`、`migrations/search_run_status_v28.py`。
- 当前测试 `test_weibo_only_product.py` 和 `test_weibo_only_migration.py` 可作为约束变更与历史数据保留的回归基础；旧四平台代码曾存在不代表其今天可运行。

以上未带 backend 前缀的 Python 路径均相对 `backend/src/longtian_api/`。

## 首轮下载器候选（后续扩展见上方专项记录）

| 平台 | 候选与已查到的能力 | 尚未证明或需要适配的部分 |
| --- | --- | --- |
| 小红书 | XHS-Downloader 接受作品 URL/短链，提供标题、文案、作者、时间、互动数及图片/视频下载。 | 部分 URL 依赖发现时的访问参数，统计与时间可能缺失；真实可用性仍需验证。 |
| 抖音 | DouK-Downloader 声明单作品数据、视频/图集及本地 API；F2 有单作品 URL 解析、详情提取和下载链路。 | DouK 官方仍提示部分功能及参数算法失效；F2 的当前单作品成功率和请求可控性未实测。 |
| 快手 | KS-Downloader 提取描述、作者、时间、下载地址和部分互动数，并下载图片/视频。 | 不同提取分支字段不同，统计存在未知缺省值；不能承诺每种 URL 或全部统计可用。 |
| 今日头条 | yt-dlp 有专门视频提取器；NewsCrawler 有文章路径识别与正文/媒体地址提取代码。 | yt-dlp 不提取文章全文；NewsCrawler 的正文处理可能漏掉嵌套结构，未证实全文完整或微头条支持，不能作为开箱即用方案。 |

官方依据：

- 小红书：[官方项目](https://github.com/JoeanAmier/XHS-Downloader)、[字段提取](https://github.com/JoeanAmier/XHS-Downloader/blob/master/source/application/explore.py)。部分统计缺失用 `-1` 表达；接入时应转换为未知，不能作为真实计数。
- 抖音：[DouK-Downloader 官方说明及失效提示](https://github.com/JoeanAmier/TikTokDownloader)、[详情接口](https://github.com/JoeanAmier/TikTokDownloader/blob/master/src/interface/detail.py)、[F2 单作品调用链](https://github.com/Johnserf-Seed/f2/blob/main/f2/apps/douyin/handler.py)、[F2 字段](https://github.com/Johnserf-Seed/f2/blob/main/f2/apps/douyin/filter.py)。F2 的部分其他流程有问题报告，不能据此外推单作品全部失效，也不能据字段代码推断单作品已可用。
- 快手：[官方项目](https://github.com/JoeanAmier/KS-Downloader)、[提取源码](https://github.com/JoeanAmier/KS-Downloader/blob/master/source/extract/extractor.py)。分享量等字段有未知缺省；媒体获取成功不等于信息完整。
- 今日头条：[yt-dlp 视频适配](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/toutiao.py)、[NewsCrawler](https://github.com/NanmiCoder/NewsCrawler)、[文章提取源码](https://github.com/NanmiCoder/NewsCrawler/blob/main/.claude/skills/news-extractor/scripts/crawlers/toutiao.py)。NewsCrawler 仅遍历特定正文直接子节点，并存在固定 Cookie 常量；深入核查显示不能据常量存在就断言其默认 run() 启用了该值，具体取决于头部模型选择，详见头条专项记录。yt-dlp 可能自行请求游客标识，接入时仍须纳入请求控制。

## 实施前仍须取得的事实

- 各平台实际搜索排序、分页、作品类型与登录障碍页面。
- 平台内容身份和访问 URL 的区别：去重不依赖临时参数，但下载仍可能需要它；不能因归一化误删必要访问上下文，也不能将其写入诊断日志。
- 各候选的版本、单作品覆盖、取消/恢复、预算与必要登录态作用域；全文和媒体完整性必须由代表性样本证明。
- 视频原始文件、预处理及模型请求分别需要的资源预算。

这些是事实验证工作，不是要求用户给出底层参数；不因未实测而宣称已选型或完成平台接入。
