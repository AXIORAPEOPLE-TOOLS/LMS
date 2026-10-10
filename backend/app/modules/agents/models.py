import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class RunKind(StrEnum):
    COURSE = "course"  # build a course from a brief
    QUIZ = "quiz"  # write the quick check for a course
    ASSIGN = "assign"  # assign training from a request


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"  # waiting for a person (confirm, approve)
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRun(IdMixin, TimestampMixin, Base):
    """One helper run: the brief, each step with what it did, and the result."""

    __tablename__ = "agent_runs"

    kind: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[str] = mapped_column(String(12), default=RunStatus.QUEUED.value, index=True)
    title: Mapped[str] = mapped_column(String(200))
    brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # [{"key", "label", "status": pending|running|done|skipped|waiting|failed, "detail", "at"}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    course_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(12), default="rules")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
