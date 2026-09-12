# v0.2.0 发行资产验证记录

状态：**待用户验收**（草稿保持未公开）。

## 发布来源

- 固定规格：`.scratch/opinion-workbench-rename/spec.md`
- 审查证据：`.scratch/opinion-workbench-rename/review-2.md`（R1–R4 已通过；本记录只跟进发行，不进行新的代码实现或审查）
- tag：`v0.2.0`
- source commit：`fc2ca91a3ec1b66e7be9e1337f09bee68bfde353`
- GitHub Actions run：[34704345345](https://github.com/jonathanhu237/opinion-workbench/actions/runs/34704345345)
- run 结果：`Portable release` 的 `windows`、`macos`、`draft` 三个 job 均 `success`
- Release 草稿：[v0.2.0](https://github.com/jonathanhu237/opinion-workbench/releases/tag/untagged-487e9801ff745d8c1af3)
- Release 状态：`draft=true`、`prerelease=false`、`published_at=null`、`target_commitish=fc2ca91a3ec1b66e7be9e1337f09bee68bfde353`

未移动旧 tag、未覆盖旧资产、未公开草稿。

## 下载资产

使用 `gh release download v0.2.0 --repo jonathanhu237/opinion-workbench --dir /tmp/opinion-workbench-v0.2.0.In3cPo` 下载到临时目录 `/tmp/opinion-workbench-v0.2.0.In3cPo`。Release 恰有以下四个资产：

| 资产名 | 字节数 | 下载文件 SHA-256 |
| --- | ---: | --- |
| `OpinionWorkbench-v0.2.0-Windows-x64.zip` | 88,788,755 | `f94a1436abfb9be22bb1b420dd0f5ef9a842ea3655e0ff3b30db7320fc1386d6` |
| `OpinionWorkbench-v0.2.0-Windows-x64.zip.sha256` | 107 | `04a5fd1dd5a742209897875b3c86a75a85278a387f5f43bccedf24376f9970b1` |
| `OpinionWorkbench-v0.2.0-macOS-arm64.zip` | 89,513,168 | `4db8822ae69c8a8a678be537e652920b180991fbc3a0a471f9062924638e9c34` |
| `OpinionWorkbench-v0.2.0-macOS-arm64.zip.sha256` | 106 | `75f68dd167ff0b3d87b847388f8349b30294cf73eaef49a32c434b38cd32fd17` |

两个 ZIP 的 sidecar 内容分别为：

```text
f94a1436abfb9be22bb1b420dd0f5ef9a842ea3655e0ff3b30db7320fc1386d6  OpinionWorkbench-v0.2.0-Windows-x64.zip
4db8822ae69c8a8a678be537e652920b180991fbc3a0a471f9062924638e9c34  OpinionWorkbench-v0.2.0-macOS-arm64.zip
```

两份 sidecar 均引用对应 ZIP basename，下载 ZIP 的 SHA-256 与 sidecar 内容一致。

## 验证命令及结果

```text
$ python3 scripts/validate_portable_release.py v0.2.0 fc2ca91a3ec1b66e7be9e1337f09bee68bfde353 --assets /tmp/opinion-workbench-v0.2.0.In3cPo
Portable assets verified; draft-only upload permitted.
```

该命令调用现有 `validate_assets`，并由其调用现有 `audit_archive`。另外直接调用 `audit_archive` 的结果为：

```text
AUDIT_ARCHIVE Windows-x64: passed
AUDIT_ARCHIVE macOS-arm64: passed
VALIDATE_ASSETS: passed
```

审计结果：

- Windows ZIP：383 个成员；`version=v0.2.0`、`source=fc2ca91a3ec1b66e7be9e1337f09bee68bfde353`、`architecture=x86_64`、`minimum_windows=10`；解压后二进制为 PE32+ x86-64。
- macOS ZIP：407 个成员；`version=v0.2.0`、`source=fc2ca91a3ec1b66e7be9e1337f09bee68bfde353`、`architecture=arm64`、`minimum_macos=14.0`；解压后二进制为 Mach-O 64-bit arm64。
- 两个 ZIP 均通过压缩包根目录、路径安全、私有/运行时资料排除、必需程序与静态资源、版本/来源提交/架构元数据以及 macOS 执行权限审计。

GitHub Actions 的构建步骤已完成解压启动烟雾检查；本记录不将其扩展为 Finder/Explorer 双击或系统安全提示验收。

## 未完成项

需要用户人工检查资产和说明，并决定是否公开草稿。Finder/Explorer 双击、系统安全提示、真实平台采集、平台登录和付费模型调用均未执行，状态仍为待用户验收。CI 的 Node.js 20 弃用提示为非阻塞 warning。
