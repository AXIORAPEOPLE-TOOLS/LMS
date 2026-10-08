"""Completion reminders for self-paced learning (sheet 12, A-06 right panel, L-10).

Self-paced items never get invitations; they get at most one combined reminder
a day, inside the person's best time window, until the item is done.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessments.models import SkillTest, TestInvite
from app.modules.identity.models import User
from app.modules.learning.models import Assignment, AssignmentStatus, Course
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.reminders import rules
from app.modules.settings.service import SettingsService
from app.shared.clock import local_now
from app.shared.schemas import Schema


class PlannedReminderOut(Schema):
    user_id: UUID
    name: str
    send_at: datetime
    local_time: str
    channels: str
    items: list[str]


@dataclass
class _OpenItem:
    kind: str  # assignment | test_invite
    id: UUID
    title: str
    minutes: int
    href: str


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)

    async def policy(self) -> rules.ReminderPolicy:
        get = self.settings.get
        return rules.ReminderPolicy(
            quiet_start=rules.parse_hhmm(await get("reminders.quiet_start")),
            quiet_end=rules.parse_hhmm(await get("reminders.quiet_end")),
            allow_weekends=await get("reminders.allow_weekends"),
            holidays=frozenset(date.fromisoformat(d) for d in await get("reminders.holidays")),
            max_per_day=await get("reminders.max_per_day"),
            max_per_week=await get("reminders.max_per_week"),
        )

    async def _open_items(self) -> dict[UUID, list[_OpenItem]]:
        items: dict[UUID, list[_OpenItem]] = defaultdict(list)
        rows = (
            await self.session.execute(
                select(Assignment.id, Assignment.user_id, Course.id, Course.title, Course.duration_minutes)
                .join(Course, Course.id == Assignment.course_id)
                .where(Assignment.status != AssignmentStatus.COMPLETED.value)
                .order_by(Assignment.due_on.is_(None), Assignment.due_on)
            )
        ).all()
        for assignment_id, user_id, course_id, title, minutes in rows:
            items[user_id].append(_OpenItem("assignment", assignment_id, title, minutes, f"/learn/courses/{course_id}"))
        invites = (
            await self.session.execute(
                select(TestInvite.id, TestInvite.user_id, SkillTest.id, SkillTest.title, SkillTest.duration_minutes)
                .join(SkillTest, SkillTest.id == TestInvite.test_id)
                .where(TestInvite.status == "pending", SkillTest.is_active.is_(True))
            )
        ).all()
        for invite_id, user_id, test_id, title, minutes in invites:
            items[user_id].append(
                _OpenItem("test_invite", invite_id, f"Skill check: {title}", minutes, f"/learn/tests/{test_id}")
            )
        return items

    async def plan(self) -> list[tuple[User, datetime, list[_OpenItem]]]:
        """Who gets a reminder today, and when (local time)."""
        policy = await self.policy()
        now = local_now()
        default_window = await self.settings.get("reminders.default_window")
        open_items = await self._open_items()
        if not open_items:
            return []
        users = {
            u.id: u
            for u in (
                await self.session.scalars(select(User).where(User.id.in_(list(open_items)), User.is_active.is_(True)))
            ).all()
        }
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        planned: list[tuple[User, datetime, list[_OpenItem]]] = []
        for user_id, items in open_items.items():
            user = users.get(user_id)
            if user is None:
                continue
            sent_today = await self._count(user_id, day_start)
            sent_week = await self._count(user_id, week_start)
            if not rules.under_caps(sent_today, sent_week, policy):
                continue
            window_raw = user.reminder_window or default_window
            window = (rules.parse_hhmm(window_raw[0]), rules.parse_hhmm(window_raw[1]))
            send_at = rules.next_send_time(now, window, policy)
            if send_at is None or send_at.date() != now.date():
                continue  # not allowed today (weekend, holiday or window passed)
            planned.append((user, send_at, items))
        planned.sort(key=lambda p: p[1])
        return planned

    async def _count(self, user_id: UUID, since_local: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(
                    Notification.user_id == user_id,
                    Notification.kind == NotificationKind.REMINDER.value,
                    Notification.created_at >= since_local,
                )
            )
            or 0
        )

    async def preview(self) -> list[PlannedReminderOut]:
        out: list[PlannedReminderOut] = []
        for user, send_at, items in await self.plan():
            channels = [
                label
                for key, label in (("in_app", "In app"), ("email", "email"), ("whatsapp", "WhatsApp"))
                if (user.reminder_channels or {}).get(key)
            ]
            out.append(
                PlannedReminderOut(
                    user_id=user.id,
                    name=user.full_name,
                    send_at=send_at,
                    local_time=f"{send_at:%H:%M}",
                    channels=" + ".join(channels) or "In app",
                    items=[i.title for i in items[:3]],
                )
            )
        return out

    async def run(self, *, automatic: bool = True) -> int:
        """Create today's reminders (delivered at each person's time). Returns how many."""
        notifications = NotificationService(self.session)
        created = 0
        for user, send_at, items in await self.plan():
            first = items[0]
            more = len(items) - 1
            body = f'Hi {user.full_name.split()[0]}, "{first.title}" takes about {first.minutes} minutes. A good time to start?'
            if more:
                body += f" You also have {more} more item{'s' if more > 1 else ''} waiting."
            result = await notifications.notify(
                user.id,
                kind=NotificationKind.REMINDER,
                title="Your next step is ready",
                body=body,
                link=first.href,
                actions=[{"label": "Start now", "href": first.href}, {"label": "Tomorrow", "action": "snooze_day"}],
                related=(first.kind, first.id),
                automatic=automatic,
                scheduled_for=send_at,
            )
            if result:
                created += 1
        return created

    async def still_needed(self, notification: Notification) -> bool:
        """Reminders stop the moment the item is complete (checked again at delivery)."""
        if notification.kind != NotificationKind.REMINDER.value or notification.related_id is None:
            return True
        if notification.related_type == "assignment":
            assignment = await self.session.get(Assignment, notification.related_id)
            return assignment is not None and assignment.status != AssignmentStatus.COMPLETED.value
        if notification.related_type == "test_invite":
            invite = await self.session.get(TestInvite, notification.related_id)
            return invite is not None and invite.status == "pending"
        return True
