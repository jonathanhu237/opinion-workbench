"""Seed synthetic v9 history before syncing v10; never use a real runtime DB."""

import os
from pathlib import Path

from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.repositories.search_runs import (
    SearchContentInput,
    SearchRunRepository,
)

path = Path(os.environ["LEGACY_RECOVERY_DATABASE"]).resolve()
assert path.is_relative_to(Path("/tmp/longtian-recovery-validation.EcUhyX"))
assert not path.exists()
assert CURRENT_DATABASE_VERSION == 9
database = Database(path)
database.initialize()
batches = SearchBatchRepository(database)
runs = SearchRunRepository(database)
batch = batches.create_batch(
    monitoring_rule_id=1,
    rule_name="旧版失败与暂停记录（模拟）",
    terms=tuple(f"对象 {position + 1}" for position in range(20)),
    platforms=("toutiao", "wb", "ks", "dy", "xhs"),
    max_results_per_term=10,
)
batches.mark_running(batch.id)
outcomes = (
    (6, "structure_changed"),
    (19, "completed_empty"),
    (19, "completed_empty"),
    (19, "completed_empty"),
    (16, "manual_challenge_required"),
)
for item_position, (last_started, outcome) in enumerate(outcomes):
    run = batches.create_attempt(batch.id, item_position)
    runs.mark_running(run.id)
    for term_position in range(last_started + 1):
        runs.set_progress(run.id, term_position)
    if item_position == 4:
        runs.observe_item(
            run_id=run.id,
            term_position=16,
            item=SearchContentInput(
                platform_content_id="0123456789abcdef01234567",
                content_type="image",
                title="旧版未完成词的模拟结果",
                snippet="保留该结果，但不能把当前搜索词当成已完成。",
                creator_hash="0123456789abcdef",
                publisher_name="测***号",
                published_at_text="2026-08-27",
                content_url="https://www.xiaohongshu.com/explore/0123456789abcdef01234567",
                observed_at="2026-08-27T15:00:00+00:00",
            ),
        )
    runs.finish(run.id, outcome)
    batches.finish_item(batch.id, item_position, outcome)
assert batches.get(batch.id).status == "paused_for_manual_action"
print(
    "Seeded synthetic v9 batch: 1 failed, 3 completed, 1 paused; 5 attempts, 100 run terms, 1 partial result."
)
