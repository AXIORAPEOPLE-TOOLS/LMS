import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import Queues, defer_job, job_handler
from app.modules.notifications.service import NotificationService
from app.modules.scheduler.registry import scheduled_task
from app.shared.clock import utcnow

logger = logging.getLogger("notifications")


@job_handler("notifications.deliver")
async def deliver(session: AsyncSession, data: dict[str, Any]) -> None:
    await NotificationService(session).deliver(UUID(data["id"]), attempt=int(data.get("attempt", 1)))


@scheduled_task("notifications.redeliver", "hourly")
async def redeliver(session: AsyncSession) -> int:
    """Safety net: anything created but never delivered (Redis was down) is queued again."""
    ids = await NotificationService(session).undelivered()
    run = utcnow().strftime("%Y%m%d%H%M")  # a fresh job id, so BullMQ does not treat it as a duplicate
    for notification_id in ids:
        defer_job(session, Queues.NOTIFICATIONS, "notifications.deliver", {"id": notification_id, "attempt": 1, "run": run})
    if ids:
        logger.warning("Redeliver sweep queued %s undelivered messages", len(ids))
    return len(ids)
