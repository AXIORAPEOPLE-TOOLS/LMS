"""HTTP middleware: request ids and fail-fast while the database is down."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.errors import DATABASE_DOWN_MESSAGE
from app.core.resilience import breaker
from app.modules.monitoring.collector import metrics

# These keep working with no database, so the UI can show what is going on.
DB_FREE_PATHS = ("/api/health",)


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        path = request.url.path
        db = breaker("database", failure_threshold=2, reset_seconds=15)
        if path.startswith("/api/") and not path.startswith(DB_FREE_PATHS) and db.is_open:
            # Answer at once instead of letting every request wait for a timeout.
            response: Response = JSONResponse(
                status_code=503,
                content={"error": {"code": "service_unavailable", "message": DATABASE_DOWN_MESSAGE, "request_id": request_id}},
                headers={"Retry-After": "15"},
            )
        else:
            metrics.in_flight += 1
            started = time.perf_counter()
            try:
                response = await call_next(request)
            finally:
                metrics.in_flight -= 1
            if path.startswith("/api/") and not path.startswith("/api/admin/monitoring"):
                route = request.scope.get("route")
                template = getattr(route, "path", None) or path  # /api/courses/{course_id}, not every id
                if not template.startswith("/api"):
                    template = "/api" + template  # routers are mounted under the API prefix
                metrics.record(request.method, template, response.status_code, (time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        return response
