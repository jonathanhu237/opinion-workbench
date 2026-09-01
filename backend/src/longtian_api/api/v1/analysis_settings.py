from typing import Annotated

from fastapi import APIRouter, Depends, Request

from longtian_api.api.v1.ai_settings import no_store, require_local_mutation
from longtian_api.api.v1.analysis_common import ERROR_RESPONSES, AnalysisRoute
from longtian_api.schemas.analysis_settings import (
    AnalysisSettings,
    AutomationUpdate,
)
from longtian_api.services.analysis_settings import AnalysisSettingsService


def get_service(request: Request) -> AnalysisSettingsService:
    return request.app.state.analysis_settings_service


Service = Annotated[AnalysisSettingsService, Depends(get_service)]
router = APIRouter(
    tags=["analysis-settings"],
    dependencies=[Depends(no_store)],
    route_class=AnalysisRoute,
    responses=ERROR_RESPONSES,
)


@router.get("/analysis-settings")
def read_settings(service: Service) -> AnalysisSettings:
    return service.read()


@router.put(
    "/analysis-settings/automation", dependencies=[Depends(require_local_mutation)]
)
def save_automation(payload: AutomationUpdate, service: Service) -> AnalysisSettings:
    return service.save_automation(payload)
