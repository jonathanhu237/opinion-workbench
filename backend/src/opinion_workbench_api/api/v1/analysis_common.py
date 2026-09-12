"""Shared secret-safe/no-store boundary for new analysis resources."""

from fastapi import HTTPException, Request

from opinion_workbench_api.api.v1.ai_summaries import SummaryRoute
from opinion_workbench_api.services.ai_errors import AIError
from opinion_workbench_api.services.analysis_errors import (
    AnalysisError,
    AnalysisErrorResponse,
)

ERROR_RESPONSES = {
    status: {"model": AnalysisErrorResponse}
    for status in (403, 404, 409, 415, 422, 503)
}


class AnalysisRoute(SummaryRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except (AnalysisError, AIError) as error:
                raise HTTPException(
                    error.status_code,
                    detail={"code": error.code, "message": error.message},
                    headers={"Cache-Control": "no-store"},
                ) from None
            except HTTPException:
                raise
            except Exception:
                error = AnalysisError("analysis_storage_unavailable")
                raise HTTPException(
                    error.status_code,
                    detail={"code": error.code, "message": error.message},
                    headers={"Cache-Control": "no-store"},
                ) from None

        return handler
