"""Read-only global projections; never derive analysis eligibility from cache misses."""

from pydantic import ValidationError

from opinion_workbench_api.repositories.analysis_shared import (
    AnalysisRepository,
    date,
    source_snapshot,
)
from opinion_workbench_api.schemas.analysis_evidence import SavedInput
from opinion_workbench_api.schemas.results import (
    LegacyAnalysis,
    LegacyAnalysisList,
    Result,
    ResultList,
    ResultMaterial,
    ResultOrigin,
    ResultOriginList,
)
from opinion_workbench_api.services.enrichment_models import EnrichedContent

NEVER_STARTED_SQL = """cl.first_attempt_id IS NULL AND cl.legacy_state IS NULL
    AND cl.active_job_id IS NULL AND cl.active_legacy_summary_id IS NULL"""
STATE_SQL = """CASE WHEN cl.active_legacy_summary_id IS NOT NULL THEN 'queued'
  WHEN a.status IS NOT NULL THEN a.status
  WHEN cl.legacy_state IS NOT NULL THEN cl.legacy_state
  WHEN cl.eligibility_origin='new' THEN 'pending_new' ELSE 'never_started' END"""
FROM_SQL = """FROM search_contents c
    JOIN content_analysis_claims cl ON cl.content_id=c.id
    LEFT JOIN content_analysis_attempts a ON a.id=cl.latest_attempt_id"""


