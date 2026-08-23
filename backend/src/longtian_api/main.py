from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from longtian_api.api.router import api_router
from longtian_api.services.platform_connections import PlatformConnectionService


def create_app(
    *,
    platform_connection_service_factory: Callable[
        [], PlatformConnectionService
    ] = PlatformConnectionService,
) -> FastAPI:
    """Create the product API and lifespan-owned local services."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        service = platform_connection_service_factory()
        application.state.platform_connection_service = service
        try:
            yield
        finally:
            await service.shutdown()

    application = FastAPI(
        title="Longtian Public Opinion API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


app = create_app()
