# 指定 URL 组件核验

Status: qualified-for-bounded-local-integration; real-site validation pending 14

## gallery-dl 1.32.10

范围是固定版本的 WeiboStatusExtractor，不运行其 CLI、用户页分发器或文件下载任务。上游原始实现有访客会话、缓存和重试，不直接授予网络执行权。项目新增独立解析进程，通过请求消息向宿主申请访问；宿主只允许本次 MID 的详情查询，最多两次（包含长正文补全），无递归 URL。组件不取得 Cookie，也不读取用户配置/缓存；使用空会话和项目提供的传输边界，上游源文件不修改。

已用真实已安装解析器、纯模拟平台返回验证正文、长文第二次查询、取消结算、验证信号零重试及图文视频候选清单，5 项通过。子进程总限 30 秒、每帧 2 MiB；响应身份必须吻合。清单和取得文件分别表达：候选 URL 不能变成 ready 媒体。实际媒体传输仍由 07/08 核验，实站兼容性留给 14。

接入钩子为实例级 config、cache、session、request；子进程检查版本必须等于 1.32.10，升级需重跑固定样本与接入审计。只作为受控解析器，没有叠加 yt-dlp。

宿主 WeiboEnricher 只请求选中的单一 MID，响应限 1 MiB、连接 5 秒/读取 10 秒，间隔至少 2 秒，不跟随重定向、不采用系统代理、不重试。只从专用 Chrome 运行时内存取对应域 SUB/SUBP，HTTP Cookie 不交给子进程、不写命令行/日志/数据库。人工验证在报告父任务上持久暂停并持有浏览器占用，只有带当前 control_revision 的 Continue 可恢复；打开窗口和 GET 不恢复。已有正文的无关任务仍可完成。新增 v23 只记录暂停元数据，启动时中断未完成任务，不自动请求平台。

通过临时数据库贯穿正文保存、总结、报告、复用；404/不可读、结构变化单独诊断，绝不以搜索预览替代。401/403/429 暂停、旧 Continue 拒绝和重启无外部调用已测试。常规样本不证明真实账号兼容性。

版本与行为依据：[微博提取器](https://github.com/mikf/gallery-dl/blob/v1.32.10/gallery_dl/extractor/weibo.py)、[提取器公共实现](https://github.com/mikf/gallery-dl/blob/v1.32.10/gallery_dl/extractor/common.py)。

## 分发

gallery-dl 使用 GPL-2.0；不把它视为无许可义务的纯命令行工具。本项目尚未做分发包。本地依赖保持版本锁定及原许可，若打包分发需携带其许可与相应源码/源码提供方式，并核对应用组合方式；这项发布核查留给 14，不能仅删除旧 submodule 就跳过。依据：[上游 LICENSE](https://github.com/mikf/gallery-dl/blob/v1.32.10/LICENSE)。

没有复制上游实现、没有传入真实账号或发起微博网络请求；模拟传输只是确定性验收，不是实站成功证据。

## 图片传输（07）

沿用解析器清单，由宿主直接流式读取允许 CDN（sinaimg.cn、weibocdn.com）的 HTTPS 地址；不跟随跳转、不带平台 Cookie，单帖合计 6 MiB（包括损坏文件），每文件 20 秒、媒体部分总计 100 秒。真实字节经 Pillow 12.3.0 的格式限制、verify 与解码验证，最多 40 MP，动态图片和未知类型明确不支持；写入目录只通过应用自己创建的 MediaOperation 描述符，随机不透明文件名禁止覆盖或路径越界。不运行第三方下载 CLI。

图片不缩小、不抽样，实际传给模型的是通过校验的相同字节。原图取得状态与模型是否提交分别展示；原媒体长期保留由 11 接入。Pillow 使用及限制依据：[Image 模块官方文档](https://pillow.readthedocs.io/en/stable/reference/Image.html)。

## 视频校验（08）

仅补足文件校验能力，复用本机已有 ffprobe 8.1.2，不使用它下载、转码或生成模型替代输入。进程只收到已下载的字节（stdin），协议白名单仅 pipe、容器仅 mov/MP4、外部 data reference 禁用；不会取得 URL、路径或 Cookie。先核对编码、尺寸、时长和音轨，再解码计帧验证实际视频与音频存在；每次探测 5 秒，stdout 16 KiB、stderr 8 KiB，取消等待进程退出。限制 MP4/H.264/AAC、30 秒、1080p 约 2 MP、最多 1,800 视频帧，仍受单帖 6 MiB 和单文件 20 秒预算约束。无音轨或不支持的编码明确标记缺口，不把封面提交为视频。

校验工具与宿主传输职责依据：[ffprobe 官方说明](https://ffmpeg.org/ffprobe.html)、[协议白名单说明](https://ffmpeg.org/ffmpeg-protocols.html)。依赖系统现有可执行文件，未打包 FFmpeg；如果后续分发捆绑，其构建选项及许可需单独核对。本次固定样本由本机 ffmpeg 生成短蓝色视频和合成音，不使用用户文件。
