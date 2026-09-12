"""Strict public report projections; execution envelopes stay inside the engine."""

import re
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from opinion_workbench_api.schemas.ai_summaries import (
    FailureCode,
    ModelRetryNotice,
    StrictModel,
    SummaryFailure,
    TokenUsage,
)
from opinion_workbench_api.schemas.analysis_evidence import (
    AnalysisSource,
    EvidenceCoverage,
)
from opinion_workbench_api.schemas.analysis_settings import (
    Count,
    PositiveId,
    PromptChoice,
)
from opinion_workbench_api.schemas.collection_schedules import UtcTimestamp
from opinion_workbench_api.schemas.content_analyses import (
    AnalysisUsage,
    AttemptStatus,
    valid_prose,
)
from opinion_workbench_api.schemas.search_runs import SearchRunStatus
from opinion_workbench_api.schemas.topic_report_engine import ProviderIntent
from opinion_workbench_api.search_failure_reasons import SearchFailureReason
from opinion_workbench_api.search_platforms import SearchPlatform

ReportStatus = Literal[
    "queued",
    "judging",
    "composing",
    "completed",
    "empty",
    "failed",
    "cancelled",
    "interrupted",
    "configuration_blocked",
]
NodeStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled", "interrupted"
]
SourceState = Literal[
    "unavailable",
    "pending",
    "judging",
    "relevant",
    "irrelevant",
    "uncertain",
    "failed",
    "cancelled",
    "interrupted",
]
ACTIVE_REPORTS = ("queued", "judging", "composing")
ACTIVE_NODES = ("queued", "running")


class ReportFailure(SummaryFailure):
    code: (
        FailureCode
        | Literal[
            "ai_configuration_required",
            "ai_configuration_changed",
            "ai_credentials_unavailable",
            "ai_settings_storage_unavailable",
        ]
    )

    @model_validator(mode="after")
    def configuration_stage(self) -> Self:
        if (
            self.code
            in (
                "ai_configuration_required",
                "ai_configuration_changed",
                "ai_credentials_unavailable",
                "ai_settings_storage_unavailable",
            )
            and self.stage != "execution"
        ):
            raise ValueError("invalid configuration failure stage")
        return self


class IntervalSelection(StrictModel):
    kind: Literal["first_seen_interval"]
    first_seen_from: UtcTimestamp
    first_seen_to: UtcTimestamp

    @field_validator("first_seen_from", "first_seen_to")
    @classmethod
    def exact_microseconds(cls, value):
        if re.search(r"\.\d{7,}", value):
            raise ValueError("unsupported sub-microsecond precision")
        return value


class JobSelection(StrictModel):
    kind: Literal["initial_job"]
    job_id: PositiveId


