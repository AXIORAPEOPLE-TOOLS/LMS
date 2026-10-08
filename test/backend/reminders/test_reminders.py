from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.learning.models import Assignment
from app.modules.notifications.models import Notification
from app.modules.reminders import rules
from app.modules.reminders.service import ReminderService
from app.modules.scheduler.registry import run_due_tasks
from app.shared import clock
from testkit import UserFactory, auth, make_course

IST = ZoneInfo("Asia/Kolkata")
POLICY = rules.ReminderPolicy(time(9), time(19), False, frozenset({date(2026, 10, 2)}), 1, 3)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)  # Oct 2026: 5th is a Monday


def test_send_inside_window_and_allowed_hours() -> None:
    window = (time(11), time(13))
    assert rules.next_send_time(at(5, 8), window, POLICY) == at(5, 11)  # Monday morning -> 11:00
    assert rules.next_send_time(at(5, 12, 30), window, POLICY) == at(5, 12, 30)  # inside the window: now
    assert rules.next_send_time(at(5, 14), window, POLICY) == at(6, 11)  # missed today -> tomorrow
    assert rules.next_send_time(at(9, 14), window, POLICY) == at(12, 11)  # Friday late -> Monday
    assert rules.next_send_time(at(1, 14), window, POLICY) == at(5, 11)  # skips the 2 Oct holiday + weekend


def test_window_outside_allowed_hours_falls_back() -> None:
    assert rules.next_send_time(at(5, 6), (time(6), time(8)), POLICY) == at(5, 9)


def test_caps() -> None:
    assert rules.under_caps(0, 2, POLICY) and not rules.under_caps(1, 1, POLICY) and not rules.under_caps(0, 3, POLICY)


async def test_engine_sends_one_combined_reminder_and_stops_when_done(
    client: AsyncClient, session: AsyncSession, database: Database, make_user: UserFactory
) -> None:
    clock.freeze(at(5, 11, 30).astimezone(ZoneInfo("UTC")))
    first = await make_course(session, "Data privacy basics", duration_minutes=20)
    second = await make_course(session, "Ethics")
    asha = await make_user(full_name="Asha Verma", reminder_window=["11:00", "13:00"])
    admin = await make_user("admin")
    session.add_all([Assignment(user_id=asha.id, course_id=first.id), Assignment(user_id=asha.id, course_id=second.id)])
    await session.commit()
    h = auth(admin)

    preview = (await client.get("/admin/reminders/preview", headers=h)).json()
    assert preview[0]["name"] == "Asha Verma" and preview[0]["local_time"] == "11:30"
    assert (await client.post("/admin/reminders/send", headers=h)).json() == {"created": 1}
    assert (await client.post("/admin/reminders/send", headers=h)).json() == {"created": 0}  # one a day

    inbox = (await client.get("/me/notifications", headers=auth(asha))).json()["items"]
    assert inbox[0]["body"].startswith('Hi Asha, "Data privacy basics" takes about 20 minutes.')
    assert "1 more item" in inbox[0]["body"]
    assert [a["label"] for a in inbox[0]["actions"]] == ["Start now", "Tomorrow"]


async def test_reminder_for_finished_item_is_dropped(database: Database, session: AsyncSession, make_user: UserFactory) -> None:
    clock.freeze(at(5, 9, 0).astimezone(ZoneInfo("UTC")))
    course = await make_course(session)
    asha = await make_user(reminder_window=["11:00", "13:00"])
    assignment = Assignment(user_id=asha.id, course_id=course.id)
    session.add(assignment)
    await session.commit()
    async with database.session_factory() as s:
        notifications = await ReminderService(s).plan()
        assert notifications[0][1] == at(5, 11)  # scheduled for her window
        await ReminderService(s).run()
        # She finishes before 11:00 ...
        (await s.get(Assignment, assignment.id)).status = "completed"  # type: ignore[union-attr]
        await s.commit()
        from app.modules.notifications.service import NotificationService

        note = (await s.scalars(select(Notification))).one()
        await NotificationService(s).deliver(note.id)  # ... so delivery drops it
        await s.commit()
    assert (await session.scalars(select(Notification))).all() == []


async def test_scheduler_runs_daily_task_once(database: Database) -> None:
    clock.freeze(at(5, 10).astimezone(ZoneInfo("UTC")))
    first = await run_due_tasks(database.session_factory)
    assert first["workflows.daily"].startswith("ok")
    second = await run_due_tasks(database.session_factory)
    assert "workflows.daily" not in second
    clock.freeze(at(6, 10).astimezone(ZoneInfo("UTC")))
    assert "workflows.daily" in await run_due_tasks(database.session_factory)


async def test_weekend_no_reminders(database: Database, session: AsyncSession, make_user: UserFactory) -> None:
    clock.freeze(at(10, 11).astimezone(ZoneInfo("UTC")))  # Saturday
    course = await make_course(session)
    user = await make_user()
    session.add(Assignment(user_id=user.id, course_id=course.id))
    await session.commit()
    async with database.session_factory() as s:
        assert await ReminderService(s).plan() == []
