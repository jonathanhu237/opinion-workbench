"""Transactional, immutable scope and canonical analysis reuse for manual summaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from longtian_api.database import Database
from longtian_api.repositories.analysis_shared import _metadata
from longtian_api.repositories.search_runs import SearchResultSourceRecord
from longtian_api.schemas.ai_summaries import (
    Decision,
    ItemStatus,
    SummaryCounts,
    SummaryCreate,
    SummaryDocument,
    SummaryFailure,
    SummaryItem,
    SummaryItemList,
    SummaryList,
    SummaryRun,
    SummarySource,
    SummaryStatus,
    SummaryUsage,
    TokenUsage,
)
from longtian_api.schemas.analysis_evidence import SavedInput as SavedInput
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIConfiguration
from longtian_api.services.ai_errors import AIError
from longtian_api.services.monitoring_rules import MAX_TERMS_PER_RULE
from longtian_api.services.summary_errors import SummaryError, failure


@dataclass(frozen=True, slots=True)
class SummaryVersions:
    analysis_prompt: str
    summary_prompt: str
    model_input: str


@dataclass(frozen=True, slots=True)
class SummaryItemRecord:
    item: SummaryItem
    observation_hash: str
    cache_key: str
    input: SavedInput | None
    input_hash: str | None

    @property
    def expected_source(self) -> SearchResultSourceRecord:
        value = self.item.source
        return SearchResultSourceRecord(
            run_id=value.source_run_id,
            result_id=value.result_id,
            platform=value.platform,
            platform_content_id=value.platform_content_id,
            content_type=value.content_type,
            content_url=value.content_url,
            title=value.title,
            snippet=value.snippet,
            matched_terms=tuple(value.matched_terms),
            collection_active=False,
            publisher_name=value.publisher_name,
            published_at_text=value.published_at_text,
            hashtags=tuple(value.hashtags),
            interaction_stats=dict(value.interaction_stats),
        )


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _json(value) -> str | None:
    return value.model_dump_json() if value is not None else None


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class SummaryRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = self.database.connect()
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except (sqlite3.Error, ValidationError, ValueError, TypeError, KeyError):
            raise SummaryError("ai_summary_storage_unavailable") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()

    def initialize(self) -> None:
        self.database.initialize()
        with self._connection(write=True) as connection:
            rows = connection.execute(
                "SELECT id FROM ai_summary_runs WHERE status IN ('queued','running')"
            ).fetchall()
            for row in rows:
                self._finish(
                    connection,
                    row["id"],
                    "interrupted",
                    failure("execution", "interrupted"),
                )

    def replay(self, source_run_id: int, payload: SummaryCreate) -> SummaryRun | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM ai_summary_runs WHERE request_id = ?",
                (payload.request_id,),
            ).fetchone()
            if row is None:
                return None
            if (
                row["source_run_id"],
                bool(row["force_refresh"]),
                row["configuration_revision"],
            ) != (source_run_id, payload.force_refresh, payload.configuration_revision):
                raise SummaryError("ai_summary_request_conflict")
            return self._read(connection, row["id"])

    def create(
        self,
        source_run_id: int,
        payload: SummaryCreate,
        configuration: AIConfiguration,
        versions: SummaryVersions,
    ) -> SummaryRun:
        with self._connection(write=True) as connection:
            source_run = connection.execute(
                "SELECT * FROM search_runs WHERE id = ?", (source_run_id,)
            ).fetchone()
            if source_run is None:
                raise SummaryError("search_run_not_found")
            if connection.execute(
                """SELECT 1 FROM search_run_contents l JOIN content_analysis_claims c
                   ON c.content_id=l.search_content_id
                   WHERE l.run_id=? AND c.active_job_id IS NOT NULL""",
                (source_run_id,),
            ).fetchone():
                raise AIError("ai_operation_active")
            active_parent = connection.execute(
                """
                SELECT 1 FROM search_batch_attempts a
                JOIN search_batches b ON b.id=a.batch_id
                WHERE a.search_run_id = ?
                  AND b.status IN ('queued','running','paused_for_manual_action')
            """,
                (source_run_id,),
            ).fetchone()
            if source_run["status"] in ("queued", "running") or active_parent:
                raise SummaryError("ai_summary_source_active")
            count = connection.execute(
                "SELECT COUNT(*) FROM search_run_contents WHERE run_id=?",
                (source_run_id,),
            ).fetchone()[0]
            if count == 0:
                raise SummaryError("ai_summary_empty_source")
            if count > 100:
                raise SummaryError("ai_summary_source_limit")
            terms = [
                r["value"]
                for r in connection.execute(
                    "SELECT value FROM search_run_terms "
                    "WHERE run_id=? ORDER BY position",
                    (source_run_id,),
                )
            ]
            if not 1 <= len(terms) <= MAX_TERMS_PER_RULE:
                raise ValueError("invalid historical terms")
            cursor = connection.execute(
                """
                INSERT INTO ai_summary_runs(request_id,source_run_id,
                  source_run_status,platform,
                  rule_name,terms_json,configuration_revision,base_url,model,force_refresh,
                  analysis_prompt_version,summary_prompt_version,model_input_version,
                  status,phase,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'queued','analysing',?)
            """,
                (
                    payload.request_id,
                    source_run_id,
                    source_run["status"],
                    source_run["platform"],
                    source_run["rule_name"],
                    json.dumps(terms, ensure_ascii=False),
                    configuration.revision,
                    configuration.base_url,
                    configuration.model,
                    int(payload.force_refresh),
                    versions.analysis_prompt,
                    versions.summary_prompt,
                    versions.model_input,
                    _timestamp(),
                ),
            )
            summary_id = cursor.lastrowid
            rows = connection.execute(
                """
                SELECT c.* FROM search_run_contents l
                JOIN search_contents c ON c.id=l.search_content_id
                WHERE l.run_id=? ORDER BY l.first_observed_at DESC,c.id ASC
            """,
                (source_run_id,),
            ).fetchall()
            for position, row in enumerate(rows):
                matched = [
                    r["value"]
                    for r in connection.execute(
                        """
                    SELECT t.value FROM search_run_content_terms m
                    JOIN search_run_terms t
                      ON t.run_id=m.run_id AND t.position=m.term_position
                    WHERE m.run_id=? AND m.search_content_id=? ORDER BY m.term_position
                """,
                        (source_run_id, row["id"]),
                    )
                ]
                if row["platform"] != source_run["platform"]:
                    raise ValueError("source platform mismatch")
                hashtags, interaction_stats = _metadata(row)
                source = SummarySource(
                    source_run_id=source_run_id,
                    result_id=row["id"],
                    platform=row["platform"],
                    platform_content_id=row["platform_content_id"],
                    content_type=row["content_type"],
                    title=row["title"],
                    snippet=row["snippet"],
                    content_url=row["content_url"],
                    published_at_text=row["published_at_text"],
                    matched_terms=matched,
                    hashtags=hashtags,
                    interaction_stats=interaction_stats,
                    creator_hash=row["creator_hash"],
                    publisher_name=row["publisher_name"],
                )
                # Relative display time ("刚刚" -> "昨天") is not changed content.
                observation = fingerprint(
                    source.model_dump(
                        exclude={"source_run_id", "result_id", "published_at_text"}
                    )
                )
                cache_key = fingerprint(
                    {
                        "observation": observation,
                        "rule_name": source_run["rule_name"],
                        "terms": terms,
                        "configuration_revision": configuration.revision,
                        "base_url": configuration.base_url,
                        "model": configuration.model,
                        "analysis_prompt": versions.analysis_prompt,
                        "model_input": versions.model_input,
                        "extractor": f"{source.platform}-enrichment-v1",
                    }
                )
                connection.execute(
                    """
                    INSERT INTO ai_summary_items(summary_run_id,content_id,
                      position,source_json,
                      observation_hash,cache_key,status) VALUES (?,?,?,?,?,?,'pending')
                """,
                    (
                        summary_id,
                        row["id"],
                        position,
                        source.model_dump_json(),
                        observation,
                        cache_key,
                    ),
                )
            return self._read(connection, summary_id)

    def read(self, summary_id: int) -> SummaryRun:
        with self._connection() as connection:
            return self._read(connection, summary_id)

    def list(
        self, source_run_id: int, *, limit: int = 20, before_id: int | None = None
    ) -> SummaryList:
        with self._connection() as connection:
            if not connection.execute(
                "SELECT 1 FROM search_runs WHERE id=?", (source_run_id,)
            ).fetchone():
                raise SummaryError("search_run_not_found")
            rows = connection.execute(
                """
                SELECT id FROM ai_summary_runs
                WHERE source_run_id=? AND (? IS NULL OR id<?)
                ORDER BY id DESC LIMIT ?
            """,
                (source_run_id, before_id, before_id, limit + 1),
            ).fetchall()
            summaries = [self._read(connection, r["id"]) for r in rows[:limit]]
            return SummaryList(
                summaries=summaries,
                next_before_id=summaries[-1].id if len(rows) > limit else None,
            )

    def items(
        self, summary_id: int, *, limit: int = 100, offset: int = 0
    ) -> SummaryItemList:
        with self._connection() as connection:
            self._require(connection, summary_id)
            rows = connection.execute(
                "SELECT * FROM ai_summary_items "
                "WHERE summary_run_id=? ORDER BY position",
                (summary_id,),
            ).fetchall()
            return SummaryItemList(
                items=[
                    self._item(connection, r).item
                    for r in rows[offset : offset + limit]
                ],
                total=len(rows),
                limit=limit,
                offset=offset,
            )

    def records(self, summary_id: int) -> list[SummaryItemRecord]:
        with self._connection() as connection:
            self._require(connection, summary_id)
            return [
                self._item(connection, r)
                for r in connection.execute(
                    "SELECT * FROM ai_summary_items "
                    "WHERE summary_run_id=? ORDER BY position",
                    (summary_id,),
                )
            ]

    def find_cached(self, record: SummaryItemRecord) -> SummaryItemRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM ai_summary_items
                WHERE cache_key=? AND id<? AND status='completed'
                  AND reused_from_item_id IS NULL ORDER BY id DESC LIMIT 1
            """,
                (record.cache_key, record.item.id),
            ).fetchone()
            if row is None:
                return None
            cached = self._item(connection, row)
            if (
                cached.input is None
                or cached.input.status != "ready"
                or not cached.input_hash
            ):
                raise ValueError("invalid reusable input")
            latest = connection.execute(
                """
                SELECT input_hash FROM ai_summary_items
                WHERE content_id=? AND input_hash IS NOT NULL
                ORDER BY id DESC LIMIT 1
            """,
                (record.item.source.result_id,),
            ).fetchone()
            # A newer acquisition can prove changed media even if its model call
            # later failed. Never resurrect an older judgment in that case.
            if latest is not None and latest["input_hash"] != cached.input_hash:
                return None
            known = connection.execute(
                "SELECT known_input_fingerprint FROM content_analysis_claims "
                "WHERE content_id=?",
                (record.item.source.result_id,),
            ).fetchone()
            if known and known[0] is not None and known[0] != cached.input_hash:
                return None
            return cached

    def start(self, summary_id: int) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            connection.execute(
                "UPDATE ai_summary_runs SET status='running',started_at=? "
                "WHERE id=? AND status='queued'",
                (_timestamp(), summary_id),
            )

    def begin_item(self, summary_id: int, item_id: int) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            connection.execute(
                "UPDATE ai_summary_items SET status='analysing',started_at=? "
                "WHERE id=? AND summary_run_id=? AND status='pending'",
                (_timestamp(), item_id, summary_id),
            )

    def reuse(self, summary_id: int, item_id: int, cached_id: int) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            cached = connection.execute(
                "SELECT * FROM ai_summary_items WHERE id=? AND status='completed' "
                "AND reused_from_item_id IS NULL",
                (cached_id,),
            ).fetchone()
            own = connection.execute(
                "SELECT * FROM ai_summary_items "
                "WHERE id=? AND summary_run_id=? AND status='pending'",
                (item_id, summary_id),
            ).fetchone()
            if cached is None or own is None or cached["cache_key"] != own["cache_key"]:
                raise ValueError("incompatible cached analysis")
            timestamp = _timestamp()
            connection.execute(
                "UPDATE ai_summary_items SET status='completed',reused_from_item_id=?,"
                "started_at=?,finished_at=? WHERE id=?",
                (cached_id, timestamp, timestamp, item_id),
            )

    def save_input(
        self, summary_id: int, item_id: int, content: SavedInput, input_hash: str | None
    ) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            connection.execute(
                "UPDATE ai_summary_items SET input_json=?,input_hash=? "
                "WHERE id=? AND summary_run_id=? AND status='analysing'",
                (content.model_dump_json(), input_hash, item_id, summary_id),
            )

    def mark_attempt(
        self, summary_id: int, item_id: int | None, *, input_hash: str | None = None
    ) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            if item_id is None:
                connection.execute(
                    "UPDATE ai_summary_runs SET composition_attempted=1,"
                    "composition_input_hash=? WHERE id=? AND phase='summarising'",
                    (input_hash, summary_id),
                )
            else:
                connection.execute(
                    "UPDATE ai_summary_items SET attempted=1 "
                    "WHERE id=? AND summary_run_id=? AND status='analysing'",
                    (item_id, summary_id),
                )

    def finish_item(
        self,
        summary_id: int,
        item_id: int,
        status: ItemStatus,
        *,
        decision: Decision | None = None,
        reason: str | None = None,
        evidence_summary: str | None = None,
        error: SummaryFailure | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            connection.execute(
                """
                UPDATE ai_summary_items SET status=?,decision=?,reason=?,
                  evidence_summary=?,error_json=?,usage_json=?,finished_at=?
                WHERE id=? AND summary_run_id=? AND status='analysing'
            """,
                (
                    status,
                    decision,
                    reason,
                    evidence_summary,
                    _json(error),
                    _json(usage),
                    _timestamp(),
                    item_id,
                    summary_id,
                ),
            )

    def summarising(self, summary_id: int) -> None:
        with self._connection(write=True) as connection:
            self._require_active(connection, summary_id)
            if connection.execute(
                "SELECT 1 FROM ai_summary_items WHERE summary_run_id=? "
                "AND status IN ('pending','analysing')",
                (summary_id,),
            ).fetchone():
                raise ValueError("unfinished analysis")
            connection.execute(
                "UPDATE ai_summary_runs SET phase='summarising' WHERE id=?",
                (summary_id,),
            )

    def finish(
        self,
        summary_id: int,
        status: SummaryStatus,
        *,
        error: SummaryFailure | None = None,
        document: SummaryDocument | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        with self._connection(write=True) as connection:
            self._finish(connection, summary_id, status, error, document, usage)

    def _finish(self, connection, summary_id, status, error, document=None, usage=None):
        row = self._require(connection, summary_id)
        if row["status"] not in ("queued", "running"):
            return
        if status not in ("completed", "failed", "cancelled", "interrupted"):
            raise ValueError("invalid terminal state")
        timestamp = _timestamp()
        pending_status = status if status in ("cancelled", "interrupted") else "failed"
        connection.execute(
            """
            UPDATE ai_summary_items SET status=?,error_json=?,finished_at=?
              WHERE summary_run_id=? AND status IN ('pending','analysing')
        """,
            (
                pending_status,
                _json(error or failure("execution", "internal_error")),
                timestamp,
                summary_id,
            ),
        )
        if document is not None:
            records = [
                self._item(connection, r)
                for r in connection.execute(
                    "SELECT * FROM ai_summary_items WHERE summary_run_id=?",
                    (summary_id,),
                )
            ]
            allowed = {
                r.item.source.result_id
                for r in records
                if r.item.decision == "relevant"
            }
            if bool(document.items) != bool(allowed) or any(
                not set(p.source_ids) <= allowed
                or len(set(p.source_ids)) != len(p.source_ids)
                for p in document.items
            ):
                raise ValueError("invalid summary references")
        connection.execute(
            """
            UPDATE ai_summary_runs SET status=?,document_json=?,error_json=?,
              composition_usage_json=?,finished_at=? WHERE id=?
        """,
            (
                status,
                _json(document),
                _json(error),
                _json(usage),
                timestamp,
                summary_id,
            ),
        )

    @staticmethod
    def _require(connection, summary_id):
        row = connection.execute(
            "SELECT * FROM ai_summary_runs WHERE id=?", (summary_id,)
        ).fetchone()
        if row is None:
            raise SummaryError("ai_summary_not_found")
        return row

    def _require_active(self, connection, summary_id):
        row = self._require(connection, summary_id)
        if row["status"] not in ("queued", "running"):
            raise ValueError("summary no longer active")
        return row

    def _item(self, connection, row) -> SummaryItemRecord:
        analysis = row
        if row["reused_from_item_id"] is not None:
            analysis = connection.execute(
                "SELECT * FROM ai_summary_items WHERE id=?",
                (row["reused_from_item_id"],),
            ).fetchone()
            if (
                analysis is None
                or analysis["status"] != "completed"
                or analysis["reused_from_item_id"] is not None
                or analysis["cache_key"] != row["cache_key"]
            ):
                raise ValueError("invalid canonical analysis reference")
        saved = (
            SavedInput.model_validate_json(analysis["input_json"])
            if analysis["input_json"]
            else None
        )
        item = SummaryItem(
            id=row["id"],
            summary_run_id=row["summary_run_id"],
            position=row["position"],
            source=SummarySource.model_validate_json(row["source_json"]),
            status=row["status"],
            decision=analysis["decision"],
            reason=analysis["reason"],
            evidence_summary=analysis["evidence_summary"],
            reused_from_item_id=row["reused_from_item_id"],
            attempted=bool(row["attempted"]),
            usage=TokenUsage.model_validate_json(row["usage_json"])
            if row["usage_json"]
            else None,
            input_status=saved.status if saved else None,
            input_issues=saved.issues if saved else [],
            error=SummaryFailure.model_validate_json(row["error_json"])
            if row["error_json"]
            else None,
            started_at=_date(row["started_at"]),
            finished_at=_date(row["finished_at"]),
        )
        return SummaryItemRecord(
            item,
            row["observation_hash"],
            row["cache_key"],
            saved,
            analysis["input_hash"],
        )

    def _read(self, connection, summary_id) -> SummaryRun:
        row = self._require(connection, summary_id)
        items = [
            self._item(connection, r).item
            for r in connection.execute(
                "SELECT * FROM ai_summary_items "
                "WHERE summary_run_id=? ORDER BY position",
                (summary_id,),
            )
        ]
        counts = dict.fromkeys(
            (
                "pending",
                "analysing",
                "relevant",
                "irrelevant",
                "uncertain",
                "input_incomplete",
                "failed",
                "cancelled",
                "interrupted",
                "reused",
            ),
            0,
        )
        for item in items:
            counts[item.decision if item.status == "completed" else item.status] += 1
            if item.reused_from_item_id is not None:
                counts["reused"] += 1
        usages = [item.usage for item in items if item.usage is not None]
        if row["composition_usage_json"]:
            usages.append(TokenUsage.model_validate_json(row["composition_usage_json"]))
        attempts = sum(item.attempted for item in items) + row["composition_attempted"]
        unknown = (attempts > 0 and not usages) or sum(
            u.total_tokens for u in usages
        ) > MAX_USAGE_TOKENS
        usage = SummaryUsage(
            attempted_requests=attempts,
            accounted_requests=len(usages),
            complete=not unknown and attempts == len(usages),
            prompt_tokens=None if unknown else sum(u.prompt_tokens for u in usages),
            completion_tokens=None
            if unknown
            else sum(u.completion_tokens for u in usages),
            total_tokens=None if unknown else sum(u.total_tokens for u in usages),
        )
        return SummaryRun(
            id=row["id"],
            request_id=row["request_id"],
            source_run_id=row["source_run_id"],
            platform=row["platform"],
            source_run_status=row["source_run_status"],
            rule_name=row["rule_name"],
            terms=json.loads(row["terms_json"]),
            configuration_revision=row["configuration_revision"],
            base_url=row["base_url"],
            model=row["model"],
            force_refresh=bool(row["force_refresh"]),
            status=row["status"],
            phase=row["phase"],
            counts=SummaryCounts(total=len(items), **counts),
            usage=usage,
            document=SummaryDocument.model_validate_json(row["document_json"])
            if row["document_json"]
            else None,
            error=SummaryFailure.model_validate_json(row["error_json"])
            if row["error_json"]
            else None,
            created_at=_date(row["created_at"]),
            started_at=_date(row["started_at"]),
            finished_at=_date(row["finished_at"]),
        )
