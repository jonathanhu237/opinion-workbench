# 跨平台 URL 解析器与现有组件复用核查

Status: researched

后续更新：本文保留实测前的源码调查快照。2026-09-06 已完成独立样本试验，当前可用性、失败证据与选型调整以[实测记录](real-validation.md)为准。

核查日期：2026-09-06。仅检索官方资料、读取公开源码和 GitHub 提交元数据；未安装或执行候选工具，未调用平台内容接口。这里的优先级是验证优先级，不是生产选型。

## parse-video-py：值得加入对照验证的轻量候选

- 项目：[wujunwei928/parse-video-py](https://github.com/wujunwei928/parse-video-py)。核查提交 `5fcf87256edb5ffcdebf0e4aac2a5a41745da76e`，提交日期 2026-08-19；MIT。该日期来自提交元数据，不代表当天所有平台都经过测试。
- 提供异步 Python `parse_video_share_url` / `parse_video_id`、JSON CLI 和本地 HTTP 接口。支持列表包含抖音、快手、小红书图集和视频，适合比较单条 URL 获取路径。官方 README 提醒优先使用 App 分享链接，电脑网页链接未充分测试；本项目 URL 恰恰来自电脑浏览器搜索，必须把这种输入作为验收样本。
- [统一返回模型](https://github.com/wujunwei928/parse-video-py/blob/5fcf87256edb5ffcdebf0e4aac2a5a41745da76e/src/parse_video_py/parser/base.py) 是 `VideoInfo`：视频/封面/音乐地址、title、images、author；没有发布时间、互动数或独立正文描述字段。这些字段不能凭平台支持列表假定已经补齐。
- [小红书源码](https://github.com/wujunwei928/parse-video-py/blob/5fcf87256edb5ffcdebf0e4aac2a5a41745da76e/src/parse_video_py/parser/redbook.py) 从网页初始状态提取作者及媒体，但 `title` 只写笔记标题，未保留 `desc` 正文；不能原样作为小红书正文补全器。小红书单 ID 调用明确不支持。
- [快手源码](https://github.com/wujunwei928/parse-video-py/blob/5fcf87256edb5ffcdebf0e4aac2a5a41745da76e/src/parse_video_py/parser/kuaishou.py) 从分享跳转及页面初始状态提取 caption、作者名称和视频/图集地址；要求第一跳存在 Location，单 ID 也不支持。标准桌面详情 URL 能否进入此路径不能只看分享短链成功。
- [抖音源码](https://github.com/wujunwei928/parse-video-py/blob/5fcf87256edb5ffcdebf0e4aac2a5a41745da76e/src/parse_video_py/parser/douyin.py) 接受部分桌面 URL 或短链，title 使用作品 desc，提取作者、图集、实况与视频地址；仍受统一模型的时间/统计缺口影响。
- 返回媒体地址不等于完成本地文件下载。可复用应用已有受控下载与校验能力，但不能把“JSON 中有视频地址”当作视频和音轨验收通过。
- 网络客户端创建集中于 [utils.py](https://github.com/wujunwei928/parse-video-py/blob/5fcf87256edb5ffcdebf0e4aac2a5a41745da76e/src/parse_video_py/utils.py)，默认使用 httpx，可配置代理；当前不是项目规定的请求预算、凭据域名范围、人工暂停协议。需要评估如何保留其获取行为并加入应用控制，而不是原样后台服务常驻。

判断：作为抖音、快手媒体解析的轻量对照候选有价值；小红书原帖补全优先比较字段更完整的专用工具。不应为了统一依赖而接受已知正文丢失。

## media-parser：备用候选，不能据平台矩阵判断头条全文能力

- 项目：[ucmao/media-parser](https://github.com/ucmao/media-parser)。核查提交 `e2e6634dbf078c2cfba3848255b107fc97a09aed`，提交日期 2026-09-06；MIT。公开代码有本地平台解析器和 REST 服务，不必依赖网站上托管的代解析 API。
- [小红书实现](https://github.com/ucmao/media-parser/blob/e2e6634dbf078c2cfba3848255b107fc97a09aed/src/parsers/xiaohongshu_parser.py) 保留标题加 desc、作者、视频与图集，优于仅导出标题的候选；基础公开接口仍没有统一发布时间/互动数获取方法。
- [基础接口](https://github.com/ucmao/media-parser/blob/e2e6634dbf078c2cfba3848255b107fc97a09aed/src/parsers/base_parser.py) 侧重标题、作者、封面、视频、图片列表、音频和字幕；平台特有原始数据可能更多，但需要单独投影，不能声称接口默认返回本项目所有元数据。
- README 将“今日头条”列为支持；实际 [XiguaParser](https://github.com/ucmao/media-parser/blob/e2e6634dbf078c2cfba3848255b107fc97a09aed/src/parsers/xigua_parser.py) 仅继承 DouyinParser，并将西瓜和头条名字注册到同一路径。核查的抖音实现没有独立的头条文章正文/微头条提取逻辑，因此该矩阵不是文章全文或微头条覆盖证据。
- [抖音实现](https://github.com/ucmao/media-parser/blob/e2e6634dbf078c2cfba3848255b107fc97a09aed/src/parsers/douyin_parser.py) 包含多条接口尝试、游客标识、重试及部分关闭 TLS 校验的请求。要将其作为受控组件，需要明确请求链路和结果归一化；最新提交不能替代这些检查或真实单帖验证。
- [URL 处理](https://github.com/ucmao/media-parser/blob/e2e6634dbf078c2cfba3848255b107fc97a09aed/utils/web_fetcher.py) 会归一化地址并对小红书保留特定访问参数。浏览器发现 URL 到补全工具输入之间必须实测；不能只传一个去掉必要上下文的 ID。

判断：可作为跨平台解析备用或源码对照；暂无证据支持用这一套取代四个平台专属能力验证。头条文章和微头条仍需另外的候选。

## gallery-dl 与 yt-dlp 的定位

- 现有微博 gallery-dl 继续复用。[当前官方支持表](https://gdl-org.github.io/docs/supportedsites.html) 没有列出本次四个平台，不能把微博组件直接当成它们已具备的获取器；此处不改动已锁定的微博依赖。
- yt-dlp 的具体平台提取能力必须按适配器区分：头条视频、抖音、小红书各自有不同覆盖，支持视频不等于支持文章正文和完整图集。详见本目录抖音及头条专项记录。
- 资源嗅探器、代理下载界面及仅包装外部代解析服务的网站，即使能保存视频，也不能自动承担“已发现 URL → 原帖正文/作者/时间/媒体”的补全职责。本次不因它们的平台列表更长就加入运行时。

## 验证优先顺序的依据

优先比较既有单作品入口和完整正文/媒体输出，再看本项目需要增加多少适配；不以支持平台数量、星数或仓库最近活动代替原站结果。先固定候选代码与最小调用方式，用同一批桌面发现 URL 对照专用工具和轻量解析器，取得真实缺口后才决定是否自写补全逻辑。
