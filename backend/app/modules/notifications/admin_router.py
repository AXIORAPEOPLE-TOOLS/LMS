"""Admin: the message log. Every message on every channel, including simulated email/WhatsApp."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.notifications.log_service import MessageLogService
from app.shared.schemas import Schema

router = APIRouter(prefix="/admin/message-log", tags=["notifications"])


class MessageLogRowOut(Schema):
    id: UUID
    created_at: datetime
    person: str
    channel: str
    to_address: str | None
    subject: str
    text: str
    status: str
    reason: str
    kind: str
    is_automatic: bool


class MessageLogOut(Schema):
    rows: list[MessageLogRowOut]
    counts: dict[str, int]  # by channel, today
    simulated_channels: list[str]


@router.get("", response_model=MessageLogOut)
async def message_log(
    session: SessionDep,
    _: AdminUser,
    channel: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> MessageLogOut:
    return MessageLogOut.model_validate(
        await MessageLogService(session).list(channel=channel, status=status, query=q, limit=limit)
    )
