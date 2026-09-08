"""Versioned platform account connection endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from longtian_api.api.dependencies import PlatformConnectionServiceDep
from longtian_api.schemas.platform_connections import (
    PlatformBrowserResponse,
    PlatformConnectionAttemptResponse,
    PlatformConnectionErrorDetail,
    PlatformConnectionErrorResponse,
    PlatformConnectionListResponse,
)
from longtian_api.services.platform_connections import PlatformConnectionError

router = APIRouter(prefix="/platform-connections", tags=["platform-connections"])

_ERROR_RESPONSES = {
    404: {"model": PlatformConnectionErrorResponse},
    409: {"model": PlatformConnectionErrorResponse},
    503: {"model": PlatformConnectionErrorResponse},
}


@router.get("")
async def list_platform_connections(
    service: PlatformConnectionServiceDep,
) -> PlatformConnectionListResponse:
    """List the current in-memory platform connection projections."""
    return await service.list_connections()


@router.post(
    "/browser",
    response_model=PlatformBrowserResponse,
    responses=_ERROR_RESPONSES,
)
async def open_managed_browser(
    service: PlatformConnectionServiceDep,
) -> PlatformBrowserResponse:
    """Open or foreground the app-owned browser without checking accounts."""
    try:
        return await service.open_browser()
    except PlatformConnectionError as error:
        detail = PlatformConnectionErrorDetail(
            code=error.code,
            message=error.message,
        )
        raise HTTPException(
            status_code=error.status_code,
            detail=detail.model_dump(),
        ) from None


@router.post(
    "/{platform}/browser",
    response_model=PlatformBrowserResponse,
    responses=_ERROR_RESPONSES,
)
async def open_platform_browser(
    platform: Annotated[str, Path(description="Stable platform identifier")],
    service: PlatformConnectionServiceDep,
) -> PlatformBrowserResponse:
    """Open the owned browser and navigate to one platform's homepage."""
    try:
        return await service.open_browser(platform)
    except PlatformConnectionError as error:
        detail = PlatformConnectionErrorDetail(
            code=error.code,
            message=error.message,
        )
        raise HTTPException(
            status_code=error.status_code,
            detail=detail.model_dump(),
        ) from None


@router.post(
    "/{platform}/attempts",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def start_platform_connection_attempt(
    platform: Annotated[str, Path(description="Stable platform identifier")],
    service: PlatformConnectionServiceDep,
) -> PlatformConnectionAttemptResponse:
    """Start one bounded authentication-only attempt without waiting for it."""
    try:
        return await service.start_attempt(platform)
    except PlatformConnectionError as error:
        detail = PlatformConnectionErrorDetail(
            code=error.code,
            message=error.message,
        )
        raise HTTPException(
            status_code=error.status_code,
            detail=detail.model_dump(),
        ) from None
