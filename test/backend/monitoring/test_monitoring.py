from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.monitoring.collector import MetricsCollector, metrics
from testkit import UserFactory, auth


def test_collector_percentiles_and_timeline() -> None:
    collector = MetricsCollector()
    for ms in (10, 20, 30, 40, 1000):
        collector.record("GET", "/api/x", 200, ms)
    collector.record("GET", "/api/x", 500, 50)
    route = collector.routes()[0]
    assert route["route"] == "GET /api/x" and route["count"] == 6 and route["errors"] == 1
    assert route["p50_ms"] in (30.0, 40.0) and route["p95_ms"] == 1000.0
    timeline = collector.timeline()
    assert len(timeline) == 30 and timeline[-1]["requests"] == 6 and timeline[-1]["errors"] == 1


async def test_snapshot_shows_every_area(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    learner = await make_user()
    await client.get("/courses", headers=auth(learner))  # some traffic
    assert (await client.get("/admin/monitoring", headers=auth(learner))).status_code == 403
    body = (await client.get("/admin/monitoring", headers=auth(admin))).json()
    assert {"server", "api", "database", "redis", "scheduler", "workflows", "breakers", "components"} <= set(body)
    assert body["server"]["cpu_count"] >= 1 and body["database"]["status"] == "up"
    assert body["redis"]["status"] == "inline" and len(body["redis"]["queues"]) == 4
    routes = [r["route"] for r in body["api"]["routes"]]
    assert "GET /api/courses" in routes  # route templates, not raw ids


async def test_unexpected_errors_appear_in_recent_errors(app: FastAPI, make_user: UserFactory) -> None:
    @app.get("/api/_explode")
    async def explode() -> None:
        raise RuntimeError("kaboom")

    admin = await make_user("admin")
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test/api") as c:
        await c.get("/_explode")
        body = (await c.get("/admin/monitoring", headers=auth(admin))).json()
    assert body["api"]["errors"][0]["path"] == "/api/_explode"
    assert "kaboom" in body["api"]["errors"][0]["message"]
    metrics._errors.clear()
