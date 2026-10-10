from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.modules.learning.schemas import AssignPreviewOut
from app.shared.audience import Audience
from app.shared.schemas import Schema


class CourseBriefIn(Schema):
    """LMS.pdf Course Creation step 1: topic, audience, goal and duration."""

    topic: str = Field(min_length=3, max_length=200)
    audience: str = Field(min_length=2, max_length=200)
    goal: str = Field(min_length=5, max_length=1000)
    duration_minutes: int = Field(default=30, ge=5, le=240)
    skill_id: UUID | None = None
    approver_id: UUID | None = None  # subject expert who checks accuracy (step 5)
    links: list[str] = Field(default=[], max_length=10)  # slides, videos, documents (step 4)
    use_knowledge: bool = True
    write_quiz: bool = True
    certification: bool = False

    @field_validator("links")
    @classmethod
    def _links(cls, links: list[str]) -> list[str]:
        clean = [link.strip() for link in links if link.strip()]
        for link in clean:
            if not link.startswith(("http://", "https://", "/")):
                raise ValueError("Links must start with http:// or https://")
        return clean


class QuizBriefIn(Schema):
    """LMS.pdf Quiz / Assessment Creation step 1: the course (its content and goals)."""

    course_id: UUID
    choice_count: int | None = Field(default=None, ge=0, le=30)
    written_count: int | None = Field(default=None, ge=0, le=10)
    pass_mark: int | None = Field(default=None, ge=1, le=100)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=180)


class AssignRequestIn(Schema):
    """LMS.pdf Training Assignment step 1, in plain words: 'POSH for Sales by 30 Nov'."""

    text: str = Field(min_length=3, max_length=500)


class AssignConfirmIn(Schema):
    course_id: UUID
    audience: Audience
    due_on: date | None = None
    is_mandatory: bool = False


class RunStepOut(Schema):
    key: str
    label: str
    status: str  # pending | running | done | skipped | waiting | failed
    detail: str = ""
    at: datetime | None = None


class AssignPlanOut(Schema):
    course_id: UUID | None
    course_title: str | None
    audience: dict[str, Any] | None
    audience_label: str | None
    due_on: date | None
    due_from_request: bool
    missing: list[str]
    preview: AssignPreviewOut | None = None


class RunSummaryOut(Schema):
    id: UUID
    kind: str
    status: str
    title: str
    course_id: UUID | None
    created_at: datetime
    finished_at: datetime | None
    step_done: int
    step_total: int


class RunOut(RunSummaryOut):
    brief: dict[str, Any]
    steps: list[RunStepOut]
    result: dict[str, Any]
    error: str | None
    course_status: str | None = None
    plan: AssignPlanOut | None = None
