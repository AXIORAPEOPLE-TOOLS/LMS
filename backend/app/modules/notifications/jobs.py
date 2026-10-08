from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import job_handler
from app.modules.notifications.service import NotificationService


@job_handler("notifications.deliver")
async def deliver(session: AsyncSession, data: dict[str, Any]) -> None:
    await NotificationService(session).deliver(UUID(data["id"]))
