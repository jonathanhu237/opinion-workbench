"""Strict local settings and immutable snapshots for platform access pacing."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opinion_workbench_api.search_platforms import SEARCH_PLATFORMS, SearchPlatform

PLATFORM_ACCESS_DEFAULT_SECONDS = 5
PLATFORM_ACCESS_MIN_SECONDS = 1
PLATFORM_ACCESS_MAX_SECONDS = 300
MAX_SAFE_INTEGER = 2**53 - 1
PlatformAccessBasis = Literal["explicit", "upgrade_safe_default", "legacy_unavailable"]


class StrictPlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PlatformIntervals(StrictPlatformModel):
    """A complete, ordered five-platform interval map."""

    wb: int = Field(ge=PLATFORM_ACCESS_MIN_SECONDS, le=PLATFORM_ACCESS_MAX_SECONDS)
    dy: int = Field(ge=PLATFORM_ACCESS_MIN_SECONDS, le=PLATFORM_ACCESS_MAX_SECONDS)
    ks: int = Field(ge=PLATFORM_ACCESS_MIN_SECONDS, le=PLATFORM_ACCESS_MAX_SECONDS)
    xhs: int = Field(ge=PLATFORM_ACCESS_MIN_SECONDS, le=PLATFORM_ACCESS_MAX_SECONDS)
    toutiao: int = Field(ge=PLATFORM_ACCESS_MIN_SECONDS, le=PLATFORM_ACCESS_MAX_SECONDS)

    @model_validator(mode="after")
    def reject_bool_values(self):
        if any(type(value) is not int for value in self.model_dump().values()):
            raise ValueError("platform intervals must be integers")
        return self

    def for_platform(self, platform: SearchPlatform | str) -> int:
        if platform not in SEARCH_PLATFORMS:
            raise ValueError("unsupported platform")
        return int(getattr(self, platform))


class PlatformAccessSnapshot(StrictPlatformModel):
    """The pacing policy captured when a task is admitted."""

    interval_seconds: PlatformIntervals
    basis: PlatformAccessBasis

    @property
    def intervals_seconds(self) -> PlatformIntervals:
        """Compatibility spelling used by a few older internal callers."""
        return self.interval_seconds

    def for_platform(self, platform: SearchPlatform | str) -> int:
        return self.interval_seconds.for_platform(platform)


class PlatformAccessSettings(StrictPlatformModel):
    revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    interval_seconds: PlatformIntervals
    updated_at: datetime

    @property
    def intervals_seconds(self) -> PlatformIntervals:
        return self.interval_seconds


class PlatformAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    interval_seconds: PlatformIntervals


class PlatformAccessDiagnostic(StrictPlatformModel):
    """Safe evidence projected when a platform blocks an application request."""

    platform: SearchPlatform
    stage: Literal["search", "detail", "media"]
    outcome: Literal["platform_blocked_or_rate_limited"]
    basis: Literal["http_status", "explicit_platform_evidence", "browser_dom_evidence"]
    status_code: int | None = Field(default=None, ge=100, le=599)
    platform_code: str | None = Field(default=None, min_length=1, max_length=100)
    retry_after_at: datetime | None = None
    manual_challenge_required: bool = False
    observed_at: datetime

    @model_validator(mode="after")
    def normalize_timestamps(self):
        for field in ("retry_after_at", "observed_at"):
            value = getattr(self, field)
            if value is not None and value.tzinfo is None:
                object.__setattr__(self, field, value.replace(tzinfo=UTC))
        return self


def default_platform_intervals() -> PlatformIntervals:
    return PlatformIntervals(
        **{platform: PLATFORM_ACCESS_DEFAULT_SECONDS for platform in SEARCH_PLATFORMS}
    )


def default_platform_access_snapshot(
    *, basis: PlatformAccessBasis = "upgrade_safe_default"
) -> PlatformAccessSnapshot:
    return PlatformAccessSnapshot(
        interval_seconds=default_platform_intervals(), basis=basis
    )
