from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from testkit import UserFactory, auth, make_role, make_skill, make_test


async def _answer_all(client: AsyncClient, attempt: dict, headers: dict, *, correct: int) -> None:
    for i, question in enumerate(attempt["questions"]):
        option = 1 if i < correct else 0  # option 1 is always right in make_test
        r = await client.put(f"/attempts/{attempt['id']}/answer", json={"question_id": question["id"], "option_index": option},
                             headers=headers)
        assert r.status_code == 204


async def test_skill_check_gives_level_rank_and_next_step(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    comm = await make_skill(session, "Customer communication")
    privacy = await make_skill(session, "Data privacy")
    role = await make_role(session, "Admissions Counsellor", {comm: 3, privacy: 2})
    test = await make_test(session, skill=comm, questions=4)
    await make_test(session, skill=privacy, title="Privacy check")
    asha = await make_user(full_name="Asha Verma", job_role_id=role.id)
    h = auth(asha)

    intro = (await client.get(f"/tests/{test.id}", headers=h)).json()
    assert intro["question_count"] == 4 and intro["pass_mark"] is None  # no pass or fail
    attempt = (await client.post(f"/tests/{test.id}/attempts", json={}, headers=h)).json()
    assert attempt["total"] == 4 and "answer_index" not in str(attempt)
    await _answer_all(client, attempt, h, correct=3)  # 75 -> level 4

    result = (await client.post(f"/attempts/{attempt['id']}/submit", headers=h)).json()
    assert (result["score"], result["level"], result["level_name"]) == (75, 4, "Advanced")
    assert result["required_level"] == 3 and result["meets_requirement"] is True
    assert (result["rank"], result["out_of"]) == (1, 1)
    assert result["skills_left_to_check"] == 1
    assert "1 more skill to check" in result["message"]

    skills = {s["skill_name"]: s for s in (await client.get("/me/skills", headers=h)).json()}
    assert skills["Customer communication"]["current_level"] == 4

    # Submitting twice is safe and returns the same result.
    again = (await client.post(f"/attempts/{attempt['id']}/submit", headers=h)).json()
    assert again["score"] == 75


async def test_answers_are_private_and_cannot_change_after_submit(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    test = await make_test(session, questions=2)
    owner = await make_user()
    other = await make_user()
    attempt = (await client.post(f"/tests/{test.id}/attempts", json={}, headers=auth(owner))).json()
    assert (await client.get(f"/attempts/{attempt['id']}", headers=auth(other))).status_code == 404
    await client.post(f"/attempts/{attempt['id']}/submit", headers=auth(owner))
    late = await client.put(
        f"/attempts/{attempt['id']}/answer",
        json={"question_id": attempt["questions"][0]["id"], "option_index": 1},
        headers=auth(owner),
    )
    assert late.status_code == 409


async def test_campaign_preview_send_and_undo(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skill = await make_skill(session)
    role = await make_role(session, "Support Executive", {skill: 3})
    test = await make_test(session, skill=skill)
    admin = await make_user("admin")
    learners = [await make_user(job_role_id=role.id) for _ in range(2)]
    body = {"test_ids": [str(test.id)], "audience": {"job_role_id": str(role.id)}, "due_on": "2026-10-20"}

    preview = (await client.post("/admin/tests/campaign/preview", json=body, headers=auth(admin))).json()
    assert preview["new_invites"] == 2
    sent = (await client.post("/admin/tests/campaign", json=body, headers=auth(admin))).json()
    mine = (await client.get("/me/tests", headers=auth(learners[0]))).json()
    assert mine[0]["status"] == "pending" and mine[0]["due_on"] == "2026-10-20"
    await client.post(f"/admin/bulk/{sent['bulk_action_id']}/undo", headers=auth(admin))
    assert (await client.get("/me/tests", headers=auth(learners[0]))).json() == []
