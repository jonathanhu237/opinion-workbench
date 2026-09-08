# 修复前已有的后端测试失败

这些用例在 DeepSeek 接入前已失败，不能据此宣称当前全量测试通过。大部分覆盖旧媒体输入或仅微博产品约束；是否废弃或更新需按当前产品规格逐项核对，不直接删除以获得绿灯。

- test_ai_analysis.py: 11
- test_ai_summaries.py: 1
- test_best_effort_enrichment.py: 2
- test_collection_schedule_repository.py: 1
- test_content_analyses.py: 2
- test_content_analysis_repository.py: 2
- test_content_enrichment.py: 1
- test_content_understanding.py: 3
- test_generation_cancellation.py: 1
- test_generation_failures.py: 1
- test_library_report_selection.py: 1
- test_media_cache.py: 7
- test_media_capacity.py: 3
- test_media_retention.py: 3
- test_native_image_report.py: 12
- test_native_text_report.py: 3
- test_native_video_report.py: 8
- test_search_recovery.py: 19
- test_topic_report_engine.py: 1
- test_weibo_only_migration.py: 2
- test_weibo_only_product.py: 4

总计：88 项。
