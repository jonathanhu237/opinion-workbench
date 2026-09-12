"""Internal, immutable text-engine contracts; never HTTP or executable history."""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, field_validator, model_validator

from opinion_workbench_api.schemas.ai_summaries import StrictModel
from opinion_workbench_api.schemas.analysis_evidence import (
    AnalysisSource,
    EvidenceCoverage,
    SavedInput,
)
from opinion_workbench_api.schemas.analysis_settings import (
    MAX_SAFE_INTEGER,
    Count,
    PositiveId,
    PromptVersion,
)
from opinion_workbench_api.schemas.content_analyses import Understanding, valid_prose
from opinion_workbench_api.services.ai_client import normalize_base_url
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.enrichment_models import (
    MAX_MEDIA_BYTES,
    preview_fingerprint,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
NodeKind = Literal["judgment", "leaf", "overview"]


def valid_text(value: str) -> str:
    """Keep exact accepted text, including whitespace; never repair Unicode."""
    if "\x00" in value:
        raise ValueError("invalid text")
    value.encode("utf-8", errors="strict")
    return value


def valid_node_key(value: str) -> str:
    parts = value.split(":")
    if not (
        (len(parts) == 2 and parts[0] in ("judgment", "leaf"))
        or (len(parts) == 3 and parts[0] == "overview")
    ):
        raise ValueError("invalid node key")
    for index, part in enumerate(parts[1:], start=1):
        if (
            not part.isascii()
            or not part.isdecimal()
            or len(part) > 16
            or str(int(part)) != part
            or int(part) > MAX_SAFE_INTEGER
            or (index == 1 and parts[0] != "leaf" and int(part) == 0)
        ):
            raise ValueError("invalid node key")
    return value


NodeKey = Annotated[str, AfterValidator(valid_node_key)]
Prose = Annotated[
    str, Field(min_length=1, max_length=2000), AfterValidator(valid_prose)
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("missing UTC time")
    return value.astimezone(UTC)


class ProviderIntent(StrictModel):
    base_url: str
    model: str = Field(min_length=1, max_length=200)
    configuration_revision: PositiveId

    @model_validator(mode="after")
    def valid_provider(self) -> Self:
        try:
            normalized = normalize_base_url(self.base_url)
        except AIError:
            raise ValueError("invalid provider") from None
        if normalized != self.base_url or any(
            ord(char) < 33 or ord(char) > 126 for char in self.model
        ):
            raise ValueError("invalid provider")
        return self


class TextPrompt(StrictModel):
    instructions: str = Field(min_length=1, max_length=8000)
    content_hash: Sha256
    schema_version: Literal["topic-report-v1"]

    @model_validator(mode="after")
    def exact_prompt(self) -> Self:
        valid_prose(self.instructions)
        if sha256(self.instructions.encode("utf-8")).hexdigest() != self.content_hash:
            raise ValueError("invalid prompt hash")
        return self


class EngineContext(StrictModel):
    prompt: TextPrompt
    provider: ProviderIntent


class FrozenTextSource(StrictModel):
    position: Count
    attempt_id: PositiveId
    source: AnalysisSource
    first_seen_at: datetime
    input: SavedInput
    understanding: Understanding
    input_fingerprint: Sha256
    initial_prompt: PromptVersion
    initial_provider: ProviderIntent

    _first_seen = field_validator("first_seen_at")(_utc)

    @field_validator("initial_prompt")
    @classmethod
    def valid_initial_prompt(cls, value: PromptVersion) -> PromptVersion:
        valid_prose(value.instructions)
        if (
            value.stage != "initial"
            or value.schema_version != "initial-understanding-v1"
            or sha256(value.instructions.encode("utf-8")).hexdigest()
            != value.content_hash
        ):
            raise ValueError("invalid initial prompt")
        return value.model_copy(update={"created_at": _utc(value.created_at)})

    @model_validator(mode="after")
    def ready_saved_evidence(self) -> Self:
        """Recheck durable metadata only; no reconstruction of media or freshness."""
        content = self.input
        modalities = content.detected_modalities
        if (
            type(content.schema_version) is not int
            or not 1_000_000_000_000 <= content.acquired_at <= 9_999_999_999_999
            or len(content.text.title) + len(content.text.body) > 20_000
            or len(content.assets) > 25
        ):
            raise ValueError("invalid saved evidence")
        text_values = [
            content.text.title,
            content.text.body,
            self.source.title,
            self.source.snippet,
            self.source.content_type,
            self.source.published_at_text,
            *self.source.matched_terms,
        ]
        for value in text_values:
            valid_text(value)
        try:
            derived_coverage = EvidenceCoverage.from_saved_input(content)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid evidence coverage") from None
        if content.coverage is not None and content.coverage != derived_coverage:
            raise ValueError("invalid evidence coverage")
        extractor = f"{self.source.platform}-enrichment-v1"
        preview_extractor = f"{self.source.platform}-search-preview-v1"
        if content.status == "ready":
            if (
                content.text.coverage != "complete"
                or not content.media_inventory_complete
                or content.issues
                or content.extractor_version != extractor
                or not 1 <= len(modalities) <= 4
                or "unknown" in modalities
                or modalities
                != sorted(
                    set(modalities), key=("text", "image", "video", "audio").index
                )
            ):
                raise ValueError("invalid ready evidence")
        elif content.extractor_version == preview_extractor:
            if (
                content.status not in ("partial", "unavailable")
                or content.assets
                or content.media_inventory_complete
                or not content.evidence_coverage.analysis_eligible
                or content.evidence_coverage.level != "search_preview"
                or self.input_fingerprint
                != preview_fingerprint(
                    platform=self.source.platform,
                    content_id=self.source.platform_content_id,
                    content_url=self.source.content_url,
                    title=self.source.title,
                    snippet=self.source.snippet,
                )
            ):
                raise ValueError("invalid search preview evidence")
        elif content.extractor_version == extractor:
            if (
                content.status not in ("partial", "unavailable", "unsupported")
                or not content.evidence_coverage.analysis_eligible
                or content.evidence_coverage.text_origin != "detail"
                or content.evidence_coverage.level == "full_source"
                or modalities
                != sorted(
                    set(modalities),
                    key=("text", "image", "video", "audio", "unknown").index,
                )
            ):
                raise ValueError("invalid partial evidence")
        else:
            raise ValueError("invalid evidence extractor")
        actual = {asset.kind for asset in content.assets}
        if content.status != "ready":
            for position, asset in enumerate(content.assets):
                if asset.position != position:
                    raise ValueError("invalid partial asset position")
                if asset.status == "ready" and (
                    asset.sha256 is None
                    or len(asset.sha256) != 64
                    or any(char not in "0123456789abcdef" for char in asset.sha256)
                    or asset.byte_size is None
                    or not 1 <= asset.byte_size <= MAX_MEDIA_BYTES
                    or asset.width is None
                    or not 1 <= asset.width <= 32_768
                    or asset.height is None
                    or not 1 <= asset.height <= 32_768
                    or asset.coverage != "complete"
                    or asset.issue_code is not None
                ):
                    raise ValueError("invalid partial ready asset")
                if asset.status != "ready" and (
                    asset.coverage != "unknown" or asset.issue_code is None
                ):
                    raise ValueError("invalid partial unavailable asset")
            return self
        if (
            actual != set(modalities) & {"image", "video"}
            or ("audio" in modalities) != ("video" in actual)
            or not (
                content.text.title.strip()
                or content.text.body.strip()
                or content.assets
            )
            or sum(asset.kind == "image" for asset in content.assets) > 24
            or sum(asset.kind == "video" for asset in content.assets) > 1
        ):
            raise ValueError("invalid ready inventory")
        byte_size = 0
        for position, asset in enumerate(content.assets):
            if (
                asset.position != position
                or asset.status != "ready"
                or asset.coverage != "complete"
                or asset.issue_code is not None
                or asset.sha256 is None
                or len(asset.sha256) != 64
                or any(char not in "0123456789abcdef" for char in asset.sha256)
                or asset.byte_size is None
                or not 1 <= asset.byte_size <= MAX_MEDIA_BYTES
                or asset.width is None
                or not 1 <= asset.width <= 32_768
                or asset.height is None
                or not 1 <= asset.height <= 32_768
            ):
                raise ValueError("invalid ready asset")
            byte_size += asset.byte_size
            if asset.kind == "image":
                if (
                    asset.mime_type not in ("image/jpeg", "image/png", "image/webp")
                    or asset.duration_ms is not None
                    or asset.audio_track != "not_applicable"
                    or asset.width * asset.height > 40_000_000
                ):
                    raise ValueError("invalid ready image")
            elif (
                asset.mime_type != "video/mp4"
                or asset.duration_ms is None
                or not 1 <= asset.duration_ms <= MAX_SAFE_INTEGER
                or asset.audio_track != "present"
            ):
                raise ValueError("invalid ready video")
        if byte_size > MAX_MEDIA_BYTES:
            raise ValueError("invalid ready media size")
        return self


class Judgment(StrictModel):
    decision: Literal["relevant", "irrelevant", "uncertain"]
    reason: str = Field(min_length=1, max_length=600)
    _prose = field_validator("reason")(valid_prose)


class RelevantSource(StrictModel):
    evidence: FrozenTextSource
    judgment: Judgment

    @model_validator(mode="after")
    def relevant_only(self) -> Self:
        if self.judgment.decision != "relevant":
            raise ValueError("non-relevant evidence")
        return self


class LeafParagraph(StrictModel):
    text: Prose
    source_ids: list[PositiveId] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_citations(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("repeated citations")
        return self


class LeafDocument(StrictModel):
    overview: Prose
    items: list[LeafParagraph] = Field(min_length=1, max_length=16)


class OverviewParagraph(StrictModel):
    text: Prose
    child_ids: list[NodeKey] = Field(min_length=1, max_length=8)
    # None is readable only for reports saved before paragraph-level citations.
    source_ids: list[PositiveId] | None = Field(
        default=None, min_length=1, max_length=128
    )

    @model_validator(mode="after")
    def unique_citations(self) -> Self:
        if len(self.child_ids) != len(set(self.child_ids)):
            raise ValueError("repeated citations")
        if self.source_ids is not None and len(self.source_ids) != len(
            set(self.source_ids)
        ):
            raise ValueError("repeated source citations")
        return self


class OverviewDocument(StrictModel):
    overview: Prose
    items: list[OverviewParagraph] = Field(min_length=1, max_length=16)


class CitedText(StrictModel):
    text: Prose
    source_ids: list[PositiveId] = Field(min_length=1, max_length=128)


class ChildOverview(StrictModel):
    key: NodeKey
    overview: Prose
    output_hash: Sha256
    membership_hash: Sha256
    source_count: PositiveId
    items: list[CitedText] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def composition_child(self) -> Self:
        if self.key.startswith("judgment:"):
            raise ValueError("invalid overview child")
        return self


class PreparedCall(StrictModel):
    kind: NodeKind
    key: NodeKey
    system_text: str = Field(min_length=1, repr=False)
    user_text: str = Field(min_length=1, repr=False)
    input_characters: Count
    input_hash: Sha256
    source_ids: tuple[PositiveId, ...]
    child_ids: tuple[NodeKey, ...]
    max_tokens: Literal[2048, 4096]
    deadline_seconds: Literal[180.0]

    _text = field_validator("system_text", "user_text")(valid_text)

    @model_validator(mode="after")
    def consistent_call(self) -> Self:
        if (
            self.key.split(":")[0] != self.kind
            or len(self.source_ids) != len(set(self.source_ids))
            or len(self.child_ids) != len(set(self.child_ids))
            or self.input_characters != len(self.system_text) + len(self.user_text)
            or type(self.max_tokens) is not int
            or type(self.deadline_seconds) is not float
        ):
            raise ValueError("invalid call")
        if self.kind == "judgment":
            valid = (
                len(self.source_ids) == 1
                and self.key == f"judgment:{self.source_ids[0]}"
                and not self.child_ids
                and self.max_tokens == 2048
            )
        elif self.kind == "leaf":
            valid = (
                1 <= len(self.source_ids) <= 8
                and not self.child_ids
                and self.max_tokens == 4096
            )
        else:
            valid = (
                not self.source_ids
                and 2 <= len(self.child_ids) <= 8
                and self.max_tokens == 4096
                and not any(key.startswith("judgment:") for key in self.child_ids)
            )
        if not valid:
            raise ValueError("invalid call membership")
        return self


class ValidatedOutput(StrictModel):
    kind: NodeKind
    output: Judgment | LeafDocument | OverviewDocument
    output_hash: Sha256

    @model_validator(mode="after")
    def matching_kind(self) -> Self:
        expected = {
            "judgment": Judgment,
            "leaf": LeafDocument,
            "overview": OverviewDocument,
        }
        if not isinstance(self.output, expected[self.kind]):
            raise ValueError("invalid output kind")
        return self


class CompletedOutput(StrictModel):
    engine_version: str
    input_hash: Sha256
    output_hash: Sha256
    output: Judgment | LeafDocument | OverviewDocument


class RequestProof(StrictModel):
    encoded_bytes: Count
    request_hash: Sha256


class LeafPlan(StrictModel):
    consumed_count: int = Field(ge=1, le=8)
    call: PreparedCall

    @model_validator(mode="after")
    def leaf_only(self) -> Self:
        if self.call.kind != "leaf" or self.consumed_count != len(self.call.source_ids):
            raise ValueError("invalid leaf plan")
        return self


class OverviewCallPlan(StrictModel):
    kind: Literal["call"]
    consumed_count: int = Field(ge=2, le=8)
    call: PreparedCall

    @model_validator(mode="after")
    def overview_only(self) -> Self:
        if self.call.kind != "overview" or self.consumed_count != len(
            self.call.child_ids
        ):
            raise ValueError("invalid overview plan")
        return self


class OverviewCarryPlan(StrictModel):
    kind: Literal["carry"]
    consumed_count: Literal[1]
    child: ChildOverview

    @field_validator("consumed_count", mode="before")
    @classmethod
    def strict_count(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("invalid carry count")
        return value


OverviewPlan = Annotated[
    OverviewCallPlan | OverviewCarryPlan, Field(discriminator="kind")
]
