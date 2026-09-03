# 通过内容 URL 委托开源组件获取内容：调研记录

Status: open
Type: research

核查日期：2026-09-03。仅核对公开官方仓库、文档和源码；没有安装、运行、登录或实测任何下载器，没有向平台发起采集请求。

## 范围与边界

- 首批实现范围是微博；小红书只查公开项目资料，不作为新采集层的试验对象。
- 第一版数据目标是搜索结果、正文、图片和视频，不采集评论。
- 需要区分“内容 URL → 正文、元数据、媒体地址”的内容解析，与“媒体地址 → 本地文件”的文件下载。被称为下载器的项目可能同时包含这两种职责。
- 从内容 URL 解析信息往往仍需请求平台网页或私有接口，可能需要 Cookie，并产生额外请求；不是发现链接后就不再依赖平台。
- 活跃提交或支持列表只证明维护/声明情况，不能证明当前样本可用、完整、无需账号或不触发风控。
- 候选名单不等于选型决定。请求范围、隐式登录/重试、凭证边界、输出完整性、暂停恢复、文件校验、版本固定和许可证分发义务都需要单独审核。

## 微博候选

### gallery-dl：优先核验的帖子级提取候选

- 微博适配器支持单帖 URL，获取帖子数据，输出正文元数据及图片、视频地址；支持仅输出 JSON/地址，文件下载可以另行处理。仅输出地址并不等于取得正文；需要读取结构化元数据。
- 单帖流程调用私有 AJAX 接口，并请求长文本；没有据此证实能够完整提取微博“头条文章”的正文。默认跳过转发，部分媒体类型也存在限制；不可将工具退出成功等同于产品内容完整。
- 源码中即使没有媒体文件，也会输出帖子级元数据消息；纯文本帖、长微博、转发、图文混合和视频帖仍需作为不同样本核验，尚未进行实际测试。
- 有 Cookie 识别和自动游客会话流程；遇到 `passport` 跳转会发起额外会话请求并重试原请求。默认 HTTP 重试为 4 次，429 默认等待 60 秒。把通用重试设为零也不能关闭所有适配器内置请求，原样调用不满足本项目的受控暂停要求。
- 维护信号：v1.32.10 发布于 2026-08-29；公开问题中仍有账号页面 403 报告，该问题不等于所有单帖失效，也不能据发布活跃断言可用。
- 许可证为 GPL-2.0。子进程调用是可选技术边界，不替代实际分发方式的许可审核。
- 来源：[微博适配器](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/weibo.py)、[输出选项](https://github.com/mikf/gallery-dl/blob/master/docs/options.md)、[配置说明](https://github.com/mikf/gallery-dl/blob/master/docs/configuration.rst)、[许可证](https://github.com/mikf/gallery-dl/blob/master/LICENSE)、[v1.32.10](https://github.com/mikf/gallery-dl/releases/tag/v1.32.10)、[账号页面 403 问题](https://github.com/mikf/gallery-dl/issues/8541)。

### yt-dlp：视频辅助候选，不是完整帖子采集器

- 微博适配器支持帖子及视频页面 URL，通过平台私有接口取得视频格式、封面、作者、互动量及描述；混合媒体处理中明确排除图片，描述字段也不是完整长文的保障。
- 可用 Python 或 CLI 先提取信息、再下载视频。也存在自动游客会话请求；默认下载/分片重试为 10 次，提取重试为 3 次，不能直接沿用默认运行行为。
- 维护信号：最近发布为 2026.08.19。源码及 wheel 使用 Unlicense，部分打包执行文件为 GPLv3+，要按最终使用的制品核对。
- 来源：[微博适配器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/weibo.py)、[官方集成及许可说明](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)、[2026.08.19](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19)。

### WeiboSpider：专用解析对照

- 按帖子 ID 获取正文，长文本另行请求，提供图片/视频 URL 与元数据；JSONL 管线不负责下载媒体。
- 要求 Cookie，基于 Scrapy，默认并发为 16；不是现成的受控单帖下载组件，也没有本产品的人工暂停协议。
- MIT 许可。2026 年可见提交主要是 README，核心目录最近提交为 2024-02-15；不因文档更新将其判为适配维护活跃。暂作字段解析参考，不优先选用。
- 来源：[单帖实现](https://github.com/nghuyong/WeiboSpider/blob/master/weibospider/spiders/tweet_by_tweet_id.py)、[字段解析](https://github.com/nghuyong/WeiboSpider/blob/master/weibospider/spiders/common.py)、[核心目录提交](https://github.com/nghuyong/WeiboSpider/commit/d4596f872eef1680220e5bf6d9984b20efa982de)。

### 初步判断（推断，未选型）

用户提出的职责拆分可行，但不等于原样运行任意下载器。优先核验 gallery-dl 的单帖提取，只有存在明确视频能力缺口时才评估 yt-dlp，避免一开始增加多套依赖。

自有层需要控制输入内容范围、请求/重试预算、凭证和人工暂停，将提供方输出转成产品模型并校验。若工具的内置请求不能受控，或为接入而需要长期大幅修改其内部，应放弃该候选；否则只是把维护用户 fork 的负担换了一个仓库。严格全浏览器访问与允许外部组件解析帖子是不同路线；Q8 已接受后一种受控混合方式，具体组件与凭证边界仍未确认。

## 小红书：XHS-Downloader

- 官方项目支持作品 URL/分享链接解析为标题、描述正文、作者、时间、互动信息、媒体下载地址，并下载图片或视频；提供终端、Python 调用及本地 HTTP API 等接入方式。
- 已有“浏览器脚本收集作品链接 → 推送本地下载器”的流程，直接支持用户提出的职责拆分。
- 主体使用 `curl_cffi` 请求网页并解析，不是通过 Chrome 的页面操作完成所有获取。Cookie 标为可选，但清晰度和成功率可能受其影响；链接受限等情况仍可能失败。
- 维护信号：2.7 发布于 2026-02-09，2026-08-29 有下载相关修复提交。许可证为 GPL-3.0，不能把本地子进程调用简单等同于没有分发义务。
- 来源：[官方 README 与接口](https://github.com/JoeanAmier/XHS-Downloader)、[内容解析源码](https://github.com/JoeanAmier/XHS-Downloader/blob/master/source/application/explore.py)、[网页请求源码](https://github.com/JoeanAmier/XHS-Downloader/blob/master/source/application/request.py)、[2.7 发布](https://github.com/JoeanAmier/XHS-Downloader/releases/tag/2.7)、[2026-08-29 提交](https://github.com/JoeanAmier/XHS-Downloader/commit/3a8849c7afb215085b32da84bcdbeb7c6d26880e)。

## 抖音：DouK-Downloader / TikTokDownloader

- 功能声明包括作品 URL 对应视频/图集、描述与元数据，以及文件、数据库或本地 Web API 输出。
- 依赖 Cookie 和平台私有详情接口。官方 README 明确警告部分功能失效、参数算法失效且停止维护，计划重构；因此不能因最近仍有提交就认为当前功能稳定可用。
- 许可证为 GPL-3.0。暂不作为已经可直接接入的确定选型。
- 来源：[官方 README 和失效警告](https://github.com/JoeanAmier/TikTokDownloader)、[详情接口](https://github.com/JoeanAmier/TikTokDownloader/blob/master/src/interface/detail.py)、[2026-08-29 提交](https://github.com/JoeanAmier/TikTokDownloader/commit/078e0537faa6bdc11458355b1e88b9ee9f5a07e9)。

## 快手：KS-Downloader

- 官方项目提供作品 URL 对应视频/图片、描述、作者、时间、媒体地址和部分统计，并提供终端及本地 API。
- 主要流程是 HTTP 获取 HTML 后解析内嵌数据，不是浏览器页面驱动；Cookie 等环境因素仍需按实际访问结果评估，不能泛化为永远免登录。
- 维护信号：1.6 发布于 2026-07-05。许可证为 GPL-3.0。
- 来源：[官方 README](https://github.com/JoeanAmier/KS-Downloader)、[字段提取源码](https://github.com/JoeanAmier/KS-Downloader/blob/master/source/extract/extractor.py)、[调用链](https://github.com/JoeanAmier/KS-Downloader/blob/master/source/app/app.py)、[1.6 发布](https://github.com/JoeanAmier/KS-Downloader/releases/tag/1.6)。

## 今日头条

本次尚未证实上述工具支持本项目所需的头条正文与媒体范围；不假定所有平台都有可直接替换的成熟下载器。

## 本地接入需要保留的约束

- 当前微博投影只提取正文/图片候选，视频清单尚未完备；默认媒体域名许可列表中微博为空，实际下载并不等同于候选地址提取成功。
- 当前文件下载与内容投影已经分离，并包含来源校验、大小/时间上限、临时文件管理、媒体类型检查、内容哈希等控制。
- 第三方工具取得文件后仍需满足产品输入契约，不应直接相信其退出码代表正文、图片、视频全部完整。
- 错误不能统一降为结构变化；尤其要把待人工处理、单项缺失、暂时网络故障、无法识别页面分别映射。
- 运行时应限制到已选定内容，不能因一个 URL 自动递归抓取账号、合集或大量其他内容。

## 用户答复后的状态

- Q8 已接受受控混合方式；工具、凭证和失败降级边界待定。
- Q9 已接受部分采集结果进入明确标注缺口的分析。
- Q10 已接受本地内容复用，要求后台提供媒体期限与容量设置；默认值、清理规则和历史引用策略待定。
- Q11 明确实际负载依据现有配置；真实执行限制已核查，详见 `runtime-contract-research.md`，时效与验收目标待定。
