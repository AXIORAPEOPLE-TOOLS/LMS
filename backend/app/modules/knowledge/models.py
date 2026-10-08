"""Knowledge Hub data (sheet 14). Separate module: works without the learning system."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.models import IdMixin, TimestampMixin, UTCDateTime


class ItemKind(StrEnum):
    SOP = "sop"
    POLICY = "policy"
    TEMPLATE = "template"
    CHECKLIST = "checklist"
    PLAYBOOK = "playbook"
    FAQ = "faq"
    FILE = "file"
    LINK = "link"
    LIST = "list"
    REPORT = "report"
    MEETING_NOTES = "meeting_notes"
    CONTACT_LIST = "contact_list"


KIND_LABELS = {
    "sop": "SOP",
    "policy": "Policy",
    "template": "Template",
    "checklist": "Checklist",
    "playbook": "Playbook",
    "faq": "FAQ",
    "file": "File",
    "link": "Link",
    "list": "List",
    "report": "Report",
    "meeting_notes": "Meeting notes",
    "contact_list": "Contact list",
}


class ItemStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Visibility(StrEnum):
    COMPANY = "company"  # everyone
    TEAM = "team"  # one department
    RESTRICTED = "restricted"  # only people granted access


class KnowledgeCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_categories"

    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    head_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_items"

    title: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(20), default=ItemKind.SOP.value, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    backup_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    visibility: Mapped[str] = mapped_column(String(12), default=Visibility.COMPANY.value)
    team_department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default=ItemStatus.PUBLISHED.value, index=True)
    version_major: Mapped[int] = mapped_column(Integer, default=1)
    version_minor: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{"name", "upload_id"}]
    file_text: Mapped[str] = mapped_column(Text, default="")  # text read from files, for search
    list_columns: Mapped[list[str]] = mapped_column(JSON, default=list)  # for kind=list
    review_months: Mapped[int] = mapped_column(Integer, default=12)
    next_review_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    linked_course_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    linked_skill_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    @property
    def version_label(self) -> str:
        return f"{self.version_major}.{self.version_minor}"


class KnowledgeVersion(IdMixin, Base):
    """A published change. Restoring makes a new version; nothing is ever overwritten."""

    __tablename__ = "knowledge_versions"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    change_note: Mapped[str] = mapped_column(String(500), default="")
    is_major: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeRevision(IdMixin, Base):
    """Every save of a draft. 'submitted' = an editor's change waiting for the owner."""

    __tablename__ = "knowledge_revisions"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | submitted | approved | rejected
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class KnowledgeReview(IdMixin, Base):
    """The owner confirms it is still right."""

    __tablename__ = "knowledge_reviews"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="still_correct")  # still_correct | updated | snoozed
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeAccess(IdMixin, Base):
    __tablename__ = "knowledge_access"
    __table_args__ = (UniqueConstraint("item_id", "principal_type", "principal_id"),)

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    principal_type: Mapped[str] = mapped_column(String(12))  # user | department
    principal_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(String(10), default="viewer")  # viewer | editor


class KnowledgeAccessRequest(IdMixin, Base):
    __tablename__ = "knowledge_access_requests"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10), default="viewer")
    reason: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeListRow(IdMixin, Base):
    """A row of a simple data list (vendors register, contacts...)."""

    __tablename__ = "knowledge_list_rows"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class KnowledgeUpload(IdMixin, Base):
    __tablename__ = "knowledge_uploads"

    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeSearchLog(IdMixin, Base):
    __tablename__ = "knowledge_search_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    query: Mapped[str] = mapped_column(String(300))
    mode: Mapped[str] = mapped_column(String(8), default="search")  # search | ask
    results: Mapped[int] = mapped_column(Integer, default=0)
    top_category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class KnowledgeReminderLog(IdMixin, Base):
    """Which ladder stage was already sent for an item and due date (no repeats)."""

    __tablename__ = "knowledge_reminder_logs"
    __table_args__ = (UniqueConstraint("item_id", "due_on", "stage", "period_key"),)

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), index=True)
    due_on: Mapped[date] = mapped_column(Date)
    stage: Mapped[int] = mapped_column(Integer)
    period_key: Mapped[str] = mapped_column(String(12), default="")  # week number for the weekly stage
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeHealthSnapshot(IdMixin, Base):
    __tablename__ = "knowledge_health_snapshots"
    __table_args__ = (UniqueConstraint("month", "category_id"),)

    month: Mapped[str] = mapped_column(String(7))  # 2026-10
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # None = company
    score: Mapped[int] = mapped_column(Integer)
