# MediaCrawler 微博原生登录验证结果

## 结论

首次二维码登录流程可用；相同独立 Chrome 用户数据目录在进程重启后未能免扫码复用登录态。

## 环境与命令

- MediaCrawler revision: `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- Google Chrome: `151.0.7922.173`
- Python: `3.11.15`（由 `uv` 按锁文件创建）
- 依赖安装：`uv sync --frozen`，成功安装 89 个锁定依赖
- 验证命令：

  ```shell
  uv run main.py --platform wb --lt qrcode --type detail --specified_id '' --get_comment no --get_sub_comment no --crawler_max_notes_count 1 --max_concurrency_num 1 --headless no --save_data_option jsonl
  ```

## 观察结果

1. 临时设置 `CDP_CONNECT_EXISTING = False` 后，MediaCrawler 成功启动独立 Chrome，并使用 `browser_data/cdp_wb_user_data_dir`。
2. CDP 连接、微博 SSO 页面加载、二维码提取和系统图片窗口展示均成功。
3. 用户扫码确认后，日志依次出现登录成功、跳转 `m.weibo.cn`、移动端 Cookie 更新成功和 crawler 完成。
4. 评论和子评论采集均关闭。空 `--specified_id` 没有覆盖仓库默认 `WEIBO_SPECIFIED_ID_LIST`，因此原生 detail 流程仍采集了默认的一条微博详情。
5. 使用相同浏览器目录第二次运行时，`WeiboClient.pong()` 再次判定 Cookie 无效并进入二维码登录；第二次扫码后流程才能完成。

## 只读诊断

- 首次运行的 `m.weibo.cn` 上下文可读取到 11 个 Cookie。
- Chrome 关闭后，其 Cookie 数据库仅保留 8 个 `weibo.com` / `passport.weibo.com` Cookie；关键 `.weibo.cn` 会话 Cookie 未持久化。
- 因此第二次启动时，移动端登录检查缺少有效会话。该结论是基于运行证据的推断，本任务未修改源码验证修复方案。

## 清理与安全检查

- 已恢复 `CDP_CONNECT_EXISTING = True`。
- 端口 9222 已关闭。
- MediaCrawler submodule 工作树干净，仍固定在 `d6f7c5b`。
- 未记录或输出 Cookie 内容，只记录数量和域名级诊断。
- 未删除或覆盖父仓库现有的 `db_data/`、`logs/`。

## 后续候选

- 单独设计 MediaCrawler 登录态显式保存/恢复机制，例如 Playwright `storage_state` 或受控 Cookie 持久化适配。
- 避免 CLI 空 `--specified_id` 回退到仓库示例 ID，确保登录验证不会意外采集默认内容。
