# 小红书、快手 URL 补全组件核查

Status: resolved

后续更新：本文保留实测前的源码调查快照。2026-09-06 已完成独立样本试验，当前可用性、失败证据与选型调整以[实测记录](real-validation.md)为准。
Type: research

核查日期：2026-09-06。范围仅为公开官方仓库、README、源码、发布记录和问题报告；没有安装、执行候选程序，没有登录、访问真实作品或下载媒体。这里的“支持”区分源码已实现与真实环境已验证；后者本次均未验证。分级只安排验证优先级，不是最终选型。

## 结论与候选分级

| 平台 | 分级 | 候选 | 依据 |
| --- | --- | --- | --- |
| 小红书 | 值得优先验证 | XHS-Downloader | 有独立作品入口、结构化文字/元数据、图文和视频下载；字段及下载链可核查。需要控制网络与输出，不能直接把本地 API 成功当作全量完成。 |
| 小红书 | 备用，限视频 | yt-dlp XiaoHongShuIE | 现有视频提取器可交出视频格式、描述和作者 ID；缺作者昵称、发布时间和互动统计，不是完整笔记补全替代品。 |
| 小红书 | 不适合作为当前现成完整组件 | ReaJason/xhs | 有单笔记解析 API，但下载便捷方法与当前签名参数不匹配，最近仓库提交在 2025 年；接口签名和下载整合负担更大。 |
| 快手 | 值得优先验证，但明确缺统计 | KS-Downloader | 有单条 HTML 提取和图集/视频下载链；网页视频分支的评论量与分享量固定为未知，本地 API 本身不下载。 |
| 快手 | 不适合作为完整补全组件 | zyipeng/video-downloader | 快手脚本从整页正则找 MP4；作者与日期固定为空，缺正文和统计，没有图集处理。还存在静态可见的 probe 参数不匹配。 |

