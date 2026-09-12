"""Persist acquired content independently of a model attempt."""

from opinion_workbench_api.repositories.analysis_shared import (
    AnalysisRepository,
    source_snapshot,
    timestamp,
)
from opinion_workbench_api.repositories.content_analyses import observation_hash
from opinion_workbench_api.schemas.analysis_evidence import SavedInput
from opinion_workbench_api.services.ai_analysis import MODEL_INPUT_VERSION
from opinion_workbench_api.services.analysis_errors import AnalysisError
from opinion_workbench_api.services.enrichment_models import (
    EnrichedContent,
    evidence_fingerprint,
)


class ContentMaterialRepository(AnalysisRepository):
    def material(self, attempt):
        """Read saved source content without touching media storage."""

        if attempt.input_fingerprint is None:
            return None
        with self.connection() as connection:
            row = connection.execute(
                """SELECT content_json FROM content_materials
                WHERE content_id=? AND input_fingerprint=?""",
                (attempt.source.result_id, attempt.input_fingerprint),
            ).fetchone()
        return (
            EnrichedContent.model_validate_json(row[0])
            if row is not None and row[0]
            else None
        )

    def save(self, content_id: int, content: EnrichedContent):
        content = EnrichedContent.model_validate(content.model_dump())
        with self.connection(write=True) as connection:
            source, _ = source_snapshot(connection, content_id)
            if (content.platform, content.content_id, content.content_url) != (
                source.platform,
                source.platform_content_id,
                source.content_url,
            ):
                raise AnalysisError("content_analysis_selection_conflict")
            digest = evidence_fingerprint(content)
            connection.execute(
                """INSERT INTO content_materials
                (content_id,observation_hash,input_json,input_fingerprint,saved_at,
                 content_json,analysis_input_version) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(content_id) DO UPDATE SET
                observation_hash=excluded.observation_hash,input_json=excluded.input_json,
                input_fingerprint=excluded.input_fingerprint,saved_at=excluded.saved_at,
                content_json=excluded.content_json,
                analysis_input_version=excluded.analysis_input_version""",
                (
                    content_id,
                    observation_hash(source),
                    SavedInput.from_content(content).model_dump_json(),
                    digest,
                    timestamp(),
                    content.model_dump_json(),
                    MODEL_INPUT_VERSION,
                ),
            )
            connection.execute(
                """UPDATE content_analysis_claims SET
                known_input_fingerprint=? WHERE content_id=?""",
                (digest, content_id),
            )
