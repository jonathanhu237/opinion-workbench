"""Atomic manual selection, frozen evidence, and durable child ownership."""

import json
from dataclasses import dataclass
from uuid import uuid4

from opinion_workbench_api.repositories.ai_summaries import fingerprint
from opinion_workbench_api.repositories.analysis_settings import resolve_prompt_choice
from opinion_workbench_api.repositories.analysis_shared import (
    AnalysisRepository,
    timestamp,
)
from opinion_workbench_api.repositories.content_analyses import (
    ContentAnalysisRepository,
)
from opinion_workbench_api.repositories.generation_selection import (
    eligibility,
    select_library,
)
from opinion_workbench_api.repositories.platform_access import PlatformAccessRepository
from opinion_workbench_api.schemas.ai_summaries import SummaryFailure
from opinion_workbench_api.schemas.analysis_evidence import AnalysisSource, SavedInput
from opinion_workbench_api.schemas.report_generations import (
    GenerationCreate,
    GenerationList,
    ReportGeneration,
    ReportRecord,
    ReportRecordList,
    SelectionPreview,
    SelectionPreviewRequest,
)
from opinion_workbench_api.schemas.topic_report_engine import ProviderIntent
from opinion_workbench_api.schemas.topic_reports import ExplicitSelection, ReportPrompt
from opinion_workbench_api.services.ai_analysis import MODEL_INPUT_VERSION
from opinion_workbench_api.services.analysis_errors import AnalysisError
from opinion_workbench_api.services.summary_errors import failure
from opinion_workbench_api.services.topic_report_errors import (
    CONFIGURATION_FAILURES,
    configuration_failure,
)

ACTIVE_GENERATIONS = ("summarising", "reporting")


@dataclass(frozen=True)
class GenerationWork:
    id: int
    status: str
    analysis_status: str
    report_status: str | None


