import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class WorkflowMode(StrEnum):
    MANUAL = "manual"  # a person does it
    HYBRID = "hybrid"  # the system prepares it, a person approves
    AUTO = "auto"  # the system does it


class Workflow(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflows"

    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(60))  # event name or schedule:daily / schedule:weekly
    trigger_label: Mapped[str] = mapped_column(String(160), default="")
    condition_label: Mapped[str] = mapped_column(String(160), default="Any role")
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"job_role_ids": [...]}
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    approval_label: Mapped[str] = mapped_column(String(160), default="")
    mode: Mapped[str] = mapped_column(String(10), default=WorkflowMode.HYBRID.value)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(default=0)


class RunStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkflowRun(IdMixin, Base):
    __tablename__ = "workflow_runs"

    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    triggered_by: Mapped[str] = mapped_column(String(20))  # event | schedule | manual
    status: Mapped[str] = mapped_column(String(20), index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"lines": [...], "people": n}
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
