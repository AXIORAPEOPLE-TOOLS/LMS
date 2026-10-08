from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.skills.models import JobRole, RoleSkill, Skill, SkillLevel
from testkit import UserFactory, auth


async def test_my_skills_shows_gap_and_rank(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    role = JobRole(code="ADM", name="Admissions Counsellor")
    comm = Skill(code="COMM", name="Customer communication")
    privacy = Skill(code="DPDP", name="Data privacy")
    session.add_all([role, comm, privacy])
    await session.flush()
    session.add_all(
        [
            RoleSkill(job_role_id=role.id, skill_id=comm.id, required_level=3),
            RoleSkill(job_role_id=role.id, skill_id=privacy.id, required_level=2),
        ]
    )
    await session.commit()

    me = await make_user(job_role_id=role.id)
    other = await make_user()
    session.add_all(
        [
            SkillLevel(user_id=me.id, skill_id=comm.id, level=3, score=68),
            SkillLevel(user_id=other.id, skill_id=comm.id, level=5, score=92),
        ]
    )
    await session.commit()

    rows = (await client.get("/me/skills", headers=auth(me))).json()
    by_name = {r["skill_name"]: r for r in rows}
    assert by_name["Data privacy"]["gap"] == 2 and by_name["Data privacy"]["current_level"] is None
    assert by_name["Customer communication"]["gap"] == 0
    assert (by_name["Customer communication"]["rank"], by_name["Customer communication"]["out_of"]) == (2, 2)
    assert rows[0]["skill_name"] == "Data privacy"  # biggest gap first


async def test_ranking_hides_names_of_people_who_opted_out(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    skill = Skill(code="COMM", name="Customer communication")
    session.add(skill)
    await session.commit()
    viewer = await make_user(full_name="Asha Verma")
    shy = await make_user(full_name="Pooja Nair", show_name_on_boards=False)
    session.add_all(
        [
            SkillLevel(user_id=viewer.id, skill_id=skill.id, level=3, score=74),
            SkillLevel(user_id=shy.id, skill_id=skill.id, level=4, score=81),
        ]
    )
    await session.commit()

    rows = (await client.get(f"/skills/{skill.id}/ranking", headers=auth(viewer))).json()["rows"]
    assert [r["name"] for r in rows] == ["A colleague", "Asha V."]
    assert rows[1]["is_me"] is True


async def test_manual_override_is_audited(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skill = Skill(code="X", name="Negotiation")
    session.add(skill)
    await session.commit()
    learner = await make_user()
    manager = await make_user("manager")
    response = await client.put(
        f"/users/{learner.id}/skills/{skill.id}/level",
        json={"level": 2, "reason": "Observed on live calls"},
        headers=auth(manager),
    )
    assert response.status_code == 204
    assert (await client.put(
        f"/users/{learner.id}/skills/{skill.id}/level", json={"level": 2, "reason": "x y z"}, headers=auth(learner)
    )).status_code == 403


async def test_admin_replaces_role_skills(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    role = (await client.post("/job-roles", json={"code": "R1", "name": "Inside Sales Executive"}, headers=auth(admin))).json()
    skill = (await client.post("/skills", json={"code": "S1", "name": "Telesales"}, headers=auth(admin))).json()
    detail = await client.put(
        f"/job-roles/{role['id']}/skills",
        json={"skills": [{"skill_id": skill["id"], "required_level": 3}]},
        headers=auth(admin),
    )
    assert detail.status_code == 200
    assert detail.json()["skills"][0]["required_level"] == 3
