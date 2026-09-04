# 本机旧 SQLite 备份清理记录

执行时间：2026-09-05（Asia/Shanghai）

## 保护范围

- 当前运行库 `/Users/jonathanhu237/code/longtian-public-opinion-management/runtime/longtian.sqlite3` 未移动。
- 专用浏览器 Profile `/Users/jonathanhu237/code/longtian-public-opinion-management/runtime/browser/managed-chrome` 未移动。
- 目标目录：`/Users/jonathanhu237/.Trash/longtian-backups-20260905`。

## 目标清单

本次命令在移动前逐项检查了以下 23 个源路径：

```text
runtime/ai-config-backup.OFUVkC/longtian.sqlite3
runtime/ai-media-probe.hAxXN3/before.sqlite3
runtime/backups/longtian-before-content-clear-20260904.sqlite3
runtime/backups/longtian-before-schema14-20260829.sqlite3
runtime/backups/longtian-before-v19-20260902.sqlite3
runtime/e2e-acceptance.WrsAaH/before.sqlite3
runtime/e2e-best-effort.pYGAA2/before-live.sqlite3
runtime/e2e-final.dawoVc/after-live.sqlite3
runtime/e2e-final.dawoVc/before-live.sqlite3
runtime/e2e-final.dawoVc/migration-probe.sqlite3
runtime/e2e-report-retry.xYp1t5/after-report.sqlite3
runtime/e2e-report-retry.xYp1t5/before-migration.sqlite3
runtime/e2e-reset.NjshhB/before-reset.sqlite3
runtime/live-search-acceptance.kfbsAw/before.sqlite3
runtime/longtian.before-batch-v7-20260826.sqlite3
runtime/longtian.before-douyin-live-20260826-152051.sqlite3
runtime/longtian.before-kuaishou-live-20260826-140730.sqlite3
runtime/longtian.before-weibo-live-20260826.sqlite3
runtime/manual-recovery-backup.TcMrPl/before.sqlite3
runtime/pre-v11-start.yqlZxO/longtian.sqlite3
runtime/rule-cleanup.XCZUrb/before.sqlite3
runtime/toutiao-fix-backup.YCHL2G/before.sqlite3
runtime/toutiao-fix.BstDT2/before.sqlite3
```

## 结果与可恢复性说明

这些源文件被使用 `mv` 移入目标目录，没有删除运行库或浏览器目录。不过目标目录使用了扁平布局，而多个源路径的文件名相同；因此文件系统重命名时发生了覆盖：目标目录目前保留 15 个唯一的 `.sqlite3` 主文件（以及它们现存的 SQLite `-wal`/`-shm` 旁车文件），8 个较早的同名备份无法从该目录恢复。

仍保留的目标文件包括：

```text
after-live.sqlite3
after-report.sqlite3
before-live.sqlite3
before-migration.sqlite3
before-reset.sqlite3
before.sqlite3
longtian-before-content-clear-20260904.sqlite3
longtian-before-schema14-20260829.sqlite3
longtian-before-v19-20260902.sqlite3
longtian.before-batch-v7-20260826.sqlite3
longtian.before-douyin-live-20260826-152051.sqlite3
longtian.before-kuaishou-live-20260826-140730.sqlite3
longtian.before-weibo-live-20260826.sqlite3
longtian.sqlite3
migration-probe.sqlite3
```

运行库迁移前已确认没有采集结果、运行、批次、报告或自动任务运行记录；迁移后保留了 AI 配置和监测规则，并通过了外键检查。该清单如实记录了扁平移动造成的同名覆盖，不能把 15 个剩余文件表述为完整的 23 份备份。
