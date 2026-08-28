"""Durable text/coverage metadata shared by legacy and independent analyses."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from longtian_api.schemas.ai_summaries import StrictModel, SummarySource
from longtian_api.schemas.analysis_settings import PositiveId
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    EnrichmentText,
    IssueCode,
    MediaMime,
    Modality,
)


class AnalysisSource(SummarySource):
    """JS-safe identities without rewriting the historical legacy contract."""

    source_run_id: PositiveId
    result_id: PositiveId


class SavedAsset(StrictModel):
    position: int = Field(ge=0, le=24)
    kind: Literal["image", "video"]
    status: Literal["ready", "unavailable", "unsupported", "failed"]
    sha256: str | None
    mime_type: MediaMime | None
    byte_size: int | None
    width: int | None
    height: int | None
    duration_ms: int | None
    audio_track: Literal["present", "absent", "unknown", "not_applicable"]
    coverage: Literal["complete", "partial", "unknown"]
    issue_code: IssueCode | None


class SavedInput(StrictModel):
    """No blob handles, filesystem paths, download locators or media bytes."""

    schema_version: Literal[1]
    extractor_version: str
    acquired_at: int
    status: Literal["ready", "partial", "unavailable", "unsupported"]
    text: EnrichmentText
    detected_modalities: list[Modality]
    media_inventory_complete: bool
    assets: list[SavedAsset]
    issues: list[IssueCode]

    @classmethod
    def from_content(cls, content: EnrichedContent) -> SavedInput:
        return cls(
            schema_version=content.schema_version,
            extractor_version=content.extractor_version,
            acquired_at=content.acquired_at,
            status=content.status,
            text=content.text,
            detected_modalities=content.detected_modalities,
            media_inventory_complete=content.media_inventory_complete,
            assets=[
                SavedAsset.model_validate(
                    asset.model_dump(exclude={"asset_id", "blob_ref", "role"})
                )
                for asset in content.assets
            ],
            issues=list(dict.fromkeys(issue.code for issue in content.issues)),
        )
