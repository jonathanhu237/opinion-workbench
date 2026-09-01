from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from longtian_api.api.v1.ai_settings import no_store, require_local_mutation
from longtian_api.api.v1.analysis_common import ERROR_RESPONSES, AnalysisRoute
from longtian_api.api.v1.results import Limit, Offset, ResourceId
from longtian_api.schemas.analysis_settings import MAX_SAFE_INTEGER
from longtian_api.schemas.content_analyses import (
    AnalysisAdmission,
    AnalysisAttempt,
    AnalysisAttemptList,
    AnalysisCancel,
    AnalysisCreate,
    AnalysisCreateRequest,
    AnalysisJob,
    AnalysisJobList,
)
from longtian_api.services.content_analyses import ContentAnalysisService


def get_service(request: Request) -> ContentAnalysisService:
    return request.app.state.content_analysis_service


Service = Annotated[ContentAnalysisService, Depends(get_service)]
router = APIRouter(
    tags=["content-analyses"],
    dependencies=[Depends(no_store)],
    route_class=AnalysisRoute,
    responses=ERROR_RESPONSES,
)


@router.post(
    "/content-analysis-jobs",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
)
async def create_job(
    payload: AnalysisCreateRequest, service: Service
) -> AnalysisAdmission:
    # Keep the service/repository compatibility envelope private while the
    # HTTP boundary accepts only the current stage-one choice contract.
    return await service.create(AnalysisCreate(**payload.model_dump()))


@router.get("/content-analysis-jobs")
def list_jobs(
    service: Service,
    limit: Limit = 20,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_SAFE_INTEGER)] = None,
) -> AnalysisJobList:
    return service.repository.list(limit=limit, before_id=before_id)


@router.get("/content-analysis-jobs/{job_id}")
def read_job(job_id: ResourceId, service: Service) -> AnalysisJob:
    return service.repository.read(job_id)


@router.get("/content-analysis-jobs/{job_id}/items")
def list_items(
    job_id: ResourceId, service: Service, limit: Limit = 50, offset: Offset = 0
) -> AnalysisAttemptList:
    return service.repository.items(job_id, limit=limit, offset=offset)


@router.get("/results/{result_id}/analyses")
def list_result_analyses(
    result_id: ResourceId, service: Service, limit: Limit = 50, offset: Offset = 0
) -> AnalysisAttemptList:
    return service.repository.items(result_id=result_id, limit=limit, offset=offset)


@router.get("/content-analyses/{attempt_id}")
def read_attempt(attempt_id: ResourceId, service: Service) -> AnalysisAttempt:
    return service.repository.attempt(attempt_id)


@router.post(
    "/content-analysis-jobs/{job_id}/cancel",
    dependencies=[Depends(require_local_mutation)],
)
async def cancel_job(
    job_id: ResourceId, payload: AnalysisCancel, service: Service
) -> AnalysisJob:
    return await service.cancel(job_id)
