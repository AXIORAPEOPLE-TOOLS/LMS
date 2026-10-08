import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, UTCDateTime


class ReportSchedule(IdMixin, Base):
    __tablename__ = "report_schedules"

    report_id: Mapped[str] = mapped_column(String(60))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    frequency: Mapped[str] = mapped_column(String(10))  # weekly | monthly
    export_format: Mapped[str] = mapped_column(String(5), default="xlsx")
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
