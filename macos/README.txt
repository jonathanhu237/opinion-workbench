Longtian macOS Apple Silicon 便携版

双击“启动.command”启动。请将整个文件夹解压后使用，不要单独移动文件。
数据保存在本文件夹的 data/，移动整个文件夹仍会使用同一份数据。升级前完全退出应用，备份 data/，将新版解压到新目录后复制 data/，不要在服务运行时复制 SQLite。

本包仅支持 Apple Silicon（arm64），不包含 .app。无需 Python、Node 或开发工具；采集需要本机 Google Chrome。未签名/未公证程序可能需要在系统提示中针对本程序选择“打开”，不要关闭全局安全策略。

data/ 含数据库、配置、凭据、浏览器登录资料和日志，可能包含敏感信息，请勿分享。凭据按 macOS 文件权限保护；跨电脑复制可能需要重新配置，不承诺 Keychain 或登录态迁移。
