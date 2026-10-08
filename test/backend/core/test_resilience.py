"""The product must degrade, never crash: friendly errors and fallbacks for every service."""

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.core.database import Database
from app.core.queue import BullMQQueue, InlineQueue, Job, defer_job, dispatch_pending, job_handler, set_queue
from app.core.resilience import CircuitBreaker, CircuitOpenError, breaker
from app.modules.ai.groq_provider import GroqProvider
from app.modules.ai.provider import RoleCandidate
from app.modules.notifications.channels import CHANNELS
from app.modules.notifications.service import NotificationService
from testkit import UserFactory

RAN: list[dict[str, Any]] = []


@job_handler("test.record")
async def _record(_: Any, data: dict[str, Any]) -> None:
    RAN.append(data)


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test/api")


async def test_unexpected_error_is_friendly_with_reference(app: FastAPI) -> None:
    @app.get("/api/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    async with _client(app) as c:
        response = await c.get("/_boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "unexpected" and "secret" not in error["message"]
    assert error["request_id"]


async def test_database_down_returns_503_then_fails_fast(app: FastAPI) -> None:
    calls = {"n": 0}

    @app.get("/api/_db")
    async def db_down() -> None:
        calls["n"] += 1
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    async with _client(app) as c:
        first = await c.get("/_db")
        second = await c.get("/_db")
        third = await c.get("/_db")
        health = await c.get("/health")
    assert first.status_code == second.status_code == third.status_code == 503
    assert first.json()["error"]["code"] == "service_unavailable"
    assert calls["n"] == 2  # breaker opened after two failures: third call never hit the route
    assert health.status_code == 200  # health still answers so the UI can explain


async def test_unreachable_database_endpoint_is_503_not_500(app: FastAPI) -> None:
    """E.g. a deleted Neon endpoint: the error comes while connecting, with no SQL statement."""
    from sqlalchemy.exc import DBAPIError

    @app.get("/api/_gone")
    async def gone() -> None:
        raise DBAPIError(None, None, Exception("The requested endpoint could not be found"))

    async with _client(app) as c:
        response = await c.get("/_gone")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


async def test_a_bad_query_is_still_a_500(app: FastAPI) -> None:
    from sqlalchemy.exc import DBAPIError

    @app.get("/api/_badsql")
    async def bad() -> None:
        raise DBAPIError("SELECT nope", {}, Exception("syntax error"))

    async with _client(app) as c:
        response = await c.get("/_badsql")
    assert response.status_code == 500 and response.json()["error"]["code"] == "unexpected"


async def test_validation_errors_are_plain(client: AsyncClient) -> None:
    response = await client.post("/auth/login", json={"email": "not-an-email", "password": "x"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed" and body["details"][0]["field"] == "email"


async def test_redis_down_runs_jobs_inline(database: Database) -> None:
    RAN.clear()
    set_queue(BullMQQueue("redis://127.0.0.1:1"))  # nothing listens here
    try:
        for i in range(4):
            async with database.session_factory() as s:
                defer_job(s, "scheduled", "test.record", {"i": i})
                await s.commit()
                await dispatch_pending(s)
    finally:
        set_queue(InlineQueue())
    assert [d["i"] for d in RAN] == [0, 1, 2, 3]
    assert breaker("redis").is_open


async def test_groq_down_falls_back_to_rules() -> None:
    provider = GroqProvider(api_key="bad", model="x", timeout=1)

    async def fail(*_: Any, **__: Any) -> Any:
        raise ConnectionError("groq unreachable")

    provider.client.chat.completions.create = fail  # type: ignore[method-assign]
    roles = [RoleCandidate(id=__import__("uuid").uuid4(), name="Admissions Counsellor")]
    for _ in range(4):
        match = await provider.match_role("Admissions Exec", roles)
        assert match is not None and match.role_name == "Admissions Counsellor"
    assert breaker("groq").is_open


async def test_email_provider_down_keeps_in_app_message(database: Database, make_user: UserFactory) -> None:
    user = await make_user()

    class Broken:
        key = "email"

        async def send(self, *_: Any) -> str:
            raise TimeoutError("smtp")

    original = CHANNELS["email"]
    CHANNELS["email"] = Broken()  # type: ignore[assignment]
    try:
        statuses = []
        for _ in range(4):
            async with database.session_factory() as s:
                n = await NotificationService(s).notify(user.id, kind="system", title="Hello")
                await s.commit()
                await dispatch_pending(s)
                await s.refresh(n)
                statuses.append(n.channel_status["email"])
    finally:
        CHANNELS["email"] = original
    assert statuses == ["failed", "failed", "failed", "paused"]


async def test_circuit_breaker_half_opens_after_cooldown() -> None:
    cb = CircuitBreaker("x", failure_threshold=1, reset_seconds=0)

    async def bad() -> None:
        raise ValueError

    try:
        await cb.call(bad)
    except ValueError:
        pass
    assert cb.state == "half_open"

    async def good() -> int:
        return 1

    assert await cb.call(good) == 1 and cb.state == "closed"
    cb2 = CircuitBreaker("y", failure_threshold=1, reset_seconds=60)
    try:
        await cb2.call(bad)
    except ValueError:
        pass
    try:
        await cb2.call(good)
        raise AssertionError
    except CircuitOpenError:
        pass


async def test_health_reports_components(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["mode"] == "full"
    assert body["components"]["database"] == "up"
    assert body["components"]["queue"] == "inline"
    assert {"database", "queue", "assistant", "email", "whatsapp", "storage"} <= set(body["components"])
