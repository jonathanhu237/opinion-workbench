# MediaCrawler 今日头条接入影响面

日期：2026-08-23

## 结论摘要

MediaCrawler 没有可插拔 platform registry；新增今日头条必须修改派生仓库。若未来通过官方/书面许可准入门，建议使用稳定平台 ID `toutiao`，再把登录验证、单关键词搜索 spike、search-only adapter 和持久化存储拆成可独立验收的后续任务。

**当前不得进入 adapter 实施。** 2026-08-23 实测 `so.toutiao.com/robots.txt` 对所有 user-agent 声明 `Disallow: /`，`www.toutiao.com/robots.txt` 也禁止 `/search`；MediaCrawler 自身许可证声明要求遵守 robots.txt。因此以下影响面是“未来获得许可后的条件式设计”，不是当前实施授权。

第一版不要实现 detail、creator、评论、媒体下载，也不要为了复用 MediaCrawler 自带 Web UI/API 而扩大范围；本项目后续会有自己的 FastAPI/React 层。

## 获得许可后必须修改的平台注册点

### Core registry

- `main.py`
  - import `ToutiaoCrawler`
  - `CrawlerFactory.CRAWLERS` 注册 `"toutiao"`
- `cmd_arg/arg.py`
  - `PlatformEnum` 增加 `TOUTIAO = "toutiao"`
  - 更新 `--platform` help
  - search-only MVP 不需要接入 `--specified_id` / `--creator_id` 映射
- `config/base_config.py`
  - 更新平台列表
  - import 新的 `toutiao_config.py`
- `config/toutiao_config.py`
  - 只放今日头条明确需要的搜索限制；不要复制 detail/creator 示例 ID

平台 ID 推荐完整单词 `toutiao`，与 `tieba` / `zhihu` 一样可读，也避免 `tt` 的歧义。它会同时成为浏览器 profile、认证状态、数据目录和日志的命名边界。

## 平台模块边界

只有准入门通过后才建议新增：

```text
media_platform/toutiao/
├── __init__.py
├── core.py       # 浏览器生命周期、登录状态、关键词循环、停止条件
├── client.py     # 只封装页面正常导航产生的结果，不手工构造私有签名请求
├── login.py      # 首次人工登录、官方挑战仅人工处理
├── help.py       # DOM/浏览器响应 payload → 规范化线索、URL 规范化
└── exception.py  # 仅平台边界异常；不吞掉 challenge/block 状态
```

是否需要 `field.py` 取决于调研后能否确认稳定的排序/时间筛选枚举。无法确认时不预建枚举。

`ToutiaoCrawler.start()` 第一版只接受 `CRAWLER_TYPE == "search"`；其他类型应明确报“不支持”，不能静默执行或落入未验证分支。

## 浏览器与认证边界

- 使用现有 `CDPBrowserManager` 启动项目专用可见 Chrome，不连接日常 Chrome。
- 首次登录、二维码、短信或平台安全挑战全部由用户手工完成。
- 不识别/拖动滑块，不自动刷新挑战，不提取或重放验证码。
- 先真实验证原生 CDP profile 的两次启动；只有复用失败时，才考虑 `BrowserAuthStateStore(platform="toutiao", urls=["https://www.toutiao.com"])`。
- 登录有效性必须由当前页面的可观察登录 UI 或平台正常页面行为确认，不能把 profile/状态文件存在当成成功。
- 登录验证和搜索 spike 应拆成独立任务，避免在一次真实账号运行里同时调试选择器、登录态和数据解析。

## 搜索数据流建议

当前推荐优先级：

```text
官方可申请的通用关键词搜索接口（若存在）
→ 有明确授权条款的第三方舆情/搜索数据服务
→ 人工搜索、人工提交链接
→ 停止
```

只有官方书面许可明确覆盖网页自动化后，才可重新评估可见 DOM 或页面正常响应；即使获准，“浏览器响应读取”也只允许消费页面本身正常触发的响应，不得把内部 URL、临时 token 或签名算法提取出来做无浏览器重放。

每个关键词默认只验证首批结果，单线程、固定间隔、硬上限；出现登录墙、验证码、异常空结果、HTTP 限制或页面结构不确定时停止并记录非敏感状态。

## 最小线索合同

