"""Strict, local-only access to non-sensitive portable UI preferences."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator

from longtian_api.api.v1.ai_settings import no_store, require_local_mutation
from longtian_api.services.summary_preferences import SummaryPreferenceService


class SummaryPreference(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    summary_concurrency: int

    @field_validator("summary_concurrency")
    @classmethod
    def allowed(cls, value: int) -> int:
        if value not in (1, 2, 4, 8, 16):
            raise ValueError("invalid summary concurrency")
        return value


router = APIRouter(tags=["summary-preferences"], dependencies=[Depends(no_store)])


def service(request: Request) -> SummaryPreferenceService:
    preferences = getattr(request.app.state, "summary_preference_service", None)
    if preferences is None:
        raise HTTPException(status_code=503, detail="偏好存储暂不可用。")
    return preferences


@router.get("/summary-preferences", response_model=SummaryPreference)
def read(preferences: Annotated[SummaryPreferenceService, Depends(service)]):
    return SummaryPreference(summary_concurrency=preferences.read())


@router.put(
    "/summary-preferences",
    dependencies=[Depends(require_local_mutation)],
    response_model=SummaryPreference,
)
def update(
    payload: SummaryPreference,
    preferences: Annotated[SummaryPreferenceService, Depends(service)],
):
    try:
        return SummaryPreference(
            summary_concurrency=preferences.update(payload.summary_concurrency)
        )
    except OSError:
        raise HTTPException(
            status_code=503, detail="偏好保存失败，请稍后再试。"
        ) from None