class ReportGenerationRepository(AnalysisRepository):
    def __init__(self, database, reports):
        super().__init__(database)
        self._analyses = ContentAnalysisRepository(database)
        self.reports = reports

    def initialize(self):
        self.database.initialize()
        with self.connection(write=True) as connection:
            rows = connection.execute(
                """SELECT analysis_job_id,report_id FROM report_generations
                WHERE status IN ('summarising','reporting')"""
            ).fetchall()
            for row in rows:
                self._analyses._finish(
                    connection, row["analysis_job_id"], "interrupted"
                )
                if row["report_id"] is not None:
                    self.reports._finish(connection, row["report_id"], "interrupted")
            connection.execute(
                """UPDATE report_generations SET status='interrupted',
                finished_at=?,pause_reason=NULL,pause_attempt_id=NULL
                WHERE status IN ('summarising','reporting')""",
                (timestamp(),),
            )

    def _require_generation(self, connection, generation_id):
        row = connection.execute(
            "SELECT * FROM report_generations WHERE id=?", (generation_id,)
        ).fetchone()
        if row is None:
            raise AnalysisError("report_generation_not_found")
        return row

    def _generation(self, connection, generation_id):
        row = self._require_generation(connection, generation_id)
        intent = GenerationCreate.model_validate_json(row["intent_json"])
        selected_ids = [
            r[0]
            for r in connection.execute(
                """SELECT content_id FROM content_analysis_attempts
                WHERE job_id=? ORDER BY position""",
                (row["analysis_job_id"],),
            )
        ]
        return ReportGeneration(
            id=row["id"],
            request_id=row["request_id"],
            name=row["name"] or f"报告 #{row['id']}",
            selection=ExplicitSelection(kind="explicit", result_ids=selected_ids),
            selection_policy=intent.selection,
            status="paused_for_manual_action" if row["pause_reason"] else row["status"],
            pause_reason=row["pause_reason"],
            pause_attempt_id=row["pause_attempt_id"],
            control_revision=row["control_revision"],
            analysis=self._analyses._read(connection, row["analysis_job_id"]),
            report=self.reports._read(connection, row["report_id"])
            if row["report_id"]
            else None,
            created_at=row["created_at"],
            finished_at=row["finished_at"],
        )

    def read_generation(self, generation_id):
        with self.connection() as connection:
            return self._generation(connection, generation_id)

    def list_generations(self, *, limit=20, before_id=None):
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT id FROM report_generations
                WHERE (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?""",
                (before_id, before_id, limit + 1),
            ).fetchall()
            return GenerationList(
                items=[self._generation(connection, row[0]) for row in rows[:limit]],
                next_before_id=rows[limit - 1][0] if len(rows) > limit else None,
            )

    def list_records(self, *, limit=20, offset=0, report_id=None):
        """Return one stable, time-ordered projection of every report record.

        Manual generations own their child report and therefore appear once as
        a ``generation`` row. Standalone topic reports (automatic, interval,
        and retry) appear as ``report`` rows; a manual child is excluded by
        the ownership join below. This keeps the UI from merging two
        independently paginated histories and accidentally duplicating rows.
        """
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT record_type, record_id, generation_id, report_id, name,
                       automation_run_id, trigger, status, created_at, selection_count,
                       processed_count, failed_count, active_count,
                       parent_report_id
                FROM (
                  SELECT
                    'generation' AS record_type,
                    g.id AS record_id,
                    g.id AS generation_id,
                    g.report_id AS report_id,
                    NULL AS automation_run_id,
                    COALESCE(NULLIF(g.name, ''), '报告 #' || g.id) AS name,
                    'manual' AS trigger,
                    CASE WHEN g.pause_reason IS NOT NULL
                         THEN 'paused_for_manual_action'
                         ELSE g.status END AS status,
                    g.created_at AS created_at,
                    (SELECT COUNT(*) FROM content_analysis_attempts a
                       WHERE a.job_id = g.analysis_job_id) AS selection_count,
                    (SELECT COUNT(*) FROM content_analysis_attempts a
                       WHERE a.job_id = g.analysis_job_id
                       AND a.status NOT IN ('queued','acquiring','analysing'))
                       AS processed_count,
                    (SELECT COUNT(*) FROM content_analysis_attempts a
                       WHERE a.job_id = g.analysis_job_id
                       AND a.status IN ('failed','input_incomplete','unsupported',
                                        'cancelled','interrupted')) AS failed_count,
                    (SELECT COUNT(*) FROM content_analysis_attempts a
                       WHERE a.job_id = g.analysis_job_id
                       AND a.status IN ('queued','acquiring','analysing'))
                       AS active_count,
                    NULL AS parent_report_id
                  FROM report_generations g
                  UNION ALL
                  SELECT
                    'report' AS record_type,
                    r.id AS record_id,
                    NULL AS generation_id,
                    r.id AS report_id,
                    COALESCE(
                      (SELECT ar.id FROM automation_runs ar
                       WHERE ar.topic_report_id = r.id
                       ORDER BY ar.id DESC LIMIT 1),
                      (SELECT ar.id FROM automation_runs ar
                       JOIN topic_report_runs parent ON parent.id = r.parent_report_id
                       WHERE ar.topic_report_id = parent.id
                       ORDER BY ar.id DESC LIMIT 1)
                    ) AS automation_run_id,
                    CASE r.trigger
                      WHEN 'automatic' THEN '自动报告 #' || r.id
                      WHEN 'interval' THEN '时间范围报告 #' || r.id
                      WHEN 'retry' THEN '报告重试 #' || r.id
                      ELSE '报告 #' || r.id
                    END AS name,
                    r.trigger AS trigger,
                    r.status AS status,
                    r.created_at AS created_at,
                    (SELECT COUNT(*) FROM topic_report_sources s
                       WHERE s.report_id = r.id) AS selection_count,
                    (SELECT COUNT(*) FROM topic_report_sources s
                       LEFT JOIN topic_report_nodes n
                         ON n.report_id = s.report_id
                        AND n.node_key = 'judgment:' || s.content_id
                       WHERE s.report_id = r.id
                       AND (s.unavailable_reason IS NOT NULL
                            OR n.status NOT IN ('queued','running')))
                       AS processed_count,
                    (SELECT COUNT(*) FROM topic_report_sources s
                       LEFT JOIN topic_report_nodes n
                         ON n.report_id = s.report_id
                        AND n.node_key = 'judgment:' || s.content_id
                       WHERE s.report_id = r.id
                       AND (s.unavailable_reason IS NOT NULL
                            OR n.status IN ('failed','cancelled','interrupted')))
                       AS failed_count,
                    (SELECT COUNT(*) FROM topic_report_sources s
                       JOIN topic_report_nodes n
                         ON n.report_id = s.report_id
                        AND n.node_key = 'judgment:' || s.content_id
                       WHERE s.report_id = r.id
                       AND s.unavailable_reason IS NULL
                       AND n.status IN ('queued','running')) AS active_count,
                    r.parent_report_id AS parent_report_id
                  FROM topic_report_runs r
                  WHERE NOT EXISTS (
                    SELECT 1 FROM report_generations g
                    WHERE g.report_id = r.id
                  )
                )
                WHERE (? IS NULL OR report_id=?)
                ORDER BY created_at DESC, record_type ASC, record_id DESC
                LIMIT ? OFFSET ?
                """,
                (report_id, report_id, limit + 1, offset),
            ).fetchall()
            values = [
                ReportRecord(
                    record_type=row["record_type"],
                    record_id=row["record_id"],
                    generation_id=row["generation_id"],
                    report_id=row["report_id"],
                    automation_run_id=row["automation_run_id"],
                    name=row["name"],
                    trigger=row["trigger"],
                    status=row["status"],
                    created_at=row["created_at"],
                    selection_count=row["selection_count"],
                    processed_count=row["processed_count"],
                    failed_count=row["failed_count"],
                    active_count=row["active_count"],
                    parent_report_id=row["parent_report_id"],
                )
                for row in rows[:limit]
            ]
            return ReportRecordList(
                items=values,
                next_offset=offset + limit if len(rows) > limit else None,
            )

    def read_record_by_report(self, report_id):
        page = self.list_records(limit=1, report_id=report_id)
        return page.items[0] if page.items else None

    def _replay_generation(self, connection, payload):
        row = connection.execute(
            "SELECT * FROM report_generations WHERE request_id=?", (payload.request_id,)
        ).fetchone()
        if row is None:
            return None
        # Rows written before v25 did not have a ``name`` field in their
        # idempotency payload.  Treat an omitted/None name as the same legacy
        # request while keeping named requests fully bound to their intent.
        hashes = {
            fingerprint(payload.model_dump()),
            fingerprint(payload.model_dump(exclude_none=True)),
        }
        # v38 intents did not contain a concurrency field. Replaying one with
        # the new default must still resolve to the original task rather than
        # creating a second report; the persisted analysis snapshot remains the
        # historical serial value. Inspect the stored intent as well as the
        # current model-field set: a new client may parse a historical payload
        # through its defaulting schema and send ``summary_concurrency=8`` even
        # though the original request omitted the field.
        try:
            stored_intent = json.loads(row["intent_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            stored_intent = None
        stored_concurrency_missing = not isinstance(stored_intent, dict) or (
            "summary_concurrency" not in stored_intent
        )
        if "summary_concurrency" not in payload.model_fields_set or (
            stored_concurrency_missing and payload.summary_concurrency == 8
        ):
            legacy = payload.model_dump()
            legacy.pop("summary_concurrency", None)
            hashes.add(fingerprint(legacy))
        if row["intent_hash"] not in hashes:
            raise AnalysisError("content_analysis_request_conflict")
        return self._generation(connection, row["id"])

    def replay_generation(self, payload):
        with self.connection() as connection:
            return self._replay_generation(connection, payload)

    def eligibility(self):
        with self.connection() as connection:
            return eligibility(connection)

    def selection_preview(self, payload: SelectionPreviewRequest) -> SelectionPreview:
        """Resolve a visible, side-effect-free selection snapshot.

        This method only reads SQLite. It deliberately does not admit an
        analysis job, freeze evidence, contact a platform, or call a model.
        """
        with self.connection() as connection:
            if payload.kind == "library":
                selected_ids = select_library(connection)
            else:
                selected_ids = list(payload.result_ids)
            if not selected_ids:
                raise AnalysisError("no_eligible_contents")
            placeholders = ",".join("?" for _ in selected_ids)
            rows = connection.execute(
                f"""SELECT cl.content_id,cl.active_job_id,
                    cl.active_legacy_summary_id,cl.legacy_state,a.status,
                    a.analysis_input_version
                    FROM content_analysis_claims cl
                    LEFT JOIN content_analysis_attempts a
                      ON a.id=cl.latest_attempt_id
                    WHERE cl.content_id IN ({placeholders})""",
                selected_ids,
            ).fetchall()
            by_id = {row["content_id"]: row for row in rows}
            if len(by_id) != len(selected_ids):
                raise AnalysisError("result_not_found")
            pending = summarized = failed = active = 0
            for content_id in selected_ids:
                row = by_id[content_id]
                if (
                    row["active_job_id"] is not None
                    or row["active_legacy_summary_id"] is not None
                    or row["status"] in ("queued", "acquiring", "analysing")
                ):
                    active += 1
                elif (
                    row["status"] == "completed"
                    and row["analysis_input_version"] == MODEL_INPUT_VERSION
                ):
                    summarized += 1
                elif row["status"] == "completed" or row["legacy_state"] in (
                    "legacy_completed",
                    "legacy_attempted",
                ):
                    # Historical summaries are retained for historical reports,
                    # but never satisfy a new text-only selection. They are
                    # pending so admission creates a fresh understanding.
                    pending += 1
                elif row["status"] in (
                    "failed",
                    "input_incomplete",
                    "unsupported",
                    "cancelled",
                    "interrupted",
                ) or (
                    row["status"] is None and row["legacy_state"] == "legacy_attempted"
                ):
                    failed += 1
                else:
                    pending += 1
            return SelectionPreview(
                selection={"kind": "explicit", "result_ids": selected_ids},
                counts={
                    "total": len(selected_ids),
                    "pending": pending,
                    "already_summarized": summarized,
                    "failed": failed,
                    "active": active,
                },
            )

    def create_generation(self, payload):
        with self.connection(write=True) as connection:
            replay = self._replay_generation(connection, payload)
            if replay is not None:
                return replay
            # Named requests are emitted by the report page and opt into the
            # single-active-task product rule.
            if payload.name is not None:
                active = connection.execute(
                    """SELECT 1 FROM report_generations
                       WHERE status IN ('summarising','reporting') LIMIT 1"""
                ).fetchone()
                if active is not None:
                    raise AnalysisError("report_generation_active")
            provider = self._analyses._provider(
                connection, payload.configuration_revision
            )
            initial = resolve_prompt_choice(
                connection, "initial", payload.initial_prompt
            )
            report = resolve_prompt_choice(connection, "report", payload.report_prompt)
            selected_ids = (
                payload.selection.result_ids
                if payload.selection.kind == "explicit"
                else select_library(connection)
            )
            if not selected_ids:
                raise AnalysisError("no_eligible_contents")
            selections = []
            for position, content_id in enumerate(selected_ids):
                claim = connection.execute(
                    "SELECT * FROM content_analysis_claims WHERE content_id=?",
                    (content_id,),
                ).fetchone()
                if claim is None:
                    raise AnalysisError("result_not_found")
                active = (
                    claim["active_job_id"] is not None
                    or claim["active_legacy_summary_id"] is not None
                )
                selections.append((content_id, position, active))
            admission = self._analyses._admit(
                connection,
                provider,
                initial.version_id,
                report.version_id,
                initial.mode,
                report.mode,
                request_id=payload.request_id,
                active=sum(active for _, _, active in selections),
                selections=tuple(selections),
                summary_concurrency=payload.summary_concurrency,
                platform_access_snapshot=PlatformAccessRepository(
                    self.database
                ).snapshot_from_connection(connection),
            )
            job_id = admission.job.id
            # Freeze reusable summaries and acquired inputs before another task can
            # change the library's latest-result pointers. No external IO here.
            attempts = connection.execute(
                """SELECT * FROM content_analysis_attempts
                    WHERE job_id=? AND status='queued' ORDER BY position""",
                (job_id,),
            ).fetchall()
            for attempt in attempts:
                self._freeze_saved_evidence(connection, attempt)
            generation_id = connection.execute(
                """INSERT INTO report_generations
                (request_id,intent_json,intent_hash,analysis_job_id,
                 report_request_id,name,status,created_at)
                VALUES (?,?,?,?,?,?,'summarising',?)""",
                (
                    payload.request_id,
                    payload.model_dump_json(),
                    fingerprint(payload.model_dump()),
                    job_id,
                    str(uuid4()),
                    payload.name or "",
                    timestamp(),
                ),
            ).lastrowid
            return self._generation(connection, generation_id)

    def _freeze_saved_evidence(self, connection, attempt):
        cached = connection.execute(
            """SELECT a.* FROM content_analysis_attempts a
            JOIN content_analysis_claims cl ON cl.content_id=a.content_id
            WHERE a.content_id=? AND a.id<? AND a.observation_hash=?
            AND a.status='completed' AND a.reused_from_attempt_id IS NULL
            AND a.analysis_input_version=?
            AND a.input_fingerprint=cl.known_input_fingerprint
            ORDER BY a.id DESC LIMIT 1""",
            (
                attempt["content_id"],
                attempt["id"],
                attempt["observation_hash"],
                MODEL_INPUT_VERSION,
            ),
        ).fetchone()
        if cached is not None:
            value = self._analyses._attempt(cached)
            if (
                value.input is not None
                and value.input.analysis_eligible
                and value.input.extractor_version
                == f"{value.source.platform}-enrichment-v1"
            ):
                connection.execute(
                    """UPDATE content_analysis_attempts SET status='completed',
                    input_json=?,input_fingerprint=?,output_json=?,reused_from_attempt_id=?,
                    analysis_input_version=?,started_at=?,finished_at=? WHERE id=?""",
                    (
                        cached["input_json"],
                        cached["input_fingerprint"],
                        cached["output_json"],
                        cached["id"],
                        cached["analysis_input_version"],
                        timestamp(),
                        timestamp(),
                        attempt["id"],
                    ),
                )
                return
        material = connection.execute(
            """SELECT input_json,input_fingerprint FROM content_materials
            WHERE content_id=? AND observation_hash=? AND analysis_input_version=?""",
            (attempt["content_id"], attempt["observation_hash"], MODEL_INPUT_VERSION),
        ).fetchone()
        if material is None:
            material = connection.execute(
                """SELECT input_json,input_fingerprint FROM content_analysis_attempts
                WHERE content_id=? AND id<? AND observation_hash=?
                AND analysis_input_version=?
                AND input_json IS NOT NULL
                AND input_fingerprint IS NOT NULL ORDER BY id DESC LIMIT 1""",
                (
                    attempt["content_id"],
                    attempt["id"],
                    attempt["observation_hash"],
                    MODEL_INPUT_VERSION,
                ),
            ).fetchone()
        if material is not None:
            source = AnalysisSource.model_validate_json(attempt["source_json"])
            saved = SavedInput.model_validate_json(material["input_json"])
            # Search-card previews are discovery evidence, not original-post
            # text.  Only a current detail input can be frozen into a new
            # report; a missing/unavailable detail remains open for acquisition.
            if (
                saved.text.coverage == "unavailable"
                or saved.extractor_version != f"{source.platform}-enrichment-v1"
                or not saved.evidence_coverage.text_available
            ):
                return
            connection.execute(
                """UPDATE content_analysis_attempts SET input_json=?,
                input_fingerprint=? WHERE id=?""",
                (material["input_json"], material["input_fingerprint"], attempt["id"]),
            )

    def next_generation(self):
        with self.connection() as connection:
            row = connection.execute(
                """SELECT g.id,g.status,a.status AS analysis_status,
                    r.status AS report_status FROM report_generations g
                    JOIN content_analysis_jobs a ON a.id=g.analysis_job_id
                    LEFT JOIN topic_report_runs r ON r.id=g.report_id
                    WHERE g.status IN ('summarising','reporting')
                    AND g.pause_reason IS NULL
                    ORDER BY CASE WHEN a.status IN ('queued','running')
                                  THEN 1 ELSE 0 END,
                    g.id LIMIT 1"""
            ).fetchone()
            return GenerationWork(**dict(row)) if row else None

    def finish_generation(self, generation_id, status):
        with self.connection(write=True) as connection:
            self._require_generation(connection, generation_id)
            connection.execute(
                """UPDATE report_generations SET status=?,finished_at=?,
                pause_reason=NULL,pause_attempt_id=NULL
                WHERE id=? AND status IN ('summarising','reporting')""",
                (status, timestamp(), generation_id),
            )

    def block_configuration(self, revision, code):
        """Stop related manual work atomically, leaving automation untouched."""
        with self.connection(write=True) as connection:
            jobs = connection.execute(
                """SELECT a.id FROM content_analysis_jobs a
                JOIN report_generations g ON g.analysis_job_id=a.id
                WHERE a.configuration_revision=? AND a.status IN ('queued','running')
                AND g.status IN ('summarising','reporting')""",
                (revision,),
            ).fetchall()
            for job in jobs:
                self._analyses._finish(connection, job[0], "configuration_blocked")
            reports = connection.execute(
                """SELECT id FROM topic_report_runs
                WHERE configuration_revision=?
                AND status IN ('queued','judging','composing')
                AND json_extract(selection_json,'$.kind')='explicit'""",
                (revision,),
            ).fetchall()
            error = (
                configuration_failure(code)
                if code in CONFIGURATION_FAILURES
                else failure("execution", code)
            )
            for report in reports:
                self.reports._finish(
                    connection, report[0], "configuration_blocked", error=error
                )
            connection.execute(
                """UPDATE report_generations
                SET status='configuration_blocked',finished_at=?,pause_reason=NULL,
                    pause_attempt_id=NULL
                WHERE status IN ('summarising','reporting') AND analysis_job_id IN (
                    SELECT a.id FROM content_analysis_jobs a
                    LEFT JOIN topic_report_runs r ON r.id=report_generations.report_id
                    WHERE a.id=report_generations.analysis_job_id
                    AND a.configuration_revision=?
                    AND (a.status='configuration_blocked'
                         OR r.status='configuration_blocked'))""",
                (timestamp(), revision),
            )

    def pause(self, job_id, attempt_id, reason):
        with self.connection(write=True) as connection:
            attempt = self._analyses._active(connection, attempt_id)
            row = connection.execute(
                "SELECT * FROM report_generations WHERE analysis_job_id=?", (job_id,)
            ).fetchone()
            if (
                row is None
                or row["status"] != "summarising"
                or row["pause_reason"] is not None
                or attempt["job_id"] != job_id
                or attempt["status"] != "acquiring"
            ):
                raise AnalysisError("content_analysis_selection_conflict")
            connection.execute(
                """UPDATE content_analysis_attempts SET status='queued'
                WHERE id=?""",
                (attempt_id,),
            )
            connection.execute(
                """UPDATE content_analysis_jobs
                SET queue_reason='browser_operation_active'
                WHERE id=?""",
                (job_id,),
            )
            connection.execute(
                """UPDATE report_generations SET pause_reason=?,pause_attempt_id=?,
                control_revision=control_revision+1 WHERE id=?""",
                (reason, attempt_id, row["id"]),
            )
            return row["id"]

    def resume(self, generation_id, expected_revision):
        with self.connection(write=True) as connection:
            row = self._require_generation(connection, generation_id)
            if (
                row["status"] != "summarising"
                or row["pause_reason"] is None
                or row["control_revision"] != expected_revision
            ):
                raise AnalysisError("content_analysis_selection_conflict")
            connection.execute(
                """UPDATE report_generations SET pause_reason=NULL,
                pause_attempt_id=NULL,
                control_revision=control_revision+1 WHERE id=?""",
                (generation_id,),
            )
            connection.execute(
                "UPDATE content_analysis_jobs SET queue_reason=NULL WHERE id=?",
                (row["analysis_job_id"],),
            )
            return self._generation(connection, generation_id)

    def for_analysis(self, job_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id FROM report_generations WHERE analysis_job_id=?", (job_id,)
            ).fetchone()
            return self._generation(connection, row[0]) if row else None

    def all_attempts_text_insufficient(self, job_id: int) -> bool:
        """Return true only for a job whose every source lacked usable text.

        A report shell is a valid business result for this case.  Requiring the
        persisted acquisition failure shape keeps model, storage, and browser
        failures from being misreported as a completed text-insufficient run.
        """
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT status,error_json FROM content_analysis_attempts
                WHERE job_id=? ORDER BY position""",
                (job_id,),
            ).fetchall()
            if not rows:
                return False
            for row in rows:
                if row["status"] not in {"input_incomplete", "unsupported"}:
                    return False
                if not row["error_json"]:
                    return False
                try:
                    error = SummaryFailure.model_validate_json(row["error_json"])
                except (TypeError, ValueError):
                    return False
                if error.stage != "acquisition" or error.code != "input_incomplete":
                    return False
            return True

    def cancel_generation(self, generation_id, expected_revision):
        """Freeze terminal guards before stopping transport; no late publication."""
        with self.connection(write=True) as connection:
            row = self._require_generation(connection, generation_id)
            if row["status"] not in ACTIVE_GENERATIONS:
                return self._generation(connection, generation_id)
            if row["control_revision"] != expected_revision:
                raise AnalysisError("content_analysis_selection_conflict")
            connection.execute(
                """UPDATE content_analysis_attempts AS a
                SET input_json=(SELECT m.input_json FROM content_materials m
                                WHERE m.content_id=a.content_id),
                    input_fingerprint=(SELECT m.input_fingerprint
                                       FROM content_materials m
                                       WHERE m.content_id=a.content_id),
                    analysis_input_version=?
                WHERE job_id=? AND status='acquiring' AND input_json IS NULL
                AND EXISTS(SELECT 1 FROM content_materials m
                    WHERE m.content_id=a.content_id
                    AND m.observation_hash=a.observation_hash
                    AND m.analysis_input_version=?)""",
                (MODEL_INPUT_VERSION, row["analysis_job_id"], MODEL_INPUT_VERSION),
            )
            self._analyses._finish(connection, row["analysis_job_id"], "cancelled")
            status = "cancelled"
            if row["report_id"] is not None:
                report = self.reports._require(connection, row["report_id"])
                if report["status"] in ("completed", "empty"):
                    status = report["status"]
                else:
                    self.reports._finish(connection, row["report_id"], "cancelled")
            connection.execute(
                """UPDATE report_generations SET status=?,finished_at=?,
                pause_reason=NULL,pause_attempt_id=NULL,control_revision=control_revision+1
                WHERE id=?""",
                (status, timestamp(), generation_id),
            )
            return self._generation(connection, generation_id)

    def admit_report(self, generation_id):
        with self.connection(write=True) as connection:
            row = self._require_generation(connection, generation_id)
            if row["report_id"] is not None:
                return self.reports._read(connection, row["report_id"])
            job = self._analyses._read(connection, row["analysis_job_id"])
            if row["status"] != "summarising" or job.status != "completed":
                raise AnalysisError("content_analysis_selection_conflict")
            selected_ids = [
                r[0]
                for r in connection.execute(
                    """SELECT content_id FROM content_analysis_attempts
                    WHERE job_id=? ORDER BY position""",
                    (job.id,),
                )
            ]
            prompt = job.report_prompt
            report_id = self.reports._new(
                connection,
                trigger="manual",
                selection={"kind": "explicit", "result_ids": selected_ids},
                request_id=row["report_request_id"],
                provider=ProviderIntent(
                    configuration_revision=job.configuration_revision,
                    base_url=job.base_url,
                    model=job.model,
                ),
                prompt=ReportPrompt(
                    version_id=prompt.id,
                    mode=prompt.mode,
                    origin=prompt.mode
                    if prompt.mode in ("default", "custom")
                    else "shared",
                    instructions=prompt.instructions,
                    content_hash=prompt.content_hash,
                    schema_version=prompt.schema_version,
                ),
            )
            for attempt in connection.execute(
                """SELECT * FROM content_analysis_attempts
                WHERE job_id=? ORDER BY position""",
                (job.id,),
            ):
                self.reports._snapshot(
                    connection, report_id, attempt["position"], attempt=attempt
                )
            connection.execute(
                """UPDATE report_generations SET report_id=?,status='reporting'
                    WHERE id=?""",
                (report_id, generation_id),
            )
            return self.reports._read(connection, report_id)
