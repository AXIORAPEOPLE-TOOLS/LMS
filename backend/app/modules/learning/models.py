import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class CourseKind(StrEnum):
    SELF_PACED = "self_paced"
    CERTIFICATION = "certification"  # pass mark + verifiable certificate


class CourseStatus(StrEnum):
    DRAFTING = "drafting"  # the builder is still working on it
    DRAFT = "draft"
    IN_REVIEW = "in_review"  # waiting for the subject expert
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SourceDocument(IdMixin, Base):
    """Text read from an uploaded SOP/PDF. Courses and knowledge items cite its pages."""

    __tablename__ = "source_documents"

    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{"page": 1, "text": "..."}]
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Course(IdMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True)
    from_level: Mapped[int] = mapped_column(Integer, default=0)
    to_level: Mapped[int] = mapped_column(Integer, default=2)
    kind: Mapped[str] = mapped_column(String(20), default=CourseKind.SELF_PACED.value)
    status: Mapped[str] = mapped_column(String(20), default=CourseStatus.DRAFT.value, index=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    pass_mark: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    languages: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["en"])
    has_video: Mapped[bool] = mapped_column(Boolean, default=False)
    has_simulation: Mapped[bool] = mapped_column(Boolean, default=False)
    validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    knowledge_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Certification courses may end in a (proctored) test instead of the course quiz.
    final_test_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skill_tests.id", ondelete="SET NULL"), nullable=True)


class LessonKind(StrEnum):
    VIDEO = "video"
    READING = "reading"
    SIMULATION = "simulation"


class Lesson(IdMixin, Base):
    __tablename__ = "lessons"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default=LessonKind.READING.value)
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=5)
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # {"en": [{"at": 0, "text": "..."}], "hi": [...]}
    captions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Simulation scenario (sheet 10): {"image": url, "steps": [{"id": "s1", "label": "Sanitiser", "x": 20, "y": 30}],
    #  "correct_order": ["s1", "s2"], "ar_supported": true}
    scenario: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CourseQuestion(IdMixin, Base):
    __tablename__ = "course_questions"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    answer_index: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")


class AssignmentStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Assignment(IdMixin, TimestampMixin, Base):
    """A course someone must (or chose to) complete."""

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=AssignmentStatus.NOT_STARTED.value, index=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    quiz_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | workflow | pathway | self
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LessonProgress(IdMixin, Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)


class LiveSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "live_sessions"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    meeting_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    audience_label: Mapped[str] = mapped_column(String(200), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    invitations_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class Invitation(IdMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("session_id", "user_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("live_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default=InvitationStatus.PENDING.value)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    attended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class BulkAction(IdMixin, Base):
    """Golden rule 4: anything sent to many people can be undone for N minutes."""

    __tablename__ = "bulk_actions"

    kind: Mapped[str] = mapped_column(String(40))  # assign_course | send_invitations | send_tests
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    summary: Mapped[str] = mapped_column(String(300), default="")
    count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    undo_until: Mapped[datetime] = mapped_column(UTCDateTime)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
