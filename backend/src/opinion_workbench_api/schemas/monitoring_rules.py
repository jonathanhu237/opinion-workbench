"""Public contracts for persisted monitoring rules."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MonitoringRuleErrorCode = Literal[
    "invalid_request",
    "invalid_monitoring_rule",
    "duplicate_monitoring_rule_term",
    "monitoring_rule_name_conflict",
    "monitoring_rule_not_found",
    "monitoring_rule_storage_unavailable",
]


class MonitoringRuleCreate(BaseModel):
    """Create payload; semantic validation is owned by the service."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    monitoring_objects: list[str]
    issue_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


class MonitoringRuleReplace(BaseModel):
    """Full replacement payload for one monitoring rule."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    monitoring_objects: list[str]
    issue_keywords: list[str]
    enabled: bool


class MonitoringRule(BaseModel):
    """Stable public projection without persistence internals."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: int
    name: str
    monitoring_objects: tuple[str, ...]
    issue_keywords: tuple[str, ...]
    terms: tuple[str, ...]
    enabled: bool


class MonitoringRuleListResponse(BaseModel):
    """Rules returned in stable creation order."""

    model_config = ConfigDict(extra="forbid")

    rules: list[MonitoringRule]


class MonitoringRuleErrorDetail(BaseModel):
    """Stable monitoring-rule product error."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: MonitoringRuleErrorCode
    message: str


class MonitoringRuleErrorResponse(BaseModel):
    """FastAPI-compatible documented error envelope."""

    model_config = ConfigDict(extra="forbid")

    detail: MonitoringRuleErrorDetail
