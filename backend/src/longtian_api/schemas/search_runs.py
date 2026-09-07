"""Public FastAPI contracts for durable platform search runs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from longtian_api.search_failure_reasons import SearchFailureReason
from longtian_api.search_platforms import SearchPlatform, is_valid_search_content_url
from longtian_api.services.native_browser_contracts import ExecutionLimit

SearchRunStatus = Literal[
    "queued",
    "running",
    "completed_with_results",
    "completed_empty",
    "completed_with_incomplete",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "timed_out",
    "cancelled",
    "internal_error",
]
SearchRunOrdering = Literal["latest", "platform"]
SearchResultKind = Literal["new", "repeated"]
SearchResultOpenOutcome = Literal[
    "opened",
    "content_not_found",
    "content_unavailable",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "internal_error",
]
SearchRunErrorCode = Literal[
    "search_platform_not_available",
    "invalid_request",
    "monitoring_rule_not_found",
    "monitoring_rule_disabled",
    "too_many_search_terms",
    "browser_operation_active",
    "search_run_not_found",
    "search_run_not_active",
    "search_result_not_found",
    "search_result_open_not_supported",
    "search_storage_unavailable",
]
SearchTermIncompleteReason = Literal["view_all_unresolved"]


class SearchRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    monitoring_rule_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    # A standalone run remains a single-platform primitive; omitting it keeps
    # the historical Weibo default while the batch surface admits all five.
    platform: SearchPlatform = "wb"
    max_results_per_term: int = Field(default=10, ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)


class SearchTermDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(ge=0, le=19)
    term: str = Field(min_length=1, max_length=200)
    reason: SearchTermIncompleteReason
    result_count: int = Field(ge=0, le=50)


class SearchRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    monitoring_rule_id: int | None
    platform: SearchPlatform
    rule_name: str
    term_count: int
    max_results_per_term: int
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    status: SearchRunStatus
    failure_reason: SearchFailureReason | None
    execution_limit: ExecutionLimit | None = None
    current_term_position: int | None
    new_count: int
    repeated_count: int
    total_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    incomplete_terms: tuple[SearchTermDiagnostic, ...] = ()
    ordering: SearchRunOrdering = "platform"

    @model_validator(mode="after")
    def validate_failure_reason(self) -> "SearchRunSummary":
        if self.execution_limit is not None and self.status != "timed_out":
            raise ValueError("execution_limit requires timed_out status")
        if self.failure_reason is not None and self.status != "structure_changed":
            raise ValueError("failure_reason requires structure_changed status")
        if self.status == "completed_with_incomplete" and not self.incomplete_terms:
            raise ValueError("incomplete status requires diagnostics")
        positions = [item.position for item in self.incomplete_terms]
        if len(positions) != len(set(positions)) or any(
            position >= self.term_count for position in positions
        ):
            raise ValueError("invalid incomplete term diagnostics")
        return self


class SearchRunDetail(SearchRunSummary):
    terms: tuple[str, ...]

    @model_validator(mode="after")
    def validate_diagnostic_terms(self) -> "SearchRunDetail":
        if any(
            self.terms[item.position] != item.term for item in self.incomplete_terms
        ):
            raise ValueError("incomplete diagnostic term does not match run terms")
        return self


class SearchRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[SearchRunSummary]
    next_before_id: int | None


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    platform: SearchPlatform
    platform_content_id: str = Field(min_length=1, max_length=128)
    content_type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(max_length=1000)
    creator_hash: str = Field(pattern=r"^(?:|[0-9a-f]{16})$")
    publisher_name: str = Field(max_length=100)
    published_at_text: str = Field(max_length=100)
    content_url: str = Field(max_length=2048)
    hashtags: tuple[str, ...] = Field(default=(), max_length=32)
    interaction_stats: dict[str, int | None] = Field(default_factory=dict)
    kind: SearchResultKind
    matched_terms: tuple[str, ...]
    first_seen_at: datetime
    last_seen_at: datetime
    first_observed_at: datetime
    last_observed_at: datetime

    @model_validator(mode="after")
    def validate_correlated_fields(self) -> "SearchResult":
        if not is_valid_search_content_url(
            self.platform, self.platform_content_id, self.content_url
        ):
            raise ValueError("invalid content URL")
        name = self.publisher_name
        masked = (
            not name
            or name == "*"
            or (len(name) == 2 and name.endswith("*"))
            or (len(name) == 5 and name[1:4] == "***")
        )
        if bool(self.creator_hash) != bool(name) or not masked:
            raise ValueError("invalid masked publisher")
        if any(not tag or len(tag) > 50 for tag in self.hashtags):
            raise ValueError("invalid hashtags")
        if any(
            key not in {"likes", "comments", "shares", "favorites"}
            or (value is not None and (type(value) is not int or value < 0))
            for key, value in self.interaction_stats.items()
        ):
            raise ValueError("invalid interaction stats")
        return self


class SearchResultListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult]
    total: int
    limit: int
    offset: int


class SearchResultOpenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: SearchResultOpenOutcome


class SearchRunErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SearchRunErrorCode
    message: str


class SearchRunErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: SearchRunErrorDetail