建议 Pydantic 模型 `ToutiaoContent`：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `content_id` | `str` | 从稳定 URL/页面字段取得；无法取得时使用规范化 URL 的稳定哈希 |
| `title` | `str` | 搜索结果可见标题 |
| `snippet` | `str` | 仅搜索结果可见摘要片段，不打开全文补采 |
| `content_url` | `str` | 规范化的 `https` 今日头条原文链接，删除跟踪参数 |
| `publish_time` | `str` | 原样可见时间；无法可靠转换时不伪造时间戳 |
| `publisher_name` | `str` | 可选；若保留则沿用项目昵称脱敏规则，不保存账号 ID/主页 |
| `source_keyword` | `str` | 触发发现的原始配置关键词 |
| `discovered_at` | `int` | 本地发现时间戳 |

明确禁止进入模型/日志/存储的字段：原始用户 ID、账号主页、头像、性别、IP 归属地、设备标识、Cookie、LocalStorage、认证头、二维码内容、内部签名/token。

URL 规范化至少需要覆盖并测试：相对 URL、协议相对 URL、合法 `toutiao.com` 子域、查询跟踪参数、跳转/分享链接和非今日头条外链。无法在不发起额外跳转的情况下确认 canonical URL 时，保留可打开的安全 URL并标记来源，不猜测 ID。

## 获得许可后的 Store 与数据库影响面

MediaCrawler 的 store 是按平台复制实现，并没有统一的内容表：

- `model/m_toutiao.py`：新增内存模型。
- `store/toutiao/__init__.py`：规范化内容并设置 `source_keyword`。
- `store/toutiao/_store_impl.py`：每个保存后端都需显式注册。
- `database/models.py`：SQLite/MySQL/Postgres 需要新的 `ToutiaoContent` ORM 表。
- `tests/test_no_user_info.py`：把新内容表/提取器加入隐私回归。

为控制风险，建议拆分：

1. **搜索 spike**：只返回内存 `ToutiaoContent` 列表或任务临时 JSON 证据，不接正式 store。
2. **最小 adapter**：接入 CLI/factory，先支持 JSONL 和项目需要的 SQLite；其他 MediaCrawler 存储后端明确报不支持。
3. **统一后端接入**：未来由项目 FastAPI/SQLite 层消费规范化线索，不继续扩张 MediaCrawler Web UI/API。

如果决定要求 MediaCrawler 所有 `SAVE_DATA_OPTION` 对今日头条完全一致，则 CSV、JSON、JSONL、SQLite/MySQL/Postgres、MongoDB、Excel 都是额外工作，不应混入第一个搜索 spike。

## 非最小影响面

MediaCrawler 自带 API/Web UI 还有独立平台枚举与列表：

- `api/schemas/crawler.py`
- `api/main.py`
- `api/routers/data.py`
- `webui/src/lib/urlParser.ts`

本项目已决定建设自己的 FastAPI/React 管理层，首个今日头条 adapter 不应修改这些上游 UI 文件。若未来明确复用 MediaCrawler Web UI，再单独补齐。

## 测试地图

后续实现至少需要：

- CLI/factory：`toutiao` 可选择，search-only 类型限制明确。
- Parser：公开结果 payload/DOM fixture → 最小合同；缺字段、广告/推荐项、外链、重复 URL 安全跳过。
- URL：canonical/relative/tracking/invalid scheme/domain 表格测试。
- Privacy：无禁用个人字段，展示名按规则脱敏。
- Login orchestration：已有登录、人工登录、挑战停止、关闭状态开关。
- Search orchestration：关键词上下文、硬上限、固定间隔、无结果、页面结构漂移、挑战/限制立即停止。
- Real regression：项目专用账号首次人工登录 → Chrome 完全退出 → 第二次免登录；随后单关键词、单批结果、0 评论/0 正文抓取。

## 可独立验收的后续任务

1. 今日头条官方/政务合作搜索能力或书面自动化许可申请；或者单独评估有明确授权条款的第三方数据服务。
2. 仅在准入门通过后：今日头条专用账号登录与原生 profile 复用验证。
3. 仅在准入门通过后：无持久化副作用的单关键词、单批搜索 spike，确定获准 transport。
4. 仅在准入门通过后：search-only MediaCrawler adapter（CLI/factory/model/parser + JSONL/SQLite）。
5. 父项目 FastAPI/SQLite ingestion 与去重；可先支持人工或合规供应商输入，不依赖直接头条 crawler。
