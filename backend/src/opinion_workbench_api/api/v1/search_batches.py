"""Versioned endpoints for durable multi-platform collection batches."""

from typing import Annotated, Literal, Never

from fastapi import APIRouter, HTTPException, Path, Query, status

from opinion_workbench_api.api.dependencies import SearchBatchServiceDep
from opinion_workbench_api.schemas.search_batches import (
    SearchBatchAttemptListResponse,
    SearchBatchCancel,
    SearchBatchControl,
    SearchBatchCreate,
    SearchBatchDetail,
    SearchBatchErrorDetail,
    SearchBatchErrorResponse,
    SearchBatchListResponse,
    SearchBatchManualPageResponse,
    SearchBatchRecover,
    SearchBatchResultListResponse,
)
from opinion_workbench_api.services.search_batches import SearchBatchError

router = APIRouter(prefix="/search-batches", tags=["search-batches"])

SearchBatchId = Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)]
SearchBatchItemPosition = Annotated[int, Path(ge=0, le=4)]
_ERROR_404 = {404: {"model": SearchBatchErrorResponse}}
_ERROR_409 = {409: {"model": SearchBatchErrorResponse}}
_ERROR_422 = {422: {"model": SearchBatchErrorResponse}}
_ERROR_503 = {503: {"model": SearchBatchErrorResponse}}


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def start_search_batch(
    payload: SearchBatchCreate,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.start_batch(payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.get("", responses={**_ERROR_422, **_ERROR_503})
async def list_search_batches(
    service: SearchBatchServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_id: Annotated[int | None, Query(gt=0, le=9_223_372_036_854_775_807)] = None,
) -> SearchBatchListResponse:
    try:
        return await service.list_batches(limit=limit, before_id=before_id)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.get("/{batch_id}", responses={**_ERROR_404, **_ERROR_422, **_ERROR_503})
async def get_search_batch(
    batch_id: SearchBatchId,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.get_batch(batch_id)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.get(
    "/{batch_id}/items/{position}/attempts",
    responses={**_ERROR_404, **_ERROR_422, **_ERROR_503},
)
async def list_search_batch_attempts(
    batch_id: SearchBatchId,
    position: SearchBatchItemPosition,
    service: SearchBatchServiceDep,
) -> SearchBatchAttemptListResponse:
    try:
        return await service.list_attempts(batch_id, position)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.post(
    "/{batch_id}/continue",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def continue_search_batch(
    batch_id: SearchBatchId,
    payload: SearchBatchControl,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.continue_batch(batch_id, payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.post(
    "/{batch_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def cancel_search_batch(
    batch_id: SearchBatchId,
    payload: SearchBatchCancel,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.cancel_batch(batch_id, payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.post(
    "/{batch_id}/skip",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def skip_search_batch_item(
    batch_id: SearchBatchId,
    payload: SearchBatchControl,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.skip_item(batch_id, payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.post(
    "/{batch_id}/manual-page",
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def show_search_batch_page(
    batch_id: SearchBatchId,
    payload: SearchBatchControl,
    service: SearchBatchServiceDep,
) -> SearchBatchManualPageResponse:
    try:
        return await service.manual_page(batch_id, payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.post(
    "/{batch_id}/items/{position}/recover",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
async def recover_search_batch_item(
    batch_id: SearchBatchId,
    position: SearchBatchItemPosition,
    payload: SearchBatchRecover,
    service: SearchBatchServiceDep,
) -> SearchBatchDetail:
    try:
        return await service.recover_item(batch_id, position, payload)
    except SearchBatchError as error:
        _raise_http_error(error)


@router.get(
    "/{batch_id}/items/{position}/results",
    responses={**_ERROR_404, **_ERROR_422, **_ERROR_503},
)
async def list_search_batch_results(
    batch_id: SearchBatchId,
    position: SearchBatchItemPosition,
    service: SearchBatchServiceDep,
    kind: Literal["all", "new", "repeated"] = "all",
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> SearchBatchResultListResponse:
    try:
        return await service.list_results(
            batch_id=batch_id, position=position, kind=kind, limit=limit, offset=offset
        )
    except SearchBatchError as error:
        _raise_http_error(error)


def _raise_http_error(error: SearchBatchError) -> Never:
    detail = SearchBatchErrorDetail(code=error.code, message=error.message)
    raise HTTPException(
        status_code=error.status_code,
        detail=detail.model_dump(),
    ) from None
