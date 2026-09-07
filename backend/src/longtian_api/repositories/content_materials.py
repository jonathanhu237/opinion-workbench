"""Persist acquired content independently of a model attempt."""

from longtian_api.repositories.analysis_shared import (
    AnalysisRepository,
    source_snapshot,
    timestamp,
)
from longtian_api.repositories.content_analyses import observation_hash
from longtian_api.schemas.analysis_evidence import SavedInput
from longtian_api.services.ai_analysis import MODEL_INPUT_VERSION
from longtian_api.services.analysis_errors import AnalysisError
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    evidence_fingerprint,
)


class ContentMaterialRepository(AnalysisRepository):
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
