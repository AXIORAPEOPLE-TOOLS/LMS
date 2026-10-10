"""Automation (LMS.pdf "Training Reminder" + "Assessment / Evaluation") with simulated email/WhatsApp.

Reminders 7 days, 2 days and on the due date; stop when finished; manager list after the deadline;
result to the employee; summary to HR and managers. Every channel attempt lands in the message log.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.queue import dispatch_pending
from app.modules.learning.models import Assignment
from app.modules.notifications.models import DeliveryLog, Notification
from app.modules.reminders.deadlines import DeadlineService
from app.modules.workflows.actions import ResultsSummary
from app.shared import clock
from testkit import UserFactory, auth, make_course

IST = ZoneInfo("Asia/Kolkata")
MONDAY = datetime(2026, 10, 5, 10, 0, tzinfo=IST)  # a weekday inside allowed hours
TODAY = MONDAY.date()


async def _run(database: Database, coro_factory) -> int:  # type: ignore[no-untyped-def]
    async with database.session_factory() as s:
        result = await coro_factory(s)
        await s.commit()
        await dispatch_pending(s)
    return result


async def _assign(session: AsyncSession, user_id: object, course_id: object, due: date, **fields: object) -> Assignment:
    assignment = Assignment(user_id=user_id, course_id=course_id, due_on=due, **fields)
    session.add(assignment)
    await session.commit()
    return assignment


async def test_due_date_stages_7_2_0_and_once_only(database: Database, session: AsyncSession, make_user: UserFactory) -> None:
    clock.freeze(MONDAY.astimezone(ZoneInfo("UTC")))
    course = await make_course(session, "Data privacy basics", duration_minutes=20)
    people = {d: await make_user(full_name=f"Due In {d}") for d in (7, 3, 2, 0)}
    for days, person in people.items():
        await _assign(session, person.id, course.id, TODAY + timedelta(days=days))

    sent = await _run(database, lambda s: DeadlineService(s).run())
    assert sent == 3  # 7, 2 and 0 days; not 3 days
    titles = sorted((await session.scalars(select(Notification.title))).all())
    assert titles == ["Due in 2 days: Data privacy basics", "Due in 7 days: Data privacy basics", "Due today: Data privacy basics"]
    assert await _run(database, lambda s: DeadlineService(s).run()) == 0  # same day again: nothing new


async def test_finished_training_gets_no_reminder(database: Database, session: AsyncSession, make_user: UserFactory) -> None:
    clock.freeze(MONDAY.astimezone(ZoneInfo("UTC")))
    course = await make_course(session)
    done = await make_user()
    await _assign(session, done.id, course.id, TODAY + timedelta(days=2), status="completed")
    assert await _run(database, lambda s: DeadlineService(s).run()) == 0


async def test_manager_gets_overdue_list_the_day_after(database: Database, session: AsyncSession, make_user: UserFactory) -> None:
    clock.freeze(MONDAY.astimezone(ZoneInfo("UTC")))
    course = await make_course(session, "POSH awareness")
    manager = await make_user("manager", full_name="Rohan Manager")
    late = await make_user(full_name="Late Learner", manager_id=manager.id)
    on_time = await make_user(full_name="Done Learner", manager_id=manager.id)
    await _assign(session, late.id, course.id, TODAY - timedelta(days=1))
    await _assign(session, on_time.id, course.id, TODAY - timedelta(days=1), status="completed")

    assert await _run(database, lambda s: DeadlineService(s).send_overdue_lists()) == 1
    note = (await session.scalars(select(Notification).where(Notification.user_id == manager.id))).one()
    assert note.title == "Missed the deadline yesterday: 1 person" and note.body == "Late Learner: POSH awareness"


async def test_every_channel_is_logged_and_external_ones_are_simulated(
    database: Database, session: AsyncSession, make_user: UserFactory
) -> None:
    clock.freeze(MONDAY.astimezone(ZoneInfo("UTC")))
    course = await make_course(session, "Cybersecurity basics")
    with_phone = await make_user(
        full_name="Priya Phone", email="priya@example.com", phone="+91 90000 00042",
        reminder_channels={"in_app": True, "email": True, "whatsapp": True},
    )
    no_phone = await make_user(full_name="Nikhil Nophone", reminder_channels={"in_app": True, "email": False, "whatsapp": True})
    await _assign(session, with_phone.id, course.id, TODAY + timedelta(days=7))
    await _assign(session, no_phone.id, course.id, TODAY + timedelta(days=7))
    await _run(database, lambda s: DeadlineService(s).run())

    logs = {(log.user_id, log.channel): log for log in (await session.scalars(select(DeliveryLog))).all()}
    assert logs[(with_phone.id, "in_app")].status == "sent"
    email = logs[(with_phone.id, "email")]
    assert email.status == "simulated" and email.to_address == "priya@example.com" and "/learn/courses/" in email.text
    assert "No provider connected" in email.reason
    whatsapp = logs[(with_phone.id, "whatsapp")]
    assert whatsapp.status == "simulated" and whatsapp.to_address == "+91 90000 00042"
    assert logs[(no_phone.id, "email")].status == "skipped"  # turned off by the person
    assert logs[(no_phone.id, "whatsapp")].status == "skipped" and logs[(no_phone.id, "whatsapp")].reason == "No phone number on file"


async def test_result_goes_to_employee_and_summary_to_hr_and_manager(
    client: AsyncClient, database: Database, session: AsyncSession, make_user: UserFactory
) -> None:
    course = await make_course(session, "Data privacy basics", lessons=0, questions=2, pass_mark=50)
    manager = await make_user("manager")
    admin = await make_user("admin")
    learner = await make_user(full_name="Asha Learner", manager_id=manager.id)
    h = auth(learner)
    questions = [q["id"] for q in (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()]
    await client.post(f"/courses/{course.id}/quiz", json={"answers": {q: 1 for q in questions}}, headers=h)
    inbox = (await client.get("/me/notifications", headers=h)).json()["items"]
    assert inbox[0]["title"] == "Not passed yet: Data privacy basics" and "2 tries left" in inbox[0]["body"]

    clock.freeze((datetime.now(IST).replace(hour=9) + timedelta(days=1)).astimezone(ZoneInfo("UTC")))  # next morning
    result = await _run(database, lambda s: ResultsSummary().execute(s, {}, None))
    assert result["people"] == 2  # one manager + one HR admin
    team = (await session.scalars(select(Notification).where(Notification.user_id == manager.id))).one()
    assert team.title == "Team results: 0 of 1 passed" and "Asha Learner" in team.body
    hr = (await session.scalars(select(Notification).where(Notification.user_id == admin.id))).one()
    assert hr.title == "Yesterday's test results: 1"


async def test_message_log_is_admin_only(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    learner = await make_user()
    assert (await client.get("/admin/message-log", headers=auth(learner))).status_code == 403
    body = (await client.get("/admin/message-log", headers=auth(admin))).json()
    assert set(body["simulated_channels"]) == {"email", "whatsapp"} and body["rows"] == []


async def test_learner_can_add_phone(client: AsyncClient, make_user: UserFactory) -> None:
    learner = await make_user()
    me = (await client.patch("/me/preferences", json={"phone": "+91 98765 43210"}, headers=auth(learner))).json()
    assert me["phone"] == "+91 98765 43210"
    assert (await client.patch("/me/preferences", json={"phone": "call me"}, headers=auth(learner))).status_code == 422
