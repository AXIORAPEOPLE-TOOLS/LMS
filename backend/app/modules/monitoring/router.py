import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.deps import AdminUser
from app.core.resilience import breaker
from app.modules.monitoring.service import snapshot

router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])

STREAM_SECONDS = 3


@router.get("")
async def monitoring(_: AdminUser) -> dict[str, Any]:
    return await snapshot()


@router.get("/stream")
async def monitoring_stream(request: Request, _: AdminUser) -> StreamingResponse:
    """Live updates every few seconds (server-sent events). The page falls back to polling."""

    async def events() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            try:
                yield f"event: snapshot\ndata: {json.dumps(await snapshot(), default=str)}\n\n"
            except Exception:
                yield f"event: degraded\ndata: {json.dumps({'retry_seconds': 10})}\n\n"
            await asyncio.sleep(STREAM_SECONDS)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/breakers/{name}/reset", status_code=204)
async def reset_breaker(name: str, _: AdminUser) -> None:
    """Close a breaker by hand after fixing the service (everything automatic has a manual way)."""
    breaker(name).record_success()
