"""Frozen report membership and short, settled graph/event transactions."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import get_args

from pydantic import ValidationError

from longtian_api.repositories.ai_summaries import fingerprint
from longtian_api.repositories.analysis_settings import (
    read_prompt,
    resolve_prompt_choice,
    resolve_prompt_version,
)
from longtian_api.repositories.analysis_shared import source_snapshot, timestamp
from longtian_api.repositories.content_analyses import ContentAnalysisRepository
from longtian_api.schemas.ai_summaries import SummaryFailure, TokenUsage
from longtian_api.schemas.analysis_evidence import AnalysisSource
from longtian_api.schemas.analysis_settings import PromptChoice, PromptSnapshot
from longtian_api.schemas.content_analyses import AnalysisUsage
from longtian_api.schemas.topic_report_engine import (
    ChildOverview,
    EngineContext,
    FrozenTextSource,
    ProviderIntent,
    TextPrompt,
)
from longtian_api.schemas.topic_reports import (
    ACTIVE_REPORTS,
    ChildSection,
    CitationSource,
    CollectionGap,
    Coverage,
    Judgment,
    NodeCounts,
    NodeStatus,
    OverviewDocument,
    ReportDocument,
    ReportFailure,
    ReportList,
    ReportNodes,
    ReportPrompt,
    ReportRun,
    ReportSection,
    ReportSectionList,
    ReportSource,
    ReportSourceList,
    ReportUsage,
    SourceState,
)
from longtian_api.services.ai_analysis import MODEL_INPUT_VERSION, AIAnalysisError
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, decode_model_json
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.model_retry import combined_usage, usage_records
from longtian_api.services.summary_errors import failure
from longtian_api.services.topic_report_engine import (
    ENGINE_VERSION,
    canonical_hash,
    output_digest,
)
from longtian_api.services.topic_report_errors import (
    CONFIGURATION_FAILURES,
    TopicReportError,
    configuration_failure,
)


def _read_report_prompt(value: str) -> ReportPrompt:
    """Decode current prompts and project the pre-v18 instruction-only shape."""

    payload = decode_model_json(value)
    if not isinstance(payload, dict):
        raise ValueError("invalid stored report prompt")
    # Rows written by the current application (and by the v14/v15 report
    # implementation) carry explicit source metadata.  Let the strict model
    # validate those fields instead of silently downgrading malformed data.
    if "origin" in payload or "mode" in payload:
        return ReportPrompt.model_validate(payload)

    # The earliest report rows stored only the user-facing instructions.  They
    # are immutable history, so infer a legacy source at read time and retain
    # an old version ID/hash when one was present; never update prompt_json.
    allowed = {"version_id", "instructions", "content_hash", "schema_version"}
    if set(payload) - allowed:
        raise ValueError("invalid stored report prompt")
    instructions = payload.get("instructions")
    if not isinstance(instructions, str):
        raise ValueError("invalid stored report prompt")
    content_hash = hashlib.sha256(instructions.encode()).hexdigest()
    stored_hash = payload.get("content_hash")
    if stored_hash is not None and stored_hash != content_hash:
        raise ValueError("invalid stored report prompt")
    return ReportPrompt(
        mode="legacy",
        origin="legacy",
        version_id=payload.get("version_id"),
        instructions=instructions,
        content_hash=content_hash,
        schema_version=payload.get("schema_version", "topic-report-v1"),
    )


def saved_failure(value, *, report=False):
    if value is None:
        return None
    result = ReportFailure.model_validate_json(value)
    expected = (
        configuration_failure(result.code)
        if result.code in CONFIGURATION_FAILURES
        else failure(result.stage, result.code)
    )
    if result.model_dump() != expected.model_dump():
        raise ValueError("invalid stored failure")
    return result if report else SummaryFailure.model_validate(result.model_dump())


def observed_usage(value):
    """Freshly validate nested transport counters, otherwise retain unknown usage."""
    if not isinstance(value, TokenUsage):
        return None
    try:
        return TokenUsage.model_validate(value.model_dump(warnings=False))
    except (ValueError, TypeError):
        return None


def aggregate_usage(rows):
    attempted = accounted = prompt = completion = total = 0
    for row in (record for item in rows for record in usage_records(item)):
        attempted += row["attempted"]
        if row["usage_json"] is not None:
            usage = TokenUsage.model_validate_json(row["usage_json"])
            if not row["attempted"] or row["reused_from_node_id"] is not None:
                raise ValueError("invalid usage ownership")
            accounted += 1
            prompt += usage.prompt_tokens
            completion += usage.completion_tokens
            total += usage.total_tokens
    unknown = (attempted > 0 and accounted == 0) or total > MAX_USAGE_TOKENS
    return AnalysisUsage(
        attempted_requests=attempted,
        accounted_requests=accounted,
        complete=not unknown and attempted == accounted,
        prompt_tokens=None if unknown else prompt,
        completion_tokens=None if unknown else completion,
        total_tokens=None if unknown else total,
    )


class TopicReportRepository:
    def __init__(self, database):
        self.database = database
        self._analyses = ContentAnalysisRepository(database)

    @contextmanager
    def connection(self, *, write=False):
        connection = None
        try:
            connection = self.database.connect()
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except (
            sqlite3.Error,
            ValidationError,
            ValueError,
            TypeError,
            KeyError,
            OverflowError,
            AIAnalysisError,
        ):
            raise TopicReportError("topic_report_storage_unavailable") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                connection.close()

    def initialize(self):
        self.database.initialize()
        with self.connection(write=True) as connection:
            for row in connection.execute(
                """SELECT id FROM topic_report_runs WHERE status IN ('queued',
                  'judging','composing')"""
            ).fetchall():
                self._finish(connection, row[0], "interrupted", recovery=True)

    def _require(self, connection, report_id):
        row = connection.execute(
            "SELECT * FROM topic_report_runs WHERE id=?", (report_id,)
        ).fetchone()
        if row is None:
            raise TopicReportError("topic_report_not_found")
        return row

    def _node_counts(self, rows):
        counts = dict.fromkeys(get_args(NodeStatus), 0)
        reused = 0
        for row in rows:
            counts[row["status"]] += 1
            reused += int(row["reused_from_node_id"] is not None)
        return NodeCounts(total=sum(counts.values()), reused=reused, **counts)

    def _source(self, connection, row):
        if (row["evidence_json"] is None) != (row["unavailable_reason"] is not None):
            raise ValueError("invalid evidence availability")
        node = connection.execute(
            "SELECT * FROM topic_report_nodes WHERE report_id=? AND node_key=?",
            (row["report_id"], f"judgment:{row['content_id']}"),
        ).fetchone()
        judgment = None
        evidence = None
        if row["unavailable_reason"] is not None:
            state = "unavailable"
            if node is not None:
                raise ValueError("unavailable judgment")
        else:
            if node is None:
                raise ValueError("missing judgment node")
            if (node["kind"], node["position"], node["level"]) != (
                "judgment",
                row["position"],
                0,
            ):
                raise ValueError("invalid judgment node identity")
            members = connection.execute(
                """SELECT source_id,position FROM topic_report_node_sources
                  WHERE node_id=? ORDER BY position""",
                (node["id"],),
            ).fetchall()
            if [tuple(member) for member in members] != [(row["id"], 0)]:
                raise ValueError("invalid judgment membership")
            if node["status"] == "completed":
                judgment = Judgment.model_validate(self._stored_output(node))
                state = judgment.decision
            else:
                state = {"queued": "pending", "running": "judging"}.get(
                    node["status"], node["status"]
                )
        source = AnalysisSource.model_validate_json(row["source_json"])
        if source.result_id != row["content_id"]:
            raise ValueError("invalid source identity")
        if row["evidence_json"] is not None:
            evidence = FrozenTextSource.model_validate_json(row["evidence_json"])
            if (
                evidence.source != source
                or evidence.position != row["position"]
                or evidence.attempt_id != row["initial_attempt_id"]
                or evidence.first_seen_at
                != datetime.fromisoformat(row["first_seen_at"])
            ):
                raise ValueError("changed frozen evidence")
        return ReportSource(
            position=row["position"],
            source=source,
            evidence_coverage=(evidence.input.evidence_coverage if evidence else None),
            first_seen_at=row["first_seen_at"],
            initial_attempt_id=row["initial_attempt_id"],
            initial_status=row["initial_status"],
            unavailable_reason=row["unavailable_reason"],
            state=state,
            judgment=judgment,
            judgment_node_id=node["id"] if node else None,
            error=saved_failure(node["error_json"]) if node else None,
        )

    def _collection_gaps(self, connection, selection, report_id):
        """Project failed platform items from every represented batch.

        Workflow reports identify their collection child directly.  Manual and
        interval reports can still be based on results discovered by a batch,
        so use each frozen source's originating run to recover those batches.
        This keeps collection gaps tied to the report's immutable source set.
        """

        batch_ids = []
        selection_kind = (
            selection.get("kind")
            if isinstance(selection, dict)
            else getattr(selection, "kind", None)
        )
        if selection_kind == "workflow_run":
            workflow_run_id = (
                selection.get("run_id")
                if isinstance(selection, dict)
                else getattr(selection, "run_id", None)
            )
            if not isinstance(workflow_run_id, int):
                return ()
            stage = connection.execute(
                """SELECT child_id FROM automation_stage_attempts
                   WHERE run_id=? AND stage='collection' AND child_kind='search_batch'
                     AND child_id IS NOT NULL
                   ORDER BY attempt_number DESC LIMIT 1""",
                (workflow_run_id,),
            ).fetchone()
            if stage is not None:
                batch_ids.append(int(stage["child_id"]))
        else:
            source_rows = connection.execute(
                """SELECT source_json FROM topic_report_sources
                   WHERE report_id=? ORDER BY position""",
                (report_id,),
            ).fetchall()
            run_ids = []
            for source_row in source_rows:
                source = decode_model_json(source_row["source_json"])
                if isinstance(source, dict) and isinstance(
                    source.get("source_run_id"), int
                ):
                    run_ids.append(source["source_run_id"])
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                batch_rows = connection.execute(
                    f"""SELECT DISTINCT batch_id FROM search_batch_attempts
                        WHERE search_run_id IN ({placeholders})""",
                    run_ids,
                ).fetchall()
                batch_ids.extend(int(row["batch_id"]) for row in batch_rows)
        batch_ids = tuple(dict.fromkeys(batch_ids))
        if not batch_ids:
            return ()
        placeholders = ",".join("?" for _ in batch_ids)
        rows = connection.execute(
            f"""SELECT item.position,item.platform,item.status,
                      run.status AS run_status,run.failure_reason
                 FROM search_batch_items AS item
                 LEFT JOIN search_batch_attempts AS attempt
                   ON attempt.batch_id=item.batch_id
                  AND attempt.item_position=item.position
                  AND attempt.attempt_number=(
                    SELECT MAX(latest.attempt_number)
                      FROM search_batch_attempts AS latest
                     WHERE latest.batch_id=item.batch_id
                       AND latest.item_position=item.position)
                 LEFT JOIN search_runs AS run ON run.id=attempt.search_run_id
                WHERE item.batch_id IN ({placeholders})
                  AND item.status IN ('failed','skipped','cancelled')
                ORDER BY item.batch_id,item.position""",
            batch_ids,
        ).fetchall()
        return tuple(
            CollectionGap(
                position=row["position"],
                platform=row["platform"],
                status=row["status"],
                run_status=row["run_status"],
                failure_reason=row["failure_reason"],
            )
            for row in rows
        )

    def _read(self, connection, report_id):
        row = self._require(connection, report_id)
        if row["status"] == "completed":
            self._verify_complete_graph(connection, report_id, row["root_section_id"])
        counts = dict.fromkeys(get_args(SourceState), 0)
        for source in connection.execute(
            "SELECT * FROM topic_report_sources WHERE report_id=? ORDER BY position",
            (report_id,),
        ):
            counts[self._source(connection, source).state] += 1
        nodes = connection.execute(
            """SELECT kind,status,attempted,usage_json,reused_from_node_id,
              retry_attempted,retry_usage_json FROM
              topic_report_nodes
              WHERE report_id=? ORDER BY id""",
            (report_id,),
        ).fetchall()
        judgments = [node for node in nodes if node["kind"] == "judgment"]
        composition = [node for node in nodes if node["kind"] != "judgment"]
        selection = decode_model_json(row["selection_json"])
        return ReportRun(
            id=report_id,
            request_id=row["request_id"],
            trigger=row["trigger"],
            initial_job_id=row["initial_job_id"],
            completion_event_id=row["completion_event_id"],
            parent_report_id=row["parent_report_id"],
            selection=selection,
            status=row["status"],
            revision=row["revision"],
            configuration_revision=row["configuration_revision"],
            base_url=row["base_url"],
            model=row["model"],
            prompt=_read_report_prompt(row["prompt_json"]),
            coverage=Coverage(
                total=sum(counts.values()),
                ready=sum(counts.values()) - counts["unavailable"],
                **counts,
            ),
            nodes=ReportNodes(
                judgments=self._node_counts(judgments),
                composition=self._node_counts(composition),
            ),
            usage=ReportUsage(
                judgment=aggregate_usage(judgments),
                composition=aggregate_usage(composition),
                total=aggregate_usage(nodes),
            ),
            collection_gaps=self._collection_gaps(connection, selection, report_id),
            root_section_id=row["root_section_id"],
            empty_reason=row["empty_reason"],
            queue_reason=row["queue_reason"],
            recovery_reason=row["recovery_reason"],
            error=saved_failure(row["error_json"], report=True),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def read(self, report_id):
        with self.connection() as connection:
            return self._read(connection, report_id)

    def all_sources_text_insufficient(self, report_id):
        """Return true only when every frozen source lacks usable text."""
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT s.unavailable_reason,a.status,a.error_json
                   FROM topic_report_sources s
                   LEFT JOIN content_analysis_attempts a
                     ON a.id=s.initial_attempt_id
                   WHERE s.report_id=? ORDER BY s.position""",
                (report_id,),
            ).fetchall()
            if not rows:
                return False
            for row in rows:
                if row["unavailable_reason"] not in {
                    "input_incomplete",
                    "unsupported",
                }:
                    return False
                if row["status"] != row["unavailable_reason"] or not row[
                    "error_json"
                ]:
                    return False
                try:
                    error = SummaryFailure.model_validate_json(row["error_json"])
                except (TypeError, ValueError):
                    return False
                if error.stage != "acquisition" or error.code != "input_incomplete":
                    return False
            return True

    def list(self, *, limit=50, before_id=None, initial_job_id=None, result_id=None):
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT r.id FROM topic_report_runs r WHERE
              (? IS NULL OR r.id<?) AND (? IS NULL OR r.initial_job_id=?) AND
              (? IS NULL OR EXISTS(SELECT 1 FROM topic_report_sources s WHERE
          s.report_id=r.id AND s.content_id=?))
              ORDER BY r.id DESC LIMIT ?""",
                (
                    before_id,
                    before_id,
                    initial_job_id,
                    initial_job_id,
                    result_id,
                    result_id,
                    limit + 1,
                ),
            ).fetchall()
            return ReportList(
                reports=[self._read(connection, row[0]) for row in rows[:limit]],
                next_before_id=rows[limit - 1][0] if len(rows) > limit else None,
            )

    def sources(self, report_id, *, limit=50, offset=0):
        with self.connection() as connection:
            self._require(connection, report_id)
            total = connection.execute(
                "SELECT COUNT(*) FROM topic_report_sources WHERE report_id=?",
                (report_id,),
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT * FROM topic_report_sources WHERE report_id=? ORDER BY
                  position LIMIT ? OFFSET ?""",
                (report_id, limit, offset),
            )
            return ReportSourceList(
                items=[self._source(connection, row) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    def _section(self, connection, node):
        if node["status"] == "completed":
            self._child(connection, node)
        children = connection.execute(
            """SELECT c.* FROM topic_report_node_children l
          JOIN topic_report_nodes c ON c.id=l.child_id WHERE l.node_id=? ORDER BY
          l.position""",
            (node["id"],),
        ).fetchall()
        members = connection.execute(
            """SELECT s.* FROM topic_report_node_sources l JOIN topic_report_sources s
          ON s.id=l.source_id WHERE l.node_id=? ORDER BY l.position""",
            (node["id"],),
        ).fetchall()
        document = overview = None
        if node["status"] == "completed":
            output = self._stored_output(node)
            if node["kind"] == "leaf":
                document = ReportDocument.model_validate(output)
            else:
                # Logical keys are mapped to this version's real child rows, never
                # to IDs embedded in an earlier report's public response.
                keys = {child["node_key"]: child["id"] for child in children}
                overview = OverviewDocument.model_validate(
                    {
                        "overview": output["overview"],
                        "items": [
                            {
                                "text": item["text"],
                                "section_ids": [keys[key] for key in item["child_ids"]],
                                "source_ids": item.get("source_ids"),
                            }
                            for item in output["items"]
                        ],
                    }
                )
        return ReportSection(
            id=node["id"],
            report_id=node["report_id"],
            kind=node["kind"],
            position=node["position"],
            level=node["level"],
            status=node["status"],
            source_count=len(members),
            document=document,
            overview_document=overview,
            sources=[
                CitationSource(
                    position=row["position"],
                    source=AnalysisSource.model_validate_json(row["source_json"]),
                )
                for row in members
            ]
            if node["kind"] == "leaf"
            else [],
            children=[
                ChildSection(
                    id=child["id"],
                    kind=child["kind"],
                    position=child["position"],
                    level=child["level"],
                    source_count=connection.execute(
                        """SELECT COUNT(*) FROM topic_report_node_sources WHERE
                          node_id=?""",
                        (child["id"],),
                    ).fetchone()[0],
                    overview=self._stored_output(child)["overview"],
                )
                for child in children
            ],
            attempted=bool(node["attempted"]),
            usage=combined_usage(node),
            reused_from_node_id=node["reused_from_node_id"],
            error=saved_failure(node["error_json"]),
        )

    def section(self, report_id, section_id):
        with self.connection() as connection:
            self._require(connection, report_id)
            row = connection.execute(
                """SELECT * FROM topic_report_nodes WHERE id=? AND report_id=? AND
                  kind!='judgment'""",
                (section_id, report_id),
            ).fetchone()
            if row is None:
                raise TopicReportError("topic_report_section_not_found")
            return self._section(connection, row)

    def sections(self, report_id, *, limit=50, offset=0, kind=None):
        with self.connection() as connection:
            self._require(connection, report_id)
            params = (report_id, kind, kind)
            where = "report_id=? AND kind!='judgment' AND (? IS NULL OR kind=?)"
            total = connection.execute(
                f"SELECT COUNT(*) FROM topic_report_nodes WHERE {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM topic_report_nodes WHERE {where} ORDER BY level,
                  position LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            )
            return ReportSectionList(
                sections=[self._section(connection, row) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    def _intent_hash(self, action, target, payload):
        return fingerprint(
            {"action": action, "target": target, "payload": payload.model_dump()}
        )

    def _replay(self, connection, action, target, payload):
        row = connection.execute(
            "SELECT * FROM topic_report_requests WHERE request_id=?",
            (payload.request_id,),
        ).fetchone()
        if row is None:
            return None
        if row["intent_hash"] != self._intent_hash(action, target, payload):
            raise TopicReportError("topic_report_request_conflict")
        return self._read(connection, row["report_id"])

    def replay(self, action, target, payload):
        with self.connection() as connection:
            return self._replay(connection, action, target, payload)

    def _save_request(self, connection, action, target, payload, report_id):
        connection.execute(
            "INSERT INTO topic_report_requests VALUES(?,?,?)",
            (payload.request_id, self._intent_hash(action, target, payload), report_id),
        )

    def _prompt(self, prompt, override):
        if override is None:
            return prompt
        return ReportPrompt(
            version_id=None,
            origin="override",
            instructions=override,
            content_hash=hashlib.sha256(override.encode()).hexdigest(),
            schema_version="topic-report-v1",
        )

    def _prompt_choice(
        self,
        connection,
        *,
        choice: PromptChoice | None = None,
        version_id: int | None = None,
        override: str | None = None,
    ) -> ReportPrompt:
        """Resolve a report choice to a durable, auditable prompt projection."""
        if override is not None:
            if choice is not None or version_id is not None:
                raise AnalysisError("invalid_analysis_prompt")
            return ReportPrompt(
                version_id=None,
                origin="override",
                instructions=override,
                content_hash=hashlib.sha256(override.encode()).hexdigest(),
                schema_version="topic-report-v1",
            )
        if version_id is not None:
            row = connection.execute(
                "SELECT stage FROM analysis_prompt_versions WHERE id=?",
                (version_id,),
            ).fetchone()
            if row is None or row["stage"] != "report":
                raise AnalysisError("analysis_prompt_changed")
        if choice is not None:
            selected = resolve_prompt_choice(connection, "report", choice)
            if version_id is not None:
                frozen = resolve_prompt_version(connection, "report", version_id)
                if (
                    frozen.instructions != selected.instructions
                    or frozen.content_hash != selected.content_hash
                    or frozen.schema_version != selected.schema_version
                ):
                    raise AnalysisError("analysis_prompt_changed")
                snapshot = frozen.model_copy(update={"mode": selected.mode})
            else:
                snapshot = selected
        elif version_id is not None:
            snapshot = resolve_prompt_version(connection, "report", version_id)
        else:
            snapshot = resolve_prompt_choice(connection, "report", None)
        return ReportPrompt(
            version_id=snapshot.version_id,
            mode=snapshot.mode,
            origin=(
                snapshot.mode if snapshot.mode in {"default", "custom"} else "shared"
            ),
            instructions=snapshot.instructions,
            content_hash=snapshot.content_hash,
            schema_version=snapshot.schema_version,
        )

    def _new(
        self,
        connection,
        *,
        trigger,
        selection,
        prompt,
        provider,
        request_id=None,
        job_id=None,
        event_id=None,
        parent_id=None,
        workflow_operation_key=None,
    ):
        import json

        return connection.execute(
            """INSERT INTO topic_report_runs(request_id,workflow_operation_key,
              trigger,initial_job_id,completion_event_id,
          parent_report_id,selection_json,prompt_json,configuration_revision,
          base_url,model,status,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?)""",
            (
                request_id,
                workflow_operation_key,
                trigger,
                job_id,
                event_id,
                parent_id,
                json.dumps(selection, ensure_ascii=False, separators=(",", ":")),
                prompt.model_dump_json(),
                provider.configuration_revision,
                provider.base_url,
                provider.model,
                timestamp(),
            ),
        ).lastrowid

    def _provider(self, connection, revision):
        record = self._analyses._provider(connection, revision)
        return ProviderIntent(
            base_url=record["base_url"],
            model=record["model"],
            configuration_revision=revision,
        )

    def _snapshot(
        self,
        connection,
        report_id,
        position,
        *,
        attempt=None,
        source=None,
        first_seen=None,
        unavailable=None,
    ):
        evidence = None
        if attempt is not None:
            item = self._analyses._attempt(attempt)
            if item.source.result_id != attempt["content_id"]:
                raise ValueError("invalid initial source identity")
            source, first_seen = item.source, item.first_seen_at.isoformat()
            # A completed attempt from an older input contract is historical
            # evidence only.  Keep it visible in historical reports, but never
            # freeze it into a new report through a caller that forgot to apply
            # the current-version eligibility query.
            if (
                unavailable is None
                and item.status == "completed"
                and attempt["analysis_input_version"] != MODEL_INPUT_VERSION
            ):
                unavailable = "stale_evidence"
            if unavailable is None and item.status == "completed":
                evidence_job_id = item.job_id
                if item.reused_from_attempt_id is not None:
                    original = connection.execute(
                        "SELECT * FROM content_analysis_attempts WHERE id=?",
                        (item.reused_from_attempt_id,),
                    ).fetchone()
                    if original is None or (
                        original["status"] != "completed"
                        or original["content_id"] != source.result_id
                        or original["input_json"] != attempt["input_json"]
                        or original["input_fingerprint"] != item.input_fingerprint
                        or original["output_json"] != attempt["output_json"]
                    ):
                        raise ValueError("invalid reused evidence provenance")
                    evidence_job_id = original["job_id"]
                job = connection.execute(
                    "SELECT * FROM content_analysis_jobs WHERE id=?", (evidence_job_id,)
                ).fetchone()
                evidence = FrozenTextSource(
                    position=position,
                    attempt_id=item.id,
                    source=source,
                    first_seen_at=item.first_seen_at,
                    input=item.input,
                    understanding=item.output,
                    input_fingerprint=item.input_fingerprint,
                    initial_prompt=read_prompt(
                        connection,
                        job["initial_prompt_version_id"],
                        mode=job["initial_prompt_mode"],
                    ),
                    initial_provider=ProviderIntent(
                        base_url=job["base_url"],
                        model=job["model"],
                        configuration_revision=job["configuration_revision"],
                    ),
                )
            elif unavailable is None:
                unavailable = (
                    "in_progress"
                    if item.status in ("queued", "acquiring", "analysing")
                    else item.status
                )
        source_id = connection.execute(
            """INSERT INTO topic_report_sources(report_id,content_id,position,
              source_json,
          first_seen_at,initial_attempt_id,initial_status,unavailable_reason,
          evidence_json) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                report_id,
                source.result_id,
                position,
                source.model_dump_json(),
                first_seen,
                attempt["id"] if attempt else None,
                attempt["status"] if attempt else None,
                unavailable,
                evidence.model_dump_json() if evidence else None,
            ),
        ).lastrowid
        if evidence is not None:
            node_id = self._insert_node(
                connection,
                report_id,
                f"judgment:{source.result_id}",
                "judgment",
                position,
                0,
            )
            connection.execute(
                "INSERT INTO topic_report_node_sources VALUES(?,?,0)",
                (node_id, source_id),
            )

    def _consume(self, connection, job_id, *, recovered=False):
        event = connection.execute(
            "SELECT * FROM analysis_completion_events WHERE job_id=?", (job_id,)
        ).fetchone()
        if event is None:
            return None
        existing = connection.execute(
            "SELECT id FROM topic_report_runs WHERE completion_event_id=?",
            (event["id"],),
        ).fetchone()
        if existing:
            if event["state"] != "consumed":
                raise ValueError("invalid event link state")
            report = self._read(connection, existing[0])
            if report.trigger != "automatic" or report.initial_job_id != job_id:
                raise ValueError("invalid event report origin")
            return report
        if event["state"] != "pending":
            raise ValueError("missing consumed report")
        job = self._analyses._read(connection, job_id)
        if (
            job.status != "completed"
            or job.completion_event_id != event["id"]
            or job.counts.queued + job.counts.acquiring + job.counts.analysing
            or job.finished_at != datetime.fromisoformat(event["settled_at"])
        ):
            raise ValueError("invalid settlement event")
        prompt = ReportPrompt(
            version_id=job.report_prompt.id,
            mode=job.report_prompt.mode,
            origin=(
                job.report_prompt.mode
                if job.report_prompt.mode in {"default", "custom"}
                else "legacy"
            ),
            instructions=job.report_prompt.instructions,
            content_hash=job.report_prompt.content_hash,
            schema_version=job.report_prompt.schema_version,
        )
        report_id = self._new(
            connection,
            trigger="automatic",
            selection={"kind": "initial_job", "job_id": job_id},
            prompt=prompt,
            provider=ProviderIntent(
                base_url=job.base_url,
                model=job.model,
                configuration_revision=job.configuration_revision,
            ),
            job_id=job_id,
            event_id=event["id"],
        )
        # Exact immutable job members; no current search-content body/title join.
        for attempt in connection.execute(
            "SELECT * FROM content_analysis_attempts WHERE job_id=? ORDER BY position",
            (job_id,),
        ):
            self._snapshot(connection, report_id, attempt["position"], attempt=attempt)
        connection.execute(
            """UPDATE analysis_completion_events SET state='consumed' WHERE id=? AND
              state='pending'""",
            (event["id"],),
        )
        if recovered:
            self._finish(connection, report_id, "interrupted", recovery=True)
        return self._read(connection, report_id)

    def create_workflow(
        self,
        *,
        run_id: int,
        analysis_job_id: int | None,
        operation_key: str,
        analysis_goal: str | None = None,
        configuration_revision: int,
        base_url: str,
        model: str,
        initial_prompt_version_id: int | None = None,
        report_prompt_version_id: int | None = None,
        report_prompt: PromptSnapshot | None = None,
    ):
        """Freeze one workflow-owned report without consuming legacy callbacks."""
        with self.connection(write=True) as connection:
            existing = connection.execute(
                "SELECT id FROM topic_report_runs WHERE workflow_operation_key=?",
                (operation_key,),
            ).fetchone()
            if existing is not None:
                report = self._read(connection, int(existing[0]))
                if (
                    report.selection.kind != "workflow_run"
                    or report.selection.run_id != run_id
                    or report.initial_job_id != analysis_job_id
                ):
                    raise ValueError("invalid workflow report replay")
                return report

            provider = ProviderIntent(
                base_url=base_url,
                model=model,
                configuration_revision=configuration_revision,
            )
            if initial_prompt_version_id is not None:
                # The report may legitimately have zero sources (and thus no
                # analysis job), but its frozen stage-one reference still has
                # to be a real initial-stage prompt before the report is
                # admitted.
                resolve_prompt_version(connection, "initial", initial_prompt_version_id)
            if report_prompt is not None:
                if report_prompt.version_id is None:
                    raise AnalysisError("analysis_prompt_changed")
                if (
                    report_prompt_version_id is not None
                    and report_prompt.version_id != report_prompt_version_id
                ):
                    raise AnalysisError("analysis_prompt_changed")
                frozen = resolve_prompt_version(
                    connection,
                    "report",
                    report_prompt.version_id,
                    mode=report_prompt.mode,
                )
                # Pre-v18 run snapshots pointed at the shared report version
                # while storing the task-specific report instructions in
                # ``analysis_goal``.  The read-time legacy projection keeps
                # both facts, so its text intentionally cannot match that
                # historical shared row.  Current default/custom snapshots
                # must still match every immutable field before admission.
                if report_prompt.mode != "legacy" and (
                    frozen.instructions != report_prompt.instructions
                    or frozen.content_hash != report_prompt.content_hash
                    or frozen.schema_version != report_prompt.schema_version
                ):
                    raise AnalysisError("analysis_prompt_changed")
                prompt = ReportPrompt(
                    version_id=report_prompt.version_id,
                    mode=report_prompt.mode,
                    origin=(
                        report_prompt.mode
                        if report_prompt.mode in {"default", "custom"}
                        else "legacy"
                    ),
                    instructions=report_prompt.instructions,
                    content_hash=report_prompt.content_hash,
                    schema_version=report_prompt.schema_version,
                )
            elif analysis_goal is not None:
                # Historical workflow snapshots only carried ``analysis_goal``
                # in their JSON.  Keep that exact text and mark the projection
                # legacy rather than treating it as a new override/version.
                if report_prompt_version_id is not None:
                    resolve_prompt_version(
                        connection, "report", report_prompt_version_id
                    )
                prompt = ReportPrompt(
                    version_id=report_prompt_version_id,
                    mode="legacy",
                    origin="legacy",
                    instructions=analysis_goal,
                    content_hash=hashlib.sha256(analysis_goal.encode()).hexdigest(),
                    schema_version="topic-report-v1",
                )
            else:
                prompt = self._prompt_choice(
                    connection,
                    version_id=report_prompt_version_id,
                )
            attempts = ()
            if analysis_job_id is not None:
                job = self._analyses._read(connection, analysis_job_id)
                if (
                    job.status != "completed"
                    or job.configuration_revision != configuration_revision
                    or job.base_url != base_url
                    or job.model != model
                    or (
                        initial_prompt_version_id is not None
                        and job.initial_prompt.id != initial_prompt_version_id
                    )
                    or (
                        report_prompt_version_id is not None
                        and job.report_prompt.id != report_prompt_version_id
                    )
                ):
                    raise ValueError("invalid workflow analysis snapshot")
                attempts = connection.execute(
                    """SELECT * FROM content_analysis_attempts
                       WHERE job_id=? ORDER BY position""",
                    (analysis_job_id,),
                ).fetchall()

            report_id = self._new(
                connection,
                trigger="automatic",
                selection={"kind": "workflow_run", "run_id": run_id},
                prompt=prompt,
                provider=provider,
                job_id=analysis_job_id,
                workflow_operation_key=operation_key,
            )
            for attempt in attempts:
                self._snapshot(
                    connection,
                    report_id,
                    attempt["position"],
                    attempt=attempt,
                )
            return self._read(connection, report_id)

    def consume(self, job_id):
        with self.connection(write=True) as connection:
            return self._consume(connection, job_id)

    def create(self, payload):
        with self.connection(write=True) as connection:
            replay = self._replay(connection, "create", None, payload)
            if replay is not None:
                return replay
            prompt = self._prompt_choice(
                connection,
                choice=payload.report_prompt,
                version_id=payload.report_prompt_version_id,
                override=payload.instructions_override,
            )
            report_id = self._new(
                connection,
                trigger="manual"
                if payload.selection.kind == "explicit"
                else "interval",
                selection=payload.selection.model_dump(),
                prompt=prompt,
                provider=self._provider(connection, payload.configuration_revision),
                request_id=payload.request_id,
            )
            # Normalize exact UTC microseconds; SQLite julianday is floating point
            # and loses valid sub-millisecond [from,to) boundary distinctions.
            connection.create_function(
                "report_utc",
                1,
                lambda value: (
                    datetime.fromisoformat(value)
                    .astimezone(UTC)
                    .isoformat(timespec="microseconds")
                ),
                deterministic=True,
            )
            if payload.selection.kind == "explicit":
                rows = connection.execute(
                    """SELECT c.id,c.first_seen_at,cl.latest_attempt_id,
                       cl.known_input_fingerprint,cl.legacy_state
                       FROM json_each(?) selected JOIN search_contents c
                       ON c.id=selected.value JOIN content_analysis_claims cl
                       ON cl.content_id=c.id ORDER BY selected.key""",
                    (json.dumps(payload.selection.result_ids),),
                ).fetchall()
                if len(rows) != len(payload.selection.result_ids):
                    raise TopicReportError("invalid_report_selection")
            else:
                start = (
                    datetime.fromisoformat(payload.selection.first_seen_from)
                    .astimezone(UTC)
                    .isoformat(timespec="microseconds")
                )
                end = (
                    datetime.fromisoformat(payload.selection.first_seen_to)
                    .astimezone(UTC)
                    .isoformat(timespec="microseconds")
                )
                rows = connection.execute(
                    """SELECT c.id,c.first_seen_at,cl.latest_attempt_id,
                       cl.known_input_fingerprint,cl.legacy_state
                       FROM search_contents c JOIN content_analysis_claims cl
                       ON cl.content_id=c.id WHERE report_utc(c.first_seen_at)>=?
                       AND report_utc(c.first_seen_at)<? ORDER BY c.id""",
                    (start, end),
                ).fetchall()
            for position, row in enumerate(rows):
                attempt = connection.execute(
                    "SELECT * FROM content_analysis_attempts WHERE id=?",
                    (row["latest_attempt_id"],),
                ).fetchone()
                if attempt is None:
                    if row["latest_attempt_id"] is not None:
                        raise ValueError("missing latest attempt")
                    source, _ = source_snapshot(connection, row["id"])
                    self._snapshot(
                        connection,
                        report_id,
                        position,
                        source=source,
                        first_seen=row["first_seen_at"],
                        unavailable="legacy_only"
                        if row["legacy_state"]
                        else "not_analysed",
                    )
                else:
                    latest = self._analyses._attempt(attempt)
                    if (
                        attempt["content_id"] != row["id"]
                        or latest.source.result_id != row["id"]
                        or latest.first_seen_at
                        != datetime.fromisoformat(row["first_seen_at"])
                    ):
                        raise ValueError("invalid selected attempt identity")
                    eligible = connection.execute(
                        """SELECT * FROM content_analysis_attempts
                          WHERE content_id=? AND status='completed'
                          AND analysis_input_version=?
                          AND input_fingerprint=? ORDER BY id DESC LIMIT 1""",
                        (
                            row["id"],
                            # Reports created after the text-only cutover may
                            # reuse only evidence written under this input
                            # contract. Historical summaries remain readable
                            # but never become new report evidence.
                            MODEL_INPUT_VERSION,
                            row["known_input_fingerprint"],
                        ),
                    ).fetchone()
                    if eligible is not None:
                        if datetime.fromisoformat(eligible["first_seen_at"]) != (
                            datetime.fromisoformat(row["first_seen_at"])
                        ):
                            raise ValueError("invalid eligible attempt identity")
                        attempt = eligible
                    # A completed attempt from before the text-only cutover is
                    # historical evidence, even when its fingerprint still
                    # matches the current source.  It must not be frozen into
                    # a new report; callers can explicitly re-run analysis to
                    # create a current-version attempt first.
                    stale = attempt["status"] == "completed" and (
                        attempt["analysis_input_version"] != MODEL_INPUT_VERSION
                        or attempt["input_fingerprint"]
                        != row["known_input_fingerprint"]
                    )
                    self._snapshot(
                        connection,
                        report_id,
                        position,
                        attempt=attempt,
                        unavailable="stale_evidence" if stale else None,
                    )
            self._save_request(connection, "create", None, payload, report_id)
            return self._read(connection, report_id)

    def retry(self, parent_id, payload):
        with self.connection(write=True) as connection:
            replay = self._replay(connection, "retry", parent_id, payload)
            if replay is not None:
                return replay
            parent = self._read(connection, parent_id)
            if parent.revision != payload.expected_revision:
                raise TopicReportError("topic_report_changed")
            if parent.status in ACTIVE_REPORTS:
                raise TopicReportError("topic_report_not_terminal")
            prompt = parent.prompt
            if (
                payload.report_prompt is not None
                or payload.report_prompt_version_id is not None
                or payload.instructions_override is not None
            ):
                prompt = self._prompt_choice(
                    connection,
                    choice=payload.report_prompt,
                    version_id=payload.report_prompt_version_id,
                    override=payload.instructions_override,
                )
            report_id = self._new(
                connection,
                trigger="retry",
                selection=parent.selection.model_dump(),
                prompt=prompt,
                provider=self._provider(connection, payload.configuration_revision),
                request_id=payload.request_id,
                job_id=parent.initial_job_id,
                parent_id=parent_id,
            )
            connection.execute(
                """INSERT INTO topic_report_sources(report_id,content_id,position,
                  source_json,
          first_seen_at,
              initial_attempt_id,initial_status,unavailable_reason,evidence_json)
          SELECT ?,content_id,position,source_json,
              first_seen_at,initial_attempt_id,initial_status,unavailable_reason,
          evidence_json FROM topic_report_sources
              WHERE report_id=? ORDER BY position""",
                (report_id, parent_id),
            )
            for source in connection.execute(
                """SELECT * FROM topic_report_sources WHERE report_id=? AND
                  evidence_json IS NOT NULL
                  ORDER BY position""",
                (report_id,),
            ):
                node_id = self._insert_node(
                    connection,
                    report_id,
                    f"judgment:{source['content_id']}",
                    "judgment",
                    source["position"],
                    0,
                )
                connection.execute(
                    "INSERT INTO topic_report_node_sources VALUES(?,?,0)",
                    (node_id, source["id"]),
                )
            self._save_request(connection, "retry", parent_id, payload, report_id)
            return self._read(connection, report_id)

    def request_cancel(self, report_id, payload):
        with self.connection(write=True) as connection:
            replay = self._replay(connection, "cancel", report_id, payload)
            if replay is not None:
                return replay
            row = self._require(connection, report_id)
            if row["revision"] != payload.expected_revision:
                raise TopicReportError("topic_report_changed")
            if row["status"] not in ACTIVE_REPORTS:
                raise TopicReportError("topic_report_not_active")
            connection.execute(
                """UPDATE topic_report_runs SET cancel_requested=1,
                  revision=revision+1 WHERE id=?""",
                (report_id,),
            )
            self._save_request(connection, "cancel", report_id, payload, report_id)
            return self._read(connection, report_id)

    def _insert_node(self, connection, report_id, key, kind, position, level):
        return connection.execute(
            """INSERT INTO topic_report_nodes(report_id,node_key,kind,position,level,
              created_at)
              VALUES(?,?,?,?,?,?)""",
            (report_id, key, kind, position, level, timestamp()),
        ).lastrowid

    def next_report(self):
        with self.connection() as connection:
            row = connection.execute(
                """SELECT id FROM topic_report_runs WHERE status='queued' AND
                  cancel_requested=0 ORDER
                  BY id LIMIT 1"""
            ).fetchone()
            return self._read(connection, row[0]) if row else None

    def stage(self, report_id, status):
        with self.connection(write=True) as connection:
            self._active(connection, report_id)
            connection.execute(
                """UPDATE topic_report_runs SET status=?,
                  started_at=COALESCE(started_at,?),
                  queue_reason=NULL WHERE id=?""",
                (status, timestamp(), report_id),
            )

    def queue(self, report_id):
        with self.connection(write=True) as connection:
            self._active(connection, report_id)
            connection.execute(
                """UPDATE topic_report_runs SET queue_reason='ai_operation_active'
                  WHERE id=?""",
                (report_id,),
            )

    def _active(self, connection, report_id):
        row = self._require(connection, report_id)
        if row["status"] not in ACTIVE_REPORTS or row["cancel_requested"]:
            raise TopicReportError("topic_report_not_active")
        return row

    def context(self, report):
        return EngineContext(
            prompt=TextPrompt(
                instructions=report.prompt.instructions,
                content_hash=report.prompt.content_hash,
                schema_version=report.prompt.schema_version,
            ),
            provider=ProviderIntent(
                base_url=report.base_url,
                model=report.model,
                configuration_revision=report.configuration_revision,
            ),
        )

    def frozen_context(self, report_id):
        # Reuse needs the canonical version's immutable prompt/provider, not an
        # O(all sources) public progress projection for every single node.
        with self.connection() as connection:
            row = self._require(connection, report_id)
            prompt = _read_report_prompt(row["prompt_json"])
            return EngineContext(
                prompt=TextPrompt(
                    instructions=prompt.instructions,
                    content_hash=prompt.content_hash,
                    schema_version=prompt.schema_version,
                ),
                provider=ProviderIntent(
                    base_url=row["base_url"],
                    model=row["model"],
                    configuration_revision=row["configuration_revision"],
                ),
            )

    def nodes(self, report_id, *, kind, level=None, offset=0, limit=100):
        with self.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT * FROM topic_report_nodes WHERE report_id=? AND kind=?
                      AND (? IS NULL OR
                      level=?) ORDER BY level,position LIMIT ? OFFSET ?""",
                    (report_id, kind, level, level, limit, offset),
                )
            ]

    def evidence(self, node_id):
        with self.connection() as connection:
            result = []
            for row in connection.execute(
                """SELECT s.* FROM topic_report_node_sources l
                  JOIN topic_report_sources s ON s.id=l.source_id
                  WHERE l.node_id=? ORDER BY l.position""",
                (node_id,),
            ):
                self._source(connection, row)
                result.append(
                    FrozenTextSource.model_validate_json(row["evidence_json"])
                )
            return result

    def relevant(self, report_id, *, offset=0, limit=8):
        from longtian_api.schemas.topic_report_engine import (
            Judgment as EngineJudgment,
        )
        from longtian_api.schemas.topic_report_engine import (
            RelevantSource,
        )

        with self.connection() as connection:
            values = []
            rows = connection.execute(
                """SELECT s.*,n.output_json FROM topic_report_sources s JOIN
                  topic_report_nodes n
              ON n.report_id=s.report_id AND n.node_key=('judgment:'||s.content_id)
              WHERE s.report_id=? AND n.status='completed' AND
          json_extract(n.output_json,'$.decision')='relevant'
              ORDER BY s.position LIMIT ? OFFSET ?""",
                (report_id, limit, offset),
            )
            for row in rows:
                self._source(connection, row)
                values.append(
                    RelevantSource(
                        evidence=FrozenTextSource.model_validate_json(
                            row["evidence_json"]
                        ),
                        judgment=EngineJudgment.model_validate_json(row["output_json"]),
                    )
                )
            return values

    def leaf_candidates(self, node_id):
        from longtian_api.schemas.topic_report_engine import (
            Judgment as EngineJudgment,
        )
        from longtian_api.schemas.topic_report_engine import (
            RelevantSource,
        )

        with self.connection() as connection:
            return [
                RelevantSource(
                    evidence=FrozenTextSource.model_validate_json(row["evidence_json"]),
                    judgment=EngineJudgment.model_validate_json(row["output_json"]),
                )
                for row in connection.execute(
                    """SELECT s.evidence_json,n.output_json
                FROM topic_report_node_sources l JOIN topic_report_sources s ON
          s.id=l.source_id
                JOIN topic_report_nodes n ON n.report_id=s.report_id AND
          n.node_key=('judgment:'||s.content_id)
                WHERE l.node_id=? AND n.status='completed' ORDER BY l.position""",
                    (node_id,),
                )
            ]

    def add_composition(self, report_id, call, *, level, position):
        with self.connection(write=True) as connection:
            self._active(connection, report_id)
            node_id = self._insert_node(
                connection, report_id, call.key, call.kind, position, level
            )
            if call.kind == "leaf":
                for index, content_id in enumerate(call.source_ids):
                    source = connection.execute(
                        """SELECT id FROM topic_report_sources WHERE report_id=? AND
                          content_id=? AND
                          evidence_json IS NOT NULL""",
                        (report_id, content_id),
                    ).fetchone()
                    connection.execute(
                        "INSERT INTO topic_report_node_sources VALUES(?,?,?)",
                        (node_id, source[0], index),
                    )
                membership = canonical_hash(
                    {
                        "schema": "topic-membership-v1",
                        "source_ids": list(call.source_ids),
                    }
                )
            else:
                manifest = []
                for index, key in enumerate(call.child_ids):
                    child = connection.execute(
                        """SELECT * FROM topic_report_nodes WHERE report_id=? AND
                          node_key=? AND status='completed'""",
                        (report_id, key),
                    ).fetchone()
                    if child is None:
                        raise ValueError("missing completed child")
                    connection.execute(
                        "INSERT INTO topic_report_node_children VALUES(?,?,?)",
                        (node_id, child["id"], index),
                    )
                    manifest.append(self._child(connection, child))
                members = connection.execute(
                    """SELECT s.id,s.position FROM topic_report_node_children c
                  JOIN topic_report_node_sources l ON l.node_id=c.child_id JOIN
          topic_report_sources s ON s.id=l.source_id
                  WHERE c.node_id=? ORDER BY s.position""",
                    (node_id,),
                ).fetchall()
                for index, member in enumerate(members):
                    connection.execute(
                        "INSERT INTO topic_report_node_sources VALUES(?,?,?)",
                        (node_id, member[0], index),
                    )
                membership = canonical_hash(
                    {
                        "schema": "topic-membership-v1",
                        "children": [
                            {
                                "key": c.key,
                                "membership_hash": c.membership_hash,
                                "source_count": c.source_count,
                            }
                            for c in manifest
                        ],
                    }
                )
            connection.execute(
                """UPDATE topic_report_nodes SET membership_hash=?,input_hash=?,
                  engine_version=?,
                  prepared_json=? WHERE id=?""",
                (
                    membership,
                    call.input_hash,
                    ENGINE_VERSION,
                    call.model_dump_json(),
                    node_id,
                ),
            )
            return node_id

    def _stored_output(self, row):
        output = decode_model_json(row["output_json"])
        if (
            row["status"] != "completed"
            or output_digest(row["kind"], output) != row["output_hash"]
        ):
            raise ValueError("invalid saved output hash")
        return output

    def _child(self, connection, row):
        if row["status"] != "completed" or row["kind"] == "judgment":
            raise ValueError("invalid child status")
        members = connection.execute(
            """SELECT s.content_id,s.report_id,l.position FROM
              topic_report_node_sources l JOIN
              topic_report_sources s
          ON s.id=l.source_id WHERE l.node_id=? ORDER BY l.position""",
            (row["id"],),
        ).fetchall()
        if (
            len({member[0] for member in members}) != len(members)
            or any(member[1] != row["report_id"] for member in members)
            or [member[2] for member in members] != list(range(len(members)))
        ):
            raise ValueError("invalid ordered graph membership")
        output = self._stored_output(row)
        if row["kind"] == "leaf":
            if (
                not 1 <= len(members) <= 8
                or row["level"] != 0
                or row["node_key"] != f"leaf:{row['position']}"
            ):
                raise ValueError("invalid leaf identity or bound")
            expected = canonical_hash(
                {"schema": "topic-membership-v1", "source_ids": [r[0] for r in members]}
            )
            cited = {
                identity for item in output["items"] for identity in item["source_ids"]
            }
            if cited != {r[0] for r in members}:
                raise ValueError("invalid leaf coverage")
        else:
            if row["node_key"] != f"overview:{row['level']}:{row['position']}":
                raise ValueError("invalid overview identity")
            child_rows = connection.execute(
                """SELECT n.* FROM topic_report_node_children c
              JOIN topic_report_nodes n ON n.id=c.child_id WHERE c.node_id=? ORDER
          BY c.position""",
                (row["id"],),
            ).fetchall()
            if not 2 <= len(child_rows) <= 8 or any(
                child["report_id"] != row["report_id"] or child["level"] >= row["level"]
                for child in child_rows
            ):
                raise ValueError("invalid child edges")
            children = [self._child(connection, child) for child in child_rows]
            descendant_ids = set()
            for child in child_rows:
                child_ids = {
                    r[0]
                    for r in connection.execute(
                        """SELECT s.content_id FROM topic_report_node_sources l
                  JOIN topic_report_sources s ON s.id=l.source_id WHERE l.node_id=?""",
                        (child["id"],),
                    )
                }
                if descendant_ids & child_ids:
                    raise ValueError("overlapping children")
                descendant_ids.update(child_ids)
            if descendant_ids != {r[0] for r in members}:
                raise ValueError("changed descendant members")
            keys = {child.key for child in children}
            if any(not set(item["child_ids"]) <= keys for item in output["items"]):
                raise ValueError("invalid child citations")
            by_key = {child.key: child for child in children}
            for item in output["items"]:
                if item.get("source_ids") is not None:
                    allowed = {
                        source_id
                        for key in item["child_ids"]
                        for paragraph in by_key[key].items
                        for source_id in paragraph.source_ids
                    }
                    if not set(item["source_ids"]) <= allowed:
                        raise ValueError("invalid paragraph source citations")
            expected = canonical_hash(
                {
                    "schema": "topic-membership-v1",
                    "children": [
                        {
                            "key": c.key,
                            "membership_hash": c.membership_hash,
                            "source_count": c.source_count,
                        }
                        for c in children
                    ],
                }
            )
            if sum(c.source_count for c in children) != len(members):
                raise ValueError("invalid descendant count")
        if expected != row["membership_hash"]:
            raise ValueError("invalid membership hash")
        return ChildOverview(
            key=row["node_key"],
            overview=output["overview"],
            output_hash=row["output_hash"],
            membership_hash=expected,
            source_count=len(members),
            items=[
                {"text": item["text"], "source_ids": item["source_ids"]}
                for item in output["items"]
                if item.get("source_ids")
            ],
        )

    def children(self, node_ids):
        with self.connection() as connection:
            return [
                self._child(
                    connection,
                    connection.execute(
                        "SELECT * FROM topic_report_nodes WHERE id=?", (node_id,)
                    ).fetchone(),
                )
                for node_id in node_ids
            ]

    def dependency_ids(self, node_id):
        with self.connection() as connection:
            return [
                r[0]
                for r in connection.execute(
                    """SELECT child_id FROM topic_report_node_children WHERE
                      node_id=? ORDER BY position""",
                    (node_id,),
                )
            ]

    def prepare(self, node_id, call, engine_version, request_hash=None):
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM topic_report_nodes WHERE id=?", (node_id,)
            ).fetchone()
            self._active(connection, row["report_id"])
            if row["status"] != "queued" or row["node_key"] != call.key:
                raise ValueError("invalid prepared node")
            if row["input_hash"] is not None and (
                row["input_hash"] != call.input_hash
                or row["engine_version"] != engine_version
            ):
                raise ValueError("changed planned input")
            connection.execute(
                """UPDATE topic_report_nodes SET engine_version=?,input_hash=?,
                  prepared_json=?,
                  request_hash=? WHERE id=?""",
                (
                    engine_version,
                    call.input_hash,
                    call.model_dump_json(),
                    request_hash,
                    node_id,
                ),
            )

    def reuse_candidate(self, report_id, key):
        with self.connection() as connection:
            parent = self._require(connection, report_id)["parent_report_id"]
            while parent is not None:
                if parent >= report_id:
                    raise ValueError("invalid retry ancestry")
                row = connection.execute(
                    """SELECT * FROM topic_report_nodes WHERE report_id=? AND
                      node_key=? AND status='completed'""",
                    (parent, key),
                ).fetchone()
                if row is not None:
                    if row["reused_from_node_id"]:
                        if row["reused_from_node_id"] >= row["id"]:
                            raise ValueError("invalid canonical node order")
                        row = connection.execute(
                            "SELECT * FROM topic_report_nodes WHERE id=?",
                            (row["reused_from_node_id"],),
                        ).fetchone()
                    if (
                        row["status"] != "completed"
                        or row["reused_from_node_id"] is not None
                    ):
                        raise ValueError("invalid canonical reuse")
                    self._stored_output(row)
                    if row["kind"] != "judgment":
                        self._child(connection, row)
                    return dict(row)
                report_id = parent
                parent = self._require(connection, report_id)["parent_report_id"]
            return None

    def mark_attempt(self, node_id):
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM topic_report_nodes WHERE id=?", (node_id,)
            ).fetchone()
            self._active(connection, row["report_id"])
            if (
                row["status"] != "queued"
                or row["input_hash"] is None
                or row["request_hash"] is None
            ):
                raise ValueError("invalid request proof")
            connection.execute(
                """UPDATE topic_report_nodes SET status='running',attempted=1,
                  started_at=? WHERE id=?""",
                (timestamp(), node_id),
            )

    def mark_retry(self, node_id, usage):
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM topic_report_nodes WHERE id=?", (node_id,)
            ).fetchone()
            self._active(connection, row["report_id"])
            if row["status"] != "running" or row["retry_attempted"]:
                raise ValueError("invalid output retry")
            connection.execute(
                """UPDATE topic_report_nodes SET retry_attempted=1,usage_json=?
                  WHERE id=?""",
                (usage.model_dump_json() if usage else None, node_id),
            )

    def finish_node(
        self, node_id, *, output=None, usage=None, error=None, reused_from=None
    ):
        usage = observed_usage(usage)
        with self.connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM topic_report_nodes WHERE id=?", (node_id,)
            ).fetchone()
            if (
                self._require(connection, row["report_id"])["status"]
                not in ACTIVE_REPORTS
            ):
                raise TopicReportError("topic_report_not_active")
            if row["status"] not in ("queued", "running"):
                raise ValueError("terminal node write")
            connection.execute(
                """UPDATE topic_report_nodes SET status=?,output_json=?,
                  output_hash=?,
                  usage_json=CASE WHEN retry_attempted=0 THEN ? ELSE usage_json END,
                  retry_usage_json=CASE WHEN retry_attempted=1 THEN ? ELSE NULL END,
              error_json=?,reused_from_node_id=?,finished_at=? WHERE id=?""",
                (
                    "completed" if output else "failed",
                    output.output.model_dump_json() if output else None,
                    output.output_hash if output else None,
                    usage.model_dump_json() if usage else None,
                    usage.model_dump_json() if usage else None,
                    error.model_dump_json() if error else None,
                    reused_from,
                    timestamp(),
                    node_id,
                ),
            )

    def _verify_complete_graph(self, connection, report_id, root_id):
        root = connection.execute(
            """SELECT * FROM topic_report_nodes WHERE id=? AND report_id=? AND
              kind!='judgment'""",
            (root_id, report_id),
        ).fetchone()
        if (
            root is None
            or connection.execute(
                """SELECT 1 FROM topic_report_nodes WHERE report_id=? AND
                  status!='completed' LIMIT 1""",
                (report_id,),
            ).fetchone()
        ):
            raise ValueError("incomplete report graph")
        self._child(connection, root)
        expected = {
            r[0]
            for r in connection.execute(
                """SELECT s.content_id FROM topic_report_sources s JOIN
                  topic_report_nodes n
          ON n.report_id=s.report_id AND n.node_key=('judgment:'||s.content_id)
          WHERE s.report_id=? AND n.status='completed' AND
      json_extract(n.output_json,'$.decision')='relevant'""",
                (report_id,),
            )
        }
        actual = {
            r[0]
            for r in connection.execute(
                """SELECT s.content_id FROM topic_report_node_sources l
          JOIN topic_report_sources s ON s.id=l.source_id WHERE l.node_id=?""",
                (root_id,),
            )
        }
        leaves = [
            r[0]
            for r in connection.execute(
                """SELECT s.content_id FROM topic_report_nodes n
          JOIN topic_report_node_sources l ON l.node_id=n.id JOIN
      topic_report_sources s ON s.id=l.source_id
          WHERE n.report_id=? AND n.kind='leaf'""",
                (report_id,),
            )
        ]
        if (
            not expected
            or actual != expected
            or set(leaves) != expected
            or len(leaves) != len(set(leaves))
        ):
            raise ValueError("incomplete relevant coverage")

    def _finish(
        self,
        connection,
        report_id,
        status,
        *,
        error=None,
        root_id=None,
        empty_reason=None,
        recovery=False,
    ):
        row = self._require(connection, report_id)
        if row["status"] not in ACTIVE_REPORTS:
            return
        if row["cancel_requested"]:
            status, root_id, empty_reason = "cancelled", None, None
        if status == "completed":
            self._verify_complete_graph(connection, report_id, root_id)
        terminal = "cancelled" if status == "cancelled" else "interrupted"
        connection.execute(
            """UPDATE topic_report_nodes SET status=?,error_json=?,finished_at=?
          WHERE report_id=? AND status IN ('queued','running')""",
            (
                terminal,
                failure("execution", terminal).model_dump_json(),
                timestamp(),
                report_id,
            ),
        )
        connection.execute(
            """UPDATE topic_report_runs SET status=?,revision=revision+1,
              root_section_id=?,
          empty_reason=?,
          queue_reason=NULL,recovery_reason=?,error_json=?,finished_at=? WHERE id=?""",
            (
                status,
                root_id,
                empty_reason,
                "backend_restart" if recovery else None,
                (
                    error
                    or (
                        failure("execution", terminal)
                        if status in ("cancelled", "interrupted")
                        else None
                    )
                ).model_dump_json()
                if (error or status in ("cancelled", "interrupted"))
                else None,
                timestamp(),
                report_id,
            ),
        )

    def finish(self, report_id, status, **kwargs):
        with self.connection(write=True) as connection:
            self._finish(connection, report_id, status, **kwargs)
            return self._read(connection, report_id)
