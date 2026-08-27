"""Constant-only errors shared by the configuration and transport boundaries."""

from longtian_api.schemas.ai_settings import AIErrorCode

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


class AIError(Exception):
    def __init__(self, code: AIErrorCode) -> None:
        super().__init__(code)
        self.code = code
        self.status_code, self.message = AI_ERROR_CONTRACTS[code]
