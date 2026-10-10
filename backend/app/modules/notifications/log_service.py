"""Read the message log (delivery_logs) for the admin page."""

from collections import Counter
from datetime import datetime, time
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.notifications.channels import CHANNELS
from app.modules.notifications.models import DeliveryLog
from app.shared.clock import local_now, org_timezone


class MessageLogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, channel: str | None, status: str | None, query: str | None, limit: int = 200) -> dict[str, Any]:
        stmt = select(DeliveryLog, User.full_name).join(User, User.id == DeliveryLog.user_id)
        if channel:
            stmt = stmt.where(DeliveryLog.channel == channel)
        if status:
            stmt = stmt.where(DeliveryLog.status == status)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(like), DeliveryLog.subject.ilike(like), DeliveryLog.to_address.ilike(like))
            )
        rows = (await self.session.execute(stmt.order_by(DeliveryLog.created_at.desc()).limit(min(limit, 500)))).all()
        start = datetime.combine(local_now().date(), time(0), tzinfo=org_timezone())
        today_channels = (await self.session.scalars(select(DeliveryLog.channel).where(DeliveryLog.created_at >= start))).all()
        return {
            "rows": [
                {
                    "id": log.id,
                    "created_at": log.created_at,
                    "person": name,
                    "channel": log.channel,
                    "to_address": log.to_address,
                    "subject": log.subject,
                    "text": log.text,
                    "status": log.status,
                    "reason": log.reason,
                    "kind": log.kind,
                    "is_automatic": log.is_automatic,
                }
                for log, name in rows
            ],
            "counts": dict(Counter(today_channels)),
            "simulated_channels": [c.key for c in CHANNELS.values() if c.simulated],
        }
