import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import IdMixin, TimestampMixin


class SystemRole(StrEnum):
    """What a person may do in the product (not their job)."""

    LEARNER = "learner"
    MANAGER = "manager"
    ADMIN = "admin"
    KNOWLEDGE_ADMIN = "knowledge_admin"
    FUNCTION_HEAD = "function_head"
    EXPERT = "expert"  # approves course drafts
    REVIEWER = "reviewer"  # reviews proctoring flags


class Department(IdMixin, TimestampMixin, Base):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    head_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    employee_code: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    system_roles: Mapped[list[str]] = mapped_column(JSON, default=lambda: [SystemRole.LEARNER.value])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_roles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    joined_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)  # for WhatsApp; optional

    # Personal preferences (L-10 My reminders, L-09 privacy on boards).
    locale: Mapped[str] = mapped_column(String(8), default="en")
    show_name_on_boards: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_window: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["11:00", "13:00"])
    reminder_channels: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=lambda: {"in_app": True, "email": True, "whatsapp": False}
    )
    hours_per_week: Mapped[int] = mapped_column(default=3)

    def has_role(self, *roles: str) -> bool:
        return any(role in (self.system_roles or []) for role in roles)

    @property
    def display_initials(self) -> str:
        parts = self.full_name.split()
        return "".join(p[0] for p in parts[:2]).upper()
