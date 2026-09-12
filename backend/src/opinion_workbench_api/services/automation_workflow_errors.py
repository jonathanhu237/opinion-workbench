"""Constant-only public errors for automatic workflow operations."""

from typing import Literal

from opinion_workbench_api.schemas.ai_summaries import StrictModel

AutomationErrorCode = Literal[
    "invalid_request",
    "automation_task_not_found",
    "automation_task_name_conflict",
    "automation_task_changed",
    "automation_invalid_schedule",
    "automation_invalid_goal",
    "automation_rule_not_found",
    "automation_rule_disabled",
    "automation_rule_invalid",
    "automation_run_active",
    "automation_run_not_found",
    "automation_run_changed",
    "automation_run_not_retryable",
    "automation_run_not_active",
    "automation_request_conflict",
    "automation_storage_unavailable",
    "automation_unavailable",
    "automation_stage_failed",
    "ai_configuration_required",
    "ai_configuration_changed",
]

ERRORS: dict[str, tuple[int, str]] = {
    "invalid_request": (422, "请求内容不正确。"),
    "automation_task_not_found": (404, "未找到自动任务。"),
    "automation_task_name_conflict": (409, "已存在同名自动任务。"),
    "automation_task_changed": (409, "自动任务已更新，请刷新后重试。"),
    "automation_invalid_schedule": (422, "自动任务计划不正确，请检查时间和时区。"),
    "automation_invalid_goal": (422, "请输入有效的舆情分析目标。"),
    "automation_rule_not_found": (404, "未找到该监控规则。"),
    "automation_rule_disabled": (409, "该监控规则已停用，请先启用后再保存。"),
    "automation_rule_invalid": (422, "监控规则当前不可用于自动任务。"),
    "automation_run_active": (409, "该自动任务已有运行中的实例，请稍后重试。"),
    "automation_run_not_found": (404, "未找到自动任务运行记录。"),
    "automation_run_changed": (409, "运行状态已更新，请刷新后重试。"),
    "automation_run_not_retryable": (409, "该运行当前不能从失败阶段重试。"),
    "automation_run_not_active": (409, "该运行已经结束，无需取消。"),
    "automation_request_conflict": (
        409,
        "请求标识已用于其他自动任务操作，请重新确认。",
    ),
    "automation_storage_unavailable": (
        503,
        "自动任务数据暂时无法读取或保存，请稍后重试。",
    ),
    "automation_unavailable": (503, "自动任务服务暂时不可用，请稍后重试。"),
    "automation_stage_failed": (409, "自动任务阶段未完成，请从失败阶段重试。"),
    "ai_configuration_required": (409, "请先配置可用的 AI 服务。"),
    "ai_configuration_changed": (409, "AI 配置已变化，请重新运行自动任务。"),
}


class AutomationWorkflowError(Exception):
    def __init__(self, code: AutomationErrorCode):
        super().__init__(code)
        self.code = code
        self.status_code, self.message = ERRORS[code]


class AutomationErrorDetail(StrictModel):
    code: AutomationErrorCode
    message: str


class AutomationErrorResponse(StrictModel):
    detail: AutomationErrorDetail
