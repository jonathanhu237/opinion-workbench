"""Atomic uncapped admissions, immutable evidence and once-per-task settlement."""

from typing import get_args

from longtian_api.repositories.ai_summaries import fingerprint
from longtian_api.repositories.analysis_settings import (
    read_prompt,
    resolve_prompt_choice,
    resolve_prompt_version,
)
from longtian_api.repositories.analysis_shared import (
    AnalysisRepository,
    date,
    source_snapshot,
    timestamp,
)
from longtian_api.repositories.results import NEVER_STARTED_SQL
from longtian_api.schemas.ai_summaries import SummaryFailure, SummarySource, TokenUsage
from longtian_api.schemas.analysis_evidence import AnalysisSource, SavedInput
from longtian_api.schemas.content_analyses import (
    AnalysisAdmission,
    AnalysisAttempt,
    AnalysisAttemptList,
    AnalysisCounts,
    AnalysisCreate,
    AnalysisJob,
    AnalysisJobList,
    AnalysisUsage,
    AttemptStatus,
    Understanding,
    WorkflowAnalysisCreate,
)
from longtian_api.services.ai_analysis import MODEL_INPUT_VERSION
from longtian_api.services.ai_client import MAX_USAGE_TOKENS
from longtian_api.services.ai_errors import AIError
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.summary_errors import failure

ACTIVE_ATTEMPTS = ("queued", "acquiring", "analysing")
WORKFLOW_RECOVERABLE_ATTEMPTS = (
    "input_incomplete",
    "unsupported",
    "failed",
    "cancelled",
    "interrupted",
)


def _resolve_prompt(connection, stage, choice, version_id, mode=None):
    """Resolve a submitted choice or legacy frozen version in one transaction."""
    if choice is not None:
        selected = resolve_prompt_choice(connection, stage, choice)
        if mode is not None and mode != selected.mode:
            raise AnalysisError("analysis_prompt_changed")
        if version_id is not None:
            # A request proof may contain both fields when replaying an older
            # intent.  They must describe the same immutable content; letting
            # the choice silently win would admit a mismatched/stale version
            # while recording a different source than the caller proved.
            frozen = resolve_prompt_version(connection, stage, version_id)
            if (
                frozen.instructions != selected.instructions
                or frozen.content_hash != selected.content_hash
                or frozen.schema_version != selected.schema_version
            ):
                raise AnalysisError("analysis_prompt_changed")
        return selected
    if version_id is not None:
        row = connection.execute(
            "SELECT stage FROM analysis_prompt_versions WHERE id=?", (version_id,)
        ).fetchone()
        if row is None or row["stage"] != stage:
            raise AnalysisError("analysis_prompt_changed")
        return resolve_prompt_version(connection, stage, version_id, mode=mode)
    if mode not in (None, "default"):
        raise AnalysisError("analysis_prompt_changed")
    return resolve_prompt_choice(connection, stage, None)


def observation_hash(source: SummarySource) -> str:
    # Neutral content understanding is independent of collection rule and origin.
    # Relative publication labels and new matched terms do not make content new.
    return fingerprint(
        source.model_dump(
            exclude={"source_run_id", "matched_terms", "published_at_text"}
        )
    )


def workflow_intent_hash(payload: WorkflowAnalysisCreate, operation_key: str) -> str:
    """Hash the private workflow intent separately from public API calls."""
    return fingerprint(
        {
            "kind": "workflow",
            "operation_key": operation_key,
            "payload": payload.model_dump(),
        }
    )


