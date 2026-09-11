Status: resolved
Type: research

# 让 LLM 直接访问原帖 URL 的可行性尝试（暂不采用）

## 目标

采集仍负责发现原帖 URL，随后只向模型服务提供详细 URL，由服务端网页抓取工具获取原帖文字并交给模型理解，以避免本项目维护各平台正文提取逻辑。不扩大到评论、推荐内容或图片、视频、声音理解。

## 调研与实测

- DeepSeek 官方 API 文档仅确认调用方提供的 Function Calling，未确认内置指定网页读取能力；未进行 DeepSeek 原帖访问实测。此结论不覆盖第三方托管的 DeepSeek 或额外接入浏览器的方案。
- 阿里云百炼文档提供联网搜索与网页抓取工具，因此使用用户授权的 API 密钥从本机调用官方接口做小样本验证。
- `qwen3.8-max` 配合 Chat Completions 的 `agent_max` 首次请求返回 HTTP 400，提示不支持该搜索策略；改用 `qwen3-max`，开启 `enable_search`、`enable_thinking` 和 `search_options.search_strategy=agent_max` 后完成测试。
- 从本地内容库各取一个平台的原帖 URL，只向 API 提交 URL 和读取要求，未提供已有标题、摘要或正文。要求返回实际取得的原帖文字及缺口，不以搜索摘要或其他网页替代原帖。
- 另以阿里云网页抓取文档作为公开页面对照。共完成六次请求，接口报告累计 81,397 token（含对照，不代表五条原帖的单位成本）；费用未独立核算。

| 平台 | 样本 URL | 本次观察 |
| --- | --- | --- |
| 微博 | https://m.weibo.cn/detail/5339025821140308 | 返回预警正文，与本地已有文字内容一致；作者等来源信息缺失。 |
| 抖音 | https://www.douyin.com/video/7659784861322706547 | 模型报告读取失败，未返回原帖文字。 |
| 快手 | https://www.kuaishou.com/short-video/3xv5b2ycyxn93j2 | 模型报告读取失败，未返回原帖文字。 |
| 小红书 | https://www.xiaohongshu.com/explore/6a9fb96b000000000e03b400 | 返回网站版权信息，没有目标笔记正文。 |
| 今日头条 | https://www.toutiao.com/article/7274860905077768743/ | 返回文章正文及记者信息，全文完整性未独立核实。 |

## 证据边界

每个平台仅测试一条，不代表平台整体成功率。本次收集的接口结果未提供可独立核验的抓取过程记录，因此模型自述的访问成功、完整性、重定向情况或登录、反爬等失败原因不能直接视为已验证事实。正文输出要求最多 800 字，此次也不是全文完整性的严格验收。没有证据证明所有模型、所有网页或所有 URL 变体均不可行。

## Answer

用户确认停止继续探索，不接入这条路线，保持现有内容补全和文字理解流程。结论是：**曾尝试让 LLM 服务直接访问原帖 URL，但不能稳定、完整地取得五个平台所需原帖文字，暂不能替代现有正文获取方案**；不是所有样本都完全无法读取。

此次仅调研与临时探针测试，未修改应用代码、数据库或 AI 配置。本记录不保存 API 密钥；用户已被提醒撤销聊天中公开的密钥。此结论不改变既有 ADR-0003、ADR-0010、ADR-0011 的获取边界与文字理解范围。

## 参考

- [阿里云百炼：网页抓取](https://help.aliyun.com/zh/model-studio/web-extractor)
- [DeepSeek：Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [DeepSeek：Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)

## Comments

用户最终意见：“那就不弄了，就这样……记录一下，我们曾经尝试让 LLM 直接访问原贴，结果没法正常获取正文。”本记录保留停止探索的决定，并区分部分样本返回文字与整体不能替代现有方案。
