"""Independent business instructions and revision-bound automatic authorization."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from opinion_workbench_api.schemas.ai_summaries import StrictModel

MAX_SAFE_INTEGER = 9_007_199_254_740_991
PositiveId = Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
Count = Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]
PromptStage = Literal["initial", "report"]
INITIAL_SCHEMA_VERSION = "initial-understanding-v1"
REPORT_SCHEMA_VERSION = "topic-report-v1"
PromptChoiceMode = Literal["default", "custom"]
PromptSnapshotMode = Literal["default", "custom", "legacy"]
DEFAULT_INITIAL_INSTRUCTIONS = (
    "理解每条来源的标题、正文、话题标签和平台文字说明，概括来源陈述，保留地点线索、"
    "时间和不确定性。只根据实际提供的文字判断，不推测图片、视频或音频中没有转写的内容；"
    "不要按地域或主题预先排除内容，不把来源指控当作已核实事实。"
)
DEFAULT_REPORT_INSTRUCTIONS = (
    "根据保存的来源材料和本次报告提示词中指定的关注对象与分析要求形成舆情报告，"
    "证据不足时保留不确定性。仅对可由原帖文字支持的判断撰写带原文引用的分析，"
    "保留时间和来源归属，不从采集对象或采集批次推断报告关注范围。"
)


class PromptVersion(StrictModel):
    id: PositiveId
    # ``version_id`` and ``mode`` are additive projection fields.  Existing
    # historical rows only have the immutable numeric id; new admissions fill
    # both fields so callers can display the effective source without treating
    # a mutable settings pointer as execution authority.
    version_id: PositiveId | None = None
    mode: PromptSnapshotMode | None = None
    stage: PromptStage
    instructions: str = Field(min_length=1, max_length=8000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: Literal["initial-understanding-v1", "topic-report-v1"]
    created_at: datetime

    @field_validator("instructions")
    @classmethod
    def valid_instructions(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid prompt instructions")
        value.encode("utf-8", errors="strict")
        return value

    @property
    def effective_version_id(self) -> int:
        return self.version_id or self.id


class PromptChoiceDefault(StrictModel):
    mode: Literal["default"]


class PromptChoiceCustom(StrictModel):
    mode: Literal["custom"]
    instructions: str = Field(min_length=1, max_length=8000)

    @field_validator("instructions")
    @classmethod
    def valid_instructions(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid prompt instructions")
        value.encode("utf-8", errors="strict")
        return value


PromptChoice = Annotated[
    PromptChoiceDefault | PromptChoiceCustom,
    Field(discriminator="mode"),
]


class PromptSnapshot(StrictModel):
    """The exact immutable prompt used by a submitted operation."""

    mode: PromptSnapshotMode
    version_id: PositiveId
    instructions: str = Field(min_length=1, max_length=8000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: Literal["initial-understanding-v1", "topic-report-v1"]

    @field_validator("instructions")
    @classmethod
    def valid_instructions(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid prompt instructions")
        value.encode("utf-8", errors="strict")
        return value

    @model_validator(mode="after")
    def valid_hash(self) -> Self:
        import hashlib

        if (
            hashlib.sha256(self.instructions.encode("utf-8")).hexdigest()
            != self.content_hash
        ):
            raise ValueError("invalid prompt hash")
        return self


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
