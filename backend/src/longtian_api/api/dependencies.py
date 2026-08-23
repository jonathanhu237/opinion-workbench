"""FastAPI dependencies owned by application lifespan."""

from typing import Annotated

from fastapi import Depends, Request

from longtian_api.services.platform_connections import PlatformConnectionService


def get_platform_connection_service(request: Request) -> PlatformConnectionService:
    """Retrieve the single service instance created by the app lifespan."""
    return request.app.state.platform_connection_service


PlatformConnectionServiceDep = Annotated[
    PlatformConnectionService, Depends(get_platform_connection_service)
]
