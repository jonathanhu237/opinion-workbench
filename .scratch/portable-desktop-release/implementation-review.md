# 双平台便携发行实施与审查记录

Status: awaiting-user-acceptance

## 固定基线与范围

原始规格为本目录 spec.md，未改变验收范围。Git 基线 cda5fa20bfe4a5e4da39b180c0be43b8e7359651，另保存整个原有未提交工作区到本机临时快照；位置记录在 /tmp/longtian-portable-baseline-location。原有 Windows、总结并发和平台间隔改动作为基线保留，不重置、提交或推送。

指定 Luna Max 实现并自测；父代理直接进行累计审查，不委派审查者。一次仅返回启动承诺的调用无实施成果，随后重新发实施调用；路径拼写错误的失败调用未实际执行代码，不计入修复次数。

## 审查

1. 初轮发现：偏好仍仅在浏览器保存；烟雾测试只检查文件存在；发布缺少已公开版本保护；Mac 资产缺版本元数据；缺少新测试与资产审计；Windows 升级说明仍反映旧数据目录。返回第一次修复。
2. 第二轮发现：烟雾驱动使用无效端口／不存在的开关，Mac 元数据不在压缩根目录，发布保护未完整校验版本／校验值，偏好 API 仍存在输入与目录隔离问题。返回第二次修复。
3. 第三轮对仍未解决项直接修复并验证：严格校验并发偏好、按注入数据库隔离文件路径、前端读取便携偏好、晚到偏好不覆盖用户修改、正常页面关闭驱动跨平台退出、离线辅助进程协议检查、草稿同提交与资产严格校验、构建源／架构信息、UTF-8 ZIP执行位和内部符号链接。

Standards：新增模块按现有校验与隔离契约修正；直接修改代码的 Ruff、格式检查和 diff 检查通过。

Spec：上述阻塞项已修正；以下是审查时的待执行状态，后续实际的 Windows 原生构建及 GitHub Actions 发布结果见“发布执行记录”。

## 父代理验证

- 后端全量：1288 passed，2 skipped，283.85 秒。
- 前端：40 个测试文件，577 项通过；TypeScript 检查通过。前端 lint 在本轮也已通过。
- 本机为 Apple Silicon，实际构建最终 Mac arm64 ZIP；通过解压后的“启动.command”入口启动，移除开发 PATH／Python 环境影响，在不同 cwd 下验证健康检查、静态页、偏好接口与 data/ 数据库。
- 包内辅助进程通过离线 broker 协议检查，没有真实平台或模型调用。
- WebSocket 页面租约断开后等待程序自己正常退出，不以 Windows 不支持的信号作为成功路径。
- 最终 ZIP 通过源信息、架构标记、必需资源、执行权限及私有运行资料审计。
- 官方 GitHub runner 文档确认 macos-14 属于 arm64；仍以实际构建架构检查为准。来源：https://docs.github.com/en/actions/reference/runners/github-hosted-runners。

日志：/tmp/portable-final-backend-full.log、/tmp/portable-final-frontend.log、/tmp/portable-final-macos-build.log、/tmp/portable-final-worker-smoke.log。

## 实施阶段产物（发布前记录）

- dist/macos/Longtian-dev-macOS-arm64.zip
- dist/macos/Longtian-dev-macOS-arm64.zip.sha256
- SHA-256：4411ca71f6e23e290c2033b4d04e8d17b72d5e251824115549139cd39785b420

以上是发布前未提交工作区生成的 dev 包，不是发布版本；后续 v0.1.2 的远端资产与草稿结果见下文。Mac Finder 双击及下载隔离弹窗仍不能由 shell 启动测试替代。

## 发布执行记录（2026-09-12）

本次已按用户授权执行发布，但草稿仍保持未公开；`Status` 继续为 `awaiting-user-acceptance`，等待维护者人工检查并决定是否公开。

### 标签、修复与工作流

- 已创建并推送不可移动的 `v0.1.0`（`2c8edb43e6a83dabacf89a3ceb43b15e84e4ffb9`）。运行 [34694162871](https://github.com/jonathanhu237/longtian-public-opinion-management/actions/runs/34694162871) 失败：`mise` `2025.10.10` 无法解析 `pnpm 11.14.0` 的平台资产。
- 修复并推送 `fix(ci): use compatible mise release`（`8bc3c20c66fc398fd2d1368c0e8ab532086522b6`），创建并推送不可移动的 `v0.1.1`。运行 [34694246488](https://github.com/jonathanhu237/longtian-public-opinion-management/actions/runs/34694246488) 的 macOS 作业通过，Windows 作业因把受版本控制的 `frontend/.env.example` 误判为敏感文件而失败。
- 修复并推送 `fix(windows): allow tracked environment template`（`a5249616a3dc2fa6caecd4113dc8652f0ff5b9d9`），创建并推送 `v0.1.2`。此前已修正 draft job 使用不带版本的 macOS 资产 glob；工作流同时固定到 `mise 2026.8.9`。
- [v0.1.2 工作流运行 34694374470](https://github.com/jonathanhu237/longtian-public-opinion-management/actions/runs/34694374470) 的 Windows、macOS 和 draft 三个作业均成功，源提交均为 `a5249616a3dc2fa6caecd4113dc8652f0ff5b9d9`。

### GitHub Release 草稿

- 草稿（保持未公开）：[v0.1.2 draft](https://github.com/jonathanhu237/longtian-public-opinion-management/releases/tag/untagged-82182be39d58242f0238)（Release ID `387568299`，`draft=true`，目标提交 `a5249616a3dc2fa6caecd4113dc8652f0ff5b9d9`）。
- 远端资产集合已核对为恰好两个 ZIP 和两个 SHA-256 校验文件：

  | 文件 | 大小（bytes） | ZIP SHA-256 |
  | --- | ---: | --- |
  | `Longtian-v0.1.2-Windows-x64.zip` | 88,783,915 | `9956835fd2ba0b86dfd6d20c0f2ff3e4121763a3117c25f0e0841758b56043cc` |
  | `Longtian-v0.1.2-Windows-x64.zip.sha256` | 99 | — |
  | `Longtian-v0.1.2-macOS-arm64.zip` | 89,504,971 | `1abae85f4bb05b149e47087f7e232d91802e2fa9e10d0baefbbae2cd711f92e9` |
  | `Longtian-v0.1.2-macOS-arm64.zip.sha256` | 98 | — |

  已从 GitHub 下载远端资产，逐一核对 sidecar 内容与 ZIP SHA-256；两个 ZIP 也通过 `validate_portable_release.py` 的版本、源提交、架构、资源、路径安全和运行资料审计。

### 验证边界

- 本地后端全量：`1288 passed, 2 skipped`；前端：`577 passed`，TypeScript 检查和 lint 通过。
- CI 两个平台的最终 ZIP 解压烟雾检查、静态资源/API/本地数据目录、包内辅助进程离线协议和正常页面关闭退出均通过。
- 未进行 Finder/Explorer 双击、系统隔离提示、真实平台采集、登录或付费模型调用；CI 烟雾测试不冒称这些验收。未使用 Centaurus、个人 runtime 数据或真实业务请求。
- 草稿没有自动公开；发布前仍需人工确认资产和说明后再在 GitHub UI 中公开。
