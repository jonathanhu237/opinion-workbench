"""Durable text/coverage metadata shared by legacy and independent analyses."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from opinion_workbench_api.schemas.ai_summaries import StrictModel, SummarySource
from opinion_workbench_api.schemas.analysis_settings import PositiveId
from opinion_workbench_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform
from opinion_workbench_api.services.enrichment_models import (
    MAX_MEDIA_BYTES,
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
    sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: MediaMime | None
    byte_size: int | None = Field(ge=1, le=MAX_MEDIA_BYTES)
    width: int | None = Field(ge=1, le=32_768)
    height: int | None = Field(ge=1, le=32_768)
    duration_ms: int | None = Field(ge=1, le=2**53 - 1)
    audio_track: Literal["present", "absent", "unknown", "not_applicable"]
    coverage: Literal["complete", "partial", "unknown"]
    issue_code: IssueCode | None

    @model_validator(mode="after")
    def validate_asset(self) -> SavedAsset:
        if self.status == "ready":
            if (
                self.sha256 is None
                or self.mime_type is None
                or self.byte_size is None
                or self.width is None
                or self.height is None
                or self.coverage != "complete"
                or self.issue_code is not None
            ):
                raise ValueError("invalid ready saved asset")
            if self.kind == "image":
                if (
                    not self.mime_type.startswith("image/")
                    or self.duration_ms is not None
                    or self.audio_track != "not_applicable"
                    or self.width * self.height > 40_000_000
                ):
                    raise ValueError("invalid ready saved image")
            elif (
                self.mime_type != "video/mp4"
                or self.duration_ms is None
                or self.audio_track != "present"
            ):
                raise ValueError("invalid ready saved video")
        elif (
            any(
                value is not None
                for value in (
                    self.sha256,
                    self.mime_type,
                    self.byte_size,
                    self.width,
                    self.height,
                    self.duration_ms,
                )
            )
            or self.coverage != "unknown"
            or self.issue_code is None
            or self.audio_track
            != ("not_applicable" if self.kind == "image" else "unknown")
        ):
            raise ValueError("invalid unavailable saved asset")
        return self


class EvidenceModalityCoverage(StrictModel):
    """Bounded counts for one modality in the evidence bundle.

    ``expected`` is the number the extractor could enumerate.  ``unknown`` is
    deliberately separate: an extractor that cannot prove an exhaustive
    inventory must not turn that uncertainty into a zero.
    """

    expected: int = Field(ge=0, le=25)
    ready: int = Field(ge=0, le=25)
    failed: int = Field(ge=0, le=25)
    unknown: int = Field(ge=0, le=25)

    @model_validator(mode="after")
    def reconciles(self) -> EvidenceModalityCoverage:
        if self.ready + self.failed > self.expected:
            raise ValueError("invalid modality coverage")
        return self


EvidenceLevel = Literal[
    "search_preview", "detail_text", "validated_media", "full_source"
]
TextOrigin = Literal["search_preview", "detail"]


class EvidenceCoverage(StrictModel):
    """Versioned, truthful coverage for the input sent to the model."""

    schema_version: Literal["evidence-coverage-v1"]
    input_contract_version: Literal["analysis-evidence-v2"]
    level: EvidenceLevel
    text_origin: TextOrigin
    text_available: bool
    text_complete: bool
    text: EvidenceModalityCoverage
    image: EvidenceModalityCoverage
    video: EvidenceModalityCoverage
    audio: EvidenceModalityCoverage
    issues: list[IssueCode] = Field(max_length=32)

    @model_validator(mode="after")
    def consistent(self) -> EvidenceCoverage:
        text_ready = 1 if self.text_available else 0
        text_failed = 0 if self.text_available else 1
        if (
            self.text.expected != 1
            or self.text.ready != text_ready
            or self.text.failed != text_failed
            or self.text.unknown != 0
            or (not self.text_available and self.text_complete)
            or len(set(self.issues)) != len(self.issues)
        ):
            raise ValueError("invalid text evidence coverage")
        if self.text_origin == "search_preview":
            if (
                self.level != "search_preview"
                or self.text_complete
                or any(
                    modality
                    != EvidenceModalityCoverage(
                        expected=0, ready=0, failed=0, unknown=1
                    )
                    for modality in (self.image, self.video, self.audio)
                )
            ):
                raise ValueError("invalid search preview coverage")
        elif self.level == "full_source" and (
            not self.text_available
            or not self.text_complete
            or self.issues
            or any(
                modality.unknown > 0
                or modality.failed > 0
                or modality.ready != modality.expected
                for modality in (self.image, self.video, self.audio)
            )
        ):
            raise ValueError("invalid full source coverage")
        if self.level == "detail_text" and (
            self.text_origin != "detail" or not self.text_available
        ):
            raise ValueError("invalid detail text coverage")
        if self.level == "validated_media" and not any(
            modality.ready > 0 for modality in (self.image, self.video, self.audio)
        ):
            raise ValueError("invalid validated media coverage")
        return self

    @property
    def analysis_eligible(self) -> bool:
        """Whether at least one non-empty, trustworthy evidence item exists."""

        return self.text.ready > 0 or any(
            modality.ready > 0 for modality in (self.image, self.video, self.audio)
        )

    @classmethod
    def from_content(cls, content: EnrichedContent) -> EvidenceCoverage:
        ready_assets = [asset for asset in content.assets if asset.status == "ready"]
        text_available = bool(content.text.title.strip() or content.text.body.strip())
        text = EvidenceModalityCoverage(
            expected=1,
            ready=1 if text_available else 0,
            failed=0 if text_available else 1,
            unknown=0,
        )

        def asset_coverage(kind: Literal["image", "video"]) -> EvidenceModalityCoverage:
            expected = sum(asset.kind == kind for asset in content.assets)
            ready = sum(
                asset.kind == kind and asset.status == "ready"
                for asset in content.assets
            )
            failed = expected - ready
            # An unknown inventory means that there may be additional assets
            # beyond the candidates the adapter exposed.
            unknown = 1 if not content.media_inventory_complete else 0
            return EvidenceModalityCoverage(
                expected=expected,
                ready=ready,
                failed=failed,
                unknown=unknown,
            )

        image = asset_coverage("image")
        video = asset_coverage("video")
        audio = EvidenceModalityCoverage(
            expected=video.expected,
            ready=sum(
                asset.kind == "video"
                and asset.status == "ready"
                and asset.audio_track == "present"
                for asset in content.assets
            ),
            failed=sum(
                asset.kind == "video"
                and (asset.status != "ready" or asset.audio_track != "present")
                for asset in content.assets
            ),
            unknown=(1 if not content.media_inventory_complete else 0)
            + sum(
                asset.kind == "video"
                and asset.status == "ready"
                and asset.audio_track == "unknown"
                for asset in content.assets
            ),
        )
        issues = list(dict.fromkeys(issue.code for issue in content.issues))
        if content.text.coverage != "complete" and not any(
            code in issues
            for code in ("text_incomplete", "text_unavailable", "text_limit")
        ):
            issues.append("text_incomplete")
        if not content.media_inventory_complete and "inventory_unknown" not in issues:
            issues.append("inventory_unknown")
        if content.status != "ready" and not issues:
            issues = ["text_incomplete"]
        if content.status == "ready" and text_available:
            level: EvidenceLevel = "full_source"
        elif text_available and content.extractor_version.endswith("-enrichment-v1"):
            level = "detail_text"
        elif ready_assets:
            level = "validated_media"
        else:
            level = "search_preview"
        return cls(
            schema_version="evidence-coverage-v1",
            input_contract_version="analysis-evidence-v2",
            level=level,
            text_origin="detail",
            text_available=text_available,
            text_complete=text_available and content.text.coverage == "complete",
            text=text,
            image=image,
            video=video,
            audio=audio,
            issues=issues,
        )

    @classmethod
    def from_text(cls, content: EnrichedContent) -> EvidenceCoverage:
        """Project detail evidence into the text-only model input contract."""
        text_available = bool(content.text.title.strip() or content.text.body.strip())
        issues = list(
            dict.fromkeys(
                issue.code
                for issue in content.issues
                if issue.code in {"text_incomplete", "text_unavailable", "text_limit"}
            )
        )
        if content.text.coverage != "complete" and not issues:
            issues = ["text_unavailable" if not text_available else "text_incomplete"]
        return cls(
            schema_version="evidence-coverage-v1",
            input_contract_version="analysis-evidence-v2",
            level="detail_text" if text_available else "search_preview",
            text_origin="detail",
            text_available=text_available,
            text_complete=text_available and content.text.coverage == "complete",
            text=EvidenceModalityCoverage(
                expected=1,
                ready=1 if text_available else 0,
                failed=0 if text_available else 1,
                unknown=0,
            ),
            image=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=0),
            video=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=0),
            audio=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=0),
            issues=issues,
        )

    @classmethod
    def from_preview(
        cls, *, title: str, snippet: str, issues: Iterable[IssueCode] = ()
    ) -> EvidenceCoverage:
        text_available = bool(title.strip() or snippet.strip())
        normalized_issues = list(dict.fromkeys(issues))
        if "text_incomplete" not in normalized_issues:
            normalized_issues.append("text_incomplete")
        if "inventory_unknown" not in normalized_issues:
            normalized_issues.append("inventory_unknown")
        return cls(
            schema_version="evidence-coverage-v1",
            input_contract_version="analysis-evidence-v2",
            level="search_preview",
            text_origin="search_preview",
            text_available=text_available,
            text_complete=False,
            text=EvidenceModalityCoverage(
                expected=1,
                ready=1 if text_available else 0,
                failed=0 if text_available else 1,
                unknown=0,
            ),
            image=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=1),
            video=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=1),
            audio=EvidenceModalityCoverage(expected=0, ready=0, failed=0, unknown=1),
            issues=normalized_issues,
        )

    @classmethod
    def from_saved_input(cls, value: object) -> EvidenceCoverage:
        """Conservatively derive coverage for a pre-v2 saved input row."""

        text = value.text
        text_available = bool(text.title.strip() or text.body.strip())
        assets = value.assets
        image_expected = sum(asset.kind == "image" for asset in assets)
        video_expected = sum(asset.kind == "video" for asset in assets)
        image_ready = sum(
            asset.kind == "image" and asset.status == "ready" for asset in assets
        )
        video_ready = sum(
            asset.kind == "video" and asset.status == "ready" for asset in assets
        )
        inventory_unknown = not value.media_inventory_complete
        issues = list(dict.fromkeys(value.issues))
        if text.coverage != "complete" and not any(
            code in issues
            for code in ("text_incomplete", "text_unavailable", "text_limit")
        ):
            issues.append("text_incomplete")
        if inventory_unknown and "inventory_unknown" not in issues:
            issues.append("inventory_unknown")
        if value.status == "ready" and text_available:
            level: EvidenceLevel = "full_source"
        elif value.extractor_version.endswith("-enrichment-v1") and text_available:
            level = "detail_text"
        elif image_ready or video_ready:
            level = "validated_media"
        else:
            level = "search_preview"
        return cls(
            schema_version="evidence-coverage-v1",
            input_contract_version="analysis-evidence-v2",
            level=level,
            text_origin=(
                "detail"
                if value.extractor_version.endswith("-enrichment-v1")
                else "search_preview"
            ),
            text_available=text_available,
            text_complete=text_available and text.coverage == "complete",
            text=EvidenceModalityCoverage(
                expected=1,
                ready=1 if text_available else 0,
                failed=0 if text_available else 1,
                unknown=0,
            ),
            image=EvidenceModalityCoverage(
                expected=image_expected,
                ready=image_ready,
                failed=image_expected - image_ready,
                unknown=1 if inventory_unknown else 0,
            ),
            video=EvidenceModalityCoverage(
                expected=video_expected,
                ready=video_ready,
                failed=video_expected - video_ready,
                unknown=1 if inventory_unknown else 0,
            ),
            audio=EvidenceModalityCoverage(
                expected=video_expected,
                ready=sum(
                    asset.kind == "video"
                    and asset.status == "ready"
                    and asset.audio_track == "present"
                    for asset in assets
                ),
                failed=sum(
                    asset.kind == "video"
                    and (asset.status != "ready" or asset.audio_track != "present")
                    for asset in assets
                ),
                unknown=(1 if inventory_unknown else 0)
                + sum(
                    asset.kind == "video"
                    and asset.status == "ready"
                    and asset.audio_track == "unknown"
                    for asset in assets
                ),
            ),
            issues=issues,
        )


class SavedInput(StrictModel):
    """No blob handles, filesystem paths, download locators or media bytes."""

    schema_version: Literal[1]
    extractor_version: str = Field(min_length=1, max_length=200)
    acquired_at: int = Field(ge=1_000_000_000_000, le=9_999_999_999_999)
    status: Literal["ready", "partial", "unavailable", "unsupported"]
    text: EnrichmentText
    detected_modalities: list[Modality]
    media_inventory_complete: bool
    assets: list[SavedAsset]
    issues: list[IssueCode]
    # Optional keeps rows written by the pre-v2 application readable.  New
    # inputs always populate it through the constructors below.
    coverage: EvidenceCoverage | None = None

    @model_validator(mode="after")
    def validate_input(self) -> SavedInput:
        if (
            len(self.text.title) + len(self.text.body) > 20_000
            or len(set(self.detected_modalities)) != len(self.detected_modalities)
            or self.detected_modalities
            != sorted(
                self.detected_modalities,
                key=("text", "image", "video", "audio", "unknown").index,
            )
            or len({asset.position for asset in self.assets}) != len(self.assets)
            or [asset.position for asset in self.assets]
            != list(range(len(self.assets)))
            or any(asset.kind not in self.detected_modalities for asset in self.assets)
            or "audio" in self.detected_modalities
            and "video" not in self.detected_modalities
            or len(set(self.issues)) != len(self.issues)
        ):
            raise ValueError("invalid saved evidence bounds")
        for value in (self.text.title, self.text.body):
            if "\x00" in value:
                raise ValueError("invalid saved text")
            value.encode("utf-8", errors="strict")
        actual_modalities = {asset.kind for asset in self.assets}
        declared_media = set(self.detected_modalities) & {"image", "video"}
        if self.media_inventory_complete and actual_modalities != declared_media:
            raise ValueError("invalid saved media inventory")
        if (
            sum(asset.kind == "image" for asset in self.assets) > 24
            or sum(asset.kind == "video" for asset in self.assets) > 1
            or sum(asset.byte_size or 0 for asset in self.assets) > MAX_MEDIA_BYTES
        ):
            raise ValueError("invalid saved media bounds")
        accepted_detail_extractors = {
            f"{platform}-enrichment-v1" for platform in SEARCH_PLATFORMS
        }
        accepted_preview_extractors = {
            f"{platform}-search-preview-v1" for platform in SEARCH_PLATFORMS
        }
        if self.status == "ready":
            if (
                self.extractor_version not in accepted_detail_extractors
                or self.text.coverage != "complete"
                or not self.media_inventory_complete
                or self.issues
                or "unknown" in self.detected_modalities
                or any(asset.status != "ready" for asset in self.assets)
                or not (
                    self.text.title.strip() or self.text.body.strip() or self.assets
                )
            ):
                raise ValueError("invalid ready saved evidence")
        elif self.extractor_version in accepted_preview_extractors:
            if (
                self.assets
                or self.media_inventory_complete
                or self.detected_modalities != ["text", "unknown"]
                or self.text.coverage not in ("partial", "unavailable")
            ):
                raise ValueError("invalid saved search preview")
        elif self.extractor_version not in accepted_detail_extractors:
            raise ValueError("invalid saved evidence extractor")
        derived = EvidenceCoverage.from_saved_input(self)
        if self.coverage is None:
            return self.model_copy(update={"coverage": derived})
        if self.coverage != derived:
            raise ValueError("invalid evidence coverage")
        return self

    @property
    def evidence_coverage(self) -> EvidenceCoverage:
        assert self.coverage is not None
        return self.coverage

    @property
    def analysis_eligible(self) -> bool:
        return self.evidence_coverage.analysis_eligible

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
            coverage=EvidenceCoverage.from_content(content),
        )

    @classmethod
    def from_preview(
        cls,
        *,
        platform: SearchPlatform,
        title: str,
        snippet: str,
        acquired_at: int,
    ) -> SavedInput:
        coverage = EvidenceCoverage.from_preview(title=title, snippet=snippet)
        return cls(
            schema_version=1,
            extractor_version=f"{platform}-search-preview-v1",
            acquired_at=acquired_at,
            status="partial" if coverage.text_available else "unavailable",
            text={
                "title": title,
                "body": snippet,
                "coverage": "partial" if coverage.text_available else "unavailable",
            },
            detected_modalities=["text", "unknown"],
            media_inventory_complete=False,
            assets=[],
            issues=coverage.issues,
            coverage=coverage,
        )
