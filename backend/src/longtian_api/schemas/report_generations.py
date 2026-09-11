"""One explicit manual intent, with separately accountable child stages."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from longtian_api.schemas.ai_summaries import StrictModel
from longtian_api.schemas.analysis_settings import Count, PositiveId, PromptChoice
from longtian_api.schemas.content_analyses import AnalysisJob, SummaryConcurrency
from longtian_api.schemas.topic_reports import (
    ExplicitSelection,
    ReportRun,
    RequestIntent,
    UtcTimestamp,
)

GenerationStatus = Literal[
    "summarising",
    "paused_for_manual_action",
    "reporting",
    "completed",
    "empty",
    "failed",
    "configuration_blocked",
    "cancelled",
    "interrupted",
]


class LibraryPendingSelection(StrictModel):
    kind: Literal["library_pending"]


GenerationSelection = Annotated[
    ExplicitSelection | LibraryPendingSelection, Field(discriminator="kind")
]


class GenerationCreate(RequestIntent):
    # ``None`` keeps old API clients/replayed historical intents valid. New
    # report-generation UI requests always send the user-visible name.
    name: str | None = Field(default=None, min_length=1, max_length=200)
    configuration_revision: PositiveId
    initial_prompt: PromptChoice
    report_prompt: PromptChoice
    summary_concurrency: SummaryConcurrency = 8
    selection: GenerationSelection

    @field_validator("summary_concurrency", mode="before")
    @classmethod
    def strict_summary_concurrency(cls, value):
        if type(value) is not int or value not in (1, 2, 4, 8, 16):
            raise ValueError("invalid summary concurrency")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("invalid report name")
        return value


class ExplicitSelectionPreview(StrictModel):
    kind: Literal["explicit"]
    result_ids: list[PositiveId] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.result_ids) != len(set(self.result_ids)):
            raise ValueError("duplicate source")
        return self


class LibrarySelectionPreview(StrictModel):
    kind: Literal["library"]


SelectionPreviewRequest = Annotated[
    ExplicitSelectionPreview | LibrarySelectionPreview,
    Field(discriminator="kind"),
]


class SelectionPreviewCounts(StrictModel):
    total: Count
    pending: Count
    already_summarized: Count
    failed: Count
    active: Count


class SelectionPreview(StrictModel):
    selection: ExplicitSelection
    counts: SelectionPreviewCounts


class GenerationEligibility(StrictModel):
    """Unreported inactive sources, split by latest analysis failure for the UI."""

    pending: Count
    failed: Count
    active: Count


PauseReason = Literal[
    "login_required", "manual_challenge_required", "platform_blocked_or_rate_limited"
]


class GenerationControl(StrictModel):
    expected_revision: Count


class ReportGeneration(StrictModel):
    id: PositiveId
    request_id: str
    name: str
    selection: ExplicitSelection
    selection_policy: GenerationSelection
    status: GenerationStatus
    analysis: AnalysisJob
    report: ReportRun | None
    created_at: UtcTimestamp
    finished_at: UtcTimestamp | None
    pause_reason: PauseReason | None
    pause_attempt_id: PositiveId | None
    control_revision: Count

    @model_validator(mode="after")
    def reconciles(self):
        RequestIntent(request_id=self.request_id)
        if (
            self.selection_policy.kind == "explicit"
            and self.selection_policy != self.selection
        ):
            raise ValueError("changed manual selection")
        if (
            self.analysis.request_id != self.request_id
            or self.analysis.counts.total != len(self.selection.result_ids)
        ):
            raise ValueError("invalid generation selection")
        if (
            self.status in ("summarising", "reporting", "paused_for_manual_action")
        ) != (self.finished_at is None):
            raise ValueError("invalid generation progress")
        if (self.status == "paused_for_manual_action") != (
            self.pause_reason is not None
        ):
            raise ValueError("invalid generation pause")
        if (self.pause_reason is None) != (self.pause_attempt_id is None):
            raise ValueError("invalid paused attempt")
        if self.status == "paused_for_manual_action" and self.analysis.status not in (
            "queued",
            "running",
        ):
            raise ValueError("inactive generation pause")
        if (
            self.status in ("summarising", "paused_for_manual_action")
            and self.report is not None
        ):
            raise ValueError("unexpected generation report")
        if self.status in ("reporting", "completed", "empty") and self.report is None:
            raise ValueError("missing generation report")
        if self.report is not None and (
            self.report.selection != self.selection
            or self.report.configuration_revision
            != self.analysis.configuration_revision
            or self.report.trigger != "manual"
        ):
            raise ValueError("invalid child report")
        if self.status in ("completed", "empty") and self.report.status != self.status:
            raise ValueError("unsettled generation report")
        return self


class GenerationList(StrictModel):
    items: list[ReportGeneration]
    next_before_id: PositiveId | None


ReportRecordStatus = Literal[
    "summarising",
    "paused_for_manual_action",
    "reporting",
    "completed",
    "empty",
    "failed",
    "configuration_blocked",
    "cancelled",
    "interrupted",
    "queued",
    "judging",
    "composing",
]


class ReportRecord(StrictModel):
    """Small, unified projection used by the report list."""

    record_type: Literal["generation", "report"]
    record_id: PositiveId
    generation_id: PositiveId | None
    report_id: PositiveId | None
    automation_run_id: PositiveId | None
    name: str = Field(min_length=1, max_length=200)
    trigger: Literal["manual", "automatic", "interval", "retry"]
    status: ReportRecordStatus
    created_at: UtcTimestamp
    selection_count: Count
    processed_count: Count
    failed_count: Count
    active_count: Count
    parent_report_id: PositiveId | None


class ReportRecordList(StrictModel):
    items: list[ReportRecord]
    next_offset: Count | None
