"""Public FastAPI contracts for durable Weibo search batches."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from longtian_api.schemas.search_runs import (
    SearchResult,
    SearchRunSummary,
    SearchTermDiagnostic,
)
from longtian_api.search_platforms import SearchPlatform

SearchBatchStatus = Literal[
    "queued",
    "running",
    "paused_for_manual_action",
    "completed",
    "completed_with_failures",
    "cancelled",
    "internal_error",
]
SearchBatchItemStatus = Literal[
    "queued",
    "running",
    "paused_for_manual_action",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]
SearchBatchErrorCode = Literal[
    "search_platform_not_available",
    "invalid_request",
    "monitoring_rule_not_found",
    "monitoring_rule_disabled",
    "too_many_search_terms",
    "browser_unavailable",
    "browser_operation_active",
    "search_batch_not_found",
    "search_batch_not_active",
    "search_batch_not_paused",
    "search_batch_state_changed",
    "search_batch_recovery_unavailable",
    "search_batch_item_not_recoverable",
    "search_storage_unavailable",
]

CheckpointBasis = Literal["explicit", "legacy_inferred", "mixed", "unknown"]
PauseReason = Literal["attempt_failed", "process_interrupted"]
CompletionBasis = Literal["attempt_success", "confirmed_terms"]
ManualPageOutcome = Literal[
    "opened_existing",
    "opened_homepage",
    "browser_unavailable",
    "navigation_failed",
    "internal_error",
    "cancelled",
]


class SearchBatchCancel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=0, le=9_223_372_036_854_775_807)


class SearchBatchRecover(SearchBatchCancel):
    expected_run_id: int | None = Field(ge=1, le=9_223_372_036_854_775_807)


class SearchBatchControl(SearchBatchRecover):
    item_position: int = Field(ge=0, le=0)


class SearchBatchManualPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ManualPageOutcome


class SearchBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    monitoring_rule_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    # The current product always admits Weibo.  Keep the persisted platform
    # provenance in the response, but let callers omit a redundant choice.
    platforms: list[SearchPlatform] = Field(
        default_factory=lambda: ["wb"], min_length=1, max_length=1
    )
    max_results_per_term: int = Field(default=10, ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def validate_unique_platforms(self) -> "SearchBatchCreate":
        if self.platforms != ["wb"]:
            raise ValueError("only Weibo is supported")
        return self


class SearchBatchAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int = Field(ge=1)
    run: SearchRunSummary


class SearchBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(ge=0, le=0)
    platform: SearchPlatform
    status: SearchBatchItemStatus
    attempt_count: int = Field(ge=0)
    latest_attempt: SearchBatchAttempt | None
    completed_term_count: int = Field(ge=0)
    remaining_term_count: int = Field(ge=0)
    next_term_position: int | None = Field(ge=0)
    checkpoint_basis: CheckpointBasis
    recovery_available: bool
    pause_reason: PauseReason | None
    completion_basis: CompletionBasis | None
    new_count: int = Field(ge=0)
    repeated_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    incomplete_terms: tuple[SearchTermDiagnostic, ...] = ()


class SearchBatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    monitoring_rule_id: int | None
    rule_name: str
    term_count: int
    platform_count: int = Field(ge=1, le=1)
    terminal_item_count: int = Field(ge=0, le=1)
    max_results_per_term: int
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    status: SearchBatchStatus
    control_revision: int = Field(ge=0)
    current_item_position: int | None = Field(default=None, ge=0, le=0)
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchBatchDetail(SearchBatchSummary):
    terms: tuple[str, ...]
    items: tuple[SearchBatchItem, ...]


class SearchBatchListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batches: list[SearchBatchSummary]
    next_before_id: int | None


class SearchBatchAttemptListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[SearchBatchAttempt]


class SearchBatchResult(SearchResult):
    source_run_id: int = Field(ge=1)


class SearchBatchResultListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchBatchResult]
    total: int
    limit: int
    offset: int


class SearchBatchErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SearchBatchErrorCode
    message: str


class SearchBatchErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: SearchBatchErrorDetail
