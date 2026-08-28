"""Global content identity, initial-analysis state and separate collection origins."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from longtian_api.schemas.ai_summaries import (
    Decision,
    ItemStatus,
    StrictModel,
)
from longtian_api.schemas.analysis_evidence import AnalysisSource
from longtian_api.schemas.analysis_settings import Count, PositiveId
from longtian_api.schemas.content_analyses import AttemptStatus
from longtian_api.schemas.search_runs import SearchRunStatus

ResultState = (
    Literal["never_started", "pending_new", "legacy_completed", "legacy_attempted"]
    | AttemptStatus
)


class Result(StrictModel):
    id: PositiveId
    source: AnalysisSource
    first_seen_at: datetime
    last_seen_at: datetime
    origin_count: Count
    analysis_state: ResultState
    latest_attempt_id: PositiveId | None
    active_job_id: PositiveId | None
    legacy_count: Count


class ResultList(StrictModel):
    items: list[Result]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count
    eligible_count: Count
    active_count: Count


class ResultOrigin(StrictModel):
    source_run_id: PositiveId
    rule_name: str
    status: SearchRunStatus
    discovery_kind: Literal["new", "repeated"]
    matched_terms: list[str]
    first_observed_at: datetime
    last_observed_at: datetime


class ResultOriginList(StrictModel):
    items: list[ResultOrigin]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count


class LegacyAnalysis(StrictModel):
    summary_id: PositiveId
    source_run_id: PositiveId
    item_id: PositiveId
    status: ItemStatus
    decision: Decision | None
    reused_from_item_id: PositiveId | None


class LegacyAnalysisList(StrictModel):
    items: list[LegacyAnalysis]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count
