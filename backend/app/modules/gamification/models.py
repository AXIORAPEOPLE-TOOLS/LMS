import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, UTCDateTime


class PointEntry(IdMixin, Base):
    """Points only for real learning; never negative (sheet 11)."""

    __tablename__ = "point_entries"
    __table_args__ = (UniqueConstraint("user_id", "reason", "ref_id"),)  # no double points

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(30))  # lesson | course | test | level_up | certificate | challenge
    ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)  # learning time, for the hours board
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class Badge(IdMixin, Base):
    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200))
    # {"type": "count", "reason": "lesson", "at_least": 1} | {"type": "points", "at_least": 1000}
    # | {"type": "streak", "days": 5} | {"type": "certificate_title", "contains": "POSH"}
    rule: Mapped[dict[str, Any]] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, default=0)


class UserBadge(IdMixin, Base):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    badge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"))
    awarded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Challenge(IdMixin, Base):
    """'Team week: finish 80% of assigned items together.' Joining is optional."""

    __tablename__ = "challenges"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=True)
    goal_pct: Mapped[int] = mapped_column(Integer, default=80)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    reward_points: Mapped[int] = mapped_column(Integer, default=50)
    reward_badge_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | won | ended
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ChallengeMember(IdMixin, Base):
    __tablename__ = "challenge_members"
    __table_args__ = (UniqueConstraint("challenge_id", "user_id"),)

    challenge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LeaderboardSnapshot(IdMixin, Base):
    """Ranks at the start of a period, so boards can show ▲ 2 / ▼ 1 movement."""

    __tablename__ = "leaderboard_snapshots"

    key: Mapped[str] = mapped_column(String(120), index=True)  # board|scope|skill
    ranks: Mapped[dict[str, int]] = mapped_column(JSON)
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
