# MediaCrawler 抖音认证源码调研

日期：2026-08-23

## 当前认证顺序

`media_platform/douyin/core.py` 当前执行：

```text
创建 BrowserContext
→ 打开 https://www.douyin.com
→ 从浏览器 Cookie 创建 DouYinClient
→ pong(browser_context)
→ 失败时进入 DouYinLogin
→ 更新内存 client Cookie
→ 进入 crawler 类型分支
```

登录后没有再次 `pong()`，也没有显式调用已有的 `BrowserAuthStateStore`。

## 登录状态合同

`media_platform/douyin/client.py` 的 `pong()` 不发送内容采集请求。它先读取当前页面 LocalStorage 的 `HasUserLogin`，再读取 allowlist URL 范围内 Cookie 的 `LOGIN_STATUS`；任一等于 `"1"` 即返回真。

抖音 crawler 与 client 使用同一 URL 集合：

- `https://douyin.com`
- `https://www.douyin.com`
- `https://creator.douyin.com`
- `https://douhot.douyin.com`
- `https://live.douyin.com`

真实回归必须验证恢复后第一次 `pong()` 通过且没有进入二维码流程，不能只以状态文件存在作为成功证据。

## 滑块风险

`media_platform/douyin/login.py` 在二维码登录后若页面标题为“验证码中间页”，会调用 `check_page_display_slider()`。该方法当前：

1. 读取滑块背景图和缺口图；
2. 使用 `utils.Slide` 计算距离；
3. 生成轨迹并模拟鼠标拖动；
4. 失败时刷新并最多重试 20 次。

源码 docstring 明确说明准确率不高。项目认证规范禁止自动绕过平台安全挑战，因此真实运行前必须把活动路径改为仅提示并等待人工处理，且测试应证明没有图片识别、鼠标拖动或自动刷新动作。

## 已建立的复用边界

- `tools/browser_auth_state.py` 已由微博任务实现，并经快手真实两次启动验证。
- 状态文件平台隔离、Cookie URL allowlist、损坏/过期安全回退、原子写入和 POSIX `0600` 权限可直接复用。
- 项目现有 `/browser_data/` Git ignore 规则覆盖默认 `browser_data/auth_state/dy.json`。
- 快手任务证明验证应先跑原生 profile 基线；只有第二次启动失败，才接入通用 store。

## 历史范围决定

本项目此前已确定平台顺序为快手、抖音、小红书最后验证；今日头条需要新增适配并单独规划。本任务只处理抖音认证，不扩展到内容采集或开放平台 API。
