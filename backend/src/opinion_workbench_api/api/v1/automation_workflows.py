"""Strict HTTP boundary for fixed-purpose automatic opinion workflows."""

from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.schemas.analysis_settings import MAX_SAFE_INTEGER
from opinion_workbench_api.schemas.automation_workflows import (
    AutomationOccurrenceList,
    AutomationRun,
    AutomationRunCancel,
    AutomationRunList,
    AutomationRunNow,
    AutomationRunRetry,
    AutomationTask,
    AutomationTaskCreate,
    AutomationTaskCreateRequest,
    AutomationTaskDelete,
    AutomationTaskList,
    AutomationTaskReplace,
    AutomationTaskReplaceRequest,
)
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.automation_workflow_errors import (
    AutomationErrorResponse,
    AutomationWorkflowError,
)
from opinion_workbench_api.services.automation_workflows import (
    AutomationWorkflowService,
)


class AutomationRoute(APIRoute):
    """Translate product errors while preserving no-store on every response."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                _raise_http(422, "invalid_request", "请求内容不正确。")
            except AutomationWorkflowError as error:
                _raise_http(error.status_code, error.code, error.message)
            except AIError as error:
                _raise_http(error.status_code, error.code, error.message)
            except HTTPException as error:
                headers = dict(error.headers or {})
                headers["Cache-Control"] = "no-store"
                error.headers = headers
                raise
            except Exception:
                _raise_http(
                    503,
                    "automation_storage_unavailable",
                    "自动任务数据暂时无法读取或保存，请稍后重试。",
                )

        return handler


def _raise_http(status_code: int, code: str, message: str) -> Never:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers={"Cache-Control": "no-store"},
    ) from None


def get_service(request: Request) -> AutomationWorkflowService:
    return request.app.state.automation_workflow_service


Service = Annotated[AutomationWorkflowService, Depends(get_service)]
Identity = Annotated[int, Path(ge=1, le=MAX_SAFE_INTEGER)]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[int | None, Query(ge=1, le=MAX_SAFE_INTEGER)]

_ERROR_RESPONSES = {
    status: {"model": AutomationErrorResponse} for status in (404, 409, 422, 503)
}

router = APIRouter(
    tags=["automation-workflows"],
    dependencies=[Depends(no_store)],
    route_class=AutomationRoute,
    responses=_ERROR_RESPONSES,
)


@router.get("/automation-tasks")
def list_tasks(
    service: Service, limit: Limit = 50, before_id: Cursor = None
) -> AutomationTaskList:
    return service.list_tasks(limit=limit, before_id=before_id)


@router.post(
    "/automation-tasks",
    status_code=201,
    dependencies=[Depends(require_local_mutation)],
)
def create_task(
    payload: AutomationTaskCreateRequest, service: Service
) -> AutomationTask:
    return service.create_task(AutomationTaskCreate(**payload.model_dump()))


@router.get("/automation-tasks/{task_id}")
def get_task(task_id: Identity, service: Service) -> AutomationTask:
    return service.get_task(task_id)


@router.put(
    "/automation-tasks/{task_id}",
    dependencies=[Depends(require_local_mutation)],
)
def replace_task(
    task_id: Identity,
    payload: AutomationTaskReplaceRequest,
    service: Service,
) -> AutomationTask:
    return service.replace_task(task_id, AutomationTaskReplace(**payload.model_dump()))


@router.delete(
    "/automation-tasks/{task_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_local_mutation)],
)
def delete_task(
    task_id: Identity, payload: AutomationTaskDelete, service: Service
) -> Response:
    service.delete_task(task_id, payload)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/automation-tasks/{task_id}/occurrences")
def list_occurrences(
    task_id: Identity,
    service: Service,
    limit: Limit = 50,
    before_id: Cursor = None,
) -> AutomationOccurrenceList:
    return service.list_occurrences(task_id, limit=limit, before_id=before_id)


@router.get("/automation-tasks/{task_id}/runs")
def list_runs(
    task_id: Identity,
    service: Service,
    limit: Limit = 50,
    before_id: Cursor = None,
) -> AutomationRunList:
    return service.list_runs(task_id, limit=limit, before_id=before_id)


@router.post(
    "/automation-tasks/{task_id}/run-now",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
)
async def run_now(
    task_id: Identity, payload: AutomationRunNow, service: Service
) -> AutomationRun:
    return await service.run_now(task_id, payload)


@router.get("/automation-runs/{run_id}")
def get_run(run_id: Identity, service: Service) -> AutomationRun:
    return service.get_run(run_id)


@router.post(
    "/automation-runs/{run_id}/cancel",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
)
async def cancel_run(
    run_id: Identity, payload: AutomationRunCancel, service: Service
) -> AutomationRun:
    return await service.cancel_run(run_id, payload)


@router.post(
    "/automation-runs/{run_id}/retry",
    status_code=202,
    dependencies=[Depends(require_local_mutation)],
)
async def retry_run(
    run_id: Identity, payload: AutomationRunRetry, service: Service
) -> AutomationRun:
    return await service.retry_run(run_id, payload)
