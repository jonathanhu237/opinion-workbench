"""Internal enrichment-v1 projections; never a public file or model API."""

import hashlib
import json
import re
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from longtian_api.search_platforms import SearchPlatform, is_valid_search_content_url

MAX_MANIFEST_BYTES = 192 * 1024
MAX_MEDIA_BYTES = 6 * 1024 * 1024

EnrichmentOutcome = Literal[
    "completed",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "access_denied",
    "lookup_miss",
    "content_unavailable",
    "structure_changed",
    "browser_unavailable",
    "browser_disconnected",
    "timed_out",
    "staging_unavailable",
    "cancelled",
    "internal_error",
]
IssueCode = Literal[
    "text_incomplete",
    "text_unavailable",
    "text_limit",
    "inventory_unknown",
    "media_missing",
    "cover_only",
    "asset_unavailable",
    "asset_expired",
    "download_failed",
    "download_timeout",
    "asset_blocked",
    "unsafe_media_url",
    "media_redirect",
    "media_limit",
    "image_limit",
    "video_limit",
    "invalid_media",
    "unsupported_transport",
    "unsupported_media_type",
    "unsupported_codec",
    "audio_missing",
    "audio_unknown",
    "probe_unavailable",
    "probe_failed",
    "structure_changed",
]
Modality = Literal["text", "image", "video", "audio", "unknown"]
MediaMime = Literal["image/jpeg", "image/png", "image/webp", "video/mp4"]
AcquisitionDiagnosticStage = Literal["detail", "media", "browser"]
AcquisitionDiagnosticOutcome = Literal[
    "access_denied",
    "asset_blocked",
    "asset_unavailable",
    "content_unavailable",
    "login_required",
    "manual_challenge_required",
    "media_limit",
    "media_redirect",
    "parser_failed",
    "platform_blocked_or_rate_limited",
    "structure_changed",
]
AcquisitionDiagnosticBasis = Literal[
    "http_status",
    "explicit_platform_evidence",
    "login_redirect",
    "platform_payload",
    "browser_dom_evidence",
    "upstream_exception",
    "transport",
]


