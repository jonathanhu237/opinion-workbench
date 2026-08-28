"""Independent business instructions and revision-bound automatic authorization."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from longtian_api.schemas.ai_summaries import StrictModel

MAX_SAFE_INTEGER = 9_007_199_254_740_991
PositiveId = Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
Count = Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]
PromptStage = Literal["initial", "report"]
INITIAL_SCHEMA_VERSION = "initial-understanding-v1"
REPORT_SCHEMA_VERSION = "topic-report-v1"
DEFAULT_INITIAL_INSTRUCTIONS = (
    "理解每条来源的完整文字和实际媒体，概括来源陈述，保留地点线索、时间、"
    "画面及音频观察和不确定性。不要按地域或主题预先排除内容，不把来源指控当作已核实事实。"
)
DEFAULT_REPORT_INSTRUCTIONS = (
    "根据保存的来源材料判断其是否涉及深圳市坪山区龙田街道。区分同名地点，"
    "证据不足时保留不确定性。仅对相关来源撰写带原文引用的分析，保留时间和来源归属。"
)


class PromptVersion(StrictModel):
    id: PositiveId
    stage: PromptStage
    instructions: str = Field(min_length=1, max_length=8000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: Literal["initial-understanding-v1", "topic-report-v1"]
    created_at: datetime


class PromptUpdate(StrictModel):
    expected_version_id: PositiveId
    instructions: str


class AutomationUpdate(StrictModel):
    expected_revision: PositiveId
    enabled: bool
    configuration_revision: PositiveId | None

    @model_validator(mode="after")
    def valid_revision(self) -> Self:
        if self.enabled != (self.configuration_revision is not None):
            raise ValueError("invalid authorization revision")
        return self


class AutomationSettings(StrictModel):
    enabled: bool
    revision: PositiveId
    approved_configuration_revision: PositiveId | None
    activation_content_id: Count
    available: bool


class AnalysisSettings(StrictModel):
    initial_prompt: PromptVersion
    report_prompt: PromptVersion
    automation: AutomationSettings
