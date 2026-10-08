from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.queue import Queues, defer_job
from app.core.resilience import CircuitOpenError, breaker
from app.modules.identity.models import User
from app.modules.notifications.channels import CHANNELS
from app.modules.notifications.models import Notification
from app.modules.settings.service import SettingsService
from app.shared.clock import utcnow


class AutomaticSendsPausedError(Exception):
    """Raised internally when the admin kill switch is on."""


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)

    async def notify(
        self,
        user_id: UUID,
        *,
        kind: str,
        title: str,
        body: str = "",
        link: str | None = None,
        actions: list[dict[str, Any]] | None = None,
        related: tuple[str, UUID] | None = None,
        automatic: bool = False,
        scheduled_for: datetime | None = None,
    ) -> Notification | None:
        """Create an in-app message and queue delivery to the person's other channels.

        Automatic sends respect the 'Stop all automatic sends' switch and return None.
        """
        if automatic and await self.settings.get("workflows.automatic_sends_paused"):
            return None
        notification = Notification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            actions=actions or [],
            related_type=related[0] if related else None,
            related_id=related[1] if related else None,
            is_automatic=automatic,
            scheduled_for=scheduled_for,
            channel_status={"in_app": "sent"},
        )
        self.session.add(notification)
        await self.session.flush()
        delay = 0
        if scheduled_for and scheduled_for > utcnow():
            delay = int((scheduled_for - utcnow()).total_seconds() * 1000)
        defer_job(self.session, Queues.NOTIFICATIONS, "notifications.deliver", {"id": notification.id}, delay_ms=delay)
        return notification

    async def deliver(self, notification_id: UUID) -> None:
        notification = await self.session.get(Notification, notification_id)
        if notification is None:
            return
        user = await self.session.get(User, notification.user_id)
        if user is None or not user.is_active:
            return
        if notification.kind == "reminder":
            from app.modules.reminders.service import ReminderService

            if not await ReminderService(self.session).still_needed(notification):
                await self.session.delete(notification)  # the item was finished meanwhile
                return
        status = dict(notification.channel_status or {})
        prefs = user.reminder_channels or {}
        for key, channel in CHANNELS.items():
            if key == "in_app" or status.get(key) == "sent":
                continue
            if not prefs.get(key, False):
                status[key] = "skipped"
                continue
            try:
                status[key] = await breaker(f"channel:{key}").call(lambda c=channel: c.send(user, notification), timeout=15)
            except CircuitOpenError:
                status[key] = "paused"  # provider is down; the in-app copy still arrived
            except Exception:
                status[key] = "failed"
        notification.channel_status = status
        notification.delivered_at = utcnow()

    async def inbox(self, user: User, *, unread_only: bool = False, limit: int = 50) -> Sequence[Notification]:
        now = utcnow()
        stmt = (
            select(Notification)
            .where(Notification.user_id == user.id)
            .where((Notification.scheduled_for.is_(None)) | (Notification.scheduled_for <= now))
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        return (await self.session.scalars(stmt)).all()

    async def unread_count(self, user: User) -> int:
        stmt = select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
        return int(await self.session.scalar(stmt) or 0)

    async def mark_read(self, user: User, notification_id: UUID) -> None:
        notification = await self.session.get(Notification, notification_id)
        if notification is None or notification.user_id != user.id:
            raise NotFoundError("We could not find that message.")
        notification.read_at = notification.read_at or utcnow()

    async def mark_all_read(self, user: User) -> None:
        await self.session.execute(
            update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=utcnow())
        )

    async def count_sent_since(self, user_id: UUID, kind: str, since: datetime) -> int:
        stmt = select(func.count()).where(
            Notification.user_id == user_id, Notification.kind == kind, Notification.created_at >= since
        )
        return int(await self.session.scalar(stmt) or 0)
