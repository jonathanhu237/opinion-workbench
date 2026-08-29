"""Read-only homepage workbench projection."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from longtian_api.api.v1.ai_settings import no_store
from longtian_api.schemas.workbench import WorkbenchSnapshot
from longtian_api.services.workbench import WorkbenchService
from longtian_api.services.workbench_errors import (
    WorkbenchError,
    WorkbenchErrorResponse,
)


def get_service(request: Request) -> WorkbenchService:
    return request.app.state.workbench_service


Service = Annotated[WorkbenchService, Depends(get_service)]
router = APIRouter(
    prefix="/workbench",
    tags=["workbench"],
    dependencies=[Depends(no_store)],
    responses={503: {"model": WorkbenchErrorResponse}},
)


@router.get("")
def read_workbench(service: Service) -> WorkbenchSnapshot:
    try:
        return service.read()
    except WorkbenchError as error:
        raise HTTPException(
            error.status_code,
            detail={"code": error.code, "message": error.message},
            headers={"Cache-Control": "no-store"},
        ) from None
    except Exception:
        error = WorkbenchError("workbench_unavailable")
        raise HTTPException(
            error.status_code,
            detail={"code": error.code, "message": error.message},
            headers={"Cache-Control": "no-store"},
        ) from None
