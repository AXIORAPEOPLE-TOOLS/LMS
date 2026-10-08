"""The demo company loads and every main screen answers for each role (a broad smoke test)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.seed.demo import PASSWORD, seed_if_empty

LEARNER_PATHS = [
    "/me", "/me/home", "/me/pathway", "/me/skills", "/me/assignments", "/me/tests", "/me/certificates", "/me/career",
    "/me/profile", "/me/badges", "/challenges", "/me/sessions", "/me/notifications", "/courses",
    "/leaderboards/skill_champions", "/leaderboards/learning_hours", "/leaderboards/pathway_progress",
    "/leaderboards/most_improved", "/leaderboards/compliance", "/knowledge/home", "/knowledge/library",
    "/knowledge/my-items", "/knowledge/search?q=refund", "/health",
]
MANAGER_PATHS = ["/team", "/reports", "/reports/mandatory_compliance", "/knowledge/dashboard"]
ADMIN_PATHS = [
    "/admin/home", "/users", "/job-roles", "/skills", "/admin/courses", "/admin/tests", "/admin/sessions",
    "/admin/workflows", "/admin/workflows/runs", "/admin/reminders/preview", "/admin/reminders/rules", "/proctoring/queue",
    "/settings", "/audit", "/admin/scheduler", "/knowledge/without-owner", "/knowledge/access-requests",
]


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def seeded(database: Database) -> None:
    async with database.session_factory() as session:
        assert await seed_if_empty(session) is True
        await session.commit()
    async with database.session_factory() as session:
        assert await seed_if_empty(session) is False  # idempotent


async def test_every_screen_answers_for_each_role(client: AsyncClient, seeded: None, session: AsyncSession) -> None:
    asha = await _login(client, "asha@example.com")
    for path in LEARNER_PATHS:
        assert (await client.get(path, headers=asha)).status_code == 200, path
    manager = await _login(client, "manager@example.com")
    for path in MANAGER_PATHS:
        assert (await client.get(path, headers=manager)).status_code == 200, path
    admin = await _login(client, "admin@example.com")
    for path in ADMIN_PATHS:
        assert (await client.get(path, headers=admin)).status_code == 200, path
    assert (await client.get("/admin/home", headers=asha)).status_code == 403


async def test_demo_matches_the_deck_story(client: AsyncClient, seeded: None) -> None:
    asha = await _login(client, "asha@example.com")
    home = (await client.get("/me/home", headers=asha)).json()
    assert home["first_name"] == "Asha" and home["streak_days"] >= 5
    assert home["next_step"]["kind"] == "pathway" and "Data privacy" in home["next_step"]["title"]
    pathway = (await client.get("/me/pathway", headers=asha)).json()
    assert pathway["total_waves"] == 3 and pathway["current_wave"] == 1
    assert [i["step"] for i in pathway["waves"][0]["items"]] == ["learn", "connect", "prove"]
    profile = (await client.get("/me/profile", headers=asha)).json()
    assert profile["level_name"] == "Practitioner" and profile["points_to_next"] == 260
    career = (await client.get("/me/career", headers=asha)).json()
    assert career["current_role_name"] == "Admissions Counsellor" and len(career["options"]) == 4
    hub = (await client.get("/knowledge/library", headers=asha)).json()
    assert hub["total"] >= 20
