"""Manual report generation: mutations start work; reads never do."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from longtian_api.api.v1.ai_settings import no_store, require_local_mutation
from longtian_api.api.v1.results import Limit, ResourceId
from longtian_api.api.v1.topic_reports import OptionalId, ReportRoute
from longtian_api.schemas.report_generations import (
    GenerationControl,
    GenerationCreate,
    GenerationEligibility,
    GenerationList,
    ReportGeneration,
    SelectionPreview,
    SelectionPreviewRequest,
)
from longtian_api.services.report_generations import ReportGenerationService


def get_service(request: Request) -> ReportGenerationService:
    return request.app.state.report_generation_service


Service = Annotated[ReportGenerationService, Depends(get_service)]
router = APIRouter(
    prefix="/report-generations",
    tags=["report-generations"],
    route_class=ReportRoute,
    dependencies=[Depends(no_store)],
)


@router.post("", status_code=202, dependencies=[Depends(require_local_mutation)])
async def create_generation(
    payload: GenerationCreate, service: Service
) -> ReportGeneration:
    return await service.create(payload)


@router.get("")
def list_generations(
    service: Service, limit: Limit = 20, before_id: OptionalId = None
) -> GenerationList:
    return service.repository.list_generations(limit=limit, before_id=before_id)


@router.get("/eligibility")
def read_eligibility(service: Service) -> GenerationEligibility:
    return service.repository.eligibility()


@router.post(
    "/selection-preview",
    dependencies=[Depends(require_local_mutation)],
)
def preview_selection(
    payload: SelectionPreviewRequest, service: Service
) -> SelectionPreview:
    return service.repository.selection_preview(payload)


@router.get("/{generation_id}")
def read_generation(generation_id: ResourceId, service: Service) -> ReportGeneration:
    return service.repository.read_generation(generation_id)


@router.post(
    "/{generation_id}/continue", dependencies=[Depends(require_local_mutation)]
)
async def continue_generation(
    generation_id: ResourceId, payload: GenerationControl, service: Service
) -> ReportGeneration:
    return await service.control(generation_id, payload)


@router.post("/{generation_id}/cancel", dependencies=[Depends(require_local_mutation)])
async def cancel_generation(
    generation_id: ResourceId, payload: GenerationControl, service: Service
) -> ReportGeneration:
    return await service.cancel(generation_id, payload)


@router.post(
    "/{generation_id}/manual-page", dependencies=[Depends(require_local_mutation)]
)
async def show_manual_page(
    generation_id: ResourceId, payload: GenerationControl, service: Service
) -> ReportGeneration:
    return await service.control(generation_id, payload, show=True)
