"""Versioned monitoring-rule CRUD endpoints."""

from typing import Annotated, Never

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from longtian_api.api.dependencies import MonitoringRuleServiceDep
from longtian_api.schemas.monitoring_rules import (
    MonitoringRule,
    MonitoringRuleCreate,
    MonitoringRuleErrorDetail,
    MonitoringRuleErrorResponse,
    MonitoringRuleListResponse,
    MonitoringRuleReplace,
)
from longtian_api.services.monitoring_rules import MonitoringRuleError

router = APIRouter(prefix="/monitoring-rules", tags=["monitoring-rules"])

MonitoringRuleId = Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)]

_ERROR_404 = {404: {"model": MonitoringRuleErrorResponse}}
_ERROR_409 = {409: {"model": MonitoringRuleErrorResponse}}
_ERROR_422 = {422: {"model": MonitoringRuleErrorResponse}}
_ERROR_503 = {503: {"model": MonitoringRuleErrorResponse}}


@router.get("", responses={**_ERROR_422, **_ERROR_503})
def list_monitoring_rules(
    service: MonitoringRuleServiceDep,
    enabled: Annotated[bool | None, Query()] = None,
) -> MonitoringRuleListResponse:
    """List persisted rules in stable creation order."""
    try:
        return service.list_rules(enabled=enabled)
    except MonitoringRuleError as error:
        _raise_http_error(error)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={**_ERROR_409, **_ERROR_422, **_ERROR_503},
)
def create_monitoring_rule(
    payload: MonitoringRuleCreate,
    service: MonitoringRuleServiceDep,
) -> MonitoringRule:
    """Persist one validated monitoring rule."""
    try:
        return service.create_rule(payload)
    except MonitoringRuleError as error:
        _raise_http_error(error)


@router.put(
    "/{rule_id}",
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_422, **_ERROR_503},
)
def replace_monitoring_rule(
    rule_id: MonitoringRuleId,
    payload: MonitoringRuleReplace,
    service: MonitoringRuleServiceDep,
) -> MonitoringRule:
    """Atomically replace one rule and its ordered terms."""
    try:
        return service.replace_rule(rule_id, payload)
    except MonitoringRuleError as error:
        _raise_http_error(error)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERROR_404, **_ERROR_422, **_ERROR_503},
)
def delete_monitoring_rule(
    rule_id: MonitoringRuleId,
    service: MonitoringRuleServiceDep,
) -> Response:
    """Delete one rule and its terms."""
    try:
        service.delete_rule(rule_id)
    except MonitoringRuleError as error:
        _raise_http_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _raise_http_error(error: MonitoringRuleError) -> Never:
    detail = MonitoringRuleErrorDetail(code=error.code, message=error.message)
    raise HTTPException(
        status_code=error.status_code,
        detail=detail.model_dump(),
    ) from None