class ExplicitSelection(StrictModel):
    kind: Literal["explicit"]
    result_ids: list[PositiveId] = Field(min_length=1)

    @field_validator("result_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("duplicate source")
        return values


class WorkflowSelection(StrictModel):
    kind: Literal["workflow_run"]
    run_id: PositiveId


class RequestIntent(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)

    @field_validator("request_id")
    @classmethod
    def valid_uuid(cls, value):
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError("invalid request ID")
        return value


class ReportCreate(RequestIntent):
    configuration_revision: PositiveId
    report_prompt_version_id: PositiveId | None = None
    report_prompt: PromptChoice | None = None
    # Legacy report overrides remain accepted for replay/history compatibility.
    instructions_override: str | None = None
    selection: Annotated[
        IntervalSelection | ExplicitSelection, Field(discriminator="kind")
    ]


class ReportRetry(RequestIntent):
    expected_revision: PositiveId
    configuration_revision: PositiveId
    report_prompt_version_id: PositiveId | None = None
    report_prompt: PromptChoice | None = None
    instructions_override: str | None = None


class ReportCreateRequest(RequestIntent):
    """Strict public payload for a new second-stage report."""

    configuration_revision: PositiveId
    report_prompt: PromptChoice
    selection: Annotated[
        IntervalSelection | ExplicitSelection, Field(discriminator="kind")
    ]


class ReportRetryRequest(RequestIntent):
    """Strict public payload; omitted prompt means reuse the parent snapshot."""

    expected_revision: PositiveId
    configuration_revision: PositiveId
    report_prompt: PromptChoice | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_prompt(cls, values):
        # ``null`` is not a PromptChoice.  Only omission carries the explicit
        # retry contract of reusing the parent's immutable prompt snapshot.
        if isinstance(values, dict) and "report_prompt" in values:
            if values["report_prompt"] is None:
                raise ValueError("report_prompt must be omitted")
        return values


class ReportCancel(RequestIntent):
    expected_revision: PositiveId


class ReportPrompt(StrictModel):
    version_id: PositiveId | None = None
    mode: Literal["default", "custom", "legacy"] | None = None
    origin: Literal["default", "custom", "legacy", "shared", "override"]
    instructions: str = Field(min_length=1, max_length=8000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: Literal["topic-report-v1"]
    _prose = field_validator("instructions")(valid_prose)

    @model_validator(mode="after")
    def consistent_origin(self) -> Self:
        import hashlib

        if self.origin in {"default", "custom", "shared"} and self.version_id is None:
            raise ValueError("invalid prompt origin")
        # A historical snapshot may still point at the immutable prompt row;
        # only an ad-hoc override is necessarily version-less.
        if self.origin == "override" and self.version_id is not None:
            raise ValueError("invalid prompt origin")
        if self.mode == "default" and self.origin not in {"default", "shared"}:
            raise ValueError("invalid prompt mode")
        if self.mode == "custom" and self.origin not in {"custom", "shared"}:
            raise ValueError("invalid prompt mode")
        if self.mode == "legacy" and self.origin != "legacy":
            raise ValueError("invalid prompt mode")
        if hashlib.sha256(self.instructions.encode()).hexdigest() != self.content_hash:
            raise ValueError("invalid prompt hash")
        return self


class Coverage(StrictModel):
    total: Count
    ready: Count
    unavailable: Count
    pending: Count
    judging: Count
    relevant: Count
    irrelevant: Count
    uncertain: Count
    failed: Count
    cancelled: Count
    interrupted: Count

    @model_validator(mode="after")
    def reconciles(self) -> Self:
        if self.total != self.ready + self.unavailable or self.ready != sum(
            value
            for key, value in self.model_dump().items()
            if key not in ("total", "ready", "unavailable")
        ):
            raise ValueError("invalid coverage")
        return self


class NodeCounts(StrictModel):
    total: Count
    queued: Count
    running: Count
    completed: Count
    failed: Count
    cancelled: Count
    interrupted: Count
    reused: Count

    @model_validator(mode="after")
    def reconciles(self) -> Self:
        if (
            self.total
            != sum(
                value
                for key, value in self.model_dump().items()
                if key not in ("total", "reused")
            )
            or self.reused > self.completed
        ):
            raise ValueError("invalid node counts")
        return self


class ReportNodes(StrictModel):
    judgments: NodeCounts
    composition: NodeCounts


class CollectionGap(StrictModel):
    """A platform item that ended without contributing searchable content."""

    position: Count
    platform: SearchPlatform
    status: Literal["failed", "skipped", "cancelled"]
    run_status: SearchRunStatus | None
    failure_reason: SearchFailureReason | None


class ReportUsage(StrictModel):
    judgment: AnalysisUsage
    composition: AnalysisUsage
    total: AnalysisUsage


class ReportRun(StrictModel):
    id: PositiveId
    request_id: str | None
    trigger: Literal["automatic", "interval", "manual", "retry"]
    initial_job_id: PositiveId | None
    completion_event_id: PositiveId | None
    parent_report_id: PositiveId | None
    selection: Annotated[
        JobSelection | WorkflowSelection | IntervalSelection | ExplicitSelection,
        Field(discriminator="kind"),
    ]
    status: ReportStatus
    revision: PositiveId
    configuration_revision: PositiveId
    base_url: str
    model: str
    prompt: ReportPrompt
    coverage: Coverage
    nodes: ReportNodes
    usage: ReportUsage
    collection_gaps: tuple[CollectionGap, ...] = ()
    root_section_id: PositiveId | None
    empty_reason: (
        Literal["no_ready_sources", "no_relevant_sources", "text_insufficient"] | None
    )
    queue_reason: Literal["ai_operation_active"] | None
    recovery_reason: Literal["backend_restart"] | None
    model_retry_notice: ModelRetryNotice | None = None
    error: ReportFailure | None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None
    finished_at: UtcTimestamp | None

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        ProviderIntent(
            base_url=self.base_url,
            model=self.model,
            configuration_revision=self.configuration_revision,
        )
        if self.request_id is not None:
            RequestIntent(request_id=self.request_id)
        active = self.status in ACTIVE_REPORTS
        if active != (self.finished_at is None):
            raise ValueError("invalid report time")
        if (self.status == "completed") != (self.root_section_id is not None):
            raise ValueError("invalid report root")
        if (self.status == "empty") != (self.empty_reason is not None):
            raise ValueError("invalid empty report")
        if self.empty_reason == "no_ready_sources" and self.coverage.ready:
            raise ValueError("invalid empty ready coverage")
        if self.empty_reason in {"no_ready_sources", "text_insufficient"} and (
            self.coverage.ready or self.usage.total.attempted_requests
        ):
            raise ValueError("invalid empty input coverage")
        if self.empty_reason == "no_relevant_sources" and (
            self.coverage.ready == 0 or self.coverage.relevant or self.coverage.failed
        ):
            raise ValueError("invalid empty relevance coverage")
        if not active and self.queue_reason is not None:
            raise ValueError("terminal queue reason")
        if self.recovery_reason is not None and self.status != "interrupted":
            raise ValueError("invalid recovery status")
        if self.coverage.ready != self.nodes.judgments.total:
            raise ValueError("invalid judgment coverage")
        if not active and (
            self.coverage.pending
            + self.coverage.judging
            + self.nodes.judgments.queued
            + self.nodes.judgments.running
            + self.nodes.composition.queued
            + self.nodes.composition.running
        ):
            raise ValueError("unsettled terminal report")
        if self.trigger == "automatic":
            if self.request_id is not None or self.parent_report_id is not None:
                raise ValueError("invalid automatic origin")
            legacy = self.selection.kind == "initial_job"
            workflow = self.selection.kind == "workflow_run"
            if not (legacy or workflow) or legacy != (
                self.completion_event_id is not None
            ):
                raise ValueError("invalid automatic selection")
        elif self.request_id is None or self.completion_event_id is not None:
            raise ValueError("invalid explicit origin")
        if (self.trigger == "retry") != (self.parent_report_id is not None):
            raise ValueError("invalid retry origin")
        if self.parent_report_id is not None and self.parent_report_id >= self.id:
            raise ValueError("invalid retry ancestry")
        if self.selection.kind == "initial_job":
            if self.selection.job_id != self.initial_job_id:
                raise ValueError("invalid job selection")
        elif self.selection.kind == "workflow_run":
            if self.completion_event_id is not None:
                raise ValueError("invalid workflow selection")
        elif self.initial_job_id is not None:
            raise ValueError("invalid interval origin")
        elif self.selection.kind == "first_seen_interval" and datetime.fromisoformat(
            self.selection.first_seen_from
        ) >= datetime.fromisoformat(self.selection.first_seen_to):
            raise ValueError("invalid stored interval")
        if self.trigger == "interval" and self.selection.kind != "first_seen_interval":
            raise ValueError("invalid interval selection")
        if self.trigger == "manual" and self.selection.kind != "explicit":
            raise ValueError("invalid manual selection")
        if self.selection.kind == "explicit" and self.coverage.total != len(
            self.selection.result_ids
        ):
            raise ValueError("invalid selected coverage")
        if self.finished_at and datetime.fromisoformat(
            self.finished_at
        ) < datetime.fromisoformat(self.created_at):
            raise ValueError("invalid report time order")
        return self


class Judgment(StrictModel):
    decision: Literal["relevant", "irrelevant", "uncertain"]
    reason: str = Field(min_length=1, max_length=600)
    _prose = field_validator("reason")(valid_prose)


class ReportSource(StrictModel):
    position: Count
    source: AnalysisSource
    evidence_coverage: EvidenceCoverage | None = None
    first_seen_at: UtcTimestamp
    initial_attempt_id: PositiveId | None
    initial_status: AttemptStatus | None
    unavailable_reason: (
        Literal[
            "not_analysed",
            "legacy_only",
            "in_progress",
            "input_incomplete",
            "unsupported",
            "failed",
            "cancelled",
            "interrupted",
            "stale_evidence",
        ]
        | None
    )
    state: SourceState
    judgment: Judgment | None
    judgment_node_id: PositiveId | None
    error: SummaryFailure | None

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        unavailable = self.state == "unavailable"
        if unavailable != (self.unavailable_reason is not None):
            raise ValueError("invalid evidence state")
        if unavailable and (
            self.judgment_node_id is not None or self.error is not None
        ):
            raise ValueError("unavailable judgment projection")
        if unavailable != (self.evidence_coverage is None):
            raise ValueError("invalid evidence coverage projection")
        if (self.initial_attempt_id is None) != (self.initial_status is None):
            raise ValueError("invalid initial attempt projection")
        if unavailable:
            expected = {
                "not_analysed": None,
                "legacy_only": None,
                "stale_evidence": "completed",
            }.get(self.unavailable_reason, self.unavailable_reason)
            if self.unavailable_reason == "in_progress":
                if self.initial_status not in ("queued", "acquiring", "analysing"):
                    raise ValueError("invalid active initial evidence")
            elif self.initial_status != expected:
                raise ValueError("invalid unavailable evidence")
        if not unavailable and (
            self.initial_status != "completed"
            or self.initial_attempt_id is None
            or self.judgment_node_id is None
        ):
            raise ValueError("missing completed evidence")
        semantic = self.state in ("relevant", "irrelevant", "uncertain")
        if semantic != (self.judgment is not None) or (
            self.judgment is not None and self.judgment.decision != self.state
        ):
            raise ValueError("invalid judgment state")
        return self


class ReportParagraph(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    source_ids: list[PositiveId] = Field(min_length=1, max_length=8)
    _prose = field_validator("text")(valid_prose)


class ReportDocument(StrictModel):
    overview: str = Field(min_length=1, max_length=2000)
    items: list[ReportParagraph] = Field(min_length=1, max_length=16)
    _prose = field_validator("overview")(valid_prose)


class OverviewParagraph(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    section_ids: list[PositiveId] = Field(min_length=1, max_length=8)
    source_ids: list[PositiveId] | None = Field(
        default=None, min_length=1, max_length=128
    )
    _prose = field_validator("text")(valid_prose)


class OverviewDocument(StrictModel):
    overview: str = Field(min_length=1, max_length=2000)
    items: list[OverviewParagraph] = Field(min_length=1, max_length=16)
    _prose = field_validator("overview")(valid_prose)


class CitationSource(StrictModel):
    position: Count
    source: AnalysisSource


class ChildSection(StrictModel):
    id: PositiveId
    kind: Literal["leaf", "overview"]
    position: Count
    level: Count
    source_count: PositiveId
    overview: str = Field(min_length=1, max_length=2000)
    _prose = field_validator("overview")(valid_prose)


class ReportSection(StrictModel):
    id: PositiveId
    report_id: PositiveId
    kind: Literal["leaf", "overview"]
    position: Count
    level: Count
    status: NodeStatus
    source_count: PositiveId
    document: ReportDocument | None
    overview_document: OverviewDocument | None
    sources: list[CitationSource] = Field(max_length=8)
    children: list[ChildSection] = Field(max_length=8)
    attempted: bool
    usage: TokenUsage | None
    reused_from_node_id: PositiveId | None
    error: SummaryFailure | None

    @model_validator(mode="after")
    def consistent_section(self) -> Self:
        if self.reused_from_node_id is not None and self.reused_from_node_id >= self.id:
            raise ValueError("invalid canonical node order")
        if self.kind == "leaf":
            if (
                self.level != 0
                or self.children
                or len(self.sources) != self.source_count
                or not self.sources
                or self.overview_document is not None
            ):
                raise ValueError("invalid leaf membership")
            document, field, allowed = (
                self.document,
                "source_ids",
                {s.source.result_id for s in self.sources},
            )
            if len(allowed) != len(self.sources):
                raise ValueError("duplicate source")
        else:
            if (
                self.level == 0
                or self.sources
                or not 2 <= len(self.children) <= 8
                or self.document is not None
            ):
                raise ValueError("invalid overview membership")
            document, field, allowed = (
                self.overview_document,
                "section_ids",
                {c.id for c in self.children},
            )
            if (
                len(allowed) != len(self.children)
                or sum(c.source_count for c in self.children) != self.source_count
                or any(c.level >= self.level for c in self.children)
            ):
                raise ValueError("invalid child membership")
        if (self.status == "completed") != (document is not None):
            raise ValueError("invalid section output")
        if document:
            cited = set()
            for item in document.items:
                ids = getattr(item, field)
                if len(set(ids)) != len(ids) or not set(ids) <= allowed:
                    raise ValueError("invalid citations")
                cited.update(ids)
            if self.kind == "leaf" and cited != allowed:
                raise ValueError("omitted citations")
        if self.usage is not None and not self.attempted:
            raise ValueError("usage without attempt")
        if self.reused_from_node_id is not None and (
            self.status != "completed" or self.attempted or self.usage is not None
        ):
            raise ValueError("invalid reuse")
        return self


class ReportList(StrictModel):
    reports: list[ReportRun]
    next_before_id: PositiveId | None


class ReportSourceList(StrictModel):
    items: list[ReportSource]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count


class ReportSectionList(StrictModel):
    sections: list[ReportSection]
    total: Count
    limit: int = Field(ge=1, le=100)
    offset: Count