class ResultsRepository(AnalysisRepository):
    @staticmethod
    def _fallback_material(source) -> ResultMaterial:
        return ResultMaterial(
            text_available=bool(source.title.strip() or source.snippet.strip()),
            image_count=0,
            video_count=0,
            inventory_complete=False,
            missing=False,
        )

    def _material(self, connection, content_id, source) -> ResultMaterial:
        row = connection.execute(
            """SELECT content_json,input_json FROM content_materials
            WHERE content_id=?""",
            (content_id,),
        ).fetchone()
        if row is None:
            return self._fallback_material(source)
        payload = row["content_json"] or row["input_json"]
        if not payload:
            return self._fallback_material(source)
        try:
            value = EnrichedContent.model_validate_json(payload)
            text_available = bool(value.text.title.strip() or value.text.body.strip())
            image_count = sum(asset.kind == "image" for asset in value.assets)
            video_count = sum(asset.kind == "video" for asset in value.assets)
            missing = (
                not text_available
                or any(asset.status != "ready" for asset in value.assets)
                or any(issue.code != "inventory_unknown" for issue in value.issues)
            )
            return ResultMaterial(
                text_available=text_available,
                image_count=image_count,
                video_count=video_count,
                inventory_complete=value.media_inventory_complete,
                missing=missing,
            )
        except (ValidationError, ValueError, TypeError):
            pass
        try:
            value = SavedInput.model_validate_json(payload)
        except (ValidationError, ValueError, TypeError):
            return self._fallback_material(source)
        text_available = bool(value.text.title.strip() or value.text.body.strip())
        image_count = sum(asset.kind == "image" for asset in value.assets)
        video_count = sum(asset.kind == "video" for asset in value.assets)
        return ResultMaterial(
            text_available=text_available,
            image_count=image_count,
            video_count=video_count,
            inventory_complete=value.media_inventory_complete,
            missing=not text_available
            or any(asset.status != "ready" for asset in value.assets)
            or any(issue != "inventory_unknown" for issue in value.issues),
        )

    def _read(self, connection, result_id) -> Result:
        source, content = source_snapshot(connection, result_id)
        row = connection.execute(
            f"""SELECT cl.latest_attempt_id,cl.active_job_id,{STATE_SQL} AS state,
              (SELECT COUNT(*) FROM search_run_contents WHERE
                search_content_id=c.id) AS origins,
              (SELECT COUNT(*) FROM ai_summary_items WHERE content_id=c.id) AS
                legacy_count
              {FROM_SQL} WHERE c.id=?""",
            (result_id,),
        ).fetchone()
        return Result(
            id=result_id,
            source=source,
            first_seen_at=date(content["first_seen_at"]),
            last_seen_at=date(content["last_seen_at"]),
            origin_count=row["origins"],
            analysis_state=row["state"],
            latest_attempt_id=row["latest_attempt_id"],
            active_job_id=row["active_job_id"],
            legacy_count=row["legacy_count"],
            material=self._material(connection, result_id, source),
        )

    def read(self, result_id: int) -> Result:
        with self.connection() as connection:
            return self._read(connection, result_id)

    def list(
        self,
        *,
        limit=50,
        offset=0,
        platform=None,
        state=None,
        first_seen_from=None,
        first_seen_to=None,
    ) -> ResultList:
        clauses, params = [], []
        for clause, value in (
            ("c.platform=?", platform),
            (f"({STATE_SQL})=?", state),
            ("c.first_seen_at>=?", first_seen_from),
            ("c.first_seen_at<?", first_seen_to),
        ):
            if value is not None:
                clauses.append(clause)
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) {FROM_SQL}{where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT c.id {FROM_SQL}{where} ORDER BY c.id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            items = [self._read(connection, row[0]) for row in rows]
            eligible = connection.execute(
                f"""SELECT COUNT(*) FROM content_analysis_claims cl WHERE
                  {NEVER_STARTED_SQL}"""
            ).fetchone()[0]
            active = connection.execute(
                """SELECT COUNT(*) FROM content_analysis_claims WHERE active_job_id
                  IS NOT NULL OR active_legacy_summary_id IS NOT NULL"""
            ).fetchone()[0]
            return ResultList(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
                eligible_count=eligible,
                active_count=active,
            )

    def origins(self, result_id, *, limit=50, offset=0) -> ResultOriginList:
        with self.connection() as connection:
            self._read(connection, result_id)
            total = connection.execute(
                "SELECT COUNT(*) FROM search_run_contents WHERE search_content_id=?",
                (result_id,),
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT l.*,r.rule_name,r.status FROM search_run_contents l
              JOIN search_runs r ON r.id=l.run_id WHERE l.search_content_id=? ORDER
                BY l.run_id LIMIT ? OFFSET ?""",
                (result_id, limit, offset),
            )
            items = []
            for row in rows:
                terms = [
                    r[0]
                    for r in connection.execute(
                        """SELECT t.value FROM search_run_content_terms m
                  JOIN search_run_terms t ON t.run_id=m.run_id AND
                    t.position=m.term_position
                  WHERE m.run_id=? AND m.search_content_id=? ORDER BY
                    m.term_position""",
                        (row["run_id"], result_id),
                    )
                ]
                items.append(
                    ResultOrigin(
                        source_run_id=row["run_id"],
                        rule_name=row["rule_name"],
                        status=row["status"],
                        discovery_kind=row["discovery_kind"],
                        matched_terms=terms,
                        first_observed_at=date(row["first_observed_at"]),
                        last_observed_at=date(row["last_observed_at"]),
                    )
                )
            return ResultOriginList(
                items=items, total=total, limit=limit, offset=offset
            )

    def legacy(self, result_id, *, limit=50, offset=0) -> LegacyAnalysisList:
        with self.connection() as connection:
            self._read(connection, result_id)
            total = connection.execute(
                "SELECT COUNT(*) FROM ai_summary_items WHERE content_id=?", (result_id,)
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT
                  i.*,r.source_run_id,COALESCE(i.decision,canonical.decision) AS
                  resolved_decision
              FROM ai_summary_items i JOIN ai_summary_runs r ON r.id=i.summary_run_id
              LEFT JOIN ai_summary_items canonical ON canonical.id=i.reused_from_item_id
              WHERE i.content_id=? ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                (result_id, limit, offset),
            )
            return LegacyAnalysisList(
                items=[
                    LegacyAnalysis(
                        summary_id=r["summary_run_id"],
                        source_run_id=r["source_run_id"],
                        item_id=r["id"],
                        status=r["status"],
                        decision=r["resolved_decision"],
                        reused_from_item_id=r["reused_from_item_id"],
                    )
                    for r in rows
                ],
                total=total,
                limit=limit,
                offset=offset,
            )
