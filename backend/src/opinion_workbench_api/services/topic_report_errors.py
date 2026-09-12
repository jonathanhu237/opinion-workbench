"""Constant-only report errors; never expose model or storage payloads."""

from typing import Literal

from opinion_workbench_api.schemas.ai_settings import AIErrorCode
from opinion_workbench_api.schemas.ai_summaries import StrictModel
from opinion_workbench_api.schemas.topic_reports import ReportFailure
from opinion_workbench_api.services.ai_errors import AI_ERROR_CONTRACTS
from opinion_workbench_api.services.analysis_errors import AnalysisErrorCode

ReportErrorCode = Literal[
    "topic_report_not_found",
    "topic_report_section_not_found",
    "topic_report_changed",
    "topic_report_request_conflict",
    "topic_report_not_terminal",
    "topic_report_not_active",
    "invalid_report_interval",
    "invalid_report_selection",
    "topic_report_storage_unavailable",
    "topic_report_unavailable",
]

CONFIGURATION_FAILURES = (
    "ai_configuration_required",
    "ai_configuration_changed",
    "ai_credentials_unavailable",
    "ai_settings_storage_unavailable",
)


def configuration_failure(code):
    if code not in CONFIGURATION_FAILURES:
        raise ValueError("invalid configuration failure")
    return ReportFailure(
        stage="execution", code=code, message=AI_ERROR_CONTRACTS[code][1]
    )


ERRORS = {
    "topic_report_not_found": (404, "未找到该文本报告。"),
    "topic_report_section_not_found": (404, "未找到该报告章节。"),
    "topic_report_changed": (409, "报告状态已更新，请刷新后重试。"),
    "topic_report_request_conflict": (409, "请求标识已用于其他报告操作，请重新确认。"),
    "topic_report_not_terminal": (409, "报告仍在处理中，请先等待或取消。"),
    "topic_report_not_active": (409, "报告已结束，无需取消。"),
    "invalid_report_interval": (422, "请选择有效的首次入库时间范围。"),
    "invalid_report_selection": (
        422,
        "选中的内容已不存在或无法读取，请刷新后重新选择。",
    ),
    "topic_report_storage_unavailable": (
        503,
        "文本报告数据暂时无法读取或保存，请稍后重试。",
    ),
    "topic_report_unavailable": (503, "文本报告服务暂时不可用，请稍后重试。"),
}


class TopicReportError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status_code, self.message = ERRORS[code]
        super().__init__(code)


class ReportErrorDetail(StrictModel):
    code: ReportErrorCode | AnalysisErrorCode | AIErrorCode
    message: str


class ReportErrorResponse(StrictModel):
    detail: ReportErrorDetail
