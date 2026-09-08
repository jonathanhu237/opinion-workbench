"""Constant-only public errors for shared analysis resources."""

from typing import Literal

from longtian_api.schemas.ai_settings import AIErrorCode
from longtian_api.schemas.ai_summaries import StrictModel

AnalysisErrorCode = Literal[
    "report_generation_not_found",
    "report_generation_active",
    "no_eligible_contents",
    "result_not_found",
    "content_analysis_not_found",
    "analysis_prompt_changed",
    "analysis_policy_changed",
    "content_analysis_request_conflict",
    "content_analysis_selection_conflict",
    "invalid_analysis_prompt",
    "invalid_result_interval",
    "analysis_storage_unavailable",
    "content_analysis_unavailable",
]
ERRORS = {
    "report_generation_not_found": (404, "未找到报告生成任务。"),
    "report_generation_active": (409, "已有报告正在生成，请等待当前任务结束后再提交。"),
    "no_eligible_contents": (
        409,
        "当前没有符合所选规则的内容，请刷新后重新选择。",
    ),
    "result_not_found": (404, "未找到采集内容。"),
    "content_analysis_not_found": (404, "未找到初步分析记录。"),
    "analysis_prompt_changed": (409, "提示词已更新，请刷新后重试。"),
    "analysis_policy_changed": (409, "自动分析设置已更新，请刷新后重试。"),
    "content_analysis_request_conflict": (409, "此请求标识已用于其他分析操作。"),
    "content_analysis_selection_conflict": (
        409,
        "所选内容状态已变化，请刷新并使用对应的重试或重新分析操作。",
    ),
    "invalid_analysis_prompt": (422, "提示词须为 1 至 8000 字的有效非空文本。"),
    "invalid_result_interval": (422, "首次采集时间范围不正确。"),
    "analysis_storage_unavailable": (503, "暂时无法读取或保存分析数据，请稍后重试。"),
    "content_analysis_unavailable": (503, "初步分析服务暂时不可用，请稍后重试。"),
}


class AnalysisError(Exception):
    def __init__(self, code: AnalysisErrorCode):
        self.code = code
        self.status_code, self.message = ERRORS[code]
        super().__init__(code)


class AnalysisErrorDetail(StrictModel):
    code: AnalysisErrorCode | AIErrorCode
    message: str


class AnalysisErrorResponse(StrictModel):
    detail: AnalysisErrorDetail
