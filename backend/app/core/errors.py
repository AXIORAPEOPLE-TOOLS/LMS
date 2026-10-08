"""Domain errors and their HTTP mapping.

Services raise these; they never import FastAPI. The handlers below turn them
into a consistent JSON body: {"error": {"code": ..., "message": ..., "request_id": ...}}.

Robustness rule: a user never sees a raw 500 or a stack trace. Infrastructure
failures become a calm 503 ("try again in a minute"); anything unexpected
becomes a friendly message with a request id that support can look up in logs.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

logger = logging.getLogger("errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthenticated"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


DATABASE_DOWN_MESSAGE = "We cannot reach the database right now. Nothing was lost. Please try again in a minute."
UNEXPECTED_MESSAGE = (
    "Something went wrong on our side. Please try again. If it keeps happening, share the reference code with support."
)


# PostgreSQL SQLSTATE classes that mean "cannot reach / not allowed in", not "bad query":
# 08 connection exception, 28 invalid authorization, 53 insufficient resources, 57P0x shutdown/cannot connect.
_CONNECTION_SQLSTATES = ("08", "28", "53", "57P")


def is_connection_failure(exc: DBAPIError) -> bool:
    """True when the database could not be reached (wrong/removed endpoint, auth, network, overload)."""
    if exc.connection_invalidated or exc.statement is None:
        return True  # failed while connecting: no statement ever ran
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(getattr(exc.orig, "__cause__", None), "sqlstate", None)
    return bool(sqlstate and str(sqlstate).startswith(_CONNECTION_SQLSTATES))


def _track(request: Request, code: str, message: str) -> None:
    from app.modules.monitoring.collector import metrics

    metrics.record_error(request.url.path, code, message, getattr(request.state, "request_id", None))


def _body(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code, content=_body(request, exc.code, exc.message, exc.details), headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": str(err["msg"]).removeprefix("Value error, ")}
            for err in exc.errors()
        ]
        message = fields[0]["message"] if fields else "Please check the form."
        return JSONResponse(status_code=422, content=_body(request, "validation_failed", message, fields))

    @app.exception_handler(OperationalError)
    @app.exception_handler(PoolTimeoutError)
    @app.exception_handler(ConnectionError)
    @app.exception_handler(TimeoutError)
    async def _handle_infra_down(request: Request, exc: Exception) -> JSONResponse:
        from app.core.resilience import breaker

        breaker("database", failure_threshold=2, reset_seconds=15).record_failure(exc)
        logger.error("Dependency unavailable on %s %s: %s", request.method, request.url.path, exc)
        _track(request, "service_unavailable", str(exc))
        return JSONResponse(
            status_code=503,
            content=_body(request, "service_unavailable", DATABASE_DOWN_MESSAGE),
            headers={"Retry-After": "30"},
        )

    @app.exception_handler(DBAPIError)
    async def _handle_db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        if is_connection_failure(exc):
            return await _handle_infra_down(request, exc)
        logger.exception("Database error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=_body(request, "unexpected", UNEXPECTED_MESSAGE))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        _track(request, "unexpected", f"{type(exc).__name__}: {exc}")
        return JSONResponse(status_code=500, content=_body(request, "unexpected", UNEXPECTED_MESSAGE))
