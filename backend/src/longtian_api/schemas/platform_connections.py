"""Public contracts for the platform account connection center."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PlatformId = Literal["wb", "dy", "ks", "xhs", "toutiao"]
PlatformAvailability = Literal["enabled", "coming_soon"]
PlatformConnectionStatus = Literal[
    "not_checked",
    "checking",
    "action_required",
    "connected",
    "disconnected",
    "failed",
    "coming_soon",
]
PlatformConnectionGuidance = Literal[
    "none",
    "enable_remote_debugging",
    "approve_connection",
    "complete_login",
    "retry",
]
PlatformConnectionErrorCode = Literal[
    "platform_not_found",
    "platform_not_available",
    "connection_attempt_active",
]


class PlatformConnection(BaseModel):
    """A safe, credential-free projection of one platform connection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: PlatformId
    display_name: str
    availability: PlatformAvailability
    status: PlatformConnectionStatus
    guidance: PlatformConnectionGuidance
    last_checked_at: datetime | None
    active_attempt_id: UUID | None


class PlatformConnectionListResponse(BaseModel):
    """Ordered platform catalog returned to the frontend."""

    model_config = ConfigDict(extra="forbid")

    platforms: list[PlatformConnection]


class PlatformConnectionAttemptResponse(BaseModel):
    """Accepted asynchronous connection attempt."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID
    platform: PlatformConnection


class PlatformConnectionErrorDetail(BaseModel):
    """Stable product error without process or credential details."""

    model_config = ConfigDict(extra="forbid")

    code: PlatformConnectionErrorCode
    message: str


class PlatformConnectionErrorResponse(BaseModel):
    """FastAPI-compatible error envelope used in OpenAPI responses."""

    model_config = ConfigDict(extra="forbid")

    detail: PlatformConnectionErrorDetail
