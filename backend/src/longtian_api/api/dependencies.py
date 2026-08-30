"""FastAPI dependencies owned by application lifespan."""

from typing import Annotated

from fastapi import Depends, Request

from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.automation_workflows import AutomationWorkflowService
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.search_batches import SearchBatchService
from longtian_api.services.search_runs import SearchRunService


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


def get_search_run_service(request: Request) -> SearchRunService:
    """Retrieve the lifespan-owned search-run service."""

    return request.app.state.search_run_service


SearchRunServiceDep = Annotated[SearchRunService, Depends(get_search_run_service)]


def get_search_batch_service(request: Request) -> SearchBatchService:
    """Retrieve the lifespan-owned search-batch service."""

    return request.app.state.search_batch_service


SearchBatchServiceDep = Annotated[SearchBatchService, Depends(get_search_batch_service)]


def get_ai_settings_service(request: Request) -> AISettingsService:
    """Retrieve the single owner of configuration and AI-operation admission."""
    return request.app.state.ai_settings_service


AISettingsServiceDep = Annotated[AISettingsService, Depends(get_ai_settings_service)]


def get_automation_workflow_service(request: Request) -> AutomationWorkflowService:
    """Retrieve the single fixed-pipeline workflow owner."""

    return request.app.state.automation_workflow_service


AutomationWorkflowServiceDep = Annotated[
    AutomationWorkflowService, Depends(get_automation_workflow_service)
]
