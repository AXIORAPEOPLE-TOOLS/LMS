"""Due-date reminders and the after-deadline manager list (LMS.pdf "Training Reminder").

    1. Every day, find assigned training that is not finished.
    2. Remind at the configured stages before the due date (default 7, 2 and 0 days).
    3. Send a short message with the link, inside the person's best time.
    4. Stop once the training is complete (checked again at delivery).
    5. The day after the deadline, send each manager one list of their overdue people.

Each stage is sent once per assignment; running the job twice the same day sends nothing new.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.learning.models import Assignment, AssignmentStatus, Course
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.reminders import rules
from app.modules.reminders.service import ReminderService
from app.modules.settings.service import SettingsService
from app.shared.clock import local_now, today


@dataclass(frozen=True)
class DueItem:
    assignment_id: UUID
    user: User
    course_id: UUID
    course_title: str
    minutes: int
    due_on: date

    @property
    def days_left(self) -> int:
        return (self.due_on - today()).days


def stage_title(days_left: int, course_title: str) -> str:
    if days_left <= 0:
        return f"Due today: {course_title}"
    return f"Due in {days_left} day{'s' if days_left != 1 else ''}: {course_title}"


class DeadlineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)

    async def _open_with_due_date(self) -> list[DueItem]:
        rows = (
            await self.session.execute(
                select(Assignment.id, User, Course.id, Course.title, Course.duration_minutes, Assignment.due_on)
                .join(User, User.id == Assignment.user_id)
                .join(Course, Course.id == Assignment.course_id)
                .where(
                    Assignment.status != AssignmentStatus.COMPLETED.value,
                    Assignment.due_on.is_not(None),
                    User.is_active.is_(True),
                )
            )
        ).all()
        return [DueItem(aid, user, cid, title, minutes, due) for aid, user, cid, title, minutes, due in rows]

    async def due_today(self) -> list[DueItem]:
        """Items whose reminder stage is today (e.g. 7, 2 or 0 days before the due date)."""
        stages = {int(d) for d in await self.settings.get("reminders.due_stages_days")}
        return [item for item in await self._open_with_due_date() if item.days_left in stages]

    async def _already_sent(self, assignment_id: UUID, title: str) -> bool:
        return bool(
            await self.session.scalar(
                select(Notification.id).where(Notification.related_id == assignment_id, Notification.title == title).limit(1)
            )
        )

    async def _send_time(self, user: User) -> datetime:
        """Inside the person's best window today; if that has passed, send now (a due date will not wait)."""
        policy = await ReminderService(self.session).policy()
        window_raw = user.reminder_window or await self.settings.get("reminders.default_window")
        window = (rules.parse_hhmm(window_raw[0]), rules.parse_hhmm(window_raw[1]))
        now = local_now()
        at = rules.next_send_time(now, window, policy, horizon_days=0)
        return at if at is not None else now

    async def run(self, *, automatic: bool = True) -> int:
        notifications = NotificationService(self.session)
        sent = 0
        for item in await self.due_today():
            title = stage_title(item.days_left, item.course_title)
            if await self._already_sent(item.assignment_id, title):
                continue
            href = f"/learn/courses/{item.course_id}"
            when = "today" if item.days_left <= 0 else f"by {item.due_on:%d %b}"
            created = await notifications.notify(
                item.user.id,
                kind=NotificationKind.REMINDER,
                title=title,
                body=(
                    f'Hi {item.user.full_name.split()[0]}, please finish "{item.course_title}" {when}. '
                    f"It takes about {item.minutes} minutes."
                ),
                link=href,
                actions=[{"label": "Start now", "href": href}],
                related=("assignment", item.assignment_id),
                automatic=automatic,
                scheduled_for=await self._send_time(item.user),
            )
            sent += created is not None
        return sent

    # ---- step 5: after the deadline, one list per manager ---------------------------------
    async def overdue_lists(self) -> dict[UUID, list[str]]:
        """People whose due date was yesterday and who have not finished, grouped by manager."""
        yesterday = today() - timedelta(days=1)
        lists: dict[UUID, list[str]] = defaultdict(list)
        for item in await self._open_with_due_date():
            if item.due_on == yesterday and item.user.manager_id:
                lists[item.user.manager_id].append(f"{item.user.full_name}: {item.course_title}")
        return lists

    async def send_overdue_lists(self, *, automatic: bool = True) -> int:
        notifications = NotificationService(self.session)
        sent = 0
        for manager_id, lines in (await self.overdue_lists()).items():
            title = f"Missed the deadline yesterday: {len(lines)} {'person' if len(lines) == 1 else 'people'}"
            created = await notifications.notify(
                manager_id,
                kind=NotificationKind.SUMMARY,
                title=title,
                body="\n".join(lines[:20]),
                link="/admin/training",
                automatic=automatic,
            )
            sent += created is not None
        return sent
