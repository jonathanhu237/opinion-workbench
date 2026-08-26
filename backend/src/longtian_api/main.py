from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from longtian_api.api.router import api_router
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.search_batches import SearchBatchService
from longtian_api.services.search_runs import SearchRunService

SearchRunServiceFactory = Callable[
    [MonitoringRuleService, PlatformConnectionService], SearchRunService
]


def create_app(
    *,
    platform_connection_service_factory: Callable[
        [], PlatformConnectionService
    ] = PlatformConnectionService,
    monitoring_rule_service_factory: Callable[
        [], MonitoringRuleService
    ] = MonitoringRuleService,
    search_run_service_factory: SearchRunServiceFactory | None = None,
) -> FastAPI:
    """Create the product API and lifespan-owned local services."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        platform_service = platform_connection_service_factory()
        try:
            monitoring_rule_service = monitoring_rule_service_factory()
            await run_in_threadpool(monitoring_rule_service.initialize)
            if search_run_service_factory is not None:
                search_run_service = search_run_service_factory(
                    monitoring_rule_service,
                    platform_service,
                )
            else:
                shared_database = monitoring_rule_service.database
                if shared_database is None:
                    raise RuntimeError(
                        "A custom monitoring repository requires an explicit "
                        "search-run service factory."
                    )
                search_run_service = SearchRunService(
                    monitoring_rules=monitoring_rule_service,
                    worker=platform_service.worker,
                    browser_operations=platform_service.browser_operations,
                    database=shared_database,
                )
            await run_in_threadpool(search_run_service.initialize)
            batch_database = search_run_service.database
            if batch_database is None:
                raise RuntimeError(
                    "A custom search-run repository requires an explicit "
                    "search-batch service integration."
                )
            search_batch_service = SearchBatchService(
                search_runs=search_run_service,
                browser_operations=platform_service.browser_operations,
                database=batch_database,
            )
            await run_in_threadpool(search_batch_service.initialize)
            application.state.platform_connection_service = platform_service
            application.state.monitoring_rule_service = monitoring_rule_service
            application.state.search_run_service = search_run_service
            application.state.search_batch_service = search_batch_service
            await search_batch_service.resume_after_startup()
            yield
        finally:
            if "search_batch_service" in locals():
                await search_batch_service.shutdown()
            if "search_run_service" in locals():
                await search_run_service.shutdown()
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
