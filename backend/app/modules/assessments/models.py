import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class Proctoring(StrEnum):
    NONE = "none"
    CAMERA = "camera"  # snapshot every N seconds + tab-switch detection


class SkillTest(IdMixin, TimestampMixin, Base):
    __tablename__ = "skill_tests"

    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="Answer how you really work. This is to help plan your learning.")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    proctoring: Mapped[str] = mapped_column(String(12), default=Proctoring.NONE.value)
    # None = skill check (no pass or fail, it shows your level). A number = mandatory test with pass mark.
    pass_mark: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    certificate_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TestQuestion(IdMixin, Base):
    __tablename__ = "test_questions"

    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_tests.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    answer_index: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")


class TestInvite(IdMixin, Base):
    """'Skill check: Customer communication · by 20 Oct' on the learner home."""

    __tablename__ = "test_invites"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_tests.id", ondelete="CASCADE"), index=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | done
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"  # proctoring flags wait for a trained reviewer
    VALID = "valid"
    RETEST = "retest"
    INVALID = "invalid"


class TestAttempt(IdMixin, Base):
    __tablename__ = "test_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_tests.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=AttemptStatus.IN_PROGRESS.value, index=True)
    mode: Mapped[str] = mapped_column(String(12), default="online")  # online | in_person
    question_order: Mapped[list[str]] = mapped_column(JSON, default=list)
    answers: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Proctoring review (A-09)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    appeal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    appeal_status: Mapped[str | None] = mapped_column(String(12), nullable=True)  # open | upheld | overturned
    appeal_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    case_closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class FlagSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


FLAG_SEVERITY = {
    "second_face": FlagSeverity.HIGH,
    "no_face": FlagSeverity.MEDIUM,
    "tab_switch": FlagSeverity.MEDIUM,
    "phone_seen": FlagSeverity.HIGH,
    "camera_off": FlagSeverity.MEDIUM,
    "noise": FlagSeverity.LOW,
}


class ProctorEvent(IdMixin, Base):
    """A snapshot or a flag. Pictures are deleted N days after the case closes."""

    __tablename__ = "proctor_events"

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_attempts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # snapshot | second_face | tab_switch | ...
    at_seconds: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str | None] = mapped_column(String(8), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class InPersonBooking(IdMixin, Base):
    """Anyone can choose an in-person test instead of camera supervision."""

    __tablename__ = "in_person_bookings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skill_tests.id", ondelete="CASCADE"))
    preferred_dates: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(12), default="requested")  # requested | scheduled | done | cancelled
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
