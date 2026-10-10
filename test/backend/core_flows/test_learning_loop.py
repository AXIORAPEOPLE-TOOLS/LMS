"""Acceptance tests for the core learning loop (docs/core-flows.md, section E).

Employee signs up with a role -> role skills on profile -> HR assigns by skill (auto) or by name (manual)
-> only those people are notified -> course -> lessons -> test -> result -> HR tracker.
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import Assignment, CourseQuizAttempt
from testkit import UserFactory, auth, make_course, make_role, make_skill


async def _setup(session: AsyncSession):  # type: ignore[no-untyped-def]
    cyber = await make_skill(session, "Cybersecurity awareness", code="CYBER")
    comms = await make_skill(session, "Customer communication", code="COMMS")
    developer = await make_role(session, "Software Developer", {cyber: 3})
    sales = await make_role(session, "Sales Executive", {comms: 3})
    course = await make_course(session, "Cybersecurity basics", lessons=2, questions=2, skill_id=cyber.id, pass_mark=50)
    return cyber, comms, developer, sales, course


async def _signup(client: AsyncClient, email: str, role_id: object, name: str = "Nisha Rao") -> dict[str, str]:
    response = await client.post(
        "/auth/signup", json={"full_name": name, "email": email, "password": "a-long-password", "job_role_id": str(role_id)}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_signup_with_role_shows_role_skills(client: AsyncClient, session: AsyncSession) -> None:
    cyber, _, developer, _, _ = await _setup(session)
    options = (await client.get("/auth/signup-options")).json()
    assert options["allowed"] is True and any(r["name"] == "Software Developer" for r in options["roles"])

    h = await _signup(client, "nisha@example.com", developer.id)
    me = (await client.get("/me", headers=h)).json()
    assert me["job_role_name"] == "Software Developer" and me["system_roles"] == ["learner"]
    skills = (await client.get("/me/skills", headers=h)).json()
    assert [s["skill_name"] for s in skills] == ["Cybersecurity awareness"]
    assert skills[0]["required_by_role"] is True and skills[0]["required_level"] == 3


async def test_signup_respects_settings(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, developer, _, _ = await _setup(session)
    admin = await make_user("admin")
    await client.put("/settings/identity.signup_email_domains", json={"value": ["acme.in"]}, headers=auth(admin))
    wrong = await client.post(
        "/auth/signup", json={"full_name": "Om", "email": "om@gmail.com", "password": "a-long-password", "job_role_id": str(developer.id)}
    )
    assert wrong.status_code == 422 and "acme.in" in wrong.json()["error"]["message"]
    await client.put("/settings/identity.allow_self_signup", json={"value": False}, headers=auth(admin))
    assert (await client.get("/auth/signup-options")).json()["allowed"] is False


async def test_skill_states_are_separate(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    cyber, _, developer, _, course = await _setup(session)
    admin = await make_user("admin")
    h = await _signup(client, "dev@example.com", developer.id)
    me = (await client.get("/me", headers=h)).json()

    state = lambda skills: (skills[0]["training"], skills[0]["proven"])  # noqa: E731
    assert state((await client.get("/me/skills", headers=h)).json()) == ("none", False)
    body = {"course_id": str(course.id), "audience": {"user_ids": [me["id"]]}}
    await client.post("/admin/assignments", json=body, headers=auth(admin))
    assert state((await client.get("/me/skills", headers=h)).json()) == ("assigned", False)
    lessons = (await client.get(f"/courses/{course.id}", headers=h)).json()["lessons"]
    for lesson in lessons:
        await client.post(f"/lessons/{lesson['id']}/complete", headers=h)
    assert state((await client.get("/me/skills", headers=h)).json()) == ("in_progress", False)
    questions = [q["id"] for q in (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()]
    await client.post(f"/courses/{course.id}/quiz", json={"answers": {q: 0 for q in questions}}, headers=h)
    # Course done is not the same as a proven level: only a skill test sets the level.
    assert state((await client.get("/me/skills", headers=h)).json()) == ("course_done", False)


async def test_assign_by_skill_previews_people_whose_role_needs_it(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    cyber, _, developer, sales, course = await _setup(session)
    admin = await make_user("admin")
    dev1 = await make_user(full_name="Arun Dev", job_role_id=developer.id)
    dev2 = await make_user(full_name="Bela Dev", job_role_id=developer.id)
    await make_user(full_name="Sam Sales", job_role_id=sales.id)
    body = {"course_id": str(course.id), "audience": {"skill_id": str(cyber.id)}, "due_on": "2030-01-31"}
    preview = (await client.post("/admin/assignments/preview", json=body, headers=auth(admin))).json()
    assert [p["name"] for p in preview["people"]] == ["Arun Dev", "Bela Dev"]
    assert preview["skill_name"] == "Cybersecurity awareness" and preview["due_on"] == "2030-01-31" and preview["new_people"] == 2
    assert {p["id"] for p in preview["people"]} == {str(dev1.id), str(dev2.id)}


async def test_manual_people_are_added_to_skill_audience(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    cyber, _, developer, sales, course = await _setup(session)
    admin = await make_user("admin")
    await make_user(full_name="Arun Dev", job_role_id=developer.id)
    sam = await make_user(full_name="Sam Sales", job_role_id=sales.id)
    body = {"course_id": str(course.id), "audience": {"skill_id": str(cyber.id), "user_ids": [str(sam.id)]}}
    preview = (await client.post("/admin/assignments/preview", json=body, headers=auth(admin))).json()
    assert [p["name"] for p in preview["people"]] == ["Arun Dev", "Sam Sales"]


async def test_only_selected_people_are_notified(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, developer, sales, course = await _setup(session)
    admin = await make_user("admin")
    chosen = await make_user(full_name="Chosen One", job_role_id=sales.id)
    other = await make_user(full_name="Not Chosen", job_role_id=developer.id)
    body = {"course_id": str(course.id), "audience": {"user_ids": [str(chosen.id)]}}
    assert (await client.post("/admin/assignments", json=body, headers=auth(admin))).json()["count"] == 1

    def titles(inbox: dict) -> list[str]:  # type: ignore[type-arg]
        return [n["title"] for n in inbox["items"]]

    assert 'New learning: "Cybersecurity basics"' in titles((await client.get("/me/notifications", headers=auth(chosen))).json())
    assert titles((await client.get("/me/notifications", headers=auth(other))).json()) == []
    assert (await client.get("/me/assignments", headers=auth(other))).json() == []


async def test_repeat_assignment_creates_no_duplicates(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, _, _, course = await _setup(session)
    admin = await make_user("admin")
    person = await make_user()
    body = {"course_id": str(course.id), "audience": {"user_ids": [str(person.id)]}}
    await client.post("/admin/assignments", json=body, headers=auth(admin))
    again = (await client.post("/admin/assignments", json=body, headers=auth(admin))).json()
    assert again["count"] == 0
    preview = (await client.post("/admin/assignments/preview", json=body, headers=auth(admin))).json()
    assert preview["already_assigned"] == 1 and preview["people"][0]["already_assigned"] is True
    count = await session.scalar(select(func.count()).select_from(Assignment).where(Assignment.user_id == person.id))
    assert count == 1


async def test_progress_is_saved_and_course_done_differs_from_test_passed(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    _, _, _, _, course = await _setup(session)
    admin = await make_user("admin")
    person = await make_user(full_name="Lena Learner")
    h = auth(person)
    await client.post("/admin/assignments", json={"course_id": str(course.id), "audience": {"user_ids": [str(person.id)]}}, headers=auth(admin))
    home = (await client.get("/me/assignments", headers=h)).json()
    assert home[0]["course_title"] == "Cybersecurity basics" and home[0]["status"] == "not_started"

    lessons = (await client.get(f"/courses/{course.id}", headers=h)).json()["lessons"]
    await client.post(f"/lessons/{lessons[0]['id']}/complete", headers=h)
    # A new "session": the course opens at the next unfinished lesson.
    detail = (await client.get(f"/courses/{course.id}", headers=h)).json()
    assert detail["my_progress"]["next_lesson_id"] == lessons[1]["id"]
    await client.post(f"/lessons/{lessons[1]['id']}/complete", headers=h)

    tracker = (await client.get(f"/admin/training/{course.id}", headers=auth(admin))).json()
    assert tracker["people"][0]["state"] == "course_done"  # lessons finished, test not passed yet

    questions = [q["id"] for q in (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()]
    failed = (await client.post(f"/courses/{course.id}/quiz", json={"answers": {q: 1 for q in questions}}, headers=h)).json()
    assert failed["score"] == 0 and failed["passed"] is False
    assert (await client.get(f"/admin/training/{course.id}", headers=auth(admin))).json()["people"][0]["state"] == "failed"
    passed = (await client.post(f"/courses/{course.id}/quiz", json={"answers": {q: 0 for q in questions}}, headers=h)).json()
    assert passed["score"] == 100 and passed["passed"] is True and passed["course_completed"] is True


async def test_attempts_are_kept_and_scored(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, _, _, course = await _setup(session)
    h = auth(await make_user())
    questions = [q["id"] for q in (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()]
    half = {questions[0]: 0, questions[1]: 1}
    first = (await client.post(f"/courses/{course.id}/quiz", json={"answers": half}, headers=h)).json()
    assert first["score"] == 50 and first["passed"] is True  # pass mark 50
    await client.post(f"/courses/{course.id}/quiz", json={"answers": {q: 1 for q in questions}}, headers=h)
    attempts = (await client.get(f"/courses/{course.id}/quiz/attempts", headers=h)).json()
    assert [(a["attempt_no"], a["score"], a["passed"]) for a in attempts] == [(1, 50, True), (2, 0, False)]
    stored = (await session.scalars(select(CourseQuizAttempt).order_by(CourseQuizAttempt.attempt_no))).all()
    assert stored[0].answers == {questions[0]: 0, questions[1]: 1}  # the submitted answers are recorded


async def test_hr_tracker_counts_each_state(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, _, _, course = await _setup(session)
    admin = await make_user("admin")
    manager = await make_user("manager")
    starter = await make_user(full_name="A Starter", manager_id=manager.id)
    idle = await make_user(full_name="B Idle")
    late = await make_user(full_name="C Late")
    ids = [str(u.id) for u in (starter, idle, late)]
    await client.post("/admin/assignments", json={"course_id": str(course.id), "audience": {"user_ids": ids[:2]}}, headers=auth(admin))
    await client.post(
        "/admin/assignments", json={"course_id": str(course.id), "audience": {"user_ids": ids[2:]}, "due_on": "2020-01-01"}, headers=auth(admin)
    )
    lessons = (await client.get(f"/courses/{course.id}", headers=auth(starter))).json()["lessons"]
    await client.post(f"/lessons/{lessons[0]['id']}/complete", headers=auth(starter))

    tracker = (await client.get(f"/admin/training/{course.id}", headers=auth(admin))).json()
    assert tracker["total"] == 3 and tracker["counts"]["not_started"] == 2 and tracker["counts"]["in_progress"] == 1
    assert tracker["overdue"] == 1 and [p["name"] for p in tracker["people"] if p["overdue"]] == ["C Late"]
    overview = (await client.get("/admin/training", headers=auth(admin))).json()
    assert overview[0]["course_title"] == "Cybersecurity basics" and overview[0]["overdue"] == 1

    # Managers see only their own team.
    mine = (await client.get(f"/admin/training/{course.id}", headers=auth(manager))).json()
    assert [p["name"] for p in mine["people"]] == ["A Starter"]
    export = await client.get(f"/admin/training/{course.id}/export", headers=auth(admin))
    assert export.status_code == 200 and "C Late" in export.text and "Not started" in export.text


async def test_employees_cannot_see_others_or_assign(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, _, _, course = await _setup(session)
    person = await make_user()
    h = auth(person)
    body = {"course_id": str(course.id), "audience": {"everyone": True}}
    assert (await client.post("/admin/assignments", json=body, headers=h)).status_code == 403
    assert (await client.get(f"/admin/training/{course.id}", headers=h)).status_code == 403
    assert (await client.get("/users", headers=h)).status_code == 403


async def test_role_change_keeps_history(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    _, _, developer, sales, course = await _setup(session)
    admin = await make_user("admin")
    person = await make_user(job_role_id=developer.id)
    await client.post("/admin/assignments", json={"course_id": str(course.id), "audience": {"user_ids": [str(person.id)]}}, headers=auth(admin))
    await client.patch(f"/users/{person.id}", json={"job_role_id": str(sales.id)}, headers=auth(admin))
    skills = (await client.get("/me/skills", headers=auth(person))).json()
    required = {s["skill_name"] for s in skills if s["required_by_role"]}
    assert required == {"Customer communication"}  # the new role's skills
    assert len((await client.get("/me/assignments", headers=auth(person))).json()) == 1  # training history kept
