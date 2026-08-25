from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from longtian_api.api.router import api_router
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService


def create_app(
    *,
    platform_connection_service_factory: Callable[
        [], PlatformConnectionService
    ] = PlatformConnectionService,
    monitoring_rule_service_factory: Callable[
        [], MonitoringRuleService
    ] = MonitoringRuleService,
) -> FastAPI:
    """Create the product API and lifespan-owned local services."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        platform_service = platform_connection_service_factory()
        try:
            monitoring_rule_service = monitoring_rule_service_factory()
            await run_in_threadpool(monitoring_rule_service.initialize)
            application.state.platform_connection_service = platform_service
            application.state.monitoring_rule_service = monitoring_rule_service
            yield
        finally:
            await platform_service.shutdown()

    application = FastAPI(
        title="Longtian Public Opinion API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_exception_handler(
        RequestValidationError,
        _request_validation_error_handler,
    )
    application.include_router(api_router)
    return application


async def _request_validation_error_handler(
    _request: Request, _error: Exception
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": {
                "code": "invalid_request",
                "message": "请求内容不正确。",
            }
        },
    )


app = create_app()
