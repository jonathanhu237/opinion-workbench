"""Constant-only errors shared by the configuration and transport boundaries."""

import math
import re

from longtian_api.schemas.ai_settings import AIErrorCode

_PROVIDER_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}\Z")
_QUOTA_CODES = frozenset(
    {
        "insufficient_quota",
        "quota_exceeded",
        "billing_hard_limit",
        "no_balance",
        "insufficient_balance",
        "account_deactivated",
    }
)
# Provider codes are deliberately allow-listed.  HTTP 429 alone is the
# transport's "rate limit or quota" bucket and is not enough evidence to
# replay a paid request safely.
_TRANSIENT_RATE_LIMIT_CODES = frozenset(
    {
        "rate_limit",
        "rate_limited",
        "rate_limit_error",
        "rate_limit_exceeded",
        "request_rate_limited",
        "requests_rate_limited",
        "too_many_requests",
        "throttled",
        "throttled_error",
        "throttling",
        "throttling.ratequota",
        "throttling.request",
        "throttling.user",
    }
)

AI_ERROR_CONTRACTS: dict[AIErrorCode, tuple[int, str]] = {
    "invalid_request": (422, "请求内容不正确。"),
    "invalid_ai_base_url": (
        422,
        "请输入有效的公网 HTTPS Base URL，不含认证信息或查询参数。",
    ),
    "invalid_ai_model": (422, "请输入有效的模型名称（最多 200 字符）。"),
    "invalid_ai_api_key": (422, "API Key 不能为空，也不能包含空白或控制字符。"),
    "ai_api_key_required": (422, "首次保存或更改 Base URL 时，请重新输入 API Key。"),
    "ai_configuration_required": (409, "请先保存 AI 配置。"),
    "ai_configuration_changed": (409, "配置已更新，请重新加载后再测试。"),
    "ai_operation_active": (409, "AI 操作正在进行，请结束后再试。"),
    "ai_credentials_unavailable": (
        503,
        "API Key 无法安全读取或保存，请检查本机存储后重新输入。",
    ),
    "ai_settings_storage_unavailable": (503, "AI 配置暂时无法读取或保存，请稍后重试。"),
    "ai_request_forbidden": (403, "请从本机应用页面操作 AI 配置。"),
    "ai_json_required": (415, "请使用 JSON 提交 AI 配置。"),
    "ai_destination_forbidden": (422, "模型地址必须指向公网 HTTPS 服务。"),
    "ai_authentication_failed": (502, "模型服务未接受 API Key，请检查密钥和服务区域。"),
    "ai_model_not_found": (502, "模型或接口不存在，请检查 Base URL 和模型名称。"),
    "ai_rate_limited": (429, "模型服务限流或额度不足，请检查后稍后重试。"),
    "ai_provider_unavailable": (503, "模型服务暂时无法连接，请稍后重试。"),
    "ai_timeout": (504, "模型请求超时，请稍后重试。"),
    "ai_invalid_response": (502, "模型未返回完整有效的文本响应，请检查接口兼容性。"),
    "ai_unsupported_input": (502, "模型服务不支持当前请求格式，请检查接口兼容性。"),
    "ai_request_too_large": (413, "模型请求超出服务限制。"),
}


def transient_rate_limit_evidence(
    provider_code: str | None, retry_after_seconds: float | None
) -> bool:
    """Classify already-bounded provider metadata without HTTP assumptions."""
    normalized = provider_code.lower() if isinstance(provider_code, str) else None
    if normalized in _QUOTA_CODES:
        return False
    return bool(
        normalized in _TRANSIENT_RATE_LIMIT_CODES
        or retry_after_seconds is not None
    )


class AIError(Exception):
    def __init__(
        self,
        code: AIErrorCode,
        *,
        provider_status_code: int | None = None,
        provider_code: str | None = None,
        retry_after_seconds: float | None = None,
        usage: object | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code, self.message = AI_ERROR_CONTRACTS[code]
        self.provider_status_code = (
            provider_status_code
            if type(provider_status_code) is int and 100 <= provider_status_code <= 599
            else None
        )
        self.provider_code = (
            provider_code
            if isinstance(provider_code, str)
            and _PROVIDER_CODE.fullmatch(provider_code)
            else None
        )
        self.retry_after_seconds = (
            retry_after_seconds
            if type(retry_after_seconds) in (int, float)
            and math.isfinite(retry_after_seconds)
            and 0 <= retry_after_seconds <= 86_400
            else None
        )
        # A provider can expose accounting even when it rejects a retryable
        # request. Keep the value opaque at this layer to avoid importing the
        # transport module (which imports AIError), and validate it when the
        # durable attempt history is written.
        self.usage = usage

    @property
    def transient_rate_limit(self) -> bool:
        """Whether the error contains enough evidence for a bounded replay.

        The public error code intentionally combines rate limiting and quota
        exhaustion.  A bare 429 (or an unknown provider code) is therefore
        ambiguous and must remain a single, accounted-for attempt.  A known
        transient code or a server-supplied Retry-After is sufficient unless a
        known quota/account code says otherwise.
        """
        if self.code != "ai_rate_limited":
            return False
        return transient_rate_limit_evidence(
            self.provider_code, self.retry_after_seconds
        )


# Definite provider/configuration-wide failures, not a malformed single answer
# or a one-off item timeout. This policy is opt-in for the new manual flow.
MANUAL_SYSTEMIC_AI_FAILURES = frozenset(
    {
        "ai_configuration_required",
        "ai_configuration_changed",
        "ai_credentials_unavailable",
        "ai_settings_storage_unavailable",
        "ai_authentication_failed",
        "ai_model_not_found",
        "ai_destination_forbidden",
        "ai_rate_limited",
    }
)
