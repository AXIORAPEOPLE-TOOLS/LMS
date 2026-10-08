import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, UTCDateTime


class NotificationKind(StrEnum):
    REMINDER = "reminder"  # self-paced completion reminder
    INVITATION = "invitation"  # scheduled session, Accept / Decline
    NUDGE = "nudge"  # from a manager
    KNOWLEDGE = "knowledge"  # review ladder, access requests
    APPROVAL = "approval"
    SYSTEM = "system"
    WELCOME = "welcome"
    SUMMARY = "summary"  # manager overdue list


class Notification(IdMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # e.g. [{"label": "Start now", "action": "open", "href": "/learn/..."}]
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # {"in_app": "sent", "email": "sent", "whatsapp": "skipped"}
    channel_status: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    related_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    related_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    is_automatic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
