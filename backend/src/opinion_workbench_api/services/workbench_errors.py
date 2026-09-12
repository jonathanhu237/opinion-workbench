"""Constant-only homepage projection errors."""

from typing import Literal

from opinion_workbench_api.schemas.ai_summaries import StrictModel

WorkbenchErrorCode = Literal["workbench_storage_unavailable", "workbench_unavailable"]

ERRORS = {
    "workbench_storage_unavailable": (
        503,
        "工作台数据暂时无法读取，请稍后重试。",
    ),
    "workbench_unavailable": (503, "工作台服务暂时不可用，请稍后重试。"),
}


class WorkbenchError(Exception):
    def __init__(self, code: WorkbenchErrorCode):
        super().__init__(code)
        self.code = code
        self.status_code, self.message = ERRORS[code]


class WorkbenchErrorDetail(StrictModel):
    code: WorkbenchErrorCode
    message: str


class WorkbenchErrorResponse(StrictModel):
    detail: WorkbenchErrorDetail
