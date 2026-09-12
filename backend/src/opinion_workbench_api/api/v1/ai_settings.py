"""Local-only settings mutations and explicit saved-configuration testing."""

import ipaddress
from typing import Never
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from opinion_workbench_api.api.dependencies import AISettingsServiceDep
from opinion_workbench_api.schemas.ai_settings import (
    AIConnectionResult,
    AIConnectionTest,
    AIErrorResponse,
    AISettings,
    AISettingsUpdate,
)
from opinion_workbench_api.services.ai_errors import AIError


def _raise_http_error(error: AIError) -> Never:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from None


def _local_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme not in ("http", "https")
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
            or any(c in value for c in ("\\", "?", "#", "%"))
        ):
            return None
        if host != "localhost":
            if not ipaddress.ip_address(host).is_loopback:
                return None
        return (
            parsed.scheme,
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def require_local_mutation(request: Request) -> None:
    hosts = request.headers.getlist("host")
    own = (
        _local_origin(f"{request.url.scheme}://{hosts[0]}") if len(hosts) == 1 else None
    )
    origins = request.headers.getlist("origin")
    if own is None or len(origins) > 1:
        _raise_http_error(AIError("ai_request_forbidden"))
    if request.headers.get("sec-fetch-site") == "cross-site":
        _raise_http_error(AIError("ai_request_forbidden"))
    if origins:
        origin = _local_origin(origins[0])
        allowed = {
            parsed
            for item in request.app.state.ai_frontend_origins
            if (parsed := _local_origin(item)) is not None
        }
        if origin is None or (origin != own and origin not in allowed):
            _raise_http_error(AIError("ai_request_forbidden"))
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        _raise_http_error(AIError("ai_json_required"))


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/ai-settings",
    tags=["ai-settings"],
    dependencies=[Depends(no_store)],
)
_ERRORS = {
    status: {"model": AIErrorResponse}
    for status in (403, 409, 413, 415, 422, 429, 502, 503, 504)
}


@router.get("", responses={503: {"model": AIErrorResponse}})
def read_ai_settings(service: AISettingsServiceDep) -> AISettings:
    try:
        return service.read()
    except AIError as error:
        _raise_http_error(error)
    except Exception:
        _raise_http_error(AIError("ai_settings_storage_unavailable"))


@router.put("", dependencies=[Depends(require_local_mutation)], responses=_ERRORS)
def save_ai_settings(
    payload: AISettingsUpdate, service: AISettingsServiceDep
) -> AISettings:
    try:
        return service.save(payload)
    except AIError as error:
        _raise_http_error(error)
    except Exception:
        _raise_http_error(AIError("ai_settings_storage_unavailable"))


@router.post("/test", dependencies=[Depends(require_local_mutation)], responses=_ERRORS)
async def test_ai_connection(
    payload: AIConnectionTest,
    service: AISettingsServiceDep,
) -> AIConnectionResult:
    try:
        return await service.test_connection(payload.revision)
    except AIError as error:
        _raise_http_error(error)
    except Exception:
        _raise_http_error(AIError("ai_provider_unavailable"))
