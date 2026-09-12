from typing import Literal

from pydantic import Field, model_validator

from opinion_workbench_api.schemas.content_analyses import StrictModel


class CachedMedia(StrictModel):
    position: int = Field(ge=0, le=24)
    kind: Literal["image", "video"]
    state: Literal[
        "cached",
        "not_acquired",
        "not_stored",
        "missing",
        "corrupt",
        "cleared",
        "unavailable",
    ]
    byte_size: int | None = Field(ge=1, le=6291456)

    @model_validator(mode="after")
    def validate_present_file(self):
        if (self.state == "cached") != (self.byte_size is not None):
            raise ValueError("invalid cached file state")
        return self


class CachedMediaList(StrictModel):
    items: list[CachedMedia] = Field(max_length=25)

    @model_validator(mode="after")
    def ordered_items(self):
        if any(item.position != index for index, item in enumerate(self.items)):
            raise ValueError("invalid cache positions")
        return self


class MediaPolicyUpdate(StrictModel):
    retention_days: int = Field(ge=1, le=3650)
    capacity_mib: int = Field(ge=1, le=20480)
    expected_revision: int = Field(ge=0, le=2**53 - 1)


class MediaCleanup(StrictModel):
    expected_revision: int = Field(ge=0, le=2**53 - 1)


class MediaPolicy(StrictModel):
    retention_days: int = Field(ge=1, le=3650)
    capacity_mib: int = Field(ge=1, le=20480)
    revision: int = Field(ge=0, le=2**53 - 1)
    reserved_bytes: int = Field(ge=0, le=2**53 - 1)
    files: int = Field(ge=0, le=10000)
    pending_files: int = Field(ge=0, le=10000)


class CleanupResult(StrictModel):
    removed_files: int = Field(ge=0, le=10000)
    removed_bytes: int = Field(ge=0, le=2**53 - 1)
    deferred: bool


class MediaPolicyResult(StrictModel):
    policy: MediaPolicy
    cleanup: CleanupResult
