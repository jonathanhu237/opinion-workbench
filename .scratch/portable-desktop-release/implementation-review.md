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

Spec：上述阻塞项已修正；Windows 原生构建及 GitHub Actions 尚未执行，不能视为 Windows 实机验收或双平台发行已完成。

## 父代理验证

- 后端全量：1288 passed，2 skipped，283.85 秒。
- 前端：40 个测试文件，577 项通过；TypeScript 检查通过。前端 lint 在本轮也已通过。
- 本机为 Apple Silicon，实际构建最终 Mac arm64 ZIP；通过解压后的“启动.command”入口启动，移除开发 PATH／Python 环境影响，在不同 cwd 下验证健康检查、静态页、偏好接口与 data/ 数据库。
- 包内辅助进程通过离线 broker 协议检查，没有真实平台或模型调用。
- WebSocket 页面租约断开后等待程序自己正常退出，不以 Windows 不支持的信号作为成功路径。
- 最终 ZIP 通过源信息、架构标记、必需资源、执行权限及私有运行资料审计。
- 官方 GitHub runner 文档确认 macos-14 属于 arm64；仍以实际构建架构检查为准。来源：https://docs.github.com/en/actions/reference/runners/github-hosted-runners。

日志：/tmp/portable-final-backend-full.log、/tmp/portable-final-frontend.log、/tmp/portable-final-macos-build.log、/tmp/portable-final-worker-smoke.log。

## 当前产物

- dist/macos/Longtian-dev-macOS-arm64.zip
- dist/macos/Longtian-dev-macOS-arm64.zip.sha256
- SHA-256：4411ca71f6e23e290c2033b4d04e8d17b72d5e251824115549139cd39785b420

以上是未提交工作区生成的 dev 包，不是已发布版本。未创建 Windows ZIP；已有平台构建脚本与Actions流程已准备，但Windows本机／runner构建、Explorer双击、系统安全提示和真实平台链路均待验收。Mac Finder双击及下载隔离弹窗也不能由shell启动测试替代。

没有提交、推送、创建标签、触发工作流或上传 GitHub Release。已存在的真实采集暂停批次和用户数据未用于这轮测试。等待用户验收及后续发布操作授权。
