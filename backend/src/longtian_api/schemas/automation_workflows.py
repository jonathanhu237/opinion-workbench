"""Strict contracts for the fixed collection-to-report automation pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from longtian_api.schemas.ai_summaries import StrictModel
from longtian_api.schemas.analysis_settings import (
    INITIAL_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    PromptChoice,
    PromptChoiceDefault,
    PromptSnapshot,
)
from longtian_api.schemas.collection_schedules import UtcTimestamp
from longtian_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_ANALYSIS_GOAL_LENGTH = 4_000
MAX_INTERVAL_MINUTES = 43_200
MAX_PLATFORMS = 5

AutomationScheduleKind = Literal["interval", "daily"]
AutomationTaskStatus = Literal[
    "queued",
    "collecting",
    "analysing",
    "reporting",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "configuration_blocked",
]
AutomationStageName = Literal["collection", "initial_analysis", "topic_report"]
AutomationStageStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "configuration_blocked",
]
AUTOMATION_STAGES: tuple[AutomationStageName, ...] = (
    "collection",
    "initial_analysis",
    "topic_report",
)


def _prose(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise ValueError("invalid prose")
    value.encode("utf-8", errors="strict")
    return value


def _uuid4(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = UUID(value)
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("invalid request ID")
    return value


def _valid_timezone(value: str) -> str:
    # ZoneInfo is intentionally imported lazily so schema imports remain cheap.
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid timezone") from None
    if not value or value.startswith(("/", "..")) or ".." in value:
        raise ValueError("invalid timezone")
    return value


def _valid_platforms(value: list[SearchPlatform]) -> list[SearchPlatform]:
    if not 1 <= len(value) <= MAX_PLATFORMS or len(set(value)) != len(value):
        raise ValueError("invalid platforms")
    if tuple(value) != tuple(
        platform for platform in SEARCH_PLATFORMS if platform in value
    ):
        raise ValueError("platforms must use catalog order")
    return value


class AutomationIntervalSchedule(StrictModel):
    kind: Literal["interval"]
    interval_minutes: int = Field(ge=1, le=MAX_INTERVAL_MINUTES)


class AutomationDailySchedule(StrictModel):
    kind: Literal["daily"]
    daily_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = Field(min_length=1, max_length=64)

    _zone = field_validator("timezone")(_valid_timezone)


AutomationSchedule = Annotated[
    AutomationIntervalSchedule | AutomationDailySchedule,
    Field(discriminator="kind"),
]


class AutomationTaskCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    monitoring_rule_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    platforms: list[SearchPlatform] = Field(
        default_factory=lambda: list(SEARCH_PLATFORMS),
        min_length=1,
        max_length=MAX_PLATFORMS,
    )
    max_results_per_term: int = Field(default=10, ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    # ``analysis_goal`` is retained as a private compatibility mirror for
    # clients written before v18.  New callers submit one choice per stage.
    analysis_goal: str | None = Field(
        default=None, min_length=1, max_length=MAX_ANALYSIS_GOAL_LENGTH
    )
    initial_prompt: PromptChoice = Field(
        default_factory=lambda: PromptChoiceDefault(mode="default")
    )
    report_prompt: PromptChoice = Field(
        default_factory=lambda: PromptChoiceDefault(mode="default")
    )
    schedule: AutomationSchedule

    _name = field_validator("name")(_prose)

    @field_validator("analysis_goal")
    @classmethod
    def optional_goal(cls, value):
        return None if value is None else _prose(value)

    _platforms = field_validator("platforms")(_valid_platforms)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_prompt(cls, values):
        # Legacy requests used ``analysis_goal`` for the report stage.  Keep
        # accepting those requests while ensuring every new persistence path
        # has an explicit PromptChoice.
        if isinstance(values, dict):
            values = dict(values)
            if (
                values.get("analysis_goal") is not None
                and "report_prompt" not in values
            ):
                values["report_prompt"] = {
                    "mode": "custom",
                    "instructions": values["analysis_goal"],
                }
        return values


class AutomationTaskReplace(AutomationTaskCreate):
    # A deleted rule is represented by a null reference while the task remains
    # visible and disabled for operator repair.
    # This is a full-replacement payload: callers must explicitly retain a
    # rule or send null for a deleted reference.  Giving this field a default
    # would silently turn omitted input into a destructive unlink.
    monitoring_rule_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    expected_revision: int = Field(ge=1, lt=MAX_SAFE_INTEGER)
    enabled: bool


class AutomationTaskCreateRequest(StrictModel):
    """Strict public task payload; the compatibility model stays internal."""

    name: str = Field(min_length=1, max_length=80)
    monitoring_rule_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    platforms: list[SearchPlatform] = Field(
        default_factory=lambda: list(SEARCH_PLATFORMS),
        min_length=1,
        max_length=MAX_PLATFORMS,
    )
    max_results_per_term: int = Field(default=10, ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    initial_prompt: PromptChoice
    report_prompt: PromptChoice
    schedule: AutomationSchedule

    _name = field_validator("name")(_prose)
    _platforms = field_validator("platforms")(_valid_platforms)


class AutomationTaskReplaceRequest(AutomationTaskCreateRequest):
    """Strict public full-replacement payload for an existing task."""

    monitoring_rule_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    # Replacement is a full snapshot; omitting the platform list must not
    # silently change an existing task's scope.
    platforms: list[SearchPlatform] = Field(min_length=1, max_length=MAX_PLATFORMS)
    expected_revision: int = Field(ge=1, lt=MAX_SAFE_INTEGER)
    enabled: bool


class AutomationTaskDelete(StrictModel):
    """Revision fence for removing an automatic task configuration."""

    expected_revision: int = Field(ge=1, lt=MAX_SAFE_INTEGER)


class AutomationSnapshot(StrictModel):
    """Immutable intent copied into each accepted run."""

    task_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    task_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    task_name: str = Field(min_length=1, max_length=80)
    monitoring_rule_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)
    rule_name: str = Field(min_length=1, max_length=80)
    terms: list[str] = Field(min_length=1, max_length=100)
    platforms: list[SearchPlatform] = Field(min_length=1, max_length=MAX_PLATFORMS)
    max_results_per_term: int = Field(ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    analysis_goal: str = Field(min_length=1, max_length=MAX_ANALYSIS_GOAL_LENGTH)
    analysis_goal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ai_configuration_revision: int | None = Field(
        default=None, ge=1, le=MAX_SAFE_INTEGER
    )
    ai_base_url: str | None = Field(default=None, max_length=2048)
    ai_model: str | None = Field(default=None, max_length=200)
    # Prompt versions are part of the accepted run intent.  They are optional
    # only for synthetic/legacy fixtures created before this field existed;
    # production admissions always freeze both IDs before child work starts.
    initial_prompt_version_id: int | None = Field(
        default=None, ge=1, le=MAX_SAFE_INTEGER
    )
    report_prompt_version_id: int | None = Field(
        default=None, ge=1, le=MAX_SAFE_INTEGER
    )
    initial_prompt: PromptSnapshot | None = None
    report_prompt: PromptSnapshot | None = None
    initial_template_version: str = Field(min_length=1, max_length=120)
    report_template_version: str = Field(min_length=1, max_length=120)
    admitted_at: UtcTimestamp

    _task_name = field_validator("task_name", "rule_name", "analysis_goal")(_prose)
    _platforms = field_validator("platforms")(_valid_platforms)

    @model_validator(mode="after")
    def validate_prompt_projections(self) -> Self:
        if self.initial_prompt is not None:
            if self.initial_prompt.schema_version != INITIAL_SCHEMA_VERSION:
                raise ValueError("invalid initial prompt snapshot")
            if (
                self.initial_prompt_version_id is None
                or self.initial_prompt.version_id != self.initial_prompt_version_id
            ):
                raise ValueError("initial prompt snapshot ID mismatch")
        if self.report_prompt is not None:
            if self.report_prompt.schema_version != REPORT_SCHEMA_VERSION:
                raise ValueError("invalid report prompt snapshot")
            if (
                self.report_prompt_version_id is None
                or self.report_prompt.version_id != self.report_prompt_version_id
            ):
                raise ValueError("report prompt snapshot ID mismatch")
        return self


class AutomationStage(StrictModel):
    name: AutomationStageName
    attempt_number: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    status: AutomationStageStatus
    child_kind: str | None = Field(default=None, min_length=1, max_length=80)
    child_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)
    input_count: int = Field(default=0, ge=0, le=MAX_SAFE_INTEGER)
    success_count: int = Field(default=0, ge=0, le=MAX_SAFE_INTEGER)
    failure_count: int = Field(default=0, ge=0, le=MAX_SAFE_INTEGER)
    usage_attempted: int = Field(default=0, ge=0, le=MAX_SAFE_INTEGER)
    usage_tokens: int | None = Field(default=None, ge=0, le=MAX_SAFE_INTEGER)
    error: AutomationFailure | None = None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None = None
    finished_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.success_count + self.failure_count > self.input_count:
            raise ValueError("invalid stage counts")
        if (self.status in ("queued", "running")) != (self.finished_at is None):
            raise ValueError("invalid stage completion time")
        if self.status not in ("queued", "running") and self.finished_at is None:
            raise ValueError("terminal stage must have completion time")
        if self.status in ("queued", "running") and self.error is not None:
            raise ValueError("active stage cannot contain error")
        return self


class AutomationFailure(StrictModel):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    message: str = Field(min_length=1, max_length=300)

    _message = field_validator("message")(_prose)


AutomationStage.model_rebuild()


class AutomationRun(StrictModel):
    id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    admission_key: str = Field(min_length=1, max_length=200)
    request_id: str | None = Field(default=None, min_length=36, max_length=36)
    task_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    trigger: Literal["scheduled", "manual"]
    task_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    snapshot: AutomationSnapshot
    status: AutomationTaskStatus
    active_stage: AutomationStageName | None
    stages: list[AutomationStage] = Field(min_length=3, max_length=3)
    attempts: list[AutomationStage] = Field(min_length=3)
    cancel_requested: bool
    outcome: Literal["completed", "no_new_sources", "cancelled"] | None
    topic_report_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)
    error: AutomationFailure | None
    revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None
    finished_at: UtcTimestamp | None

    _request = field_validator("request_id")(_uuid4)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        if tuple(stage.name for stage in self.stages) != AUTOMATION_STAGES:
            raise ValueError("invalid fixed stage order")
        positions = {name: index for index, name in enumerate(AUTOMATION_STAGES)}
        if any(
            positions[current.name] > positions[following.name]
            for current, following in zip(
                self.attempts, self.attempts[1:], strict=False
            )
        ):
            raise ValueError("invalid attempt stage order")
        for name, current in zip(AUTOMATION_STAGES, self.stages, strict=True):
            history = [attempt for attempt in self.attempts if attempt.name == name]
            if not history or [item.attempt_number for item in history] != list(
                range(1, len(history) + 1)
            ):
                raise ValueError("invalid attempt history")
            if history[-1] != current:
                raise ValueError("latest stage does not match attempt history")
        active = self.status in {
            "queued",
            "collecting",
            "analysing",
            "reporting",
        }
        if active != (self.finished_at is None):
            raise ValueError("invalid run completion time")
        if self.status == "completed" and self.outcome is None:
            raise ValueError("completed run requires outcome")
        if self.status == "cancelled" and self.outcome != "cancelled":
            raise ValueError("cancelled run requires cancellation outcome")
        if not active and any(
            stage.status in {"queued", "running"} for stage in self.stages
        ):
            raise ValueError("terminal run has active stage")
        return self


class AutomationTask(StrictModel):
    id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    name: str = Field(min_length=1, max_length=80)
    monitoring_rule_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)
    rule_name: str = Field(min_length=1, max_length=80)
    rule_state: Literal["enabled", "disabled", "deleted", "invalid"]
    platforms: list[SearchPlatform] = Field(min_length=1, max_length=MAX_PLATFORMS)
    max_results_per_term: int = Field(ge=1, le=50)
    max_total_results: int | None = Field(default=None, ge=1, le=50)
    analysis_goal: str = Field(min_length=1, max_length=MAX_ANALYSIS_GOAL_LENGTH)
    initial_prompt: PromptSnapshot | None = None
    report_prompt: PromptSnapshot | None = None
    schedule: AutomationSchedule
    enabled: bool
    revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    anchor_at: UtcTimestamp | None
    next_due_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    latest_run: AutomationRun | None
    available: bool

    _name = field_validator("name", "rule_name", "analysis_goal")(_prose)
    _platforms = field_validator("platforms")(_valid_platforms)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.initial_prompt is not None and (
            self.initial_prompt.schema_version != INITIAL_SCHEMA_VERSION
        ):
            raise ValueError("invalid initial prompt snapshot")
        if self.report_prompt is not None and (
            self.report_prompt.schema_version != REPORT_SCHEMA_VERSION
        ):
            raise ValueError("invalid report prompt snapshot")
        if (self.monitoring_rule_id is None) != (self.rule_state == "deleted"):
            raise ValueError("invalid task rule state")
        if self.enabled != (
            self.anchor_at is not None and self.next_due_at is not None
        ):
            raise ValueError("invalid task schedule state")
        if self.enabled and datetime.fromisoformat(
            self.next_due_at
        ) <= datetime.fromisoformat(self.anchor_at):
            raise ValueError("next due must be after anchor")
        if self.latest_run is not None and self.latest_run.task_id != self.id:
            raise ValueError("invalid latest run")
        return self


class AutomationTaskList(StrictModel):
    tasks: list[AutomationTask] = Field(max_length=100)
    next_before_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)


class AutomationOccurrence(StrictModel):
    id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    task_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    task_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    due_at: UtcTimestamp
    status: Literal["claimed", "admitted", "skipped", "missed", "interrupted"]
    reason: str | None = Field(default=None, min_length=1, max_length=80)
    run_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)
    missed_count: int = Field(default=0, ge=0, le=MAX_SAFE_INTEGER)
    missed_until: UtcTimestamp | None = None
    created_at: UtcTimestamp
    admitted_at: UtcTimestamp | None = None
    run_status: AutomationTaskStatus | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        linked = self.run_id is not None
        valid = (
            (self.status == "claimed" and not linked and self.reason is None)
            or (self.status == "admitted" and linked and self.reason is None)
            or (self.status == "skipped" and not linked and self.reason is not None)
            or (
                self.status == "missed"
                and not linked
                and self.reason in {"offline", "clock_jump"}
                and self.missed_count > 0
                and self.missed_until is not None
            )
            or (
                self.status == "interrupted"
                and not linked
                and self.reason == "dispatch_interrupted"
            )
        )
        if not valid or (
            self.status != "missed" and (self.missed_count or self.missed_until)
        ):
            raise ValueError("invalid occurrence state")
        if linked != (self.run_status is not None):
            raise ValueError("invalid occurrence run link")
        return self


class AutomationOccurrenceList(StrictModel):
    occurrences: list[AutomationOccurrence]
    next_before_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)


class AutomationRunList(StrictModel):
    runs: list[AutomationRun]
    next_before_id: int | None = Field(default=None, ge=1, le=MAX_SAFE_INTEGER)


class AutomationRunNow(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)

    _request = field_validator("request_id")(_uuid4)


class AutomationRunCancel(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)
    expected_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)

    _request = field_validator("request_id")(_uuid4)


class AutomationRunRetry(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)
    expected_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)

    _request = field_validator("request_id")(_uuid4)
