# 微博浏览器发现接入记录

Status: implemented-offline

## 边界

显式运行选择 `LONGTIAN_COLLECTOR_BACKEND=native-weibo` 接入项目拥有的微博 DOM 采集器；缺省仍为 legacy，14 完成前不切换日常入口。不调用 MediaCrawler 搜索或补全、不导出 Cookie、不读取日常 Chrome Profile。启动保持懒加载，读取应用列表不启动 Chrome。

目前实现针对本机 macOS 的系统 Chrome，沿用 `runtime/browser/managed-chrome`。仅该专用目录的锁和调试端点用于进程协调；目录不私密、存在符号链接或已有 Chrome 占用时拒绝启动，不修复或删除登录数据。沿用旧运行时的互斥锁文件，关闭只作用于自己启动的进程。`--no-startup-window` 阻止启动时恢复历史窗口，然后通过项目拥有的新页访问微博。

执行上限独立于工作量：默认 40 次页面导航、1,200 次受控页 HTTP 请求、180 秒，导航间隔 2 秒。它们不是成功率或无风控承诺，也不是整个 Chrome（更新/扩展等）后台流量计数。CDP Fetch 在发出请求前计数，每个重定向经过检查；跳过页的 Service Worker、关闭本页 WebSocket。仅允许微博及列明的新浪静态资源域 HTTPS，请求预算耗尽后停止本页。安全页面暂停时阻止后续程序请求；用户点击打开平台后才释放页面供人工处理，采集仍需显式继续。

搜索解析只读取渲染后的 DOM，按 mid 与相关帖子链接共同证明身份，统一为 m.weibo.cn/detail/mid。页面不含成功/无结果证据时等待有限时间，最终给出可理解诊断，不当成空结果。v22 仅给历史 search_runs 增加可空 execution_limit 字段；时间/页数/请求预算可追溯，既有记录不改状态。

## 验证与待验收

13 项浏览器页面/应用链路样本与 9 项进程/CDP 外部替身测试覆盖正常入库、跨词/批次别名、失败后再发现、空页与验证区分、预算与取消、人工继续、目录保护和禁止站外请求。另有相关后端 240 项、前端 87 项回归通过，typecheck 与新增源码 Ruff 检查通过；最后启动参数调整另行复测。

所有账号、DOM、Chrome 进程、模型都是隔离样本或替身，没有启动真实 Chrome、采集微博或访问小红书。实站 DOM 选择器、系统 Chrome/CDP 版本兼容性、登录状态识别及实际网络范围仍由 14 做有界验收，不能用离线通过代替。当前 URL 补全与原媒体下载尚未接入，未适配平台入口统一停用由 13 收口。

## 核验依据

- [Playwright 的 CDP 接入说明](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)：绑定既有浏览器的默认上下文；no_defaults 保留上下文默认设置。官方同时提示 CDP 兼容性低于自有协议，因此保留实机验证门槛。
- [CDP Fetch](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/) 与 [Network](https://chromedevtools.github.io/devtools-protocol/tot/Network/)：发出前暂停、继续/拒绝请求，以及 Service Worker bypass。未调用网络响应体读取来替代搜索页面解析。
- [Chromium 启动逻辑](https://chromium.googlesource.com/chromium/src/+/lkgr/chrome/browser/ui/startup/startup_browser_creator.cc)：no-startup-window 的启动窗口行为。
- [weibo-mid 已公开的转换示例](https://github.com/node-modules/weibo-mid)：验证 MID/BID 数值对应关系；项目没有引入该 npm 包或复制实现。

锁文件与专用目录协议来自项目既有运行时的兼容约束，而不是对用户日常浏览器的自动发现。
