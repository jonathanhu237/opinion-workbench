# URL 补全工具探针

这些脚本用于 2026-09-06 的独立样本验证，结论见 [实测记录](../real-validation.md)。不是应用适配器、服务或自动测试套件。

## 环境

- 从仓库根目录运行。输出固定在被 Git 忽略的 `runtime/tool-validation/`。
- `venv` 使用 mise 管理的 Python 3.13.15；依赖快照为 [requirements-observed.txt](requirements-observed.txt)。该快照是实际探针环境，不是各上游 requirements 的原样复刻；例如 curl-cffi 实测为 0.15.0。
- F2 另有 Python 3.11.16 的 `f2-venv`，按固定提交的上游 pyproject 安装，避免 F2 的 websockets 12 与 XHS 导入的 MCP 依赖混用。其依赖快照为 [requirements-f2-observed.txt](requirements-f2-observed.txt)，F2 本身从 `upstream/f2` 安装。
- `upstream/{xhs,ks,f2,parse-video,news,weitoutiao}` 保存实测记录中对应提交的源码；脚本不会自动下载或升级它们。
- 浏览器脚本使用现有 `backend/.venv` 的 Playwright，但只创建 `runtime/tool-validation/browser` 这个专用 Chrome 用户目录。它不连接已有 CDP，也不导出 Cookie。

## 复跑入口

先运行浏览器取样。小红书笔记访问参数来自首页卡片；它们可能过期，首页推荐也会变化，因此原样脚本不是长期稳定的在线测试。

```sh
backend/.venv/bin/python .scratch/multi-platform-reintegration/probes/browser_probe.py toutiao-article xhs-discovery douyin-video ks-sample weitoutiao
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/content_probe.py toutiao-rendered
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/content_probe.py toutiao-article-image
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/content_probe.py weitoutiao
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/content_probe.py toutiao-video
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py xhs-images
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py xhs-video
runtime/tool-validation/f2-venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py douyin-f2
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py douyin-parse-video
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py ks
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py ks-rendered
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py ks-share
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py ks-parse-video
```

初次头条普通 HTTP 对照通过临时命令调用原 `ToutiaoNewsCrawler.run(persist=False)`，`fetch_attempts=1`、`fetch_timeout=15`，并用同一响应 HTML 调用 Trafilatura；结果在 `artifacts/toutiao-article-result.json` 与 `toutiao-article-trafilatura.json`。上面的 `toutiao-rendered` 使用随后保存的浏览器 HTML，不能代替这次普通 HTTP 失败记录。

`completed: true` 仅代表调用返回，不能作为内容或媒体成功断言。请检查 `error`、`message`、返回字段、预期媒体数量、磁盘文件及解码结果。原工具可能缓存已下载文件或写入整帖记录。

快手的恢复试验显式使用已有配置关闭整帖记录，并重用上一次由工具保存的元数据；若 JSON 被失败诊断覆盖，可从本次工具自己的 `artifacts/ks-share/Data/DetailData.db` 只读恢复，不访问应用业务数据库：

```sh
runtime/tool-validation/venv/bin/python .scratch/multi-platform-reintegration/probes/downloader_probe.py ks-share --ignore-tool-record --cached-detail
```

该恢复需要之前取得过有效详情。它证明图片下载的缓存续作，不能证明新的详情获取成功。首次预算中断、原记录导致跳过和后续详情失败分别保存在 `initial-budget-result.json`、`retry-skipped-result.json`、`recovery-detail-failed-result.json`。

最终媒体验证使用 Pillow `Image.verify()`，以及 ffprobe 读取流和时长、ffmpeg 前 3 秒解码。未调用 AI；若用于正式集成，应另行实现来源范围、统一预算、取消、逐媒体完整性和人工恢复控制。

## 后续：模型仅接收原帖 URL 的独立试验

用户另行授权后的模型调用见 [URL模型实测](../url-model-validation.md)。`url_only_probe.py` 使用 `backend/.venv`，只读应用当前配置及其精确凭证引用，以新的独立请求执行；不把本地基准或已下载媒体发给模型。它不修改应用运行时。

已完成的运行名为 `initial`、`stronger`、`complete-link`。请求文件采用独占创建，不能在同一目录静默重复付费请求；更换运行名会产生新调用。初次小红书选择的是裸链接；当前脚本默认选择完整标题卡片链接，`--bare-xhs` 可复现原链接形式。原始请求体保留了每轮提示词和参数，以其为准。

用户更换密钥后的 `key-updated` 运行已完成Qwen3.8-Max七条样本，见[新密钥复测](../qwen38-url-validation.md)及 `key-updated-summary.json`。`run-summary.json` 是旧密钥首轮快照，不能当成所有后续运行的总计。

本轮仅分析既有 `result.json`、`events.json`、`answer.md` 和 `run-summary.json` 即可复核，不需要重新调用模型。默认每次最多180秒、每进程最多2个请求并发；供应商内部工具调用不由此计数。不要把HTTP 200、返回回答或token消耗当作原帖读取成功；须检查 `response_status`、`response_error`、抓取证据和素材对照。
