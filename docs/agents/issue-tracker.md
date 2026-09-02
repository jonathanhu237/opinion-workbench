# Issue tracker: Local Markdown

本仓库的任务和规格存放在 `.scratch/` 下，使用 Markdown 文件管理。

## 约定

- 每个功能使用独立目录：`.scratch/<feature-slug>/`。
- 规格文件：`.scratch/<feature-slug>/spec.md`。
- 每张任务单独存放于 `issues/<NN>-<slug>.md`，编号从 `01` 开始。
- 任务状态使用文件顶部的 `Status:` 行记录。
- 评论和讨论历史追加到文件底部的 `## Comments` 下。

## 当技能要求发布到任务跟踪系统

在对应功能目录下创建规格或任务文件，必要时创建目录。

## 当技能要求读取相关任务

读取指定路径的文件。仅提供编号且存在歧义时，先确定所属功能。

## Wayfinding 操作

供 `/wayfinder` 使用：

- 工作地图：`.scratch/<effort>/map.md`，记录 Notes、Decisions-so-far 和 Fog。
- 子任务：`.scratch/<effort>/issues/<NN>-<slug>.md`，正文记录待解决的问题。
- 类型：使用 `Type:` 行，值为 research、prototype、grilling 或 task。
- 状态：使用 `Status:` 行，值为 open、claimed 或 resolved。
- 依赖：使用 `Blocked by: NN, NN`；所有依赖任务 resolved 后才可开始。
- 选择任务：按编号选取首个 open 且依赖已解决的任务。
- 领取任务：开始工作前将状态改为 claimed 并保存。
- 完成任务：在 `## Answer` 下追加结果，将状态改为 resolved，
  并将摘要和任务文件链接追加到 map.md 的 Decisions-so-far。
