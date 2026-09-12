"""Local manual mutations and read-only summary history."""

from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.datastructures import MutableHeaders

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.schemas.ai_summaries import (
    SummaryCancel,
    SummaryCreate,
    SummaryErrorResponse,
    SummaryItemList,
    SummaryList,
    SummaryRun,
)
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.ai_summaries import SummaryService
from opinion_workbench_api.services.summary_errors import SummaryError


def get_summary_service(request: Request) -> SummaryService:
    return request.app.state.ai_summary_service


Service = Annotated[SummaryService, Depends(get_summary_service)]
ResourceId = Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)]


def _raise(error: SummaryError | AIError) -> Never:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
        headers={"Cache-Control": "no-store"},
    ) from None


class SummaryRoute(APIRoute):
    """Exception responses do not inherit the normal response dependency's headers."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                _raise(AIError("invalid_request"))
            except HTTPException as error:
                headers = MutableHeaders(headers=error.headers)
                headers["Cache-Control"] = "no-store"
                error.headers = dict(headers)
                raise

        return handler


router = APIRouter(
    tags=["ai-summaries"],
    dependencies=[Depends(no_store)],
    route_class=SummaryRoute,
)
_ERRORS = {
    status: {"model": SummaryErrorResponse} for status in (403, 404, 409, 415, 422, 503)
}


@router.post(
    "/search-runs/{source_run_id}/ai-summaries",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
    responses=_ERRORS,
)
async def create_summary(
    source_run_id: ResourceId, payload: SummaryCreate, service: Service
) -> SummaryRun:
    try:
        return await service.create(source_run_id, payload)
    except (SummaryError, AIError) as error:
        _raise(error)
    except Exception:
        _raise(SummaryError("ai_summary_unavailable"))


@router.get("/search-runs/{source_run_id}/ai-summaries", responses=_ERRORS)
def list_summaries(
    source_run_id: ResourceId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before_id: Annotated[int | None, Query(ge=1, le=9_223_372_036_854_775_807)] = None,
) -> SummaryList:
    try:
        return service.repository.list(source_run_id, limit=limit, before_id=before_id)
    except SummaryError as error:
        _raise(error)
    except Exception:
        _raise(SummaryError("ai_summary_storage_unavailable"))


@router.get("/ai-summaries/{summary_id}", responses=_ERRORS)
def read_summary(summary_id: ResourceId, service: Service) -> SummaryRun:
    try:
        return service.read(summary_id)
    except SummaryError as error:
        _raise(error)
    except Exception:
        _raise(SummaryError("ai_summary_storage_unavailable"))


@router.get("/ai-summaries/{summary_id}/items", responses=_ERRORS)
def list_summary_items(
    summary_id: ResourceId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> SummaryItemList:
    try:
        return service.repository.items(summary_id, limit=limit, offset=offset)
    except SummaryError as error:
        _raise(error)
    except Exception:
        _raise(SummaryError("ai_summary_storage_unavailable"))


@router.post(
    "/ai-summaries/{summary_id}/cancel",
    dependencies=[Depends(require_local_mutation)],
    responses=_ERRORS,
)
async def cancel_summary(
    summary_id: ResourceId, payload: SummaryCancel, service: Service
) -> SummaryRun:
    try:
        return await service.cancel(summary_id)
    except (SummaryError, AIError) as error:
        _raise(error)
    except Exception:
        _raise(SummaryError("ai_summary_unavailable"))
