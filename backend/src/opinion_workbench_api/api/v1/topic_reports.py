"""Read-only report history and explicit saved-text operations."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.api.v1.ai_summaries import SummaryRoute
from opinion_workbench_api.api.v1.results import Limit, Offset, ResourceId
from opinion_workbench_api.schemas.analysis_settings import MAX_SAFE_INTEGER
from opinion_workbench_api.schemas.topic_reports import (
    ReportCancel,
    ReportCreate,
    ReportCreateRequest,
    ReportList,
    ReportRetry,
    ReportRetryRequest,
    ReportRun,
    ReportSection,
    ReportSectionList,
    ReportSourceList,
)
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.analysis_errors import AnalysisError
from opinion_workbench_api.services.topic_report_errors import (
    ReportErrorResponse,
    TopicReportError,
)
from opinion_workbench_api.services.topic_reports import TopicReportService


class ReportRoute(SummaryRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except (TopicReportError, AnalysisError, AIError) as error:
                raise HTTPException(
                    error.status_code,
                    detail={"code": error.code, "message": error.message},
                    headers={"Cache-Control": "no-store"},
                ) from None
            except HTTPException:
                raise
            except Exception:
                error = TopicReportError("topic_report_storage_unavailable")
                raise HTTPException(
                    error.status_code,
                    detail={"code": error.code, "message": error.message},
                    headers={"Cache-Control": "no-store"},
                ) from None

        return handler


def get_service(request: Request) -> TopicReportService:
    return request.app.state.topic_report_service


Service = Annotated[TopicReportService, Depends(get_service)]
OptionalId = Annotated[int | None, Query(ge=1, le=MAX_SAFE_INTEGER)]
router = APIRouter(
    prefix="/topic-reports",
    tags=["topic-reports"],
    dependencies=[Depends(no_store)],
    route_class=ReportRoute,
    responses={
        status: {"model": ReportErrorResponse}
        for status in (403, 404, 409, 415, 422, 503)
    },
)


@router.get("")
def list_reports(
    service: Service,
    limit: Limit = 50,
    before_id: OptionalId = None,
    initial_job_id: OptionalId = None,
    result_id: OptionalId = None,
) -> ReportList:
    return service.repository.list(
        limit=limit,
        before_id=before_id,
        initial_job_id=initial_job_id,
        result_id=result_id,
    )


@router.post("", status_code=202, dependencies=[Depends(require_local_mutation)])
async def create_report(payload: ReportCreateRequest, service: Service) -> ReportRun:
    return await service.create(ReportCreate(**payload.model_dump(exclude_none=True)))


@router.get("/{report_id}")
def read_report(report_id: ResourceId, service: Service) -> ReportRun:
    return service.repository.read(report_id)


@router.get("/{report_id}/sources")
def list_sources(
    report_id: ResourceId, service: Service, limit: Limit = 50, offset: Offset = 0
) -> ReportSourceList:
    return service.repository.sources(report_id, limit=limit, offset=offset)


@router.get("/{report_id}/sections")
def list_sections(
    report_id: ResourceId,
    service: Service,
    limit: Limit = 50,
    offset: Offset = 0,
    kind: Literal["leaf", "overview"] | None = None,
) -> ReportSectionList:
    return service.repository.sections(report_id, limit=limit, offset=offset, kind=kind)


@router.get("/{report_id}/sections/{section_id}")
def read_section(
    report_id: ResourceId, section_id: ResourceId, service: Service
) -> ReportSection:
    return service.repository.section(report_id, section_id)


@router.post(
    "/{report_id}/retry",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
)
async def retry_report(
    report_id: ResourceId, payload: ReportRetryRequest, service: Service
) -> ReportRun:
    return await service.retry(
        report_id, ReportRetry(**payload.model_dump(exclude_none=True))
    )


@router.post("/{report_id}/cancel", dependencies=[Depends(require_local_mutation)])
async def cancel_report(
    report_id: ResourceId, payload: ReportCancel, service: Service
) -> ReportRun:
    return await service.cancel(report_id, payload)
