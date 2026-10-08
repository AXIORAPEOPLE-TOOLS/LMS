from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pathways import rules
from app.modules.skills.models import Skill, SkillLevel
from testkit import UserFactory, auth, make_course, make_role, make_test


def test_waves_put_mandatory_first_then_biggest_gaps() -> None:
    gaps = [
        rules.GapInput("comm", "Verbal communication", 2, 0),
        rules.GapInput("dpdp", "Data privacy", 2, 0, is_mandatory=True),
        rules.GapInput("ethics", "Ethics", 2, 1),
        rules.GapInput("crm", "CRM", 3, 3),  # no gap
        rules.GapInput("time", "Time management", 3, None),
    ]
    plan = rules.plan_waves(gaps, wave_size=3, hours_per_level=1.8)
    assert [(p.skill_id, p.wave) for p in plan] == [("dpdp", 1), ("time", 1), ("comm", 1), ("ethics", 2)]
    assert plan[0].estimated_hours == 3.6


async def test_whole_pathway_loop(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skills = [Skill(code=f"S{i}", name=n) for i, n in enumerate(["Data privacy", "Verbal", "Ethics", "Writing"])]
    session.add_all(skills)
    await session.commit()
    role = await make_role(session, "Admissions Counsellor", {s: 2 for s in skills})
    course = await make_course(session, "Data privacy basics", lessons=1, questions=0, skill_id=skills[0].id)
    test = await make_test(session, skill=skills[0], questions=4)
    manager = await make_user("manager", full_name="Mona Manager")
    expert = await make_user(full_name="Esha Expert")
    session.add(SkillLevel(user_id=expert.id, skill_id=skills[0].id, level=5, score=95))
    await session.commit()
    asha = await make_user(full_name="Asha Verma", job_role_id=role.id, manager_id=manager.id)
    h = auth(asha)

    built = (await client.post("/me/pathway/generate", json={}, headers=h)).json()
    assert built["status"] == "pending_approval" and built["total_waves"] == 2
    assert built["next_step"] is None  # nothing to do until approved
    first = built["waves"][0]["items"][0]
    assert first["skill_name"] == "Data privacy" and first["course_title"] == "Data privacy basics"
    assert first["mentor_name"] == "Esha Expert"

    approvals = (await client.get("/me/notifications", headers=auth(manager))).json()["items"]
    assert "needs your approval" in approvals[0]["title"]
    assert (await client.post(f"/pathways/{built['id']}/approve", headers=h)).status_code == 403
    assert (await client.post(f"/pathways/{built['id']}/approve", headers=auth(manager))).status_code == 204

    view = (await client.get("/me/pathway", headers=h)).json()
    assert view["status"] == "active" and view["current_wave"] == 1
    assert view["waves"][1]["status"] == "locked"
    assert view["next_step"]["title"] == "Learn: Data privacy basics"
    # The wave's course now shows in my learning.
    assert any(a["source"] == "pathway" for a in (await client.get("/me/assignments", headers=h)).json())

    # Learn: finishing the course moves the step on by itself.
    lesson = (await client.get(f"/courses/{course.id}", headers=h)).json()["lessons"][0]
    await client.post(f"/lessons/{lesson['id']}/complete", headers=h)
    item = (await client.get("/me/pathway", headers=h)).json()["waves"][0]["items"][0]
    assert item["step"] == "practise"

    # Practise: evidence -> manager signs off.
    await client.post(f"/me/pathway/items/{item['id']}/evidence",
                      json={"evidence": "Used the checklist on a real admission call."}, headers=h)
    item = (await client.get("/me/pathway", headers=h)).json()["waves"][0]["items"][0]
    assert item["waiting_for_signoff"] is True
    await client.post(f"/pathway-items/{item['id']}/sign-off", json={"approve": True}, headers=auth(manager))

    # Connect -> prove creates a retest invite.
    await client.post(f"/me/pathway/items/{item['id']}/connected", headers=h)
    tests = (await client.get("/me/tests", headers=h)).json()
    assert tests[0]["test"]["id"] == str(test.id)

    attempt = (await client.post(f"/tests/{test.id}/attempts", json={}, headers=h)).json()
    for q in attempt["questions"]:
        await client.put(f"/attempts/{attempt['id']}/answer", json={"question_id": q["id"], "option_index": 1}, headers=h)
    await client.post(f"/attempts/{attempt['id']}/submit", headers=h)
    item = (await client.get("/me/pathway", headers=h)).json()["waves"][0]["items"][0]
    assert item["step"] == "done"

    # Finish the other wave-1 skills by hand (no courses linked) to unlock wave 2.
    view = (await client.get("/me/pathway", headers=h)).json()
    for other in view["waves"][0]["items"][1:]:
        await client.post(f"/me/pathway/items/{other['id']}/learned", headers=h)
        await client.post(f"/me/pathway/items/{other['id']}/evidence", json={"evidence": "Did it on a live case."}, headers=h)
        await client.post(f"/pathway-items/{other['id']}/sign-off", json={"approve": True}, headers=auth(manager))
        await client.post(f"/me/pathway/items/{other['id']}/connected", headers=h)
    for other in view["waves"][0]["items"][1:]:
        manual = await client.put(f"/users/{asha.id}/skills/{other['skill_id']}/level",
                                  json={"level": 2, "reason": "Observed by manager"}, headers=auth(manager))
        assert manual.status_code == 204
    view = (await client.get("/me/pathway", headers=h)).json()
    assert view["waves"][0]["status"] == "done" and view["current_wave"] == 2


async def test_wave_two_steps_are_locked(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skills = [Skill(code=f"S{i}", name=f"Skill {i}") for i in range(4)]
    session.add_all(skills)
    await session.commit()
    role = await make_role(session, "Role", {s: 1 for s in skills})
    learner = await make_user(job_role_id=role.id)  # no manager: starts straight away
    built = (await client.post("/me/pathway/generate", json={}, headers=auth(learner))).json()
    assert built["status"] == "active"
    locked = built["waves"][1]["items"][0]
    response = await client.post(f"/me/pathway/items/{locked['id']}/learned", headers=auth(learner))
    assert response.status_code == 409 and "opens when" in response.json()["error"]["message"]
