"""Strict AI configuration projections. Saved credentials are never serializable."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

AIErrorCode = Literal[
    "invalid_request",
    "invalid_ai_base_url",
    "invalid_ai_model",
    "invalid_ai_api_key",
    "ai_api_key_required",
    "ai_configuration_required",
    "ai_configuration_changed",
    "ai_operation_active",
    "ai_credentials_unavailable",
    "ai_settings_storage_unavailable",
    "ai_request_forbidden",
    "ai_json_required",
    "ai_destination_forbidden",
    "ai_authentication_failed",
    "ai_model_not_found",
    "ai_rate_limited",
    "ai_provider_unavailable",
    "ai_timeout",
    "ai_invalid_response",
    "ai_unsupported_input",
    "ai_request_too_large",
]


class AISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    base_url: str = Field(max_length=2048)
    model: str = Field(max_length=200)
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)


class AISettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    base_url: str | None
    model: str | None
    has_api_key: bool
    revision: int = Field(ge=0)


class AIConnectionTest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    revision: int = Field(gt=0, le=9_223_372_036_854_775_807)


class AIConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["connected"] = "connected"
    revision: int


class AIErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: AIErrorCode
    message: str


class AIErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: AIErrorDetail
