"""Constant-only public admission and durable summary failures."""

from longtian_api.schemas.ai_summaries import FailureCode, FailureStage, SummaryFailure
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS

SUMMARY_ERRORS = {
    "search_run_not_found": (404, "采集任务不存在。"),
    "ai_summary_not_found": (404, "汇总记录不存在。"),
    "ai_summary_source_active": (409, "采集任务尚未结束，请结束后再生成汇总。"),
    "ai_summary_request_conflict": (409, "此请求已用于其他汇总，请刷新后重试。"),
    "browser_operation_active": (409, "浏览器正在执行其他操作，请结束后再试。"),
    "ai_summary_empty_source": (422, "采集任务没有结果，暂时无法生成汇总。"),
    "ai_summary_source_limit": (422, "一次最多汇总 100 条内容，请缩小采集范围。"),
    "ai_summary_storage_unavailable": (503, "汇总记录暂时无法读取或保存，请稍后重试。"),
    "ai_summary_unavailable": (503, "汇总服务暂时不可用，请稍后重试。"),
}

FAILURE_MESSAGES: dict[FailureCode, str] = {
    "input_incomplete": "原文或图片、视频不完整，未提交模型分析。",
    "source_changed": "原始内容已更新，请重新生成汇总。",
    "source_active": "采集任务重新开始，暂未读取这条内容。",
    "browser_operation_active": "浏览器正在执行其他操作，请结束后重新生成汇总。",
    "acquisition_failed": "原文暂时无法读取，请检查平台登录或验证状态。",
    "source_content_unavailable": "原帖已删除或不可读取，未使用搜索摘要代替正文。",
    "platform_not_supported": (
        "该平台尚未接入正文和媒体补全；已有内容及成功总结仍可使用。"
    ),
    "source_structure_changed": "原文返回结构无法识别，未提交模型。",
    "acquisition_timed_out": "原文获取超过本次时限，未自动重试。",
    "stored_content_unavailable": (
        "已保存材料不足以分析，且此获取路径尚未接入；未访问平台账号。"
    ),
    "invalid_enrichment": "原文数据未通过校验，未提交模型分析。",
    "unsupported_model": "当前模型尚未支持此类多模态输入，请检查 AI 配置。",
    "request_too_large": "内容超过本次分析限制，未提交模型。",
    "invalid_json": "模型返回的内容不是有效 JSON，请重新生成汇总。",
    "invalid_schema": "模型返回的分析格式不正确，请重新生成汇总。",
    "invalid_citations": "模型返回的引用不正确，请重新生成汇总。",
    "credential_leakage": "模型返回内容未通过安全检查，已停止保存。",
    "cancelled": "已取消。",
    "interrupted": "上次运行已中断，请重新生成汇总。",
    "internal_error": "分析暂时无法完成，请重新生成汇总。",
    "storage_unavailable": "分析结果暂时无法保存，请检查本机存储。",
    **{
        code: message
        for code, (_, message) in AI_ERROR_CONTRACTS.items()
        if code
        in (
            "ai_destination_forbidden",
            "ai_authentication_failed",
            "ai_model_not_found",
            "ai_rate_limited",
            "ai_provider_unavailable",
            "ai_timeout",
            "ai_invalid_response",
            "ai_unsupported_input",
            "ai_request_too_large",
        )
    },
}


class SummaryError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.status_code, self.message = SUMMARY_ERRORS[code]


def failure(stage: FailureStage, code: FailureCode) -> SummaryFailure:
    return SummaryFailure(stage=stage, code=code, message=FAILURE_MESSAGES[code])
