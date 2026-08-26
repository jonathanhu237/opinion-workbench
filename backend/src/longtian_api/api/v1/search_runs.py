"""Versioned endpoints for durable manual collection runs."""

from typing import Annotated, Literal, Never

from fastapi import APIRouter, HTTPException, Path, Query, status

from longtian_api.api.dependencies import SearchRunServiceDep
from longtian_api.schemas.search_runs import (
    SearchResultListResponse,
    SearchResultOpenResponse,
    SearchRunCreate,
    SearchRunDetail,
    SearchRunErrorDetail,
    SearchRunErrorResponse,
    SearchRunListResponse,
)
from longtian_api.services.search_runs import SearchRunError

router = APIRouter(prefix="/search-runs", tags=["search-runs"])

SearchRunId = Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)]
SearchResultId = Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)]
_ERROR_404 = {404: {"model": SearchRunErrorResponse}}
_ERROR_409 = {409: {"model": SearchRunErrorResponse}}
_ERROR_422 = {422: {"model": SearchRunErrorResponse}}
_ERROR_503 = {503: {"model": SearchRunErrorResponse}}


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def start_search_run(
    payload: SearchRunCreate,
    service: SearchRunServiceDep,
) -> SearchRunDetail:
    try:
        return await service.start_run(payload)
    except SearchRunError as error:
        _raise_http_error(error)


@router.get("", responses={**_ERROR_422, **_ERROR_503})
async def list_search_runs(
    service: SearchRunServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_id: Annotated[int | None, Query(gt=0, le=9_223_372_036_854_775_807)] = None,
) -> SearchRunListResponse:
    try:
        return await service.list_runs(limit=limit, before_id=before_id)
    except SearchRunError as error:
        _raise_http_error(error)


@router.get("/{run_id}", responses={**_ERROR_404, **_ERROR_422, **_ERROR_503})
async def get_search_run(
    run_id: SearchRunId,
    service: SearchRunServiceDep,
) -> SearchRunDetail:
    try:
        return await service.get_run(run_id)
    except SearchRunError as error:
        _raise_http_error(error)


@router.get("/{run_id}/results", responses={**_ERROR_404, **_ERROR_422, **_ERROR_503})
async def list_search_run_results(
    run_id: SearchRunId,
    service: SearchRunServiceDep,
    kind: Annotated[Literal["all", "new", "repeated"], Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> SearchResultListResponse:
    try:
        return await service.list_results(
            run_id=run_id,
            kind=kind,
            limit=limit,
            offset=offset,
        )
    except SearchRunError as error:
        _raise_http_error(error)


@router.post(
    "/{run_id}/results/{result_id}/open",
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def open_search_run_result(
    run_id: SearchRunId,
    result_id: SearchResultId,
    service: SearchRunServiceDep,
) -> SearchResultOpenResponse:
    try:
        return await service.open_result(run_id=run_id, result_id=result_id)
    except SearchRunError as error:
        _raise_http_error(error)


@router.post(
    "/{run_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def cancel_search_run(
    run_id: SearchRunId,
    service: SearchRunServiceDep,
) -> SearchRunDetail:
    try:
        return await service.cancel_run(run_id)
    except SearchRunError as error:
        _raise_http_error(error)


def _raise_http_error(error: SearchRunError) -> Never:
    detail = SearchRunErrorDetail(code=error.code, message=error.message)
    raise HTTPException(
        status_code=error.status_code,
        detail=detail.model_dump(),
    ) from None
