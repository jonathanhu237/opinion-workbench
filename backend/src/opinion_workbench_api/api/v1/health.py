from fastapi import APIRouter

from opinion_workbench_api.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def get_health() -> HealthResponse:
    """Report whether the local API process is available."""
    return HealthResponse(status="ok", service="opinion-workbench-api")
