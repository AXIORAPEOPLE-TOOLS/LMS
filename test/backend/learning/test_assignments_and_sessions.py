from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared import clock
from testkit import UserFactory, auth, make_course, make_role, make_skill


async def test_assign_preview_send_and_undo(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skill = await make_skill(session)
    role = await make_role(session, "Admissions Counsellor", {skill: 3})
    course = await make_course(session)
    admin = await make_user("admin")
    people = [await make_user(job_role_id=role.id) for _ in range(3)]
    body = {"course_id": str(course.id), "audience": {"job_role_id": str(role.id)}, "due_on": "2026-10-16"}

    preview = (await client.post("/admin/assignments/preview", json=body, headers=auth(admin))).json()
    assert preview["new_people"] == 3 and "Admissions Counsellor" in preview["audience_label"]
    sent = (await client.post("/admin/assignments", json=body, headers=auth(admin))).json()
    assert sent["count"] == 3
    again = (await client.post("/admin/assignments/preview", json=body, headers=auth(admin))).json()
    assert again["new_people"] == 0 and again["already_assigned"] == 3

    assert len((await client.get("/me/assignments", headers=auth(people[0]))).json()) == 1
    undo = (await client.post(f"/admin/bulk/{sent['bulk_action_id']}/undo", headers=auth(admin))).json()
    assert undo == {"undone": 3}
    assert (await client.get("/me/assignments", headers=auth(people[0]))).json() == []


async def test_undo_window_closes_after_ten_minutes(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course = await make_course(session)
    admin = await make_user("admin")
    learner = await make_user()
    body = {"course_id": str(course.id), "audience": {"user_ids": [str(learner.id)]}}
    headers = auth(admin)  # token minted before the clock moves
    sent = (await client.post("/admin/assignments", json=body, headers=headers)).json()
    clock.freeze(datetime.now(UTC) + timedelta(minutes=11))
    late = await client.post(f"/admin/bulk/{sent['bulk_action_id']}/undo", headers=headers)
    assert late.status_code == 409 and "closed" in late.json()["error"]["message"]


async def test_cannot_assign_unpublished_course(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course = await make_course(session, status="draft")
    admin = await make_user("admin")
    learner = await make_user()
    body = {"course_id": str(course.id), "audience": {"user_ids": [str(learner.id)]}}
    assert (await client.post("/admin/assignments", json=body, headers=auth(admin))).status_code == 422


async def test_session_invitations_accept_decline(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    trainer = await make_user(full_name="Meera Kapoor")
    asha = await make_user(full_name="Asha Verma")
    dev = await make_user(full_name="Dev Patel")
    start = datetime.now(UTC) + timedelta(days=3)
    payload = {
        "title": "Objection handling",
        "trainer_id": str(trainer.id),
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=1)).isoformat(),
        "meeting_link": "https://meet.example.com/x",
        "audience": {"user_ids": [str(asha.id), str(dev.id)]},
    }
    created = (await client.post("/admin/sessions", json=payload, headers=auth(admin))).json()
    assert created["waiting"] == 2 and created["trainer_name"] == "Meera Kapoor"
    # Nothing is sent until the admin sends, after previewing.
    assert (await client.get("/me/sessions", headers=auth(asha))).json() == []
    preview = (await client.get(f"/admin/sessions/{created['id']}/preview", headers=auth(admin))).json()
    assert preview["people"] == 2 and "Objection handling" in preview["message"]
    await client.post(f"/admin/sessions/{created['id']}/send", headers=auth(admin))

    inbox = (await client.get("/me/notifications", headers=auth(asha))).json()["items"]
    assert inbox[0]["kind"] == "invitation"
    assert [a["label"] for a in inbox[0]["actions"]] == ["Accept", "Decline"]
    rsvp = f"/sessions/{created['id']}/rsvp"
    accepted = (await client.post(rsvp, json={"accept": True}, headers=auth(asha))).json()
    assert accepted["my_status"] == "accepted"
    await client.post(rsvp, json={"accept": False}, headers=auth(dev))
    stats = (await client.get("/admin/sessions", headers=auth(admin))).json()[0]
    assert (stats["accepted"], stats["declined"], stats["waiting"]) == (1, 1, 0)


async def test_session_must_end_after_start(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    now = datetime.now(UTC)
    payload = {
        "title": "x",
        "starts_at": now.isoformat(),
        "ends_at": (now - timedelta(hours=1)).isoformat(),
        "audience": {"everyone": True},
    }
    assert (await client.post("/admin/sessions", json=payload, headers=auth(admin))).status_code == 422
