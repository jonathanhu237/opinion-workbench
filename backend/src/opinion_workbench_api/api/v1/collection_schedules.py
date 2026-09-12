"""Read-only schedule history and explicit local configuration mutations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.api.v1.ai_summaries import SummaryRoute
from opinion_workbench_api.schemas.collection_schedules import (
    MAX_SAFE_INTEGER,
    CollectionOccurrenceList,
    CollectionSchedule,
    CollectionScheduleCreate,
    CollectionScheduleList,
    CollectionScheduleReplace,
)
from opinion_workbench_api.services.collection_schedule_errors import (
    CollectionScheduleError,
    CollectionScheduleErrorResponse,
)
from opinion_workbench_api.services.collection_schedules import (
    CollectionScheduleService,
)


class ScheduleRoute(SummaryRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except HTTPException:
                raise
            except Exception as error:
                safe = (
                    error
                    if isinstance(error, CollectionScheduleError)
                    else CollectionScheduleError(
                        "collection_schedule_storage_unavailable"
                    )
                )
                raise HTTPException(
                    safe.status_code,
                    detail={"code": safe.code, "message": safe.message},
                    headers={"Cache-Control": "no-store"},
                ) from None

        return handler


def service(request: Request) -> CollectionScheduleService:
    return request.app.state.collection_schedule_service


Service = Annotated[CollectionScheduleService, Depends(service)]
Identity = Annotated[int, Path(ge=1, le=MAX_SAFE_INTEGER)]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[int | None, Query(ge=1, le=MAX_SAFE_INTEGER)]
router = APIRouter(
    prefix="/collection-schedules",
    tags=["collection-schedules"],
    dependencies=[Depends(no_store)],
    route_class=ScheduleRoute,
    responses={
        code: {"model": CollectionScheduleErrorResponse}
        for code in (403, 404, 409, 415, 422, 503)
    },
)


@router.get("")
def list_schedules(
    owner: Service, limit: Limit = 50, before_id: Cursor = None
) -> CollectionScheduleList:
    return owner.list(limit=limit, before_id=before_id)


@router.post("", status_code=201, dependencies=[Depends(require_local_mutation)])
def create_schedule(
    payload: CollectionScheduleCreate, owner: Service
) -> CollectionSchedule:
    return owner.create(payload)


@router.get("/{schedule_id}")
def get_schedule(schedule_id: Identity, owner: Service) -> CollectionSchedule:
    return owner.get(schedule_id)


@router.put("/{schedule_id}", dependencies=[Depends(require_local_mutation)])
def replace_schedule(
    schedule_id: Identity, payload: CollectionScheduleReplace, owner: Service
) -> CollectionSchedule:
    return owner.replace(schedule_id, payload)


@router.get("/{schedule_id}/occurrences")
def occurrences(
    schedule_id: Identity, owner: Service, limit: Limit = 50, before_id: Cursor = None
) -> CollectionOccurrenceList:
    return owner.repository.occurrences(schedule_id, limit=limit, before_id=before_id)
