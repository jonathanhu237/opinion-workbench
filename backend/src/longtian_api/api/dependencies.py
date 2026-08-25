"""FastAPI dependencies owned by application lifespan."""

from typing import Annotated

from fastapi import Depends, Request

from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService


def get_platform_connection_service(request: Request) -> PlatformConnectionService:
    """Retrieve the single service instance created by the app lifespan."""
    return request.app.state.platform_connection_service


PlatformConnectionServiceDep = Annotated[
    PlatformConnectionService, Depends(get_platform_connection_service)
]


def get_monitoring_rule_service(request: Request) -> MonitoringRuleService:
    """Retrieve the initialized monitoring-rule service from app state."""
    return request.app.state.monitoring_rule_service


MonitoringRuleServiceDep = Annotated[
    MonitoringRuleService, Depends(get_monitoring_rule_service)
]
