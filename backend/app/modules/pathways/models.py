import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class PathwayStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    COMPLETED = "completed"


class Step(StrEnum):
    """Each skill has four steps: learn, practise, connect, prove."""

    LEARN = "learn"
    PRACTISE = "practise"
    CONNECT = "connect"
    PROVE = "prove"
    DONE = "done"


STEP_ORDER = [Step.LEARN, Step.PRACTISE, Step.CONNECT, Step.PROVE, Step.DONE]


class Pathway(IdMixin, TimestampMixin, Base):
    __tablename__ = "pathways"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=PathwayStatus.PENDING_APPROVAL.value, index=True)
    target_role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_roles.id", ondelete="SET NULL"), nullable=True)
    hours_per_week: Mapped[int] = mapped_column(Integer, default=3)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class PathwayItem(IdMixin, Base):
    __tablename__ = "pathway_items"

    pathway_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pathways.id", ondelete="CASCADE"), index=True)
    wave: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    from_level: Mapped[int] = mapped_column(Integer)
    to_level: Mapped[int] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(String(10), default=Step.LEARN.value)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    mentor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    practise_task: Mapped[str] = mapped_column(Text, default="")
    practise_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    practise_submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    practise_signed_off_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    certificate_on_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_hours: Mapped[float] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
