"""Strict, read-only projections used by the homepage workbench."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from longtian_api.schemas.ai_summaries import StrictModel
from longtian_api.schemas.analysis_settings import Count, PositiveId
from longtian_api.schemas.automation_workflows import (
    AutomationSchedule,
    AutomationStageName,
)
from longtian_api.schemas.collection_schedules import UtcTimestamp
from longtian_api.schemas.topic_reports import Coverage
from longtian_api.search_platforms import SearchPlatform

WorkbenchAttentionKind = Literal[
    "automation_task",
    "automation_run",
    "collection_batch",
    "initial_analysis",
    "report",
]
WorkbenchAttentionSeverity = Literal["action_required", "warning", "error"]
WorkbenchAttentionStatus = Literal[
    "invalid",
    "skipped",
    "missed",
    "interrupted",
    "paused_for_manual_action",
    "completed_with_failures",
    "internal_error",
    "configuration_blocked",
    "failed",
    "unsuccessful_members",
    "previous_run_active",
    "configuration_unavailable",
]
WorkbenchAttentionReason = Literal[
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
    "attempt_failed",
    "process_interrupted",
    "login_required",
    "manual_challenge_required",
    "platform_blocked_or_rate_limited",
    "structure_changed",
    "timed_out",
    "browser_unavailable_run",
    "internal_error",
    "configuration_blocked",
    "interrupted",
    "unsuccessful_members",
]


class WorkbenchAttention(StrictModel):
    """A current blocker or latest unhealthy outcome.

    Resource IDs are intentionally kept separate from links.  The frontend owns
    navigation so this contract cannot accidentally make persisted URL text
    authoritative.
    """

    kind: WorkbenchAttentionKind
    severity: WorkbenchAttentionSeverity
    status: WorkbenchAttentionStatus
    reason: WorkbenchAttentionReason | None
    resource_id: PositiveId
    owner: str = Field(min_length=1, max_length=80)
    occurred_at: UtcTimestamp
    unsuccessful_count: Count | None


class WorkbenchCollectionActivity(StrictModel):
    id: PositiveId
    status: Literal["queued", "running", "paused_for_manual_action"]
    rule_name: str = Field(min_length=1, max_length=80)
    current_platform: SearchPlatform | None
    current_item_position: Count | None
    completed_item_count: Count
    item_count: Count
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None

    @model_validator(mode="after")
    def valid_counts(self) -> WorkbenchCollectionActivity:
        if self.completed_item_count > self.item_count:
            raise ValueError("invalid collection activity counts")
        if self.current_item_position is not None and (
            self.current_item_position >= self.item_count
        ):
            raise ValueError("invalid collection activity position")
        return self


class WorkbenchAnalysisActivity(StrictModel):
    id: PositiveId
    status: Literal["queued", "running"]
    total_count: Count
    completed_count: Count
    unsuccessful_count: Count
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None

    @model_validator(mode="after")
    def valid_counts(self) -> WorkbenchAnalysisActivity:
        if self.completed_count + self.unsuccessful_count > self.total_count:
            raise ValueError("invalid analysis activity counts")
        return self


class WorkbenchReportActivity(StrictModel):
    id: PositiveId
    status: Literal["queued", "judging", "composing"]
    total_count: Count
    completed_count: Count
    failed_count: Count
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None

    @model_validator(mode="after")
    def valid_counts(self) -> WorkbenchReportActivity:
        if self.completed_count + self.failed_count > self.total_count:
            raise ValueError("invalid report activity counts")
        return self


class WorkbenchActivity(StrictModel):
    automation: WorkbenchAutomationActivity | None
    collection: WorkbenchCollectionActivity | None
    initial_analysis: WorkbenchAnalysisActivity | None
    report: WorkbenchReportActivity | None


class WorkbenchAutomationActivity(StrictModel):
    run_id: PositiveId
    task_id: PositiveId
    task_name: str = Field(min_length=1, max_length=80)
    status: Literal["queued", "collecting", "analysing", "reporting"]
    active_stage: AutomationStageName | None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None


# Resolve the forward reference introduced by keeping the existing domain
# activity projections alongside the workflow-level owner.
WorkbenchActivity.model_rebuild()


class WorkbenchNextAutomation(StrictModel):
    id: PositiveId
    name: str = Field(min_length=1, max_length=80)
    rule_name: str = Field(min_length=1, max_length=80)
    due_at: UtcTimestamp
    schedule: AutomationSchedule


class WorkbenchLatestReport(StrictModel):
    id: PositiveId
    status: Literal["completed", "empty"]
    created_at: UtcTimestamp
    finished_at: UtcTimestamp
    overview: str | None = Field(min_length=1, max_length=2000)
    empty_reason: (
        Literal["no_ready_sources", "no_relevant_sources", "text_insufficient"] | None
    )
    coverage: Coverage

    @model_validator(mode="after")
    def valid_report_state(self) -> WorkbenchLatestReport:
        if self.status == "completed":
            if self.overview is None or self.empty_reason is not None:
                raise ValueError("invalid completed report projection")
        elif self.overview is not None or self.empty_reason is None:
            raise ValueError("invalid empty report projection")
        return self


class WorkbenchSnapshot(StrictModel):
    observed_at: UtcTimestamp
    attention: list[WorkbenchAttention] = Field(max_length=100)
    activity: WorkbenchActivity
    next_automation: WorkbenchNextAutomation | None
    latest_report: WorkbenchLatestReport | None
