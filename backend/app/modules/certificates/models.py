import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, UTCDateTime


class Certificate(IdMixin, Base):
    __tablename__ = "certificates"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # C-2026-004217
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    test_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skill_tests.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int | None] = mapped_column(nullable=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(12), default="valid")  # valid | renewed | revoked
    revoked_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    renewal_reminders_sent: Mapped[list[int]] = mapped_column(JSON, default=list)
