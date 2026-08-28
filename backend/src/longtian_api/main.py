from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from longtian_api.api.router import api_router
from longtian_api.database import Database
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.ai_summaries import SummaryService
from longtian_api.services.analysis_settings import AnalysisSettingsService
from longtian_api.services.collection_schedules import CollectionScheduleService
from longtian_api.services.content_analyses import ContentAnalysisService
from longtian_api.services.content_enrichment import ContentEnrichmentService
from longtian_api.services.enrichment_staging import MediaSpool
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.results import ResultsService
from longtian_api.services.search_batches import SearchBatchService
from longtian_api.services.search_runs import SearchRunService
from longtian_api.services.topic_reports import TopicReportService

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
    ai_settings_service_factory: Callable[[Database], AISettingsService] | None = None,
    content_enrichment_service_factory: Callable[
        [Database, PlatformConnectionService], ContentEnrichmentService
    ]
    | None = None,
    ai_frontend_origins: tuple[str, ...] = (),
    analysis_automation_available: bool = True,
    collection_automation_available: bool = True,
    topic_reports_available: bool = True,
    topic_report_service_factory: Callable[
        [Database, AISettingsService], TopicReportService
    ]
    | None = None,
    collection_schedule_service_factory: Callable[
        [Database, SearchBatchService], CollectionScheduleService
    ]
    | None = None,
    content_analysis_service_factory: Callable[
        [Database, AISettingsService, ContentEnrichmentService], ContentAnalysisService
    ]
    | None = None,
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
            ai_settings_service = (
                ai_settings_service_factory(batch_database)
                if ai_settings_service_factory is not None
                else AISettingsService(batch_database)
            )
            await run_in_threadpool(ai_settings_service.initialize)
            enrichment_service = (
                content_enrichment_service_factory(batch_database, platform_service)
                if content_enrichment_service_factory is not None
                else ContentEnrichmentService(
                    repository=SearchRunRepository(batch_database),
                    worker=platform_service.worker,
                    browser_operations=platform_service.browser_operations,
                    spool=MediaSpool(batch_database.path.parent / "media"),
                )
            )
            summary_service = SummaryService(
                database=batch_database,
                ai_settings=ai_settings_service,
                enrichment=enrichment_service,
            )
            await run_in_threadpool(summary_service.initialize)
            analysis_settings_service = AnalysisSettingsService(
                batch_database,
                ai_settings_service,
                available=analysis_automation_available,
            )
            content_analysis_service = (
                content_analysis_service_factory(
                    batch_database, ai_settings_service, enrichment_service
                )
                if content_analysis_service_factory is not None
                else ContentAnalysisService(
                    database=batch_database,
                    ai_settings=ai_settings_service,
                    enrichment=enrichment_service,
                    available=analysis_automation_available,
                )
            )
            await run_in_threadpool(content_analysis_service.initialize)
            topic_report_service = (
                topic_report_service_factory(batch_database, ai_settings_service)
                if topic_report_service_factory is not None
                else TopicReportService(
                    database=batch_database,
                    ai_settings=ai_settings_service,
                    available=topic_reports_available,
                )
            )
            await run_in_threadpool(topic_report_service.initialize)
            if topic_reports_available:
                content_analysis_service.on_job_finished = (
                    topic_report_service.initial_analysis_finished
                )
            search_run_service.on_collection_finished = (
                content_analysis_service.collection_finished
            )
            search_batch_service.on_collection_finished = (
                content_analysis_service.collection_finished
            )
            application.state.results_service = ResultsService(batch_database)
            application.state.analysis_settings_service = analysis_settings_service
            application.state.content_analysis_service = content_analysis_service
            application.state.topic_report_service = topic_report_service
            application.state.platform_connection_service = platform_service
            application.state.monitoring_rule_service = monitoring_rule_service
            application.state.search_run_service = search_run_service
            application.state.search_batch_service = search_batch_service
            application.state.ai_settings_service = ai_settings_service
            application.state.content_enrichment_service = enrichment_service
            application.state.ai_summary_service = summary_service
            await search_batch_service.resume_after_startup()
            collection_schedule_service = (
                collection_schedule_service_factory(
                    batch_database, search_batch_service
                )
                if collection_schedule_service_factory is not None
                else CollectionScheduleService(
                    batch_database,
                    search_batch_service,
                    available=collection_automation_available,
                )
            )
            application.state.collection_schedule_service = collection_schedule_service
            await collection_schedule_service.start()
            yield
        finally:
            # Stop timer admission first; drain every owner even after a failure.
            scope = locals()
            await _shutdown_services(
                [
                    scope.get("collection_schedule_service"),
                    scope.get("content_analysis_service"),
                    scope.get("topic_report_service"),
                    scope.get("summary_service"),
                    scope.get("enrichment_service"),
                    scope.get("ai_settings_service"),
                    scope.get("search_batch_service"),
                    scope.get("search_run_service"),
                    platform_service,
                ]
            )

    application = FastAPI(
        title="Longtian Public Opinion API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_exception_handler(
        RequestValidationError,
        _request_validation_error_handler,
    )
    application.state.ai_frontend_origins = ai_frontend_origins
    application.include_router(api_router)
    return application


async def _shutdown_services(services: list) -> None:
    failure = None
    for service in services:
        if service is not None:
            try:
                await service.shutdown()
            except BaseException as error:
                if failure is None:
                    failure = error
    if failure is not None:
        raise failure


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
