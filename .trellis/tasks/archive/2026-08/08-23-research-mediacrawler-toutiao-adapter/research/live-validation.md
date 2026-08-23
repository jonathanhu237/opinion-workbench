# 今日头条适配最终真实验证

Date: 2026-08-24 (Asia/Shanghai)

## Evidence boundary

- 本文件只记录验收所需的数量、布尔状态、文件权限和目标 host。
- 不记录 Cookie 名称或值、二维码数据、页面正文或原始 HTML、动态 token、请求头、认证头、搜索结果标题或账号信息。
- 登录态使用任务专用临时路径；不记录其绝对路径。最终验证完成后，该路径已随任务临时目录一起永久删除。

## Anonymous full-adapter regression

- 使用全新标准可见 Chrome `BrowserContext`，未进入 CDP 或持久化 profile 分支。
- 关键词为 `龙田街道`，只读取第一页，最大接受数量为 10。
- 完整适配器运行退出码为 `0`。
- JSONL 共写入 10 条结果，`content_id` 全部唯一。
- 10 条结果的 `content_id`、`title`、`content_url`、`source_keyword` 和 `discovered_at` 均完整。
- 规范化链接的 host 全部为 `www.toutiao.com`。
- 发布者名称均经过脱敏；禁止的个人信息与认证字段均不存在。

## User-operated login regression

- 第一次人工登录尝试遇到登录页导航竞态后失败；未完成登录，未保存状态。
- 第二次人工登录尝试到达官方安全挑战，但当时的旧行为在人工处理前结束运行；未完成登录，未保存状态。
- 修复后的第三次人工登录尝试保持官方可见挑战页面供用户手动处理；适配器未检查、操作、求解或绕过挑战。
- 用户手动完成官方流程后，DOM 在线认证检查成功。
- 只有在线认证成功后，`BrowserAuthStateStore` 才向任务专用临时状态文件保存 39 个 allowlist Cookie；文件权限为 `0600`。
- 随后的单结果搜索完成，运行退出码为 `0`。

## Full-browser-restart regression

- 完全退出浏览器后，使用同一任务专用临时状态重新启动全新标准可见 Chrome 上下文。
- 状态存储恢复了 39 个 allowlist Cookie。
- 重启运行没有进入 `ToutiaoLogin`，没有再次打开二维码流程；随后执行了 DOM 在线认证检查。
- 在线认证确认后刷新保存状态，并完成一次单结果搜索；运行退出码为 `0`。
- 状态文件的存在未被当作登录成功依据；两次成功运行均以 DOM 在线状态为准。

## Cleanup

- 清理前确认本机没有进程监听 TCP 端口 `9222`。
- 六个由本任务显式创建的 `/tmp` 验证目录均通过 `find -depth -delete` 永久清理；其中包括用于重启回归的临时 `0600` 登录态文件。
- 未删除或修改父项目既有 `browser_data/`、`db_data/`、`logs/` 或其他用户运行目录。
- 清理后不再保留本次真实回归产生的 Cookie 状态、JSONL 结果或临时脚本。

## Acceptance result

- 匿名第一页搜索、最大数量限制、必填字段、唯一 ID、今日头条 host 限制、发布者脱敏和禁止字段过滤：通过。
- 人工挑战边界、成功后才保存、`0600` 权限、完整浏览器重启、无需再次登录及在线状态复核：通过。
- 搜索和认证均未使用 CDP、持久化 profile、私有响应重放、自动挑战处理或导航重试：通过。
- 任务临时目录、临时认证态和验证输出清理完成，既有项目运行目录未触碰：通过。
- MediaCrawler 派生仓库已在 `main` 提交并推送 `815ce9332c74097914c61899a0e37ea1b60e0af3`；远端 `refs/heads/main` 可达该 revision。父仓库已通过 `812a604` 更新 gitlink 并提交任务证据，任务归档仍待完成。
