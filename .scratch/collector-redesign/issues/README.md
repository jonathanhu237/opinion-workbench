# 采集与报告重设计：任务索引

用户已确认按以下 14 张任务拆分。每张任务独立成文，均标记 ready-for-agent；此标签表示可供领取，不表示依赖已完成或已授权开始编码。

当前实施状态（2026-09-03）：01–13 已完成离线实施与相应回归；14 等待微博实机范围确认。各票勾选指离线验收，不能替代真实账号验证和最终依赖退出。下表保留发布时的依赖关系；最新验证、未切换事项和待审查风险见 [实施记录](../implementation.md) 与 [验证记录](../verification.md)。

父规格：[微博先行的舆情爬取与报告生成重设计](../spec.md)。本次发布没有修改或关闭父规格。

## 任务与直接依赖

| 编号 | 任务 | Blocked by | 发布状态 |
| --- | --- | --- | --- |
| 01 | [采集器替换的前置整理](01-collector-boundary-prefactor.md) | 无 | ready-for-agent |
| 02 | [微博浏览器搜索入库](02-weibo-browser-discovery.md) | 01 | ready-for-agent |
| 03 | [手选已有总结生成报告](03-selected-summaries-to-report.md) | 无 | ready-for-agent |
| 04 | [未分析正文自动总结并出报告](04-stored-text-to-report.md) | 03 | ready-for-agent |
| 05 | [全库未分析与失败项批量处理](05-library-wide-pending-and-failed.md) | 04 | ready-for-agent |
| 06 | [微博 URL 补全正文并出报告](06-weibo-url-text-enrichment.md) | 01、04 | ready-for-agent |
| 07 | [图片内容进入总结与报告](07-image-understanding-to-report.md) | 06 | ready-for-agent |
| 08 | [视频内容进入总结与报告](08-video-understanding-to-report.md) | 06 | ready-for-agent |
| 09 | [部分失败交付与报告单独重试](09-partial-failure-and-report-retry.md) | 04 | ready-for-agent |
| 10 | [取消、中断与人工恢复](10-cancel-interruption-manual-recovery.md) | 02、06 | ready-for-agent |
| 11 | [原媒体持久保存与复用](11-persistent-media-cache.md) | 07 | ready-for-agent |
| 12 | [媒体期限、容量与安全清理](12-media-retention-and-cleanup.md) | 11 | ready-for-agent |
| 13 | [未适配平台提示与历史兼容](13-platform-availability-and-history.md) | 01、03 | ready-for-agent |
| 14 | [微博实机验收与旧依赖退出](14-weibo-validation-and-mediacrawler-exit.md) | 05、08、09、10、12、13 | ready-for-agent |

## 领取规则

- 必须先完成所列直接前置任务，再领取当前任务；不要仅因标签为 ready-for-agent 就跳过依赖。
- 发布时无前置依赖的是 01 与 03，二者可以独立推进；这不是自动启动指令。
- 06 完成后，07 与 08 可以分别推进；两者遵守同一媒体与补全契约。
- 11 先用图片链路验证共同缓存，视频存储契约不额外要求等待 08；真实图片与视频组合在 14 汇合验证。
- 14 已通过前置依赖覆盖其余全部任务，是实机验收与旧依赖退出的最终关口。实际访问及删除仍遵守明确的账号、请求预算和数据保留边界。
- 每张任务都包含自己的界面或可观察行为、持久结果和验收，不把全部测试推到最后。01 是保留旧行为的最小前置整理。

## 范围约束

首批只做微博及本项目手动流程；采集入库与报告选材启动分开，报告内部自动衔接。自动化本轮不改，小红书不参与试验，不购买第三方数据服务。

完整任务以各独立文件为准，本文件仅提供导航和依赖索引。
