"""Build actual historical schemas, never relabel a current schema as old."""

import json
from uuid import uuid4

from longtian_api import database as migrations
from longtian_api.database import Database


def create_legacy_schema(database: Database, version: int) -> None:
    with database.connect() as connection:
        for number in range(1, version + 1):
            getattr(migrations, f"_migrate_to_version_{number}")(connection)


def seed_historical_content(database: Database, count: int = 2) -> int:
    """Frozen v10/v11 SQL, not current repositories against an old schema."""
    timestamp = "2026-08-28T00:00:00+00:00"
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        run_id = connection.execute(
            """INSERT INTO search_runs(monitoring_rule_id,platform,rule_name,
               max_results_per_term,status,current_term_position,created_at,
               started_at,finished_at) VALUES (1,'wb','历史规则',50,
               'completed_with_results',0,?,?,?)""",
            (timestamp, timestamp, timestamp),
        ).lastrowid
        connection.execute(
            "INSERT INTO search_run_terms VALUES (?,0,'历史关键词')", (run_id,)
        )
        for index in range(count):
            identity = str(1000 + index)
            content_id = connection.execute(
                """INSERT INTO search_contents(platform,platform_content_id,
                   content_type,title,snippet,creator_hash,publisher_name,
                   published_at_text,content_url,first_seen_at,last_seen_at)
                   VALUES ('wb',?,'post','历史标题','历史摘要','','','刚刚',?,?,?)""",
                (
                    identity,
                    f"https://m.weibo.cn/detail/{identity}",
                    timestamp,
                    timestamp,
                ),
            ).lastrowid
            connection.execute(
                "INSERT INTO search_run_contents VALUES (?,?,'new',?,?)",
                (run_id, content_id, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO search_run_content_terms VALUES (?,?,0,?)",
                (run_id, content_id, timestamp),
            )
        connection.execute("COMMIT")
        return run_id


def seed_v11_summaries(database: Database, source_run_id: int) -> None:
    """Frozen v11 SQL/JSON for completed/reused/unsuccessful/active legacy rows."""
    timestamp = "2026-08-28T00:00:00+00:00"
    saved_input = json.dumps(
        {
            "schema_version": 1,
            "extractor_version": "wb-enrichment-v1",
            "acquired_at": 1750000000000,
            "status": "ready",
            "text": {
                "title": "完整历史标题",
                "body": "完整历史正文",
                "coverage": "complete",
            },
            "detected_modalities": ["text"],
            "media_inventory_complete": True,
            "assets": [],
            "issues": [],
        },
        ensure_ascii=False,
    )
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        canonical = None
        for position, (content_id, item_status, reused) in enumerate(
            [
                (1, "completed", False),
                (1, "completed", True),
                (2, "input_incomplete", False),
                (3, "failed", False),
                (4, "cancelled", False),
                (5, "interrupted", False),
                (6, "pending", False),
            ]
        ):
            status = (
                "queued"
                if item_status == "pending"
                else (
                    "completed"
                    if item_status == "completed"
                    else item_status
                    if item_status in ("cancelled", "interrupted")
                    else "failed"
                )
            )
            summary_id = connection.execute(
                """INSERT INTO ai_summary_runs(request_id,source_run_id,
                   source_run_status,platform,rule_name,terms_json,
                   configuration_revision,base_url,model,force_refresh,
                   analysis_prompt_version,summary_prompt_version,model_input_version,
                   status,phase,document_json,created_at,started_at,finished_at)
                   VALUES (?,?,'completed_with_results','wb','历史规则',?,1,
                     'https://example.com/v1','historical-model',0,'old-analysis',
                     'old-report','old-input',?,'analysing',?,?,?,?)""",
                (
                    str(uuid4()),
                    source_run_id,
                    '["历史关键词"]',
                    status,
                    '{"overview":"历史报告","items":[]}'
                    if status == "completed"
                    else None,
                    timestamp,
                    timestamp,
                    None if status == "queued" else timestamp,
                ),
            ).lastrowid
            source = json.dumps(
                {
                    "source_run_id": source_run_id,
                    "result_id": content_id,
                    "platform": "wb",
                    "platform_content_id": str(999 + content_id),
                    "content_type": "post",
                    "title": "历史标题",
                    "snippet": "历史摘要",
                    "content_url": f"https://m.weibo.cn/detail/{999 + content_id}",
                    "published_at_text": "刚刚",
                    "matched_terms": ["历史关键词"],
                },
                ensure_ascii=False,
            )
            completed = item_status == "completed" and not reused
            item_id = connection.execute(
                """INSERT INTO ai_summary_items(summary_run_id,content_id,position,
                   source_json,observation_hash,cache_key,input_json,input_hash,status,
                   decision,reason,evidence_summary,reused_from_item_id,attempted,
                   usage_json,started_at,finished_at)
                   VALUES (?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    summary_id,
                    content_id,
                    source,
                    "a" * 64,
                    f"cache-{position}",
                    saved_input if completed else None,
                    "b" * 64 if completed else None,
                    item_status,
                    "uncertain" if completed else None,
                    "来源无法证明关联" if completed else None,
                    "旧版范围内的内容判断" if completed else None,
                    canonical if reused else None,
                    int(completed),
                    '{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}'
                    if completed
                    else None,
                    timestamp,
                    None if item_status == "pending" else timestamp,
                ),
            ).lastrowid
            if canonical is None:
                canonical = item_id
        connection.execute("COMMIT")
