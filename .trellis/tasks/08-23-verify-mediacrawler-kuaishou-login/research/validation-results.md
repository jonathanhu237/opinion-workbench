# MediaCrawler 快手登录验证记录

日期：2026-08-23

## 结论

快手原生首次扫码能够成功，但完全关闭 Chrome 后，同一 profile 的第二次启动首次服务端 `pong()` 仍为假并再次进入二维码流程。按批准的条件式方案接入现有 `BrowserAuthStateStore` 后，真实两次启动回归通过：首次扫码后的二次 `pong()` 为真并保存状态；第二次启动先恢复状态，首次 `pong()` 直接为真，未进入登录类、未展示二维码、未采集内容。

## 隔离与运行配置

- 平台：`ks`
- 登录方式：`qrcode`
- 运行模式：`auth_validation`，未进入 search/detail/creator 分支
- 浏览器：MediaCrawler 启动的独立 Google Chrome 151
- CDP：`ENABLE_CDP_MODE=True`、`CDP_CONNECT_EXISTING=False`、端口 9222
- 登录态：`SAVE_LOGIN_STATE=True`
- 清理：`AUTO_CLOSE_BROWSER=True`
- 内容与评论采集均未执行

浏览器 profile 只写入任务专用 `/tmp/mediacrawler-ks-*` 目录，没有使用或删除项目现有 `browser_data/`、`db_data/` 或 `logs/`。

## 执行证据

### 隔离运行器修正

第一次隔离启动成功连接 CDP，但快手 GraphQL 模板使用仓库相对路径，进程在临时工作目录创建 client 时因找不到模板而退出。Chrome、端口和该次临时目录随后均已清理；此时尚未进入登录流程。

后续运行保持浏览器 profile 位于临时目录，只在 CDP 启动完成后把进程工作目录切回 MediaCrawler 仓库，以便读取现有 GraphQL 模板。该修正仅存在于验证命令中，没有修改源码。

### 前置安全验证

一次原生启动在点击登录前被快手官方“请完成安全验证”拼图滑块遮罩拦截。只读页面诊断确认登录元素仍存在，拦截来自全屏安全验证遮罩，而非登录选择器消失。未自动处理或绕过滑块。

### 原生基线

早期一次二维码尝试因未及时扫码，在现有 600 次、每次 1 秒的轮询策略结束后超时。用户可及时操作窗口后，使用全新隔离 profile 重新执行并得到完整基线：

1. 独立 Chrome、CDP 9222 和快手首页启动成功。
2. 首次服务端 `pong()` 为假，原生 `KuaishouLogin` 展示二维码。
3. 用户扫码并在手机端确认后，原生登录轮询检测成功，认证验证模式正常结束。
4. Chrome 和 9222 完全关闭后，以同一隔离 profile 第二次启动。
5. 第二次启动的首次服务端 `pong()` 仍为假，并再次进入 `KuaishouLogin`、展示二维码。

该结果证明单靠快手 Chrome profile 不能满足免重复扫码，因此触发批准的条件式接线。

### 条件式接线

- 在快手 BrowserContext 和页面准备完成后创建 `BrowserAuthStateStore(platform="ks", urls=["https://www.kuaishou.com"])`。
- 恢复发生在 client 创建和首次服务端 `pong()` 前。
- 首次 `pong()` 失败时保留原生二维码流程；扫码后更新 client，并增加二次服务端 `pong()`。
- 只有服务端确认登录有效时才保存状态；`SAVE_LOGIN_STATE=False` 时完全跳过 store。
- 通用认证状态 helper、其他平台和采集逻辑均未修改。

### 接线后的真实两次启动回归

使用另一个全新隔离目录执行：

1. 首次启动：首次 `pong()` 为假，原生二维码扫码成功；更新 client 后二次 `pong()` 为真，状态保存成功。
2. 状态文件 POSIX mode 为 `0600`；默认 `browser_data/auth_state/ks.json` 命中仓库 `/browser_data/` Git ignore 规则。
3. Chrome 和 9222 完全关闭。
4. 第二次启动：状态先于 client 创建恢复，首次服务端 `pong()` 直接为真。
5. 第二次启动没有进入 `KuaishouLogin`、没有展示二维码，也没有采集内容。
6. 第二次运行正常结束并关闭 Chrome。

证据只记录状态、顺序、数量和文件元数据，不包含 Cookie 名称、Cookie 值、二维码内容或请求认证头。

## 验收状态

| 验收项 | 状态 | 说明 |
| --- | --- | --- |
| 独立 Chrome 和快手页面打开 | 通过 | CDP 9222 正常连接 |
| 原生二维码显示 | 通过 | 登录入口点击和二维码提取成功 |
| 首次扫码登录 | 通过 | 原生登录轮询检测成功 |
| 登录后服务端 `pong()` | 通过 | 接线后二次 `pong()` 为真才保存 |
| 第二次启动免扫码 | 通过 | restore 后首次 `pong()` 为真，无二维码 |
| 状态文件安全边界 | 通过 | mode `0600`，默认路径被 Git 忽略 |
| 无内容采集 | 通过 | `auth_validation` 未匹配采集分支 |
| 运行环境清理 | 通过 | Chrome 退出、9222 未监听、任务临时目录已删除 |

## 代码与工作树

- `third_party/MediaCrawler` 仍在 `main`，只包含批准范围内的 `media_platform/kuaishou/core.py` 修改和 `tests/test_kuaishou_auth_state.py` 新文件。
- 通用认证状态 helper、其他平台源码和项目运行目录未修改。
- 父仓库既有未跟踪 `db_data/`、`logs/` 保持不变。

## 下一步

- focused tests：22 项通过（快手编排、通用 store、微博回归）。
- 完整 `tests/`：118 项通过。
- scoped pre-commit、`compileall` 和 `git diff --check` 通过。
- 最终复核执行了项目级 mypy：共报告 119 个分布于 22 个既有导入模块的存量错误；本次快手变更行及新增测试没有新增错误。
- 全量 pre-commit 暴露仓库既有 header/EOF 问题并修改了无关文件；所有由该 hook 产生的计划外改动已精确恢复，随后对本任务两文件执行 scoped pre-commit 并通过。
