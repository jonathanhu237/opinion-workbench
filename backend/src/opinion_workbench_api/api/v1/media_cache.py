"""Read-only, snapshot-authorized access to validated local original bytes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from opinion_workbench_api.api.v1.ai_settings import no_store, require_local_mutation
from opinion_workbench_api.api.v1.analysis_common import ERROR_RESPONSES, AnalysisRoute
from opinion_workbench_api.api.v1.results import ResourceId
from opinion_workbench_api.schemas.media_cache import (
    CachedMediaList,
    MediaCleanup,
    MediaPolicy,
    MediaPolicyResult,
    MediaPolicyUpdate,
)

router = APIRouter(
    tags=["media-cache"],
    dependencies=[Depends(no_store)],
    route_class=AnalysisRoute,
    responses=ERROR_RESPONSES,
)


@router.get("/media-cache-settings")
def read_policy(request: Request) -> MediaPolicy:
    return MediaPolicy.model_validate(request.app.state.media_cache.retention.read())


@router.put("/media-cache-settings", dependencies=[Depends(require_local_mutation)])
def save_policy(payload: MediaPolicyUpdate, request: Request) -> MediaPolicyResult:
    return MediaPolicyResult.model_validate(
        request.app.state.media_cache.retention.update(payload)
    )


@router.post(
    "/media-cache-settings/cleanup", dependencies=[Depends(require_local_mutation)]
)
def clean_cache(payload: MediaCleanup, request: Request) -> MediaPolicyResult:
    return MediaPolicyResult.model_validate(
        request.app.state.media_cache.retention.clean(payload.expected_revision)
    )


@router.get("/content-analyses/{attempt_id}/media-cache")
def read_cache(attempt_id: ResourceId, request: Request) -> CachedMediaList:
    attempt = request.app.state.content_analysis_service.repository.attempt(attempt_id)
    return CachedMediaList.model_validate(
        request.app.state.media_cache.describe(
            attempt.source.result_id, attempt.input.assets if attempt.input else []
        )
    )


@router.get("/content-analyses/{attempt_id}/media/{position}")
def read_original(attempt_id: ResourceId, position: int, request: Request):
    attempt = request.app.state.content_analysis_service.repository.attempt(attempt_id)
    if attempt.input is None or not 0 <= position < len(attempt.input.assets):
        raise HTTPException(404, detail="本地原媒体不可用。")
    asset = attempt.input.assets[position]
    lease = request.app.state.media_cache.acquire(attempt.source.result_id, [asset])
    try:
        raw = lease.data.get(position)
        if raw is None:
            raise HTTPException(404, detail="本地原媒体不可用。")
        return Response(
            raw,
            media_type=asset.mime_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "Content-Disposition": "inline",
            },
        )
    finally:
        lease.close()
