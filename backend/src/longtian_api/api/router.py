from fastapi import APIRouter

from longtian_api.api.v1.health import router as health_router
from longtian_api.api.v1.platform_connections import (
    router as platform_connections_router,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(platform_connections_router)
