"""Strict interval configuration and truthful scheduling-history projections."""

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from longtian_api.schemas.search_batches import SearchBatchCreate, SearchBatchStatus
from longtian_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_INTERVAL_MINUTES = 43_200
OccurrenceStatus = Literal["claimed", "dispatched", "skipped", "missed", "interrupted"]
OccurrenceReason = Literal[
    "browser_operation_active",
    "browser_unavailable",
    "monitoring_rule_not_found",
    "monitoring_rule_disabled",
    "invalid_monitoring_rule",
    "too_many_search_terms",
    "schedule_changed",
    "storage_unavailable",
    "dispatch_interrupted",
    "offline",
    "clock_jump",
]


def _valid_utc_timestamp(value: str) -> str:
    datetime.fromisoformat(value)
    return value


UtcTimestamp = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|\+00:00)$"
    ),
    AfterValidator(_valid_utc_timestamp),
]


def validate_schedule_platforms(platforms: Sequence[SearchPlatform]) -> None:
    """One catalog-order contract for projections and durable timer admission."""
    if not 1 <= len(platforms) <= 5 or tuple(platforms) != tuple(
        platform for platform in SEARCH_PLATFORMS if platform in platforms
    ):
        raise ValueError("Invalid schedule platforms")


class CollectionInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: int = Field(ge=1, le=MAX_INTERVAL_MINUTES)
    unit: Literal["minutes", "hours"]


class CollectionScheduleCreate(SearchBatchCreate):
    monitoring_rule_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    interval: CollectionInterval


class CollectionScheduleReplace(CollectionScheduleCreate):
    monitoring_rule_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    max_results_per_term: int = Field(ge=1, le=50)
    expected_revision: int = Field(ge=1, lt=MAX_SAFE_INTEGER)
    enabled: bool


class CollectionOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    schedule_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    schedule_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    due_at: UtcTimestamp
    status: OccurrenceStatus
    reason: OccurrenceReason | None
    batch_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    batch_status: SearchBatchStatus | None
    missed_count: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    missed_until: UtcTimestamp | None
    created_at: UtcTimestamp
    dispatched_at: UtcTimestamp | None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        linked = self.batch_id is not None
        missed = self.status == "missed"
        valid_state = (
            (self.status == "claimed" and not linked and self.reason is None)
            or (self.status == "dispatched" and linked and self.reason is None)
            or (
                self.status == "skipped"
                and not linked
                and self.reason is not None
                and self.reason not in {"offline", "clock_jump", "dispatch_interrupted"}
            )
            or (missed and not linked and self.reason in {"offline", "clock_jump"})
            or (self.status == "interrupted" and self.reason == "dispatch_interrupted")
        )
        if (
            not valid_state
            or linked != (self.batch_status is not None)
            or linked != (self.dispatched_at is not None)
            or (
                missed
                and (
                    self.missed_count < 1
                    or self.missed_until is None
                    or datetime.fromisoformat(self.missed_until)
                    < datetime.fromisoformat(self.due_at)
                )
            )
            or (
                not missed and (self.missed_count != 0 or self.missed_until is not None)
            )
        ):
            raise ValueError("Invalid occurrence state")
        return self


class CollectionSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    monitoring_rule_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    rule_name: str = Field(min_length=1, max_length=80)
    rule_state: Literal["enabled", "disabled", "deleted", "invalid"]
    platforms: list[SearchPlatform] = Field(min_length=1, max_length=5)
    max_results_per_term: int = Field(ge=1, le=50)
    interval_minutes: int = Field(ge=1, le=MAX_INTERVAL_MINUTES)
    enabled: bool
    revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    anchor_at: UtcTimestamp | None
    next_due_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    latest_occurrence: CollectionOccurrence | None
    available: bool

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[SearchPlatform]) -> list[SearchPlatform]:
        validate_schedule_platforms(value)
        return value

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if (
            self.rule_name != self.rule_name.strip()
            or (self.monitoring_rule_id is None) != (self.rule_state == "deleted")
            or (
                self.enabled
                and (
                    self.anchor_at is None
                    or self.next_due_at is None
                    or datetime.fromisoformat(self.next_due_at)
                    <= datetime.fromisoformat(self.anchor_at)
                )
            )
            or (
                not self.enabled
                and (self.anchor_at is not None or self.next_due_at is not None)
            )
            or (
                self.latest_occurrence is not None
                and (
                    self.latest_occurrence.schedule_id != self.id
                    or self.latest_occurrence.schedule_revision > self.revision
                )
            )
        ):
            raise ValueError("Invalid schedule state")
        return self


class CollectionScheduleList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedules: list[CollectionSchedule] = Field(max_length=100)
    next_before_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)


class CollectionOccurrenceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrences: list[CollectionOccurrence] = Field(max_length=100)
    next_before_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
