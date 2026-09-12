"""Local platform access pacing settings."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.api.v1.analysis_common import ERROR_RESPONSES, AnalysisRoute
from opinion_workbench_api.schemas.platform_access import (
    PlatformAccessSettings,
    PlatformAccessUpdate,
)
from opinion_workbench_api.services.platform_access import PlatformAccessService


def get_service(request: Request) -> PlatformAccessService:
    return request.app.state.platform_access_service


Service = Annotated[PlatformAccessService, Depends(get_service)]
router = APIRouter(
    tags=["platform-access"],
    dependencies=[Depends(no_store)],
    route_class=AnalysisRoute,
    responses=ERROR_RESPONSES,
)


@router.get("/platform-access-pacing")
@router.get("/platform-access-settings")
def read_settings(service: Service) -> PlatformAccessSettings:
    return service.read()


@router.put("/platform-access-pacing", dependencies=[Depends(require_local_mutation)])
@router.put("/platform-access-settings", dependencies=[Depends(require_local_mutation)])
def update_settings(
    payload: PlatformAccessUpdate, service: Service
) -> PlatformAccessSettings:
    return service.update(payload)
