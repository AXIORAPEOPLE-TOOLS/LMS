from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.learning.models import Assignment
from app.modules.workflows.defaults import ensure_default_workflows
from app.modules.workflows.models import Workflow
from testkit import UserFactory, auth, make_course, make_role, make_skill, make_test


async def _setup(session: AsyncSession) -> None:
    await ensure_default_workflows(session)
    await session.commit()


async def _new_joiner(session: AsyncSession) -> Workflow:
    return (await session.scalars(select(Workflow).where(Workflow.code == "new_joiner"))).one()


async def test_defaults_are_listed(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    await _setup(session)
    admin = await make_user("admin")
    body = (await client.get("/admin/workflows", headers=auth(admin))).json()
    assert [w["name"] for w in body["workflows"]][:2] == ["New joiner", "Skill test campaign"]
    new_joiner = body["workflows"][0]
    assert new_joiner["mode"] == "hybrid"
    assert new_joiner["action_labels"] == ["Assign mandatory training", "Create skill tests for the role", "Send welcome"]
    assert body["paused"] is False


async def test_hybrid_new_joiner_waits_for_approval_then_sends(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    await _setup(session)
    skill = await make_skill(session)
    role = await make_role(session, "Counsellor", {skill: 3})
    await make_test(session, skill=skill)
    posh = await make_course(session, "POSH awareness", is_mandatory=True)
    admin = await make_user("admin")
    h = auth(admin)

    created = []
    for email in ("a@example.com", "b@example.com"):
        r = await client.post("/users", json={"email": email, "full_name": "New Person", "password": "Welcome123",
                                              "job_role_id": str(role.id)}, headers=h)
        created.append(r.json()["id"])
    runs = (await client.get("/admin/workflows/runs?status=pending_approval", headers=h)).json()
    assert len(runs) == 1  # both joiners go into one batch
    assert runs[0]["preview"]["people"] == 2
    assert 'Assign "POSH awareness" to 2 people' in runs[0]["preview"]["lines"]
    assert (await session.scalars(select(Assignment))).all() == []  # nothing sent yet

    done = (await client.post(f"/admin/workflows/runs/{runs[0]['id']}/decision", json={"approve": True}, headers=h)).json()
    assert done["status"] == "completed"
    assignments = (await session.scalars(select(Assignment).where(Assignment.course_id == posh.id))).all()
    assert len(assignments) == 2 and all(a.is_mandatory and a.source == "workflow" for a in assignments)
    newcomer = await session.get(__import__("app.modules.identity.models", fromlist=["User"]).User,
                                 __import__("uuid").UUID(created[0]))
    tests = (await client.get("/me/tests", headers=auth(newcomer))).json()
    assert len(tests) == 1
    inbox = [n["title"] for n in (await client.get("/me/notifications", headers=auth(newcomer))).json()["items"]]
    assert any(t.startswith("Welcome") for t in inbox)


async def test_auto_mode_runs_immediately_and_stop_all_holds_it(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    await _setup(session)
    await make_course(session, "DPDP basics", is_mandatory=True)
    admin = await make_user("admin")
    h = auth(admin)
    workflow = await _new_joiner(session)
    await client.put(f"/admin/workflows/{workflow.id}/mode", json={"mode": "auto"}, headers=h)

    await client.post("/users", json={"email": "c@example.com", "full_name": "Auto Person", "password": "Welcome123"},
                      headers=h)
    assert len((await session.scalars(select(Assignment))).all()) == 1

    await client.put("/admin/workflows/pause", json={"paused": True}, headers=h)
    await client.post("/users", json={"email": "d@example.com", "full_name": "Held Person", "password": "Welcome123"},
                      headers=h)
    assert len((await session.scalars(select(Assignment))).all()) == 1  # held for a person to approve
    pending = (await client.get("/admin/workflows/runs?status=pending_approval", headers=h)).json()
    assert len(pending) == 1


async def test_manual_mode_does_nothing_until_run_by_hand(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    await _setup(session)
    await make_course(session, "POSH", is_mandatory=True)
    admin = await make_user("admin")
    h = auth(admin)
    workflow = await _new_joiner(session)
    await client.put(f"/admin/workflows/{workflow.id}/mode", json={"mode": "manual"}, headers=h)
    person = (await client.post("/users", json={"email": "e@example.com", "full_name": "Manual Person",
                                                "password": "Welcome123"}, headers=h)).json()
    assert (await client.get("/admin/workflows/runs", headers=h)).json() == []

    context = {"context": {"user_ids": [person["id"]]}}
    preview = (await client.post(f"/admin/workflows/{workflow.id}/preview", json=context, headers=h)).json()
    assert preview["people"] == 1
    run = (await client.post(f"/admin/workflows/{workflow.id}/run", json=context, headers=h)).json()
    assert run["status"] == "completed" and run["triggered_by"] == "manual"


async def test_failed_run_sends_nothing(client: AsyncClient, database: Database, make_user: UserFactory) -> None:
    from app.modules.workflows.actions import ACTIONS, ActionResult

    async with database.session_factory() as s:
        await ensure_default_workflows(s)
        await s.commit()
        workflow = (await s.scalars(select(Workflow).where(Workflow.code == "new_joiner"))).one()

    class Boom:
        code, label = "send_welcome", "Send welcome"

        async def preview(self, *_: object) -> ActionResult:
            return ActionResult(lines=[], people=0)

        async def execute(self, *_: object) -> ActionResult:
            raise RuntimeError("provider down")

    original = ACTIONS["send_welcome"]
    ACTIONS["send_welcome"] = Boom()  # type: ignore[assignment]
    try:
        admin = await make_user("admin")
        run = (await client.post(f"/admin/workflows/{workflow.id}/run", json={"context": {"user_ids": [str(admin.id)]}},
                                 headers=auth(admin))).json()
    finally:
        ACTIONS["send_welcome"] = original
    assert run["status"] == "failed" and run["result"]["error"] == "This run could not finish. Nothing was sent."
