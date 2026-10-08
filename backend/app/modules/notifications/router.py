from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.core.deps import CurrentUser, SessionDep
from app.modules.notifications.service import NotificationService
from app.shared.schemas import Schema

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


class NotificationOut(Schema):
    id: UUID
    kind: str
    title: str
    body: str
    link: str | None
    actions: list[dict[str, Any]]
    related_type: str | None
    related_id: UUID | None
    created_at: datetime
    read_at: datetime | None


class InboxOut(Schema):
    items: list[NotificationOut]
    unread: int


@router.get("", response_model=InboxOut)
async def inbox(session: SessionDep, user: CurrentUser, unread_only: bool = False) -> InboxOut:
    service = NotificationService(session)
    items = await service.inbox(user, unread_only=unread_only)
    return InboxOut(items=[NotificationOut.model_validate(n) for n in items], unread=await service.unread_count(user))


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(notification_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await NotificationService(session).mark_read(user, notification_id)


@router.post("/read-all", status_code=204)
async def mark_all_read(session: SessionDep, user: CurrentUser) -> None:
    await NotificationService(session).mark_all_read(user)