没有发现第二个同时具备可靠维护证据、完整快手原帖字段和图文/视频下载能力的独立候选。跨平台 parse-video-py、media-parser、gallery-dl 由另份研究覆盖；这里不重复结论。XHS-Downloader 的 Web UI 派生仓库主要扩展界面、队列、文件服务，没有据此证明形成独立的平台适配备援。[派生项目说明](https://github.com/komens/XHS-Downloader-web)

## XHS-Downloader

### 核查版本与维护证据

- 本次固定源码：[`3a8849c7afb215085b32da84bcdbeb7c6d26880e`](https://github.com/JoeanAmier/XHS-Downloader/commit/3a8849c7afb215085b32da84bcdbeb7c6d26880e)，2026-08-29，增加下载缓冲机制。前一日还有指定图文文件下载的功能提交，不能把这些等同平台访问已通过实测。
- 该源码自标 **2.8 beta**；最新正式发布仍是 [2.7，2026-02-09](https://github.com/JoeanAmier/XHS-Downloader/releases/tag/2.7)。以下以固定源码为准，不能把 master 的新接口或进度回调能力自动归到 2.7。[版本声明](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/module/static.py)
- 2026-09-05 有用户报告配置 Cookie 后闪退/报错，仍开放；这证明存在近期失败报告，不证明全部笔记都不能用，也未确认是当前固定版本的通用故障。[问题 #475](https://github.com/JoeanAmier/XHS-Downloader/issues/475)

### URL → 原帖字段 → 媒体的实际链路

1. `XHS.extract()` 接收文本，提取其中作品链接；短链先 GET 跟随重定向，再请求作品 HTML。支持 explore、discovery/item、用户路径下的单笔记以及 xhslink.com/cn；当前代码还匹配 rednote 域名。调用方应严格只交一条已选作品 URL，保留原查询参数。[入口和链接处理](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/app.py)
2. HTML 中提取 `window.__INITIAL_STATE__`，支持手机及 PC 的 note 数据路径。PC 分支取 `noteDetailMap` 最后一个值，没有按输入 ID 再选择；产品仍需核对输出作品 ID 与任务 ID，不能仅信任非空对象。[转换器](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/expansion/converter.py)
3. 提取 `title`、`desc`、作者 ID/昵称、发布时间/更新时间、标签及赞/评/藏/分享。统计缺失为字符串 `-1`，时间缺失为未知/None；`desc` 是笔记文案，不是 OCR 或视频转写。作者名称后续可能用于别名和文件名处理，应核查原始名称保留方式。[字段提取](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/explore.py)
4. 图文遍历返回数据的 `imageList` 生成图片 URL，并遍历每项 stream 提取 livePhoto 视频；普通视频优先 originVideoKey，否则按清晰度、码率或文件大小选一个视频版本。它拿的是返回清单内每张图片或一个选定视频版本，不保证平台没有隐藏/未返回的媒体。[图片提取](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/image.py)、[视频提取](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/video.py)
5. 默认 `image_download=True`、`video_download=True`，但构造入口的 `live_download=False`；下载全部实况附带视频必须显式设置。`index` 会选择部分图片，默认不设才遍历全部。下载按已有文件路径跳过，最多 4 个文件并发，输出进度及布尔结果；文件类型识别失败会回落默认后缀，不是严格拒收未知类型。[下载器](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/download.py)

### 调用形态与接入成本

| 形态 | 源码行为 | 对本项目的影响 |
| --- | --- | --- |
| Python | `async with XHS(...)`；`extract(url, download=..., check_record=..., progress_callback=..., result_callback=...)` 返回 `list[dict]`。 | 可把数据与文件结果分别转成产品事件；类采用单例，任务隔离和多登录态不能仅靠同进程创建多个对象。 |
| CLI/TUI | 支持命令行/终端下载、多个链接及剪贴板模式。 | 作为后台组件应采用明确参数或封装入口；交互提示及控制台文字不宜作为稳定协议。 |
| 本地 HTTP API | `/xhs/detail` 接收单条 URL 与可选 download、cookie、index；实际只处理解析后的第一条，返回 `message/params/data`。 | 非空 data 可存在于媒体失败/跳过场景，API “获取数据成功”不证明文件齐全；`params` 会回显 Cookie，必须过滤响应/日志。默认监听 `0.0.0.0`，需改为本机地址。 |

调用及 API 证据：[app.py](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/app.py)、[请求/响应模型](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/module/model.py)。

### 登录、额外请求、暂停恢复

- 官方说明 Cookie 非强制，高分辨率获取可能需要 Cookie，链接带 `xsec_token`，旧日期链接可能受限；不能将“无需账号登录”理解为无需访问参数或永远免验证。[README](https://github.com/JoeanAmier/XHS-Downloader)
- 普通完整 URL 的基本链是一个 HTML GET；短链额外增加一次重定向请求及重定向链。`extract` 只遍历传入文本内的作品链接，没有发现自动把单笔记扩展成作者全量作品；用户脚本批量滚动和其他入口属于另一路径。
- 页面请求和每个媒体下载均使用 `max_retry`，默认 5，即最多初次加 5 次；可设 0。请求后的随机延时均值参数为 6 秒，设重试为零不取消延时和重定向。[重试/延时](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/module/tools.py)
- 页面请求失败被捕获、记录 URL 和异常，然后返回空串；没有产品需要的“明确验证证据 → 等待人工恢复”协议。每次传入 Cookie 的请求使用独立同步 `curl_cffi.get`，其余走 AsyncSession；只替换异步 client 无法覆盖所有网络出口。[请求实现](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/application/request.py)
- 页面和下载 Session 都显式 `verify=False`、允许重定向；配置代理时还会测试代理。须将 TLS、最终目的域、Cookie 域和预算置于产品桥接层控制，保留真实浏览器能力只是独立事项。[Session 构造](https://github.com/JoeanAmier/XHS-Downloader/blob/3a8849c7afb215085b32da84bcdbeb7c6d26880e/source/module/manager.py)
- 组件已有 Range 和临时文件，但 `extract()` 会重新取正文；要做到产品的“仅重试未完成媒体”，需保存结构化清单、单独驱动其 Download 能力。现成进度回调有帮助，仍须校验文件数、ID、签名媒体 URL 脱敏和缓存状态。

**判断（推断）**：值得优先验证，接入负担为中等偏高：平台解析已具备，但网络桥接、错误分类、单例隔离、结果协议和媒体校验需要实做。不是下载器本地 HTTP API 套一层即可满足现有微博边界。

## KS-Downloader

### 核查版本与维护证据

固定源码：[`117969db7ab32090dc887319a61a43fa7a4dfebd`](https://github.com/JoeanAmier/KS-Downloader/commit/117969db7ab32090dc887319a61a43fa7a4dfebd)，2026-08-29，最近一次是 Docker 调整；2026-08-27 有[下载缓冲功能提交](https://github.com/JoeanAmier/KS-Downloader/commit/b6a3b3c324060e58c8733b11d3a793b6fa5786da)。当前源码自标 **1.7 beta**；最新正式发布为 [1.6，2026-07-05](https://github.com/JoeanAmier/KS-Downloader/releases/tag/1.6)，其中从 httpx 改为 curl_cffi、调整延时并移除浏览器读 Cookie。维护活动存在，但不是当前平台样本验收。[版本声明](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/static/internal.py)

### 单作品链与字段缺口

- `examiner.run()` 解分享短链，再由 `detail_one()` 解析作品 ID、请求 HTML、交给 HTMLExtractor；没有发现单作品路径自动调用用户作品列表。源码还留有 User/APILive 批量能力，但不在上述单条调用链上。[入口](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/app/app.py)、[链接解析](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/link/examiner.py)
- PC 分支解析 `window.__APOLLO_STATE__` 内指定 ID 的 `VisionVideoDetailPhoto`：文案、作者、时间、赞/播放、封面、单视频 URL；**`commentCount` 和 `shareCount` 在该分支固定为 `-1`**，不能宣称能拿到这两项。
- 手机图文分支从 `window.INIT_STATE` 的 photo 抽取 caption、作者、时间、赞/播放/分享/评论；缺统计填 `-1`。图集遍历 `ext_params.atlas.list`，使用一个 CDN 拼接所有返回项；单图用封面。它硬分手机图片与 PC 视频两路，不能由“支持快手”外推所有内容类型。作者昵称经过后续文件名/别名处理，原始值需核查保留。[字段与媒体清单源码](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/extract/extractor.py)
- `detail_one` 保存数据前把 `download` 从 list 原地转换为空格分隔字符串，随后返回相同对象；对外输出必须按固定版本做结构转换，不应默认 API 返回 URL 数组。[保存调用](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/app/app.py#L313)

### 调用形态与完成状态

| 形态 | 已证实行为 | 限制 |
| --- | --- | --- |
| 本地 API | `/share` 解短链；`/detail/` 接受 text/cookies/proxy，处理第一条作品，返回 metadata。 | **没有 download 入参，调用 `detail_one()` 的默认 download=False；这个 API 本身不下载。** params 会回显 cookies。 |
| Python | `KS.detail_one(url, download=True, proxy=..., cookies=...)` 有单条补全及下载路径，返回 dict 或错误字符串。 | 初始化读取其配置、建立库/目录，接口相较 XHS 更依赖内部对象；需自己的适配入口。 |
| CLI/TUI | `detail()` 遍历指定作品 URL 并可下载；`user()` 是独立批量入口。 | `detail()` 不返回结构化作品集合，控制台状态不能替代稳定输出协议。 |

证据：[API 和入口](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/app/app.py#L503)、[API 参数模型](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/model/base.py)、[响应模型](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/model/response.py)。

下载器遍历图集、使用 Range、默认 4 并发；但 `gather()` 的文件结果没有返回给 `detail_one()`，单文件成功即写作品 ID 下载记录。因此补全返回 dict 不能证明全部文件成功，部分图集失败需要产品自己的逐文件完成清单。源码下载器实际设置 `self.client = manager.client`，而不是 manager.client_download；这意味着媒体请求与页面 Session 共用 Cookie 容器，需要桥接按媒体域过滤凭证。[下载器](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/downloader/downloader.py)、[Manager](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/manager/manager.py)

### 网络及控制适配

- 完整链接取 HTML；分享短链增加解析请求/重定向，可能到 chenzhongtech 等被解析器明确支持的域。旧 live.kuaishou 作品链接匹配在验证入口被注释掉。[链接实现](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/link/examiner.py)
- Cookie 可空，也可项目提供；未看到详情 HTML 路径主动读取日常浏览器 Cookie。每次传 cookies 时走同步 `get`，共享 Session 走 async；两条出口都要纳入桥接。[页面请求](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/link/detail.py)
- 默认重试 5，即最多 6 次尝试，可设 0；请求后带均值参数 6 秒的随机等待。网络错误和缓存错误被转成 None 再重试，没有明确人工暂停恢复协议。[重试](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/tools/retry.py)、[延时](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/tools/sleep.py)、[错误捕获](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/tools/capture.py)
- Session 显式关闭 TLS 校验并允许重定向；配置 proxy 会先请求 new-reco 做测试，代理失败后返回 None，存在回退直连行为。只有配置代理不是网络边界控制。[client](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/tools/client.py)、[参数初始化](https://github.com/JoeanAmier/KS-Downloader/blob/117969db7ab32090dc887319a61a43fa7a4dfebd/source/config/parameter.py)

**判断（推断）**：值得优先验证图文、单视频和短链，但完整互动数据不能验收为已具备；接入负担高于 XHS，主要增加媒体结果回传、字段不变性、凭证网络边界和配置/库隔离。GPL-3.0 的实际分发安排仍需按制品处理；本地调用本身不消除分发义务。

## 小红书备用与排除理由

### yt-dlp：仅视频备用

最新正式版本是 [2026.08.19](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19)。本次核查 master 的 XiaoHongShuIE：读取指定 ID 的 noteDetailMap，输出视频 formats、笔记 desc、标签及 userId；imageList 被当成 thumbnails，不构成完整图集下载协议。输出没有作者昵称、发布时间及互动字段。可用标准 CLI/Python 获取 JSON/下载视频，但没有单独原生本地 HTTP API；如选用需固定该提取器版本并核实 release 是否一致。[提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xiaohongshu.py)

即便仅提取信息，存在 originVideoKey 时仍发起原视频 GET 检查可用性；不能把“只要 metadata”当作只有一个页面请求。该提取器没有单条到作者列表递归。对本项目它只可能弥补视频格式能力，不足以替代 XHS 完整信息路径。通用重试、Cookie 和下载选项仍要通过产品封装约束。[同一源码的原视频检查](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xiaohongshu.py#L72)

### ReaJason/xhs：不作为现成完整组件

本次固定为 [`f4b62d9f8e4078e631fc6e4ec8e430bc711ee9f0`](https://github.com/ReaJason/xhs/commit/f4b62d9f8e4078e631fc6e4ec8e430bc711ee9f0)，最新提交时间 2025-07-01，内容为上传功能。`get_note_by_id(note_id, xsec_token, xsec_source)` 请求单笔记接口，`get_note_by_id_from_html` 提供 HTML 路；需要调用方处理 URL→ID/token。请求签名使用外部传入函数；有验证码、IP 阻断、签名错误的专门异常，错误粒度可参考。

但 `save_files_from_note_id(note_id, dir_path)` 内部仍调用 `get_note_by_id(note_id)`，缺少已必填的 xsec_token：这是静态明确的便捷下载入口不匹配，不是已运行后的平台故障判断。不能把该库“有获取与下载方法”当作今天的即用全链路。[固定版本源码](https://github.com/ReaJason/xhs/blob/f4b62d9f8e4078e631fc6e4ec8e430bc711ee9f0/xhs/core.py)

## 快手替代核查：zyipeng/video-downloader

固定为 [`ebdbf9e444ea4a18fab2442b50b519ed2b268615`](https://github.com/zyipeng/video-downloader/commit/ebdbf9e444ea4a18fab2442b50b519ed2b268615)，2026-06-02，版本说明 2.8.1；仓库无独立 release。它是 Bash/yt-dlp/aria2 工具集合，小红书实际委托 yt-dlp，没有第二个独立小红书解析器。[README](https://github.com/zyipeng/video-downloader)

- 快手脚本 curl 跟随分享页重定向，从整页正则找所有 `.mp4` 字符串，按 URL 字样挑第一个；没有把候选媒体与目标作品 ID 做结构化绑定。
- probe 返回 title/formats，但 uploader、upload_date、thumbnail 写为空，duration 为 None；没有 caption、互动字段或图片图集。probe 对每个候选发 HEAD，下载默认 aria2 16 连接，curl 页面重试 2 次。[快手脚本](https://github.com/zyipeng/video-downloader/blob/ebdbf9e444ea4a18fab2442b50b519ed2b268615/scripts/download-kuaishou.sh)
- 还有静态参数不匹配：probe.sh 调用 `download-kuaishou.sh --probe-only URL`，被调脚本 shift 后仍按 `MODE URL` 取第二参数，URL 为空进入 usage 退出；未实测，按源码调用关系判定。[probe 调用](https://github.com/zyipeng/video-downloader/blob/ebdbf9e444ea4a18fab2442b50b519ed2b268615/scripts/probe.sh#L101)

因此不适合作完整原帖补全备援；即使后续修复 probe，它仍只有视频地址层面的价值。yt-dlp 的快手新站支持请求仍开放，也未由此找到现成快手完整提取器。[支持请求 #14010](https://github.com/yt-dlp/yt-dlp/issues/14010)

## 进入真实验证前应落实的最小问题

1. 固定正式版还是已核查 beta commit；不能混用 README、不同分支和 release 接口。
2. 每平台由项目浏览器刚发现的完整 URL/token 开始，分别验单图、多图、视频、实况及访问失败；比对原文、作者、时间、返回媒体数，而不是仅看成功退出。
3. 先验证一条完整 URL 的网络边界、重定向、登录态域、零自动重试与明确人工暂停；之后才验短链、失败恢复和图集部分失败。
4. 确认快手网页视频缺评论/分享是否可接受；若要求这些字段必须完整，KS-Downloader 单独不满足要求。
5. 保留现有微博的逐文件校验/复用/重试语义；上游下载记录、路径存在和非空元数据不得直接判定产品完成。

本研究未触发实现；仍需用户明确实现请求。上述验证项是技术缺口，不是此次研究已完成的验收结果。
