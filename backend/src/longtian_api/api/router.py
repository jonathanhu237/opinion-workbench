from fastapi import APIRouter

from longtian_api.api.v1.ai_settings import router as ai_settings_router
from longtian_api.api.v1.ai_summaries import router as ai_summaries_router
from longtian_api.api.v1.analysis_settings import router as analysis_settings_router
from longtian_api.api.v1.automation_workflows import (
    router as automation_workflows_router,
)
from longtian_api.api.v1.content_analyses import router as content_analyses_router
from longtian_api.api.v1.health import router as health_router
from longtian_api.api.v1.media_cache import router as media_cache_router
from longtian_api.api.v1.monitoring_rules import router as monitoring_rules_router
from longtian_api.api.v1.platform_connections import (
    router as platform_connections_router,
)
from longtian_api.api.v1.report_generations import router as report_generations_router
from longtian_api.api.v1.results import router as results_router
from longtian_api.api.v1.search_batches import router as search_batches_router
from longtian_api.api.v1.search_runs import router as search_runs_router
from longtian_api.api.v1.topic_reports import router as topic_reports_router
from longtian_api.api.v1.workbench import router as workbench_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(media_cache_router)
api_router.include_router(platform_connections_router)
api_router.include_router(monitoring_rules_router)
api_router.include_router(search_runs_router)
api_router.include_router(search_batches_router)
api_router.include_router(ai_settings_router)
api_router.include_router(ai_summaries_router)
api_router.include_router(analysis_settings_router)
api_router.include_router(automation_workflows_router)
api_router.include_router(results_router)
api_router.include_router(content_analyses_router)
api_router.include_router(topic_reports_router)
api_router.include_router(report_generations_router)
api_router.include_router(workbench_router)
