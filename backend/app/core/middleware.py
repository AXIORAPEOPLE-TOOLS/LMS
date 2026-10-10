"""HTTP middleware: request ids, the API call log, and fail-fast while the database is down."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import DATABASE_DOWN_MESSAGE
from app.core.resilience import breaker
from app.modules.monitoring.collector import metrics

# These keep working with no database, so the UI can show what is going on.
DB_FREE_PATHS = ("/api/health",)
# Polled every few seconds by the UI; logged only when they fail or are slow.
QUIET_PATHS = ("/api/health", "/api/admin/monitoring")

logger = logging.getLogger("api")
SECRET_PARAMS = re.compile(r"((?:token|password|key|secret)[^=&]*=)[^&]*", re.I)


def log_call(request: Request, status: int, ms: float) -> None:
    """One line per API call: GET /api/courses?q=x -> 200 in 34 ms (user=..., ip=..., rid=...)."""
    settings = get_settings()
    path = request.url.path
    if not settings.log_requests or not path.startswith("/api/"):
        return
    slow = ms >= settings.slow_request_ms
    if path.startswith(QUIET_PATHS) and status < 400 and not slow:
        return
    query = "?" + SECRET_PARAMS.sub(r"\1***", request.url.query) if request.url.query else ""
    user = getattr(request.state, "user_id", None) or "-"
    ip = request.client.host if request.client else "-"
    rid = getattr(request.state, "request_id", "-")
    message = "%s %s%s -> %s in %.0f ms (user=%s ip=%s rid=%s)"
    args = (request.method, path, query[:200], status, ms, user, ip, rid)
    if status >= 500:
        logger.error(message, *args)
    elif slow:
        logger.warning("SLOW " + message, *args)
    elif status >= 400:
        logger.warning(message, *args)
    else:
        logger.info(message, *args)


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        path = request.url.path
        started = time.perf_counter()
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
        log_call(request, response.status_code, (time.perf_counter() - started) * 1000)
        return response
