from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.queue import Queues, defer_job
from app.core.resilience import CircuitOpenError, breaker
from app.modules.identity.models import User
from app.modules.notifications.channels import CHANNELS
from app.modules.notifications.models import DeliveryLog, Notification
from app.modules.settings.service import SettingsService
from app.shared.clock import utcnow

FINAL_STATUSES = {"sent", "simulated", "skipped"}


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
            channel_status={},
        )
        self.session.add(notification)
        await self.session.flush()
        delay = 0
        if scheduled_for and scheduled_for > utcnow():
            delay = int((scheduled_for - utcnow()).total_seconds() * 1000)
        defer_job(self.session, Queues.NOTIFICATIONS, "notifications.deliver", {"id": notification.id}, delay_ms=delay)
        return notification

    async def deliver(self, notification_id: UUID, attempt: int = 1) -> None:
        """Send on every channel the person chose. Safe to run again: finished channels are not repeated.

        A failed or paused channel is retried later with a growing delay (`delivery_retry_attempts`).
        """
        # Fresh row, locked: two workers (or a retry) never deliver the same message twice.
        notification = (
            await self.session.scalars(
                select(Notification)
                .where(Notification.id == notification_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).first()
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
            if status.get(key) in FINAL_STATUSES:
                continue  # already done on an earlier attempt
            message = channel.render(user, notification)
            reason = ""
            if key != "in_app" and not prefs.get(key, False):
                status[key], reason = "skipped", "Turned off in the person's reminder settings"
            elif message.to is None:
                status[key], reason = "skipped", message.missing
            elif key == "in_app":
                status[key] = "sent"
            else:
                try:
                    status[key] = await breaker(f"channel:{key}").call(
                        lambda c=channel, m=message: c.send(user, notification, m), timeout=15
                    )
                except CircuitOpenError:
                    status[key], reason = "paused", "Provider is down; the in-app copy still arrived"
                except Exception as exc:
                    status[key], reason = "failed", str(exc)[:200]
            if channel.simulated and status[key] == "simulated":
                reason = "No provider connected yet: logged, not sent"
            if status[key] in ("failed", "paused"):
                retry = self._retry_delay_ms(attempt)
                reason = f"{reason}. " if reason else ""
                reason += f"Retry {attempt + 1} in {retry // 1000} s" if retry else "No more retries"
            self.session.add(
                DeliveryLog(
                    notification_id=notification.id,
                    user_id=user.id,
                    channel=key,
                    to_address=message.to,
                    subject=message.subject[:200],
                    text=message.text,
                    status=status[key],
                    reason=reason,
                    kind=notification.kind,
                    is_automatic=notification.is_automatic,
                )
            )
        notification.channel_status = status
        notification.delivered_at = utcnow()
        retry = self._retry_delay_ms(attempt)
        if retry and any(v in ("failed", "paused") for v in status.values()):
            defer_job(
                self.session,
                Queues.NOTIFICATIONS,
                "notifications.deliver",
                {"id": notification.id, "attempt": attempt + 1},
                delay_ms=retry,
            )

    @staticmethod
    def _retry_delay_ms(attempt: int) -> int:
        """0 when no retries are left; otherwise backoff, then 2x, 4x ..."""
        settings = get_settings()
        if attempt >= settings.delivery_retry_attempts:
            return 0
        return settings.job_backoff_ms * 2 ** (attempt - 1)

    async def undelivered(self, older_than_minutes: int = 10, limit: int = 2_000) -> list[UUID]:
        """Messages that never reached the worker (e.g. Redis was down). Used by the redeliver sweep."""
        from datetime import timedelta

        cutoff = utcnow() - timedelta(minutes=older_than_minutes)
        stmt = (
            select(Notification.id)
            .where(
                Notification.delivered_at.is_(None),
                Notification.created_at < cutoff,
                (Notification.scheduled_for.is_(None)) | (Notification.scheduled_for < cutoff),
            )
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

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
