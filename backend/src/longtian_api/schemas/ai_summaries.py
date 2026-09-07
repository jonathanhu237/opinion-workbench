"""Strict, secret-free contracts for manually requested full-run summaries."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from longtian_api.schemas.ai_settings import AIErrorCode
from longtian_api.schemas.search_runs import SearchRunStatus
from longtian_api.search_platforms import SearchPlatform
from longtian_api.services.ai_client import MAX_USAGE_TOKENS, AIUsage
from longtian_api.services.enrichment_models import (
    AcquisitionDiagnostic,
    IssueCode,
    valid_source_url,
)
from longtian_api.services.monitoring_rules import MAX_TERMS_PER_RULE

PositiveId = Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]
SummaryStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled", "interrupted"
]
ItemStatus = Literal[
    "pending",
    "analysing",
    "completed",
    "input_incomplete",
    "failed",
    "cancelled",
    "interrupted",
]
Decision = Literal["relevant", "irrelevant", "uncertain"]
FailureStage = Literal["acquisition", "input", "analysis", "composition", "execution"]
FailureCode = Literal[
    "input_incomplete",
    "source_changed",
    "source_active",
    "browser_operation_active",
    "browser_unavailable",
    "acquisition_failed",
    "source_access_denied",
    "source_content_unavailable",
    "platform_not_supported",
    "source_structure_changed",
    "acquisition_timed_out",
    "stored_content_unavailable",
    "invalid_enrichment",
    "unsupported_model",
    "request_too_large",
    "invalid_json",
    "invalid_schema",
    "invalid_citations",
    "credential_leakage",
    "ai_destination_forbidden",
    "ai_authentication_failed",
    "ai_model_not_found",
    "ai_rate_limited",
    "ai_provider_unavailable",
    "ai_timeout",
    "ai_invalid_response",
    "ai_unsupported_input",
    "ai_request_too_large",
    "cancelled",
    "interrupted",
    "internal_error",
    "storage_unavailable",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SummaryCreate(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)
    force_refresh: bool
    configuration_revision: PositiveId

    @model_validator(mode="after")
    def valid_request_id(self) -> Self:
        value = UUID(self.request_id)
        if value.version != 4 or str(value) != self.request_id:
            raise ValueError("invalid request ID")
        return self


class SummaryCancel(StrictModel):
    pass


class SummaryFailure(StrictModel):
    stage: FailureStage
    code: FailureCode
    message: str
    validation_issues: list[Annotated[str, Field(max_length=200)]] | None = Field(
        default=None, max_length=8, exclude_if=lambda value: value is None
    )
    diagnostic: AcquisitionDiagnostic | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


TokenUsage = AIUsage


class SummaryUsage(StrictModel):
    attempted_requests: int = Field(ge=0, le=101)
    accounted_requests: int = Field(ge=0, le=101)
    complete: bool
    prompt_tokens: int | None = Field(ge=0, le=MAX_USAGE_TOKENS)
    completion_tokens: int | None = Field(ge=0, le=MAX_USAGE_TOKENS)
    total_tokens: int | None = Field(ge=0, le=MAX_USAGE_TOKENS)

    @model_validator(mode="after")
    def valid_accounting(self) -> Self:
        if self.accounted_requests > self.attempted_requests:
            raise ValueError("invalid usage coverage")
        totals = (self.prompt_tokens, self.completion_tokens, self.total_tokens)
        if all(value is None for value in totals):
            if self.complete or not self.attempted_requests:
                raise ValueError("invalid unknown accounting")
        else:
            if (
                self.prompt_tokens is None
                or self.completion_tokens is None
                or self.total_tokens is None
            ):
                raise ValueError("invalid usage totals")
            if (
                self.total_tokens != self.prompt_tokens + self.completion_tokens
                or self.complete != (self.accounted_requests == self.attempted_requests)
            ):
                raise ValueError("invalid usage totals")
            if self.attempted_requests and not self.accounted_requests:
                raise ValueError("unknown usage is not zero")
        return self


class SummaryCounts(StrictModel):
    total: int = Field(ge=1, le=100)
    pending: int = Field(ge=0, le=100)
    analysing: int = Field(ge=0, le=100)
    relevant: int = Field(ge=0, le=100)
    irrelevant: int = Field(ge=0, le=100)
    uncertain: int = Field(ge=0, le=100)
    input_incomplete: int = Field(ge=0, le=100)
    failed: int = Field(ge=0, le=100)
    cancelled: int = Field(ge=0, le=100)
    interrupted: int = Field(ge=0, le=100)
    reused: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def reconciles(self) -> Self:
        values = self.model_dump()
        if self.total != sum(
            v for k, v in values.items() if k not in ("total", "reused")
        ):
            raise ValueError("invalid summary counts")
        if self.reused > self.relevant + self.irrelevant + self.uncertain:
            raise ValueError("invalid reuse count")
        return self


class SummaryParagraph(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    source_ids: list[PositiveId] = Field(min_length=1, max_length=100)


class SummaryDocument(StrictModel):
    overview: str = Field(min_length=1, max_length=2000)
    items: list[SummaryParagraph] = Field(max_length=100)


class SummarySource(StrictModel):
    source_run_id: PositiveId
    result_id: PositiveId
    platform: SearchPlatform
    platform_content_id: str = Field(min_length=1, max_length=128)
    content_type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(max_length=1000)
    content_url: str = Field(min_length=1, max_length=2048)
    published_at_text: str = Field(max_length=100)
    matched_terms: list[str] = Field(min_length=1, max_length=MAX_TERMS_PER_RULE)
    hashtags: list[str] = Field(default_factory=list, max_length=32)
    interaction_stats: dict[str, int | None] = Field(default_factory=dict)
    creator_hash: str = Field(default="", pattern=r"^(?:|[0-9a-f]{16})$")
    publisher_name: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def valid_identity(self) -> Self:
        if not valid_source_url(
            self.platform, self.platform_content_id, self.content_url
        ):
            raise ValueError("invalid source identity")
        if any(not tag or len(tag) > 50 for tag in self.hashtags):
            raise ValueError("invalid hashtags")
        name = self.publisher_name
        masked = (
            not name
            or name == "*"
            or (len(name) == 2 and name.endswith("*"))
            or (len(name) == 5 and name[1:4] == "***")
        )
        if bool(self.creator_hash) != bool(name) or not masked:
            raise ValueError("invalid masked publisher")
        if any(
            key not in {"likes", "comments", "shares", "favorites"}
            or (value is not None and (type(value) is not int or value < 0))
            for key, value in self.interaction_stats.items()
        ):
            raise ValueError("invalid interaction stats")
        return self


class SummaryItem(StrictModel):
    id: PositiveId
    summary_run_id: PositiveId
    position: int = Field(ge=0, le=99)
    source: SummarySource
    status: ItemStatus
    decision: Decision | None
    reason: str | None = Field(min_length=1, max_length=300)
    evidence_summary: str | None = Field(min_length=1, max_length=1000)
    reused_from_item_id: PositiveId | None
    attempted: bool
    usage: TokenUsage | None
    input_status: Literal["ready", "partial", "unavailable", "unsupported"] | None
    input_issues: list[IssueCode]
    error: SummaryFailure | None
    started_at: datetime | None
    finished_at: datetime | None

    @model_validator(mode="after")
    def valid_state(self) -> Self:
        analysis = (self.decision, self.reason, self.evidence_summary)
        if self.status == "completed":
            if any(value is None for value in analysis) or self.error is not None:
                raise ValueError("invalid completed analysis")
            if self.input_status != "ready" or self.input_issues:
                raise ValueError("incomplete completed analysis")
            if self.reused_from_item_id is None and not self.attempted:
                raise ValueError("analysis without request")
        elif any(value is not None for value in analysis):
            raise ValueError("failed input is not a verdict")
        if self.reused_from_item_id is not None and (
            self.status != "completed" or self.attempted or self.usage is not None
        ):
            raise ValueError("invalid reuse")
        if self.usage is not None and not self.attempted:
            raise ValueError("usage without request")
        if (self.status in ("pending", "analysing")) != (self.finished_at is None):
            raise ValueError("invalid item completion time")
        return self


class SummaryRun(StrictModel):
    id: PositiveId
    request_id: str
    source_run_id: PositiveId
    platform: SearchPlatform
    source_run_status: SearchRunStatus
    rule_name: str
    terms: list[str]
    configuration_revision: PositiveId
    base_url: str
    model: str
    force_refresh: bool
    status: SummaryStatus
    phase: Literal["analysing", "summarising"]
    counts: SummaryCounts
    usage: SummaryUsage
    document: SummaryDocument | None
    error: SummaryFailure | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @model_validator(mode="after")
    def valid_state(self) -> Self:
        terminal = self.status not in ("queued", "running")
        if terminal != (self.finished_at is not None):
            raise ValueError("invalid completion time")
        if terminal and self.counts.pending + self.counts.analysing:
            raise ValueError("unfinished terminal items")
        if (self.status == "completed") != (self.document is not None):
            raise ValueError("invalid summary document")
        return self


class SummaryList(StrictModel):
    summaries: list[SummaryRun]
    next_before_id: PositiveId | None


class SummaryItemList(StrictModel):
    items: list[SummaryItem]
    total: int = Field(ge=1, le=100)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class SummaryErrorDetail(StrictModel):
    code: (
        AIErrorCode
        | Literal[
            "search_run_not_found",
            "ai_summary_not_found",
            "ai_summary_source_active",
            "ai_summary_request_conflict",
            "browser_operation_active",
            "ai_summary_empty_source",
            "ai_summary_source_limit",
            "ai_summary_storage_unavailable",
            "ai_summary_unavailable",
        ]
    )
    message: str


class SummaryErrorResponse(StrictModel):
    detail: SummaryErrorDetail