class EnrichmentValidationError(Exception):
    """No untrusted field, file path or raw decoding error escapes this boundary."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AcquisitionDiagnostic(_StrictModel):
    """Bounded, secret-free evidence for one acquisition failure or pause."""

    stage: AcquisitionDiagnosticStage
    outcome: AcquisitionDiagnosticOutcome
    status_code: int | None = Field(default=None, ge=100, le=599)
    basis: AcquisitionDiagnosticBasis
    asset_position: int | None = Field(default=None, ge=0, le=24)
    target: Literal["selected_post", "media_asset", "search_page"]


class EnrichmentBudget(_StrictModel):
    max_text_chars: int = Field(default=20_000, ge=1, le=20_000)
    max_images: int = Field(default=24, ge=1, le=24)
    max_videos: int = Field(default=1, ge=1, le=1)
    max_total_bytes: int = Field(default=MAX_MEDIA_BYTES, ge=1, le=MAX_MEDIA_BYTES)


class ManifestDescriptor(_StrictModel):
    handle: str
    byte_size: int = Field(ge=1, le=MAX_MANIFEST_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: Literal["application/json"]

    @model_validator(mode="after")
    def check_handle(self) -> Self:
        validate_handle(self.handle)
        return self


class EnrichmentText(_StrictModel):
    title: str = Field(max_length=1_000, repr=False)
    body: str = Field(max_length=20_000, repr=False)
    coverage: Literal["complete", "partial", "unavailable"]


class EnrichmentIssue(_StrictModel):
    code: IssueCode
    asset_position: int | None = Field(ge=0, le=24)
    diagnostic: AcquisitionDiagnostic | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class EnrichmentAsset(_StrictModel):
    asset_id: str
    position: int = Field(ge=0, le=24)
    kind: Literal["image", "video"]
    role: Literal["content"]
    status: Literal["ready", "unavailable", "unsupported", "failed"]
    blob_ref: str | None
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
    def check_asset(self) -> Self:
        validate_handle(self.asset_id)
        if self.status == "ready":
            if (
                self.blob_ref != self.asset_id
                or self.sha256 is None
                or self.mime_type is None
                or self.byte_size is None
                or self.width is None
                or self.height is None
                or self.coverage != "complete"
                or self.issue_code is not None
            ):
                raise ValueError("invalid ready asset")
            if self.kind == "image":
                if (
                    not self.mime_type.startswith("image/")
                    or self.duration_ms is not None
                    or self.audio_track != "not_applicable"
                    or self.width * self.height > 40_000_000
                ):
                    raise ValueError("invalid ready image")
            elif (
                self.mime_type != "video/mp4"
                or self.duration_ms is None
                or self.audio_track != "present"
            ):
                raise ValueError("invalid ready video")
        elif (
            any(
                value is not None
                for value in (
                    self.blob_ref,
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
            raise ValueError("invalid unavailable asset")
        return self


class EnrichedContent(_StrictModel):
    schema_version: Literal[1]
    platform: SearchPlatform
    content_id: str = Field(min_length=1, max_length=128)
    content_url: str = Field(min_length=1, max_length=2048, repr=False)
    acquired_at: int = Field(ge=1_000_000_000_000, le=9_999_999_999_999)
    extractor_version: str
    status: Literal["ready", "partial", "unavailable", "unsupported"]
    text: EnrichmentText
    detected_modalities: list[Modality] = Field(min_length=1, max_length=5)
    media_inventory_complete: bool
    assets: list[EnrichmentAsset] = Field(max_length=25)
    issues: list[EnrichmentIssue] = Field(max_length=32)

    @model_validator(mode="before")
    @classmethod
    def check_schema_integer(cls, value):
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("invalid schema version")
        return value

    @model_validator(mode="after")
    def check_content(self) -> Self:
        if (
            type(self.schema_version) is not int
            or self.extractor_version != f"{self.platform}-enrichment-v1"
            or not valid_source_url(self.platform, self.content_id, self.content_url)
            or len(self.text.title) + len(self.text.body) > 20_000
            or len(set(self.detected_modalities)) != len(self.detected_modalities)
            or self.detected_modalities
            != sorted(
                self.detected_modalities,
                key=("text", "image", "video", "audio", "unknown").index,
            )
            or len({asset.asset_id for asset in self.assets}) != len(self.assets)
        ):
            raise ValueError("invalid content identity or bounds")
        for value in (self.text.title, self.text.body):
            if "\x00" in value:
                raise ValueError("invalid text")
            value.encode("utf-8", errors="strict")
        for position, asset in enumerate(self.assets):
            if asset.position != position or asset.kind not in self.detected_modalities:
                raise ValueError("invalid asset inventory")
            if asset.issue_code is not None and not any(
                issue.asset_position == position and issue.code == asset.issue_code
                for issue in self.issues
            ):
                raise ValueError("missing asset issue")
        if len({(issue.code, issue.asset_position) for issue in self.issues}) != len(
            self.issues
        ):
            raise ValueError("duplicate issue")
        for issue in self.issues:
            if issue.asset_position is not None and (
                issue.asset_position >= len(self.assets)
                or self.assets[issue.asset_position].issue_code != issue.code
            ):
                raise ValueError("invalid issue reference")
        if self.status == "ready":
            actual = {asset.kind for asset in self.assets}
            declared = set(self.detected_modalities) & {"image", "video"}
            if (
                self.text.coverage != "complete"
                or not self.media_inventory_complete
                or self.issues
                or "unknown" in self.detected_modalities
                or actual != declared
                or any(asset.status != "ready" for asset in self.assets)
                or ("audio" in self.detected_modalities) != ("video" in actual)
                or not (
                    self.text.title.strip() or self.text.body.strip() or self.assets
                )
            ):
                raise ValueError("incomplete ready content")
        elif not self.issues:
            raise ValueError("missing incomplete input reason")
        return self


def validate_handle(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise EnrichmentValidationError
    if UUID(hex=value).version != 4:
        raise EnrichmentValidationError
    return value


def valid_source_url(platform: SearchPlatform, content_id: str, value: str) -> bool:
    if (
        type(content_id) is not str
        or not 1 <= len(content_id) <= 128
        or type(value) is not str
    ):
        return False
    if (
        not 1 <= len(value) <= 2048
        or any(ord(char) < 33 or ord(char) == 127 for char in value)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", content_id) is None
    ):
        return False
    return is_valid_search_content_url(platform, content_id, value)


def validate_content(
    value: object,
    *,
    platform: SearchPlatform,
    content_id: str,
    content_url: str,
    budget: EnrichmentBudget,
) -> EnrichedContent:
    try:
        result = EnrichedContent.model_validate(value)
        if (
            result.platform != platform
            or result.content_id != content_id
            or result.content_url != content_url
            or len(result.text.title) + len(result.text.body) > budget.max_text_chars
            or sum(asset.kind == "image" for asset in result.assets) > budget.max_images
            or sum(asset.kind == "video" for asset in result.assets) > budget.max_videos
            or sum(asset.byte_size or 0 for asset in result.assets)
            > budget.max_total_bytes
        ):
            raise EnrichmentValidationError
        return result
    except (ValidationError, ValueError, TypeError, UnicodeError):
        raise EnrichmentValidationError from None


def decode_json_object(data: bytes) -> dict[str, object]:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise EnrichmentValidationError from None


def evidence_fingerprint(content: EnrichedContent) -> str:
    data = content.model_dump()
    del data["acquired_at"]
    for issue in data["issues"]:
        issue.pop("diagnostic", None)
    for asset in data["assets"]:
        del asset["asset_id"]
        del asset["blob_ref"]
    encoded = json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preview_fingerprint(
    *,
    platform: SearchPlatform,
    content_id: str,
    content_url: str,
    title: str,
    snippet: str,
) -> str:
    """Hash only the frozen search evidence used by preview analysis.

    Search previews intentionally have a separate fingerprint from enriched
    content.  A later successful detail acquisition therefore cannot silently
    reuse a model result that only saw a title/snippet.
    """

    encoded = json.dumps(
        {
            "schema": "search-preview-v1",
            "platform": platform,
            "content_id": content_id,
            "content_url": content_url,
            "title": title,
            "snippet": snippet,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
