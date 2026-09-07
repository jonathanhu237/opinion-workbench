# URL 内容补全工具候选与验证顺序

Status: probed

2026-09-06 更新。先前的官方资料与源码调查之后，用户已授权并完成一轮独立真实样本试验，详见[实测结果](real-validation.md)。候选尚未正式接入，也未锁定为应用运行时依赖。

## 结论

已有工具可供验证，应先复用它们的单作品获取能力。初查漏掉了跨平台单链接解析器和微头条专用获取器，不能据初查名单就预设需要自写四套补全器。各平台的内容类型及返回字段不同，当前也没有证据支持用一套工具完成全部五平台正文、元数据及媒体补全。

| 范围 | 候选与建议角色 | 选择依据和边界 |
| --- | --- | --- |
| 微博 | 保持现有 gallery-dl | 已有应用链路继续复用，本次不因其他平台选型而重做微博获取器。 |
| 小红书 | XHS-Downloader 优先接入候选 | 实测取得 16 张图片和一条带音轨视频，元数据可提取；关键词搜索 URL 和应用流程仍待验收。 |
| 快手 | KS-Downloader 保留分享图集候选，parse-video-py 作字段对照 | 图集通过缓存续作取得 25 张图片；桌面视频 URL 失败，原工具整帖下载记录会跳过部分失败图集，不能直接沿用完整性判断。 |
| 抖音 | parse-video-py 提升为已取得媒体的候选；F2 本次未通过 | 同一视频用 F2 返回 403，用 parse-video-py 取得文案、作者及带音轨视频；后者的返回结构缺少日期、统计，尚未验证图集。 |
| 头条文章 | 浏览器 HTML + NewsCrawler，Trafilatura 作正文对照 | 普通 HTTP 响应无法提取；原工具解析渲染 HTML 后取得完整正文、作者、时间及图片引用；嵌套正文与嵌入视频仍待验证。 |
| 微头条 | HunterWangwei/ToutiaoCrawler 技术候选 | 实测取得 422 字符正文及 8/8 张图片；许可仍未明确，不作为已确定可分发的正式依赖。 |
| 头条独立视频 | yt-dlp 优先接入候选 | 实测完整下载预算内 360p 视频并确认音轨；本样本缺少 timestamp，且超出现有应用视频预算。 |

官方入口：[XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)、[KS-Downloader](https://github.com/JoeanAmier/KS-Downloader)、[F2](https://github.com/Johnserf-Seed/f2)、[Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)、[parse-video-py](https://github.com/wujunwei928/parse-video-py)、[DouK-Downloader](https://github.com/JoeanAmier/TikTokDownloader)、[NewsCrawler](https://github.com/NanmiCoder/NewsCrawler)、[Trafilatura](https://github.com/adbar/trafilatura)、[ToutiaoCrawler](https://github.com/HunterWangwei/ToutiaoCrawler)、[yt-dlp](https://github.com/yt-dlp/yt-dlp)。这些入口用于导航，具体判断以专项记录链接的固定版本源码为依据。

## 如何决定正式接入

1. 固定候选版本及单作品入口，先用同一批浏览器搜索发现的完整 URL 进行对照，避免只证明 App 分享短链可用。必要访问参数留给获取器，内容身份独立用于去重。
2. 对照原帖正文、作者、时间及图片数量；视频必须真正下载、可解码并保留原有音轨，进入本项目的分析链。仅返回媒体地址、搜索摘要、封面或成功退出均不足以通过。
3. 先验证普通图文/视频，再验证多图部分失败、普通拒绝、登录障碍和续作，确认与现有整批人工暂停、普通失败继续及缓存复用规则一致。
4. 统计缺失按已确认 Q11 显示未知，不阻断报告。任何缺失的正文/媒体须以真实覆盖状态进入分析，不能把工具默认值当成事实。
5. 若候选已能完成获取，只做数据投影和运行控制适配；只有实际验证暴露能力缺口，才评估另一现成候选或必要的专属补全逻辑。头条工具的许可、内容类型和字段限制须同时核清，技术代码存在不等于可直接分发。

## 详细证据

- [小红书与快手](tools-xhs-ks.md)：版本差异、Python/API 入口、返回字段、逐文件结果及网络控制。
- [抖音](tools-douyin.md)：完整字段候选、维护/失效证据及视频提取备选。
- [今日头条](tools-toutiao.md)：全文、微头条和独立视频分别能复用哪些工具。
- [跨平台解析器](tools-common.md)：统一接口的已知字段缺口，及不能据平台矩阵认定完整支持的原因。
- [应用现状](research.md)：已有微博链路、数据库约束及视频输入限制。

设计讨论、工具调查和本轮独立样本试验已完成。五平台产品实施和 AI 全链路验收尚未执行。
