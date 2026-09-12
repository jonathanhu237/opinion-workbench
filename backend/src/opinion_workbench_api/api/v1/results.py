from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from opinion_workbench_api.api.v1.ai_settings import no_store
from opinion_workbench_api.api.v1.analysis_common import ERROR_RESPONSES, AnalysisRoute
from opinion_workbench_api.schemas.analysis_settings import MAX_SAFE_INTEGER
from opinion_workbench_api.schemas.results import (
    LegacyAnalysisList,
    Result,
    ResultList,
    ResultOriginList,
    ResultState,
)
from opinion_workbench_api.search_platforms import SearchPlatform
from opinion_workbench_api.services.results import ResultsService


def get_service(request: Request) -> ResultsService:
    return request.app.state.results_service


Service = Annotated[ResultsService, Depends(get_service)]
ResourceId = Annotated[int, Path(ge=1, le=MAX_SAFE_INTEGER)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=MAX_SAFE_INTEGER)]
router = APIRouter(
    tags=["results"],
    dependencies=[Depends(no_store)],
    route_class=AnalysisRoute,
    responses=ERROR_RESPONSES,
)


@router.get("/results")
def list_results(
    service: Service,
    limit: Limit = 50,
    offset: Offset = 0,
    platform: SearchPlatform | None = None,
    state: ResultState | None = None,
    first_seen_from: datetime | None = None,
    first_seen_to: datetime | None = None,
) -> ResultList:
    return service.list(
        limit=limit,
        offset=offset,
        platform=platform,
        state=state,
        first_seen_from=first_seen_from,
        first_seen_to=first_seen_to,
    )


@router.get("/results/{result_id}")
def read_result(result_id: ResourceId, service: Service) -> Result:
    return service.repository.read(result_id)


@router.get("/results/{result_id}/origins")
def list_origins(
    result_id: ResourceId, service: Service, limit: Limit = 50, offset: Offset = 0
) -> ResultOriginList:
    return service.repository.origins(result_id, limit=limit, offset=offset)


@router.get("/results/{result_id}/legacy-analyses")
def list_legacy(
    result_id: ResourceId, service: Service, limit: Limit = 50, offset: Offset = 0
) -> LegacyAnalysisList:
    return service.repository.legacy(result_id, limit=limit, offset=offset)
