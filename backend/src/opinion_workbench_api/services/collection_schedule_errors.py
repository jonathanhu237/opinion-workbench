"""Constant-only errors; never expose rule content, paths or SQL."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ScheduleErrorCode = Literal[
    "collection_schedule_not_found",
    "collection_schedule_changed",
    "invalid_collection_interval",
    "invalid_collection_schedule",
    "monitoring_rule_not_found",
    "monitoring_rule_disabled",
    "too_many_search_terms",
    "collection_schedule_storage_unavailable",
    "collection_schedule_unavailable",
    "invalid_request",
    "ai_request_forbidden",
    "ai_json_required",
]
ERRORS = {
    "collection_schedule_not_found": (404, "未找到定时采集计划。"),
    "collection_schedule_changed": (409, "定时采集计划已更新，请刷新后重试。"),
    "invalid_collection_interval": (
        422,
        "采集间隔须为 1 至 43200 个整分钟（最多 30 天）。",
    ),
    "invalid_collection_schedule": (422, "定时采集配置不正确，请检查监控规则和平台。"),
    "monitoring_rule_not_found": (404, "未找到该监控规则。"),
    "monitoring_rule_disabled": (409, "该监控规则已停用，请先启用后再采集。"),
    "too_many_search_terms": (422, "一次最多采集 20 个搜索词，请拆分监控规则后重试。"),
    "collection_schedule_storage_unavailable": (
        503,
        "定时采集数据暂时无法读取或保存，请稍后重试。",
    ),
    "collection_schedule_unavailable": (503, "定时采集服务暂时不可用，请稍后重试。"),
}


class CollectionScheduleError(Exception):
    def __init__(self, code: ScheduleErrorCode):
        super().__init__(code)
        self.code = code
        self.status_code, self.message = ERRORS[code]


class CollectionScheduleErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ScheduleErrorCode
    message: str


class CollectionScheduleErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detail: CollectionScheduleErrorDetail
