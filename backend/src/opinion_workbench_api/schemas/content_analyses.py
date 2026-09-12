"""Strict independent initial-understanding jobs; no topic relevance verdict."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from opinion_workbench_api.schemas.ai_summaries import (
    ModelRetryNotice,
    StrictModel,
    SummaryFailure,
    SummaryUsage,
    TokenUsage,
)
from opinion_workbench_api.schemas.analysis_evidence import AnalysisSource, SavedInput
from opinion_workbench_api.schemas.analysis_settings import (
    Count,
    PositiveId,
    PromptChoice,
    PromptSnapshotMode,
    PromptVersion,
)
from opinion_workbench_api.schemas.platform_access import (
    PlatformAccessDiagnostic,
    PlatformAccessSnapshot,
)

AttemptStatus = Literal[
    "queued",
    "acquiring",
    "analysing",
    "completed",
    "input_incomplete",
    "unsupported",
    "failed",
    "cancelled",
    "interrupted",
]
JobStatus = Literal[
    "queued",
    "running",
    "completed",
    "cancelled",
    "interrupted",
    "configuration_blocked",
]
SummaryConcurrency = Literal[1, 2, 4, 8, 16]


def valid_prose(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise ValueError("invalid prose")
    value.encode("utf-8", errors="strict")
    return value


class LocationClue(StrictModel):
    excerpt: str = Field(min_length=1, max_length=200)
    modality: Literal["text", "image", "video", "audio"]
    _prose = field_validator("excerpt")(valid_prose)


class Understanding(StrictModel):
    summary: str = Field(min_length=1, max_length=1500)
    location_clues: list[LocationClue] = Field(max_length=12)
    time_context: str = Field(min_length=1, max_length=500)
    media_observations: list[Annotated[str, Field(min_length=1, max_length=400)]] = (
        Field(max_length=12)
    )
    uncertainties: str = Field(min_length=1, max_length=500)
    _prose = field_validator("summary", "time_context", "uncertainties")(valid_prose)

    @model_validator(mode="after")
    def bounded_prose(self) -> Self:
        values = [
            self.summary,
            self.time_context,
            self.uncertainties,
            *(clue.excerpt for clue in self.location_clues),
            *self.media_observations,
        ]
        for value in values:
            valid_prose(value)
        if sum(map(len, values)) > 6000:
            raise ValueError("understanding too large")
        return self


class AllNeverStarted(StrictModel):
    kind: Literal["all_never_started"]


class SelectedResults(StrictModel):
    kind: Literal["explicit", "retry", "reanalysis"]
    result_ids: list[PositiveId] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(self.result_ids) != len(set(self.result_ids)):
            raise ValueError("duplicate result")
        return self


class AnalysisCreate(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)
    configuration_revision: PositiveId
    # Version IDs remain accepted for replay and internal callers.  Public
    # callers may submit only the initial-stage choice; the report stage then
    # resolves to the immutable built-in default unless explicitly selected.
    initial_prompt_version_id: PositiveId | None = None
    report_prompt_version_id: PositiveId | None = None
    initial_prompt_mode: PromptSnapshotMode | None = None
    report_prompt_mode: PromptSnapshotMode | None = None
    initial_prompt: PromptChoice | None = None
    report_prompt: PromptChoice | None = None
    # Internal callers (not the public request model) may freeze the platform
    # pacing used by this job at admission.
    platform_access_snapshot: PlatformAccessSnapshot | None = None
    force_refresh: bool
    selection: Annotated[AllNeverStarted | SelectedResults, Field(discriminator="kind")]

    @model_validator(mode="after")
    def canonical_request(self) -> Self:
        request_id = UUID(self.request_id)
        if request_id.version != 4 or str(request_id) != self.request_id:
            raise ValueError("invalid request ID")
        if self.initial_prompt is None and self.initial_prompt_version_id is None:
            raise ValueError("initial prompt is required")
        return self


class AnalysisCreateRequest(StrictModel):
    """Strict public payload for one initial-understanding submission."""

    request_id: str = Field(min_length=36, max_length=36)
    configuration_revision: PositiveId
    initial_prompt: PromptChoice
    force_refresh: bool
    selection: Annotated[AllNeverStarted | SelectedResults, Field(discriminator="kind")]

    @model_validator(mode="after")
    def valid_request(self) -> Self:
        request_id = UUID(self.request_id)
        if request_id.version != 4 or str(request_id) != self.request_id:
            raise ValueError("invalid request ID")
        return self


class WorkflowAnalysisCreate(StrictModel):
    """Internal uncapped intent for one exact automation-run membership."""

    request_id: str = Field(min_length=36, max_length=36)
    configuration_revision: PositiveId
    initial_prompt_version_id: PositiveId | None = None
    report_prompt_version_id: PositiveId | None = None
    initial_prompt_mode: PromptSnapshotMode | None = None
    report_prompt_mode: PromptSnapshotMode | None = None
    initial_prompt: PromptChoice | None = None
    report_prompt: PromptChoice | None = None
    platform_access_snapshot: PlatformAccessSnapshot | None = None
    force_refresh: bool
    result_ids: list[PositiveId] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_intent(self) -> Self:
        request_id = UUID(self.request_id)
        if request_id.version != 4 or str(request_id) != self.request_id:
            raise ValueError("invalid request ID")
        if len(self.result_ids) != len(set(self.result_ids)):
            raise ValueError("duplicate result")
        if self.initial_prompt is None and self.initial_prompt_version_id is None:
            raise ValueError("initial prompt is required")
        return self


class AnalysisUsage(SummaryUsage):
    attempted_requests: Count
    accounted_requests: Count


class AnalysisCounts(StrictModel):
    total: PositiveId
    queued: Count
    acquiring: Count
    analysing: Count
    completed: Count
    input_incomplete: Count
    unsupported: Count
    failed: Count
    cancelled: Count
    interrupted: Count
    reused: Count

    @model_validator(mode="after")
    def reconciles(self) -> Self:
        if self.total != sum(
            v for k, v in self.model_dump().items() if k not in ("total", "reused")
        ):
            raise ValueError("invalid counts")
        if self.reused > self.completed:
            raise ValueError("invalid reuse")
        return self


class AnalysisAttempt(StrictModel):
    id: PositiveId
    job_id: PositiveId
    position: Count
    source: AnalysisSource
    first_seen_at: datetime
    status: AttemptStatus
    output: Understanding | None
    input: SavedInput | None
    input_fingerprint: str | None
    reused_from_attempt_id: PositiveId | None
    attempted: bool
    usage: TokenUsage | None
    error: SummaryFailure | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        if (self.status in ("queued", "acquiring", "analysing")) != (
            self.finished_at is None
        ):
            raise ValueError("invalid terminal time")
        if (self.status == "completed") != (self.output is not None):
            raise ValueError("invalid output state")
        if self.status == "completed" and (
            self.input is None
            or not self.input.analysis_eligible
            or self.error is not None
            or not self.input_fingerprint
            or not (self.attempted or self.reused_from_attempt_id)
        ):
            raise ValueError("invalid completed evidence")
        if self.usage is not None and not self.attempted:
            raise ValueError("usage without request")
        if self.reused_from_attempt_id is not None and (
            self.status != "completed" or self.attempted or self.usage is not None
        ):
            raise ValueError("invalid reused evidence")
        return self


class AnalysisJob(StrictModel):
    id: PositiveId
    request_id: str | None
    trigger: Literal["manual", "automatic"]
    status: JobStatus
    configuration_revision: PositiveId
    base_url: str
    model: str
    initial_prompt: PromptVersion
    report_prompt: PromptVersion
    force_refresh: bool
    summary_concurrency: SummaryConcurrency = 1
    platform_access_snapshot: PlatformAccessSnapshot | None = None
    access_waiting: bool = False
    access_notice: PlatformAccessDiagnostic | None = None
    model_retry_notice: ModelRetryNotice | None = None
    counts: AnalysisCounts
    usage: AnalysisUsage
    queue_reason: Literal["ai_operation_active", "browser_operation_active"] | None
    completion_event_id: PositiveId | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @model_validator(mode="after")
    def terminal_proof(self) -> Self:
        if (self.status in ("queued", "running")) != (self.finished_at is None):
            raise ValueError("invalid job time")
        if (
            self.finished_at is not None
            and self.counts.queued + self.counts.acquiring + self.counts.analysing
        ):
            raise ValueError("unsettled job")
        if (self.status == "completed") != (self.completion_event_id is not None):
            raise ValueError("invalid completion event")
        return self


class AnalysisAdmission(StrictModel):
    job: AnalysisJob | None
    admitted_count: Count
    already_active_count: Count


class AnalysisJobList(StrictModel):
    jobs: list[AnalysisJob]
    next_before_id: PositiveId | None


class AnalysisAttemptList(StrictModel):
    items: list[AnalysisAttempt]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count


class AnalysisCancel(StrictModel):
    pass