class ContentAnalysisRepository(AnalysisRepository):
    def initialize(self) -> None:
        self.database.initialize()
        with self.connection(write=True) as connection:
            for row in connection.execute(
                """SELECT id FROM content_analysis_jobs WHERE status IN
                  ('queued','running')"""
            ).fetchall():
                self._finish(connection, row[0], "interrupted")

    def _require_job(self, connection, job_id):
        row = connection.execute(
            "SELECT * FROM content_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AnalysisError("content_analysis_not_found")
        return row

    def _read(self, connection, job_id) -> AnalysisJob:
        row = self._require_job(connection, job_id)
        counts = dict.fromkeys(get_args(AttemptStatus), 0)
        counts["reused"] = 0
        attempted = accounted = prompt = completion = total_tokens = 0
        for item in connection.execute(
            """SELECT status,reused_from_attempt_id,attempted,usage_json FROM
              content_analysis_attempts WHERE job_id=? ORDER BY position""",
            (job_id,),
        ):
            counts[item["status"]] += 1
            counts["reused"] += int(item["reused_from_attempt_id"] is not None)
            attempted += item["attempted"]
            if item["usage_json"] is not None:
                usage = TokenUsage.model_validate_json(item["usage_json"])
                accounted += 1
                prompt += usage.prompt_tokens
                completion += usage.completion_tokens
                total_tokens += usage.total_tokens
        unknown = (attempted > 0 and accounted == 0) or total_tokens > MAX_USAGE_TOKENS
        event = connection.execute(
            "SELECT id FROM analysis_completion_events WHERE job_id=?", (job_id,)
        ).fetchone()
        return AnalysisJob(
            id=job_id,
            request_id=row["request_id"],
            trigger=row["trigger"],
            status=row["status"],
            configuration_revision=row["configuration_revision"],
            base_url=row["base_url"],
            model=row["model"],
            initial_prompt=read_prompt(
                connection,
                row["initial_prompt_version_id"],
                mode=row["initial_prompt_mode"],
            ),
            report_prompt=read_prompt(
                connection,
                row["report_prompt_version_id"],
                mode=row["report_prompt_mode"],
            ),
            force_refresh=bool(row["force_refresh"]),
            counts=AnalysisCounts(
                total=sum(v for k, v in counts.items() if k != "reused"), **counts
            ),
            usage=AnalysisUsage(
                attempted_requests=attempted,
                accounted_requests=accounted,
                complete=not unknown and attempted == accounted,
                prompt_tokens=None if unknown else prompt,
                completion_tokens=None if unknown else completion,
                total_tokens=None if unknown else total_tokens,
            ),
            queue_reason=row["queue_reason"],
            completion_event_id=event[0] if event else None,
            created_at=date(row["created_at"]),
            started_at=date(row["started_at"]),
            finished_at=date(row["finished_at"]),
        )

    def read(self, job_id) -> AnalysisJob:
        with self.connection() as connection:
            return self._read(connection, job_id)

    def list(self, *, limit=20, before_id=None) -> AnalysisJobList:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT id FROM content_analysis_jobs WHERE (? IS NULL OR id<?)
                  ORDER BY id DESC LIMIT ?""",
                (before_id, before_id, limit + 1),
            ).fetchall()
            return AnalysisJobList(
                jobs=[self._read(connection, r[0]) for r in rows[:limit]],
                next_before_id=rows[limit - 1][0] if len(rows) > limit else None,
            )

    def _attempt(self, row) -> AnalysisAttempt:
        return AnalysisAttempt(
            id=row["id"],
            job_id=row["job_id"],
            position=row["position"],
            source=AnalysisSource.model_validate_json(row["source_json"]),
            first_seen_at=date(row["first_seen_at"]),
            status=row["status"],
            output=Understanding.model_validate_json(row["output_json"])
            if row["output_json"]
            else None,
            input=SavedInput.model_validate_json(row["input_json"])
            if row["input_json"]
            else None,
            input_fingerprint=row["input_fingerprint"],
            reused_from_attempt_id=row["reused_from_attempt_id"],
            attempted=bool(row["attempted"]),
            usage=TokenUsage.model_validate_json(row["usage_json"])
            if row["usage_json"]
            else None,
            error=SummaryFailure.model_validate_json(row["error_json"])
            if row["error_json"]
            else None,
            created_at=date(row["created_at"]),
            started_at=date(row["started_at"]),
            finished_at=date(row["finished_at"]),
        )

    def attempt(self, attempt_id) -> AnalysisAttempt:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_analysis_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise AnalysisError("content_analysis_not_found")
            return self._attempt(row)

    def items(
        self, job_id=None, *, result_id=None, limit=50, offset=0
    ) -> AnalysisAttemptList:
        with self.connection() as connection:
            if job_id is not None:
                self._require_job(connection, job_id)
                where, value, order = "job_id=?", job_id, "position"
            else:
                source_snapshot(connection, result_id)
                where, value, order = "content_id=?", result_id, "id DESC"
            total = connection.execute(
                f"SELECT COUNT(*) FROM content_analysis_attempts WHERE {where}",
                (value,),
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM content_analysis_attempts WHERE {where} ORDER BY
                  {order} LIMIT ? OFFSET ?""",
                (value, limit, offset),
            )
            return AnalysisAttemptList(
                items=[self._attempt(r) for r in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    def _replay(self, connection, payload):
        row = connection.execute(
            "SELECT * FROM content_analysis_requests WHERE request_id=?",
            (payload.request_id,),
        ).fetchone()
        if row is None:
            return None
        if row["intent_hash"] != fingerprint(payload.model_dump()):
            raise AnalysisError("content_analysis_request_conflict")
        return AnalysisAdmission(
            job=self._read(connection, row["job_id"]) if row["job_id"] else None,
            admitted_count=row["admitted_count"],
            already_active_count=row["already_active_count"],
        )

    def _workflow_replay(
        self, connection, payload: WorkflowAnalysisCreate, operation_key: str
    ):
        existing_origin = connection.execute(
            "SELECT id,request_id FROM content_analysis_jobs WHERE automatic_origin=?",
            (operation_key,),
        ).fetchone()
        request = connection.execute(
            "SELECT * FROM content_analysis_requests WHERE request_id=?",
            (payload.request_id,),
        ).fetchone()
        if request is None:
            # ``automatic_origin`` is the durable workflow-stage key.  The
            # service normally derives request_id from it, but the repository
            # must fail closed if a lower-level caller presents the same key
            # with a different (or missing) request proof instead of leaking
            # the UNIQUE constraint as a storage error.
            if existing_origin is not None:
                raise AnalysisError("content_analysis_request_conflict")
            return None
        if request["intent_hash"] != workflow_intent_hash(payload, operation_key):
            raise AnalysisError("content_analysis_request_conflict")
        if request["job_id"] is None:
            if existing_origin is not None:
                raise AnalysisError("content_analysis_request_conflict")
            return AnalysisAdmission(
                job=None,
                admitted_count=request["admitted_count"],
                already_active_count=request["already_active_count"],
            )
        replay = AnalysisAdmission(
            job=self._read(connection, request["job_id"]),
            admitted_count=request["admitted_count"],
            already_active_count=request["already_active_count"],
        )
        if replay.job.trigger != "automatic":
            raise AnalysisError("content_analysis_request_conflict")
        row = connection.execute(
            "SELECT request_id,trigger,automatic_origin "
            "FROM content_analysis_jobs WHERE id=?",
            (replay.job.id,),
        ).fetchone()
        if (
            row is None
            or row["request_id"] != payload.request_id
            or row["trigger"] != "automatic"
            or row["automatic_origin"] != operation_key
            or (existing_origin is not None and existing_origin["id"] != replay.job.id)
        ):
            raise AnalysisError("content_analysis_request_conflict")
        return replay

    def replay(self, payload: AnalysisCreate):
        with self.connection() as connection:
            return self._replay(connection, payload)

    def workflow_replay(self, payload: WorkflowAnalysisCreate, *, operation_key: str):
        with self.connection() as connection:
            return self._workflow_replay(connection, payload, operation_key)

    def create(self, payload: AnalysisCreate) -> AnalysisAdmission:
        with self.connection(write=True) as connection:
            replay = self._replay(connection, payload)
            if replay is not None:
                return replay
            initial_prompt = _resolve_prompt(
                connection,
                "initial",
                payload.initial_prompt,
                payload.initial_prompt_version_id,
                payload.initial_prompt_mode,
            )
            report_prompt = _resolve_prompt(
                connection,
                "report",
                payload.report_prompt,
                payload.report_prompt_version_id,
                payload.report_prompt_mode,
            )
            provider = self._provider(connection, payload.configuration_revision)
            connection.execute(
                "CREATE TEMP TABLE selected_contents(id INTEGER PRIMARY KEY)"
            )
            if payload.selection.kind == "all_never_started":
                connection.execute(
                    f"""INSERT INTO selected_contents SELECT content_id FROM
                      content_analysis_claims cl WHERE {NEVER_STARTED_SQL}"""
                )
                active = connection.execute(
                    """SELECT COUNT(*) FROM content_analysis_claims WHERE
                      active_job_id IS NOT NULL OR active_legacy_summary_id IS NOT
                      NULL"""
                ).fetchone()[0]
            else:
                active = 0
                for content_id in payload.selection.result_ids:
                    claim = connection.execute(
                        """SELECT cl.*,a.status AS latest_status FROM
                          content_analysis_claims cl
                      LEFT JOIN content_analysis_attempts a ON
                        a.id=cl.latest_attempt_id WHERE cl.content_id=?""",
                        (content_id,),
                    ).fetchone()
                    if claim is None:
                        raise AnalysisError("result_not_found")
                    if claim["active_job_id"] or claim["active_legacy_summary_id"]:
                        active += 1
                        continue
                    kind = payload.selection.kind
                    valid = (
                        (
                            kind == "explicit"
                            and claim["first_attempt_id"] is None
                            and claim["legacy_state"] is None
                        )
                        or (
                            kind == "retry"
                            and (
                                claim["latest_status"]
                                in (
                                    "input_incomplete",
                                    "unsupported",
                                    "failed",
                                    "cancelled",
                                    "interrupted",
                                )
                                or (
                                    claim["latest_status"] is None
                                    and claim["legacy_state"] == "legacy_attempted"
                                )
                            )
                        )
                        or (
                            kind == "reanalysis"
                            and (
                                claim["latest_status"] == "completed"
                                or (
                                    claim["latest_status"] is None
                                    and claim["legacy_state"] == "legacy_completed"
                                )
                            )
                        )
                    )
                    if not valid:
                        raise AnalysisError("content_analysis_selection_conflict")
                    connection.execute(
                        "INSERT INTO selected_contents VALUES (?)", (content_id,)
                    )
            result = self._admit(
                connection,
                provider,
                initial_prompt.version_id,
                report_prompt.version_id,
                initial_prompt.mode,
                report_prompt.mode,
                request_id=payload.request_id,
                force_refresh=payload.force_refresh,
                active=active,
            )
            connection.execute(
                "INSERT INTO content_analysis_requests VALUES (?,?,?,?,?)",
                (
                    payload.request_id,
                    fingerprint(payload.model_dump()),
                    result.job.id if result.job else None,
                    result.admitted_count,
                    result.already_active_count,
                ),
            )
            return result

    def workflow_create(
        self, payload: WorkflowAnalysisCreate, *, operation_key: str
    ) -> AnalysisAdmission:
        """Admit a mixed workflow membership without changing public selection rules.

        Automatic runs receive one frozen analysis job for their exact ordered
        membership.  A workflow membership may contain never-started,
        recoverable, completed, legacy-only and currently active sources at the
        same time; the public ``explicit`` selection intentionally cannot do
        that and remains unchanged.  Completed sources are admitted as queued
        attempts, allowing the normal cache/reuse path to copy their saved
        evidence without a model request.  Legacy-only sources are queued for
        the neutral-understanding contract instead of reinterpreting an old
        topic judgment.  Sources owned by another analysis path are frozen as
        unavailable attempts, so report coverage remains exact without taking
        a duplicate claim.

        All selection and claim writes happen in one transaction.  The
        operation UUID and intent hash are persisted using the same replay
        table as manual admissions, so an ambiguous workflow response cannot
        create another job or another claim.
        """
        with self.connection(write=True) as connection:
            replay = self._workflow_replay(connection, payload, operation_key)
            if replay is not None:
                return replay
            initial_prompt = _resolve_prompt(
                connection,
                "initial",
                payload.initial_prompt,
                payload.initial_prompt_version_id,
                payload.initial_prompt_mode,
            )
            report_prompt = _resolve_prompt(
                connection,
                "report",
                payload.report_prompt,
                payload.report_prompt_version_id,
                payload.report_prompt_mode,
            )
            provider = self._provider(connection, payload.configuration_revision)

            selections: list[tuple[int, int, bool]] = []
            active = 0
            for position, content_id in enumerate(payload.result_ids):
                claim = connection.execute(
                    """SELECT cl.*,a.status AS latest_status FROM
                         content_analysis_claims cl
                       LEFT JOIN content_analysis_attempts a ON
                         a.id=cl.latest_attempt_id
                       WHERE cl.content_id=?""",
                    (content_id,),
                ).fetchone()
                if claim is None:
                    raise AnalysisError("result_not_found")

                latest_status = claim["latest_status"]
                if (
                    claim["active_job_id"]
                    or claim["active_legacy_summary_id"]
                    or latest_status in ACTIVE_ATTEMPTS
                ):
                    # Keep exact workflow/report coverage, but never take a
                    # second claim while another owner is settling the source.
                    active += 1
                    selections.append((content_id, position, True))
                    continue

                valid = (
                    (latest_status is None and claim["first_attempt_id"] is None)
                    or latest_status == "completed"
                    or latest_status in WORKFLOW_RECOVERABLE_ATTEMPTS
                    or (
                        latest_status is None
                        and claim["legacy_state"]
                        in ("legacy_completed", "legacy_attempted")
                    )
                )
                if not valid:
                    raise AnalysisError("content_analysis_selection_conflict")
                selections.append((content_id, position, False))

            result = self._admit(
                connection,
                provider,
                initial_prompt.version_id,
                report_prompt.version_id,
                initial_prompt.mode,
                report_prompt.mode,
                request_id=payload.request_id,
                origin=operation_key,
                force_refresh=payload.force_refresh,
                active=active,
                selections=tuple(selections),
            )
            connection.execute(
                "INSERT INTO content_analysis_requests VALUES (?,?,?,?,?)",
                (
                    payload.request_id,
                    workflow_intent_hash(payload, operation_key),
                    result.job.id if result.job else None,
                    result.admitted_count,
                    result.already_active_count,
                ),
            )
            return result

    def _provider(self, connection, revision):
        row = connection.execute(
            "SELECT base_url,model,revision FROM ai_settings WHERE id=1"
        ).fetchone()
        if row is None:
            raise AIError("ai_configuration_required")
        if row["revision"] != revision:
            raise AIError("ai_configuration_changed")
        return row

    def _admit(
        self,
        connection,
        provider,
        initial_prompt_version_id,
        report_prompt_version_id,
        initial_prompt_mode,
        report_prompt_mode,
        *,
        request_id=None,
        origin=None,
        force_refresh=False,
        active=0,
        selections: tuple[tuple[int, int, bool], ...] | None = None,
    ):
        if selections is None:
            selections = tuple(
                (int(row[0]), position, False)
                for position, row in enumerate(
                    connection.execute("SELECT id FROM selected_contents ORDER BY id")
                )
            )
        admitted = sum(not unavailable for _, _, unavailable in selections)
        if not selections:
            return AnalysisAdmission(
                job=None, admitted_count=0, already_active_count=active
            )
        now = timestamp()
        job_id = connection.execute(
            """INSERT INTO content_analysis_jobs(request_id,trigger,automatic_origin,
          configuration_revision,base_url,model,initial_prompt_version_id,
          initial_prompt_mode,report_prompt_version_id,report_prompt_mode,
          force_refresh,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'queued',?)""",
            (
                request_id,
                "automatic" if origin else "manual",
                origin,
                provider["revision"],
                provider["base_url"],
                provider["model"],
                initial_prompt_version_id,
                initial_prompt_mode,
                report_prompt_version_id,
                report_prompt_mode,
                int(force_refresh),
                now,
            ),
        ).lastrowid
        prompt = read_prompt(connection, initial_prompt_version_id)
        for content_id, position, unavailable in selections:
            source, row = source_snapshot(connection, content_id)
            observation = observation_hash(source)
            cache_key = fingerprint(
                {
                    "observation": observation,
                    "prompt": prompt.content_hash,
                    "schema": prompt.schema_version,
                    "configuration_revision": provider["revision"],
                    "base_url": provider["base_url"],
                    "model": provider["model"],
                    "input": MODEL_INPUT_VERSION,
                    "extractor": f"{source.platform}-enrichment-v1",
                }
            )
            if unavailable:
                connection.execute(
                    """INSERT INTO content_analysis_attempts(
                      job_id,content_id,source_run_id,position,source_json,
                      first_seen_at,observation_hash,cache_key,error_json,status,
                      created_at,finished_at)
                      VALUES (?,?,?,?,?,?,?,?,?,'input_incomplete',?,?)""",
                    (
                        job_id,
                        content_id,
                        source.source_run_id,
                        position,
                        source.model_dump_json(),
                        row["first_seen_at"],
                        observation,
                        cache_key,
                        failure("acquisition", "source_active").model_dump_json(),
                        now,
                        now,
                    ),
                )
                continue
            attempt_id = connection.execute(
                """INSERT INTO content_analysis_attempts(
                  job_id,content_id,source_run_id,position,source_json,
                  first_seen_at,observation_hash,cache_key,status,created_at)
                  VALUES (?,?,?,?,?,?,?,?,'queued',?)""",
                (
                    job_id,
                    content_id,
                    source.source_run_id,
                    position,
                    source.model_dump_json(),
                    row["first_seen_at"],
                    observation,
                    cache_key,
                    now,
                ),
            ).lastrowid
            updated = connection.execute(
                """UPDATE content_analysis_claims SET active_job_id=?,
              first_attempt_id=COALESCE(first_attempt_id,?),latest_attempt_id=?
                WHERE content_id=?
              AND active_job_id IS NULL AND active_legacy_summary_id IS NULL""",
                (job_id, attempt_id, attempt_id, content_id),
            )
            if updated.rowcount != 1:
                raise AnalysisError("content_analysis_selection_conflict")
        return AnalysisAdmission(
            job=self._read(connection, job_id),
            admitted_count=admitted,
            already_active_count=active,
        )

    def collection_finished(
        self, kind: str, identity: int, *, available: bool
    ) -> AnalysisAdmission | None:
        """Called after browser release, never by GET/startup; preserve backlog."""
        with self.connection(write=True) as connection:
            if kind == "run":
                row = connection.execute(
                    "SELECT status FROM search_runs WHERE id=?", (identity,)
                ).fetchone()
                if row is None or row[0] in ("queued", "running", "cancelled"):
                    return None
                if connection.execute(
                    "SELECT 1 FROM search_batch_attempts WHERE search_run_id=?",
                    (identity,),
                ).fetchone():
                    return None
                origins = [identity]
            elif kind == "batch":
                row = connection.execute(
                    "SELECT status FROM search_batches WHERE id=?", (identity,)
                ).fetchone()
                if row is None or row[0] in (
                    "queued",
                    "running",
                    "paused_for_manual_action",
                    "cancelled",
                ):
                    return None
                origins = [
                    r[0]
                    for r in connection.execute(
                        """SELECT search_run_id FROM search_batch_attempts WHERE
                          batch_id=? ORDER BY search_run_id""",
                        (identity,),
                    )
                ]
            else:
                raise ValueError("invalid collection kind")
            origin = f"{kind}:{identity}"
            previous = connection.execute(
                "SELECT job_id FROM collection_analysis_handoffs WHERE origin=?",
                (origin,),
            ).fetchone()
            if previous is not None:
                return None
            if previous is None:
                connection.execute(
                    """INSERT INTO collection_analysis_handoffs(origin,created_at)
                      VALUES (?,?)""",
                    (origin, timestamp()),
                )
            for run_id in origins:
                connection.execute(
                    """UPDATE content_analysis_claims SET auto_ready=1 WHERE
                      eligibility_origin='new' AND discovery_run_id=?""",
                    (run_id,),
                )
            # Recover the crash between a collector's terminal commit and its
            # callback, only on a later ordinary collection completion. Startup,
            # old history and failed/interrupted analysis remain excluded.
            connection.execute("""UPDATE content_analysis_claims SET auto_ready=1
              WHERE eligibility_origin='new' AND auto_ready=0 AND EXISTS (
                SELECT 1 FROM search_runs r WHERE r.id=discovery_run_id
                  AND r.status NOT IN ('queued','running','cancelled')
                  AND NOT EXISTS (SELECT 1 FROM search_batch_attempts a
                    JOIN search_batches b ON b.id=a.batch_id
                    WHERE a.search_run_id=r.id AND b.status IN
                      ('queued','running','paused_for_manual_action','cancelled')))
            """)
            settings = connection.execute(
                "SELECT * FROM analysis_settings WHERE id=1"
            ).fetchone()
            if not available or not settings["enabled"]:
                return None
            try:
                provider = self._provider(
                    connection, settings["approved_configuration_revision"]
                )
            except AIError:
                # Durable candidates remain visible; never use a new destination.
                return None
            # The settings row retains historical foreign keys for old
            # records, but it is no longer the source of the product defaults.
            # Resolve both fixed templates here so a stale/legacy pointer can
            # never change a newly admitted automatic job.
            initial_prompt = resolve_prompt_choice(connection, "initial", None)
            report_prompt = resolve_prompt_choice(connection, "report", None)
            connection.execute(
                "CREATE TEMP TABLE selected_contents(id INTEGER PRIMARY KEY)"
            )
            connection.execute(f"""INSERT INTO selected_contents
              SELECT content_id FROM content_analysis_claims cl
              WHERE {NEVER_STARTED_SQL} AND eligibility_origin='new' AND
                auto_ready=1""")
            result = self._admit(
                connection,
                provider,
                initial_prompt.version_id,
                report_prompt.version_id,
                initial_prompt.mode,
                report_prompt.mode,
                origin=origin,
            )
            if result.job:
                connection.execute(
                    "UPDATE collection_analysis_handoffs SET job_id=? WHERE origin=?",
                    (result.job.id, origin),
                )
            return result

    def next_job(self) -> AnalysisJob | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT j.id FROM content_analysis_jobs j WHERE j.status IN
                  ('queued','running') AND NOT EXISTS(SELECT 1 FROM report_generations g
                  WHERE g.analysis_job_id=j.id
                  AND (g.pause_reason IS NOT NULL OR g.status!='summarising'))
                  ORDER BY COALESCE(j.queue_reason='browser_operation_active',0),j.id
                  LIMIT 1"""
            ).fetchone()
            return self._read(connection, row[0]) if row else None

    def is_report_generation(self, job_id: int) -> bool:
        with self.connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM report_generations WHERE analysis_job_id=?",
                    (job_id,),
                ).fetchone()
                is not None
            )

    def next_attempt(self, job_id) -> AnalysisAttempt | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM content_analysis_attempts WHERE job_id=? AND
                  status='queued' ORDER BY position LIMIT 1""",
                (job_id,),
            ).fetchone()
            return self._attempt(row) if row else None

    def queue(self, job_id, reason) -> None:
        with self.connection(write=True) as connection:
            if reason == "browser_operation_active":
                connection.execute(
                    """UPDATE content_analysis_attempts SET status='queued'
                    WHERE job_id=? AND status='acquiring'""",
                    (job_id,),
                )
            connection.execute(
                """UPDATE content_analysis_jobs SET queue_reason=? WHERE id=? AND
                  status IN ('queued','running')""",
                (reason, job_id),
            )

    def start(self, job_id) -> None:
        with self.connection(write=True) as connection:
            connection.execute(
                """UPDATE content_analysis_jobs SET
                  status='running',started_at=COALESCE(started_at,?),queue_reason=NULL
                  WHERE id=? AND status IN ('queued','running')""",
                (timestamp(), job_id),
            )

    def _active(self, connection, attempt_id):
        row = connection.execute(
            """SELECT a.* FROM content_analysis_attempts a JOIN
              content_analysis_jobs j ON j.id=a.job_id
          JOIN content_analysis_claims cl ON cl.content_id=a.content_id AND
            cl.active_job_id=a.job_id AND cl.latest_attempt_id=a.id
          WHERE a.id=? AND j.status IN ('queued','running') AND a.status IN
            ('queued','acquiring','analysing')""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise AnalysisError("content_analysis_selection_conflict")
        return row

    def begin(self, attempt_id):
        with self.connection(write=True) as connection:
            row = self._active(connection, attempt_id)
            if row["status"] != "queued":
                raise AnalysisError("content_analysis_selection_conflict")
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  status='acquiring',started_at=? WHERE id=?""",
                (timestamp(), attempt_id),
            )

    def save_input(self, attempt_id, content: SavedInput, input_fingerprint):
        with self.connection(write=True) as connection:
            row = self._active(connection, attempt_id)
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  input_json=?,input_fingerprint=? WHERE id=?""",
                (content.model_dump_json(), input_fingerprint, attempt_id),
            )
            if input_fingerprint is not None:
                connection.execute(
                    """UPDATE content_analysis_claims SET known_input_fingerprint=?
                      WHERE content_id=?""",
                    (input_fingerprint, row["content_id"]),
                )

    def mark_attempt(self, attempt_id):
        with self.connection(write=True) as connection:
            row = self._active(connection, attempt_id)
            if row["attempted"] or row["status"] != "acquiring":
                raise AnalysisError("content_analysis_selection_conflict")
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  status='analysing',attempted=1 WHERE id=?""",
                (attempt_id,),
            )

    def finish_attempt(
        self, attempt_id, status, *, output=None, error=None, usage=None
    ):
        if status in ACTIVE_ATTEMPTS:
            raise ValueError("terminal status required")
        with self.connection(write=True) as connection:
            self._active(connection, attempt_id)
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  status=?,output_json=?,error_json=?,usage_json=?,finished_at=?
                  WHERE id=?""",
                (
                    status,
                    output.model_dump_json() if output else None,
                    error.model_dump_json() if error else None,
                    usage.model_dump_json() if usage else None,
                    timestamp(),
                    attempt_id,
                ),
            )

    def reuse(self, attempt_id) -> bool:
        with self.connection(write=True) as connection:
            row = self._active(connection, attempt_id)
            current_source, _ = source_snapshot(connection, row["content_id"])
            if observation_hash(current_source) != row["observation_hash"]:
                return False
            cached = connection.execute(
                """SELECT a.* FROM content_analysis_attempts a
              JOIN content_analysis_claims cl ON cl.content_id=a.content_id
              WHERE a.cache_key=? AND a.id<? AND a.status='completed' AND
                a.reused_from_attempt_id IS NULL
                AND a.input_fingerprint=cl.known_input_fingerprint ORDER BY a.id
                  DESC LIMIT 1""",
                (row["cache_key"], attempt_id),
            ).fetchone()
            if cached is None:
                return False
            validated = self._attempt(cached)
            accepted_extractors = {
                f"{validated.source.platform}-enrichment-v1",
                f"{validated.source.platform}-search-preview-v1",
            }
            if (
                validated.input is None
                or not validated.input.analysis_eligible
                or validated.input.extractor_version not in accepted_extractors
            ):
                return False
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  status='completed',input_json=?,input_fingerprint=?,
              output_json=?,reused_from_attempt_id=?,started_at=?,finished_at=?
                WHERE id=?""",
                (
                    cached["input_json"],
                    cached["input_fingerprint"],
                    cached["output_json"],
                    cached["id"],
                    timestamp(),
                    timestamp(),
                    attempt_id,
                ),
            )
            return True

    def _finish(self, connection, job_id, status):
        row = self._require_job(connection, job_id)
        if row["status"] not in ("queued", "running"):
            return
        now = timestamp()
        if status == "completed":
            if connection.execute(
                """SELECT 1 FROM content_analysis_attempts WHERE job_id=? AND status
                  IN ('queued','acquiring','analysing')""",
                (job_id,),
            ).fetchone():
                raise AnalysisError("content_analysis_selection_conflict")
        else:
            terminal = "cancelled" if status == "cancelled" else "interrupted"
            connection.execute(
                """UPDATE content_analysis_attempts SET
                  status=?,error_json=?,finished_at=?
              WHERE job_id=? AND status IN ('queued','acquiring','analysing')""",
                (
                    terminal,
                    failure("execution", terminal).model_dump_json(),
                    now,
                    job_id,
                ),
            )
        connection.execute(
            """UPDATE content_analysis_jobs SET
              status=?,finished_at=?,queue_reason=NULL WHERE id=?""",
            (status, now, job_id),
        )
        connection.execute(
            """UPDATE content_analysis_claims SET active_job_id=NULL WHERE
              active_job_id=?""",
            (job_id,),
        )
        if status == "completed":
            connection.execute(
                """INSERT INTO analysis_completion_events(job_id,settled_at) VALUES
                  (?,?)""",
                (job_id, now),
            )

    def finish(self, job_id, status):
        with self.connection(write=True) as connection:
            self._finish(connection, job_id, status)

    def completion_events(self, *, after_id=0, limit=100):
        with self.connection() as connection:
            events = []
            for row in connection.execute(
                """SELECT * FROM analysis_completion_events WHERE id>? ORDER BY id
                  LIMIT ?""",
                (after_id, limit),
            ):
                job = self._read(connection, row["job_id"])
                successful = [
                    r[0]
                    for r in connection.execute(
                        """SELECT id FROM content_analysis_attempts WHERE job_id=?
                          AND status='completed' ORDER BY position""",
                        (job.id,),
                    )
                ]
                events.append(
                    {
                        "id": row["id"],
                        "job": job,
                        "settled_at": date(row["settled_at"]),
                        "state": row["state"],
                        "successful_attempt_ids": successful,
                    }
                )
            return events
