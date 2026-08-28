from fastapi import APIRouter

from longtian_api.api.v1.ai_settings import router as ai_settings_router
from longtian_api.api.v1.ai_summaries import router as ai_summaries_router
from longtian_api.api.v1.health import router as health_router
from longtian_api.api.v1.monitoring_rules import router as monitoring_rules_router
from longtian_api.api.v1.platform_connections import (
    router as platform_connections_router,
)
from longtian_api.api.v1.search_batches import router as search_batches_router
from longtian_api.api.v1.search_runs import router as search_runs_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(platform_connections_router)
api_router.include_router(monitoring_rules_router)
api_router.include_router(search_runs_router)
api_router.include_router(search_batches_router)
api_router.include_router(ai_settings_router)
api_router.include_router(ai_summaries_router)
