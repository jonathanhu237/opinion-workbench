# 复用本机浏览器登录态：规划记录

## 结论

复用用户正在使用的 Chrome 适合首次登录检测和人工辅助登录，但不宜作为每日
无人值守采集的唯一运行方式。推荐后续采用混合模式：交互阶段连接现有 Chrome
检测五个平台；后台采集阶段使用应用专属的最小登录态或专属浏览器 Profile。

该能力不属于当前 React + FastAPI 初始化任务的实现范围。

## 事实依据

- Chrome 136 起，命令行远程调试不能直接控制默认用户数据目录，官方建议使用
  非默认目录隔离自动化。
- Chrome 144 起提供 `chrome://inspect/#remote-debugging` 的显式授权流程，可在
  用户批准后连接正在运行的默认 Chrome；每次新连接需要用户确认。
- Playwright 的 `connect_over_cdp` 仅支持 Chromium，并明确说明其能力完整度低于
  Playwright 原生协议连接。
- Chrome 的授权警告说明：远程调试客户端能够读取保存数据、Cookie 和站点数据，
  并可导航到任意 URL，因此必须限制在本机可信客户端。

## 当前 MediaCrawler 适配情况

- 小红书、抖音、微博、快手已接入 `CDPBrowserManager`。
- 今日头条目前明确忽略 CDP 配置，启动独立可见浏览器；若采用统一的本机浏览器
  检测流程，需要另行适配。
- `CDPBrowserManager` 已有 `CDP_CONNECT_EXISTING` 路径，可等待本机 Chrome
  远程调试授权并通过 CDP 连接。

## 推荐的后续登录中心流程

1. 检测本机受支持的 Chrome 及版本。
2. 引导用户在 `chrome://inspect/#remote-debugging` 开启授权，并接受连接请求。
3. 为五个平台分别打开临时标签页，调用平台级在线登录探针，不仅检查 Cookie
   是否存在。
4. 显示 `已登录`、`未登录`、`登录态失效`、`无法检测` 状态。
5. 未登录的平台由用户在当前浏览器中人工登录，然后重新检测。
6. 如果需要无人值守采集，经用户明确选择后，将目标域名白名单内的最小 Cookie
   保存为应用专属登录态；否则仅在当前浏览器连接存活时工作。

## 方案比较

### A. 直接复用用户默认 Chrome

- 首次体验最好，直接使用用户已有的五个平台登录态。
- 需要 Chrome 正在运行或由程序启动，并由用户批准远程调试连接。
- 对用户全部日常标签页、Cookie 和站点数据具有过大的控制面。
- Chrome 或后端重启后可能需要重新授权，不适合作为严格无人值守任务的唯一方案。
- 当前小红书、抖音、微博、快手已有 CDP 基础，今日头条仍需统一适配。

### B. 应用专属持久化 Chrome Profile

- 用户需要在专属浏览器中首次登录五个平台一次。
- 此后应用可自行启动浏览器，无需控制用户日常 Profile 或重复批准 CDP。
- 能保留 Cookie、LocalStorage、IndexedDB 和设备相关状态，平台兼容性通常优于
  只保存 Cookie。
- 登录和浏览数据与日常 Chrome 隔离，适合作为定时采集的默认执行环境。
- 会占用更多磁盘，并需要管理 Profile 锁、异常退出和版本兼容。

### C. 新浏览器上下文 + 最小 Cookie 文件

- 当前派生仓库已有 `BrowserAuthStateStore` 基础，改造量较小。
- 数据量小、容易校验和按平台隔离，也可自动运行。
- 对依赖 LocalStorage、IndexedDB、设备状态或更严格风控的平台，登录恢复可能不如
  完整 Profile 稳定。

### D. 首次复用默认 Chrome，再导出最小登录态

- 首次体验和后续无人值守兼顾。
- 需要维护“默认 Chrome CDP + 登录态导出 + 应用浏览器恢复”两套路径。
- 登录凭据跨浏览器环境迁移可能触发平台验证，复杂度最高，适合作为后续体验优化，
  不适合作为 MVP 前置条件。

### E. 将最小 Cookie 放入 SQLite

- 这只是 C/D 的存储实现，不改变浏览器是否可无人值守或登录恢复是否稳定。
- SQLite 默认不加密；将凭据与业务数据放在同一个数据库会增加导出泄漏风险。
- 当前文件存储已可工作，除非后续明确需要加密、事务或单文件备份，否则不优先改造。

## 已确认决策（2026-08-24）

MVP 优先采用 A：复用用户当前 Chrome Profile，以已有真实环境和登录连续性为先。
Chrome 未运行时由程序启动；用户按 Chrome 安全机制批准远程调试连接，后端尽量
保持该 CDP 连接，避免每次采集重复授权。

应用专属持久化 Profile 保留为未来可选模式，仅在用户明确要求完全无人值守、并能
接受重新登录与独立 Profile 时再实施。Cookie 导入和 SQLite 登录态存储不作为 MVP
前置能力。

## 风险与约束

- 纯复用模式依赖 Chrome 正在运行、远程调试已启用并且用户批准连接，无法保证
  定时任务始终可执行。
- 自动化操作可能与用户正在浏览的标签页互相干扰，应使用临时标签页并及时关闭。
- 远程调试端口只能监听 loopback，不应暴露给局域网。
- 登录状态需要通过平台接口或页面行为验证，不能仅根据 Cookie 名称判断。

## 风控假设与验证要求

- 用户默认 Profile 拥有更长时间的 Cookie、LocalStorage、IndexedDB、缓存、设备
  标识和真实使用连续性；专属新 Profile 缺少这些历史状态，理论上可能更容易触发
  新设备验证或平台风控。
- 专属 Profile 并非每次新建。若长期复用同一目录、使用本机真实 Chrome、固定设备
  和网络、headed 运行并由用户首次人工登录，它会逐步形成稳定状态，风险显著低于
  每次创建临时上下文或只注入 Cookie。
- 平台不会公开完整风控规则，因此上述结论属于基于浏览器持久状态和指纹研究的工程
  推断，不能代替五个平台的实测。
- 在正式决定默认 Profile 前，应对候选平台做低频 A/B 验证，记录登录挑战次数、
  滑块/短信验证、会话存活时间、搜索成功率和对日常浏览器的干扰。
- 如果默认 Chrome 的实测通过率明显更高，应优先采用默认 Chrome + 持久 CDP
  连接，即使牺牲完全无人值守；能够执行且偶尔需授权，优于无人值守但持续触发风控。

## Primary Sources

- https://developer.chrome.com/blog/remote-debugging-port
- https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session
- https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect
- https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp
