# 现有配置、登录态与媒体生命周期核查

Status: resolved
Type: research

核查日期：2026-09-03。只读检查本地代码及默认运行库中的负载字段/数量；未读取凭证内容，未启动服务、浏览器、采集或下载。下述存储配置是核查时快照，不保证与其他自定义数据库实例相同。

## Answer

### Q11：实际负载应来自现有配置

- 默认运行库有一条启用规则：5 个监控对象与 4 个舆情关键词组合成 20 个搜索词；没有记录其具体内容。
- 保存的一条未删除自动任务目前停用，配置为每 60 分钟、5 个平台、每词最多 3 条结果。若执行完整且无中断，单次微博搜索输出上界为 60 条，五平台为 300 条；去重后可更少。这不是请求数、实际吞吐量或性能承诺，不能外推重复尝试的累计量。
- 规则层允许最多 100 个组合词，但采集入口最多接受 20 个，不会自动拆分。结果条数可配置为每词 1–50，表单默认 10；不存在独立的每平台或每批次总量配置。
- 微博目前每页按 10 条估算，最多获取 `ceil(max_results_per_term / 10)` 页，再限制输出数。每词设为 3 仍可能读取整页；正文解析、媒体文件传输和重试另产生访问。
- 没有采集发布日期起止或回溯天数配置；实时搜索模式不代表覆盖某个时间窗口的全部内容。
- 自动任务支持间隔或指定时区的每日时间。相同任务仍在进行时，下一次到期跳过而不是叠加；错过时点不追赶补跑。不同任务仍受全局浏览器占用约束，忙时拒绝新的采集入口。
- 单平台整次搜索默认 180 秒，是所有关键词共用的执行预算；正文/媒体补全另有每内容预算。这些超时不应被当作产品时效指标。
- 补全当前硬限为正文 20,000 字符、图片 24 张、视频 1 个、总媒体 6 MiB，并非 UI 中的配置项。完整媒体缓存与 AI 输入的预算需要在设计中区别；不能单纯放大原有内存输入上限来实现原视频保存。

依据：`backend/src/longtian_api/database.py:24`、`services/monitoring_rules.py:172`、`services/search_runs.py:57`、`:151`、`schemas/search_batches.py:85`、`repositories/automation_workflows.py:491`、`services/search_batches.py:300`、`services/enrichment_models.py:76`；`third_party/MediaCrawler/media_platform/weibo/product_search.py:223`、`:307`。

配置可以给出验收输入，不能单独推出成功率、完整率、召回率、真实请求数、安全频率、可接受人工介入次数或完成时间。正文/媒体是为所有命中补全还是按分析范围补全，仍是未确定的产品选择。

### 登录态：新增的是组件信任边界

- 当前产品使用专用 Chrome 配置目录，worker 持有浏览器上下文；不应降级连接用户日常浏览器。
- 微博搜索已经在本地 worker 内从对应微博域取得 Cookie 并用于 Python HTTP 请求。因此混合方式不是首次让登录态离开浏览器。
- 把登录态交给另一个第三方解析组件，仍是需要明确的信任边界；不能因为已有 HTTP 搜索，就默认允许导出完整浏览器配置或所有平台 Cookie。
- 当前媒体直链下载器反而不携带平台 Cookie，并在每次下载前清空 Cookie。新方案需要区分需要登录的帖子解析与无需登录的媒体传输。
- 设计建议：仅指定的本地受控组件按任务取得对应平台的必要登录态；不进入普通日志或命令行参数、不外传其他平台信息。是否可以完全不落盘，要等具体接口核查，尚未承诺。

依据：`backend/src/longtian_api/services/platform_connections.py:87`、`:398`、`services/media_crawler_auth_worker.py:340`、`:1665`；`third_party/MediaCrawler/tools/auth_worker.py:165`、`media_platform/weibo/product_search.py:297`、`tools/product_media.py:376`。

### 媒体：现状是分析暂存，不是持久缓存

- 目前分析需要时才进入正文/媒体补全；已有分析结果满足复用条件时，可以直接复用旧输入和输出，不重新获取媒体。这是分析结果复用，不是原始文件复用。
- 原始媒体进入单条分析暂存目录，校验后以实际字节提供给模型；每条分析结束时清理本次暂存文件。
- 持久保存的是正文、媒体状态/哈希/尺寸等元信息与分析输出。`SavedInput` 明确禁止文件路径、下载地址、媒体字节；UI 也明确说明不保存原始图片或视频。
- 所以现有历史分析仍可查看文字及状态，但没有历史原图/视频回放能力。用户要求的期限/容量设置需要新增持久媒体缓存，而非仅扩展已有设置。
- 未来清理后应区分“当时获取成功”和“现在本地文件已清理”；删除缓存不应篡改历史分析输入。自动清理的优先级与是否允许自动重新访问平台，仍待用户决定。

依据：`backend/src/longtian_api/main.py:117`、`services/content_analyses.py:269`、`repositories/content_analyses.py:895`、`services/ai_analysis.py:265`、`services/content_enrichment.py:243`、`services/enrichment_staging.py:243`、`schemas/analysis_evidence.py:377`；`frontend/src/routes/results-evidence.tsx:282`。

## Comments

- 本文只记录设计事实及建议，不授权安装第三方工具、提取凭证、清理文件或改变调度配置。所有代码和既有运行数据保持原样。
