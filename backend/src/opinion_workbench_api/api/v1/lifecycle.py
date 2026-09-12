from fastapi import APIRouter, WebSocket

from opinion_workbench_api.services.application_lifecycle import ApplicationLifecycle

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


@router.websocket("/ws")
async def lifecycle_socket(websocket: WebSocket) -> None:
    lifecycle: ApplicationLifecycle | None = getattr(
        websocket.app.state, "application_lifecycle", None
    )
    if lifecycle is None:
        await websocket.close(code=1008, reason="application lifecycle unavailable")
        return
    await lifecycle.handle_websocket(websocket)
