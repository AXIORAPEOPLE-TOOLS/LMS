from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessments.models import TestInvite
from app.modules.learning.models import Assignment
from app.modules.skills.models import CareerMove, Skill, SkillLevel
from app.shared import clock
from testkit import UserFactory, auth, make_course, make_role, make_test


async def _career_setup(session: AsyncSession, make_user: UserFactory):  # type: ignore[no-untyped-def]
    skills = [Skill(code=f"K{i}", name=n) for i, n in enumerate(
        ["Admissions counselling", "Data privacy", "POSH awareness", "Coaching", "Negotiation"])]
    session.add_all(skills)
    await session.commit()
    current = await make_role(session, "Admissions Counsellor", {skills[0]: 3, skills[1]: 2})
    senior = await make_role(session, "Senior Admissions Counsellor", {skills[0]: 4, skills[1]: 3, skills[2]: 2,
                                                                       skills[3]: 3, skills[4]: 3})
    side = await make_role(session, "Inside Sales Executive", {skills[0]: 2})
    session.add_all([
        CareerMove(from_role_id=current.id, to_role_id=senior.id, kind="vertical"),
        CareerMove(from_role_id=current.id, to_role_id=side.id, kind="lateral"),
    ])
    me = await make_user(job_role_id=current.id)
    session.add_all([
        SkillLevel(user_id=me.id, skill_id=skills[0].id, level=3, score=68),
        SkillLevel(user_id=me.id, skill_id=skills[1].id, level=0, score=10),
        SkillLevel(user_id=me.id, skill_id=skills[2].id, level=0, score=5),
    ])
    await session.commit()
    return me, senior, side, skills


async def test_career_readiness_uses_tested_skills_only(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    me, senior, side, _ = await _career_setup(session, make_user)
    career = (await client.get("/me/career", headers=auth(me))).json()
    assert career["current_role_name"] == "Admissions Counsellor"
    assert (career["role_ready_skills"], career["core_skills"]) == (1, 2)
    by_name = {o["role_name"]: o for o in career["options"]}
    assert by_name["Inside Sales Executive"]["readiness_pct"] == 100 and by_name["Inside Sales Executive"]["direction"] == "side"
    senior_opt = by_name["Senior Admissions Counsellor"]
    assert senior_opt["readiness_pct"] == round(3 / 9 * 100)  # 3 tested skills: need 4+3+2, have 3+0+0

    detail = (await client.get(f"/me/career/{senior.id}", headers=auth(me))).json()
    assert (detail["tested"], detail["total"]) == (3, 5)
    assert [g["skill_name"] for g in detail["skills_to_close"]] == ["Data privacy", "POSH awareness", "Admissions counselling"]
    assert detail["test_next"] == ["Coaching", "Negotiation"]
    assert detail["weeks"] > 0

    assert (await client.post(f"/me/career/{senior.id}/add-to-pathway", headers=auth(me))).status_code == 204
    pathway = (await client.get("/me/pathway", headers=auth(me))).json()
    assert pathway["target_role_name"] == "Senior Admissions Counsellor"


async def test_home_always_shows_one_next_step(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    learner = await make_user(full_name="Asha Verma")
    home = (await client.get("/me/home", headers=auth(learner))).json()
    assert home["first_name"] == "Asha" and home["next_step"]["kind"] == "explore"  # never a dead end

    test = await make_test(session, title="Customer communication")
    session.add(TestInvite(user_id=learner.id, test_id=test.id, due_on=clock.today() + timedelta(days=10)))
    await session.commit()
    home = (await client.get("/me/home", headers=auth(learner))).json()
    assert home["next_step"]["kind"] == "skill_check"

    course = await make_course(session, "POSH basics")
    session.add(Assignment(user_id=learner.id, course_id=course.id, is_mandatory=True,
                           due_on=clock.today() - timedelta(days=2)))
    await session.commit()
    home = (await client.get("/me/home", headers=auth(learner))).json()
    assert home["next_step"]["kind"] == "assignment" and home["next_step"]["is_overdue"] is True
    assert any(c["kind"] == "skill_check" for c in home["coming_up"])


async def test_manager_team_view_and_nudge(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    manager = await make_user("manager", full_name="Mona Manager")
    late = await make_user(full_name="Dev Patel", manager_id=manager.id)
    fine = await make_user(full_name="Riya Sharma", manager_id=manager.id)
    outsider = await make_user()
    course = await make_course(session, "DPDP basics")
    session.add(Assignment(user_id=late.id, course_id=course.id, due_on=clock.today() - timedelta(days=6)))
    await session.commit()

    team = (await client.get("/team", headers=auth(manager))).json()
    assert team["counts"] == {"on_track": 1, "due_soon": 0, "overdue": 1, "to_approve": 0, "people": 2}
    assert team["attention"][0]["detail"] == "DPDP basics · 6 days overdue"
    assert {r["name"] for r in team["heatmap"]["rows"]} == {"Dev P.", "Riya S."}

    assert (await client.get("/team", headers=auth(fine))).status_code == 403
    nudge = {"user_id": str(late.id), "item": "DPDP basics"}
    assert (await client.post("/team/nudge", json=nudge, headers=auth(manager))).status_code == 204
    assert (await client.post("/team/nudge", json=nudge, headers=auth(manager))).status_code == 409  # once a day
    other = {"user_id": str(outsider.id)}
    assert (await client.post("/team/nudge", json=other, headers=auth(manager))).status_code == 403
    inbox = (await client.get("/me/notifications", headers=auth(late))).json()["items"]
    assert inbox[0]["title"] == "A friendly reminder from Mona"
    _ = datetime.now(UTC)
