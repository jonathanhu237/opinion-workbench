from fastapi import APIRouter

from longtian_api.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def get_health() -> HealthResponse:
    """Report whether the local API process is available."""
    return HealthResponse(status="ok", service="longtian-public-opinion-api")
