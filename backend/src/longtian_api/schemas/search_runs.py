"""Public FastAPI contracts for durable platform search runs."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SearchRunStatus = Literal[
    "queued",
    "running",
    "completed_with_results",
    "completed_empty",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "browser_unavailable",
    "timed_out",
    "cancelled",
    "internal_error",
]
SearchResultKind = Literal["new", "repeated"]
SearchRunErrorCode = Literal[
    "invalid_request",
    "monitoring_rule_not_found",
    "monitoring_rule_disabled",
    "too_many_search_terms",
    "browser_operation_active",
    "search_run_not_found",
    "search_run_not_active",
    "search_storage_unavailable",
]


class SearchRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    monitoring_rule_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    platform: Literal["toutiao"]
    max_results_per_term: int = Field(default=10, ge=1, le=50)


class SearchRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    monitoring_rule_id: int | None
    platform: Literal["toutiao"]
    rule_name: str
    term_count: int
    max_results_per_term: int
    status: SearchRunStatus
    current_term_position: int | None
    new_count: int
    repeated_count: int
    total_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchRunDetail(SearchRunSummary):
    terms: tuple[str, ...]


class SearchRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[SearchRunSummary]
    next_before_id: int | None


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    platform: Literal["toutiao"]
    platform_content_id: str = Field(min_length=1, max_length=128)
    content_type: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(max_length=1000)
    creator_hash: str = Field(pattern=r"^(?:|[0-9a-f]{16})$")
    publisher_name: str = Field(max_length=100)
    published_at_text: str = Field(max_length=100)
    content_url: str = Field(max_length=2048)
    kind: SearchResultKind
    matched_terms: tuple[str, ...]
    first_seen_at: datetime
    last_seen_at: datetime
    first_observed_at: datetime
    last_observed_at: datetime

    @field_validator("content_url")
    @classmethod
    def validate_content_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = (parsed.hostname or "").rstrip(".").lower()
            port = parsed.port
        except ValueError:
            raise ValueError("invalid content URL") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not (hostname == "toutiao.com" or hostname.endswith(".toutiao.com"))
            or parsed.username is not None
            or parsed.password is not None
            or (port is not None and port != (80 if parsed.scheme == "http" else 443))
            or parsed.fragment
        ):
            raise ValueError("invalid content URL")
        return value

    @model_validator(mode="after")
    def validate_masked_publisher(self) -> "SearchResult":
        name = self.publisher_name
        masked = (
            not name
            or name == "*"
            or (len(name) == 2 and name.endswith("*"))
            or (len(name) == 5 and name[1:4] == "***")
        )
        if bool(self.creator_hash) != bool(name) or not masked:
            raise ValueError("invalid masked publisher")
        return self


class SearchResultListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult]
    total: int
    limit: int
    offset: int


class SearchRunErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SearchRunErrorCode
    message: str


class SearchRunErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: SearchRunErrorDetail
