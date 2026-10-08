import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class Skill(IdMixin, TimestampMixin, Base):
    __tablename__ = "skills"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(80), default="Core")
    description: Mapped[str] = mapped_column(Text, default="")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)


class JobRole(IdMixin, TimestampMixin, Base):
    __tablename__ = "job_roles"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    industry_group: Mapped[str] = mapped_column(String(80), default="Education services")
    family: Mapped[str] = mapped_column(String(80), default="General")
    seniority: Mapped[int] = mapped_column(Integer, default=1)


class RoleSkill(IdMixin, Base):
    __tablename__ = "role_skills"
    __table_args__ = (UniqueConstraint("job_role_id", "skill_id"),)

    job_role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_roles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    required_level: Mapped[int] = mapped_column(Integer)
    is_core: Mapped[bool] = mapped_column(Boolean, default=True)


class CareerMoveKind(StrEnum):
    VERTICAL = "vertical"
    LATERAL = "lateral"


class CareerMove(IdMixin, Base):
    __tablename__ = "career_moves"
    __table_args__ = (UniqueConstraint("from_role_id", "to_role_id"),)

    from_role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_roles.id", ondelete="CASCADE"), index=True)
    to_role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_roles.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), default=CareerMoveKind.VERTICAL.value)


class SkillLevel(IdMixin, Base):
    """A person's current level in one skill (latest valid evidence wins)."""

    __tablename__ = "skill_levels"
    __table_args__ = (UniqueConstraint("user_id", "skill_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="test")  # test | manual | retest
    assessed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
