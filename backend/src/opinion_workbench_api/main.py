from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from opinion_workbench_api.api.router import api_router
from opinion_workbench_api.application_paths import is_frozen_runtime
from opinion_workbench_api.database import Database
from opinion_workbench_api.repositories.search_runs import SearchRunRepository
from opinion_workbench_api.services.ai_settings import AISettingsService
from opinion_workbench_api.services.ai_summaries import SummaryService
from opinion_workbench_api.services.analysis_settings import AnalysisSettingsService
from opinion_workbench_api.services.application_lifecycle import ApplicationLifecycle
from opinion_workbench_api.services.automation_workflows import (
    AutomationWorkflowService,
)
from opinion_workbench_api.services.content_analyses import ContentAnalysisService
from opinion_workbench_api.services.content_enrichment import ContentEnrichmentService
from opinion_workbench_api.services.monitoring_rules import MonitoringRuleService
from opinion_workbench_api.services.platform_access import PlatformAccessService
from opinion_workbench_api.services.platform_connections import (
    PlatformConnectionService,
)
from opinion_workbench_api.services.report_generations import ReportGenerationService
from opinion_workbench_api.services.results import ResultsService
from opinion_workbench_api.services.search_batches import SearchBatchService
from opinion_workbench_api.services.search_runs import SearchRunService
from opinion_workbench_api.services.summary_preferences import SummaryPreferenceService
from opinion_workbench_api.services.topic_reports import TopicReportService
from opinion_workbench_api.services.workbench import WorkbenchService

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
    platform_access_service_factory: Callable[[Database], PlatformAccessService]
    | None = None,
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
    automation_workflow_available: bool = True,
    automation_workflow_service_factory: Callable[[Database], AutomationWorkflowService]
    | None = None,
    topic_report_service_factory: Callable[
        [Database, AISettingsService], TopicReportService
    ]
    | None = None,
    # Kept in the factory signature for callers that construct historical
    # fixtures; the old scheduler is no longer registered by the lifespan.
    collection_schedule_service_factory: Callable | None = None,
    content_analysis_service_factory: Callable[
        [Database, AISettingsService, ContentEnrichmentService], ContentAnalysisService
    ]
    | None = None,
    static_dir: Path | None = None,
    packaged: bool | None = None,
    lifecycle_enabled: bool | None = None,
    lifecycle_on_expired: Callable[[], object] | None = None,
    automation_resume_on_startup: bool | None = None,
) -> FastAPI:
    """Create the product API and lifespan-owned local services."""

    packaged_mode = is_frozen_runtime() if packaged is None else packaged
    lifecycle_mode = packaged_mode if lifecycle_enabled is None else lifecycle_enabled
    resume_automation = (
        not packaged_mode
        if automation_resume_on_startup is None
        else automation_resume_on_startup
    )
    static_root = static_dir.absolute() if static_dir is not None else None

    def build_platform_access(database: Database) -> PlatformAccessService:
        if platform_access_service_factory is not None:
            return platform_access_service_factory(database)
        return PlatformAccessService(database)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        platform_service = platform_connection_service_factory()
        lifecycle_service = ApplicationLifecycle(
            enabled=lifecycle_mode,
            on_expired=lifecycle_on_expired,
        )
        application.state.application_lifecycle = lifecycle_service
        try:
            monitoring_rule_service = monitoring_rule_service_factory()
            await run_in_threadpool(monitoring_rule_service.initialize)
            preference_database = monitoring_rule_service.database
            application.state.summary_preference_service = (
                SummaryPreferenceService(
                    preference_database.path.parent / "preferences.json"
                )
                if preference_database is not None
                else None
            )
            platform_access_service = None
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
                platform_access_service = build_platform_access(shared_database)
                await run_in_threadpool(platform_access_service.initialize)
                search_run_service = SearchRunService(
                    monitoring_rules=monitoring_rule_service,
                    worker=platform_service.worker,
                    browser_operations=platform_service.browser_operations,
                    database=shared_database,
                    platform_access=platform_access_service.coordinator,
                )
            await run_in_threadpool(search_run_service.initialize)
            batch_database = search_run_service.database
            if batch_database is None:
                raise RuntimeError(
                    "A custom search-run repository requires an explicit "
                    "search-batch service integration."
                )
            if platform_access_service is None:
                platform_access_service = build_platform_access(batch_database)
                await run_in_threadpool(platform_access_service.initialize)
            configure_access = getattr(
                platform_service, "configure_platform_access", None
            )
            if callable(configure_access):
                configure_access(platform_access_service.coordinator)
            configure_search_access = getattr(
                search_run_service, "configure_platform_access", None
            )
            if callable(configure_search_access):
                configure_search_access(platform_access_service.coordinator)
            search_batch_service = SearchBatchService(
                search_runs=search_run_service,
                browser_operations=platform_service.browser_operations,
                database=batch_database,
                platform_access=platform_access_service.coordinator,
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
                    platform_access=platform_access_service.coordinator,
                )
            )
            configure_enrichment_access = getattr(
                enrichment_service, "configure_platform_access", None
            )
            if callable(configure_enrichment_access):
                configure_enrichment_access(platform_access_service.coordinator)
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
            report_generation_service = ReportGenerationService(
                batch_database,
                analyses=content_analysis_service,
                reports=topic_report_service,
                ai_settings=ai_settings_service,
                platform_access=platform_access_service.coordinator,
            )
            await run_in_threadpool(report_generation_service.initialize)
            # Automatic progression belongs exclusively to the fixed workflow
            # owner.  The domain services remain independently callable; their
            # historical callback attributes are deliberately inert.
            content_analysis_service.on_job_finished = None
            search_run_service.on_collection_finished = None
            search_batch_service.on_collection_finished = None
            automation_workflow_service = (
                automation_workflow_service_factory(batch_database)
                if automation_workflow_service_factory is not None
                else AutomationWorkflowService(
                    batch_database,
                    monitoring_rules=monitoring_rule_service,
                    batches=search_batch_service,
                    analyses=content_analysis_service,
                    reports=topic_report_service,
                    ai_settings=ai_settings_service,
                    platform_access=platform_access_service,
                    available=automation_workflow_available,
                )
            )
            await run_in_threadpool(automation_workflow_service.initialize)
            application.state.results_service = ResultsService(batch_database)
            application.state.analysis_settings_service = analysis_settings_service
            application.state.content_analysis_service = content_analysis_service
            application.state.topic_report_service = topic_report_service
            application.state.report_generation_service = report_generation_service
            application.state.workbench_service = WorkbenchService(
                batch_database,
                automation_available=automation_workflow_available,
            )
            application.state.platform_connection_service = platform_service
            application.state.platform_access_service = platform_access_service
            application.state.monitoring_rule_service = monitoring_rule_service
            application.state.search_run_service = search_run_service
            application.state.search_batch_service = search_batch_service
            application.state.ai_settings_service = ai_settings_service
            application.state.content_enrichment_service = enrichment_service
            application.state.ai_summary_service = summary_service
            application.state.automation_workflow_service = automation_workflow_service
            await search_batch_service.resume_after_startup()
            await automation_workflow_service.start(
                resume_active_runs=resume_automation
            )
            yield
        finally:
            # Stop timer admission first; drain every owner even after a failure.
            scope = locals()
            await lifecycle_service.shutdown()
            await _shutdown_services(
                [
                    scope.get("automation_workflow_service"),
                    scope.get("report_generation_service"),
                    scope.get("content_analysis_service"),
                    scope.get("topic_report_service"),
                    scope.get("summary_service"),
                    scope.get("enrichment_service"),
                    scope.get("ai_settings_service"),
                    scope.get("search_batch_service"),
                    scope.get("search_run_service"),
                    scope.get("platform_access_service"),
                    platform_service,
                ]
            )

    application = FastAPI(
        title="OpinionWorkbench Public Opinion API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_exception_handler(
        RequestValidationError,
        _request_validation_error_handler,
    )
    application.state.ai_frontend_origins = ai_frontend_origins
    application.state.packaged = packaged_mode
    application.state.static_dir = static_root
    application.include_router(api_router)
    if static_root is not None:
        application.add_api_route(
            "/{path:path}",
            lambda path: _serve_frontend(static_root, path),
            methods=["GET"],
            include_in_schema=False,
        )
    return application


def _serve_frontend(static_root: Path, path: str):
    """Serve Vite output and fall back to ``index.html`` for SPA routes."""

    root = static_root.resolve()
    candidate = (root / path).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=404, detail="Not found")
    if path == "" or not candidate.is_file():
        # API and asset paths are real resources.  Returning the SPA shell for
        # a typo here turns a useful 404 into an HTML/MIME failure in the
        # browser and can hide a broken packaged install.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if path == "assets" or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = root / "index.html"
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(candidate)


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
