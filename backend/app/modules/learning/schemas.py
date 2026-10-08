from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.shared.audience import Audience
from app.shared.schemas import Schema


class LessonOut(Schema):
    id: UUID
    position: int
    title: str
    kind: str
    summary: str
    body: str
    source_ref: str | None
    duration_minutes: int
    media_url: str | None
    captions: dict[str, Any]
    scenario: dict[str, Any] | None
    completed: bool = False


class LessonIn(Schema):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="reading", pattern="^(video|reading|simulation)$")
    summary: str = ""
    body: str = ""
    source_ref: str | None = None
    duration_minutes: int = Field(default=5, ge=1, le=240)
    media_url: str | None = None
    captions: dict[str, Any] = {}
    scenario: dict[str, Any] | None = None


class QuestionOut(Schema):
    """What a learner sees: never the answer."""

    id: UUID
    position: int
    text: str
    options: list[str]


class QuestionAdminOut(QuestionOut):
    answer_index: int
    reason: str


class QuestionIn(Schema):
    text: str = Field(min_length=3)
    options: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    reason: str = ""

    @model_validator(mode="after")
    def _answer_in_range(self) -> "QuestionIn":
        if self.answer_index >= len(self.options):
            raise ValueError("The right answer must be one of the options.")
        return self


class CourseSummaryOut(Schema):
    id: UUID
    title: str
    description: str
    skill_id: UUID | None
    skill_name: str | None = None
    from_level: int
    to_level: int
    kind: str
    status: str
    is_mandatory: bool
    pass_mark: int | None
    duration_minutes: int
    languages: list[str]
    has_video: bool
    has_simulation: bool
    lesson_count: int = 0


class MyProgressOut(Schema):
    assignment_id: UUID | None
    status: str
    progress_pct: int
    due_on: date | None
    quiz_score: int | None
    completed_lessons: int
    next_lesson_id: UUID | None


class CourseDetailOut(CourseSummaryOut):
    lessons: list[LessonOut]
    question_count: int
    my_progress: MyProgressOut | None = None
    source_filename: str | None = None
    approver_id: UUID | None = None
    review_note: str | None = None
    final_test_id: UUID | None = None


class CourseAdminDetailOut(CourseDetailOut):
    questions: list[QuestionAdminOut]


class CourseIn(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    skill_id: UUID | None = None
    from_level: int = Field(default=0, ge=0, le=5)
    to_level: int = Field(default=2, ge=0, le=5)
    kind: str = Field(default="self_paced", pattern="^(self_paced|certification)$")
    is_mandatory: bool = False
    pass_mark: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int = Field(default=20, ge=1, le=600)
    languages: list[str] = ["en"]
    validity_months: int | None = Field(default=None, ge=1, le=60)
    final_test_id: UUID | None = None


class CourseUpdate(Schema):
    title: str | None = None
    description: str | None = None
    skill_id: UUID | None = None
    from_level: int | None = Field(default=None, ge=0, le=5)
    to_level: int | None = Field(default=None, ge=0, le=5)
    kind: str | None = Field(default=None, pattern="^(self_paced|certification)$")
    is_mandatory: bool | None = None
    pass_mark: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    languages: list[str] | None = None
    validity_months: int | None = None
    final_test_id: UUID | None = None


class ContentReplace(Schema):
    lessons: list[LessonIn]
    questions: list[QuestionIn] = []


class DraftOptions(Schema):
    skill_id: UUID | None = None
    from_level: int = Field(default=0, ge=0, le=5)
    to_level: int = Field(default=2, ge=0, le=5)
    narrated_video: bool = True
    simulation: bool = True
    certification: bool = False
    quiz_size: int = Field(default=12, ge=3, le=30)
    languages: list[str] = ["en", "hi"]


class SubmitForReviewIn(Schema):
    approver_id: UUID


class ReviewDecisionIn(Schema):
    approve: bool
    note: str = Field(default="", max_length=2000)


class SimulationAttemptIn(Schema):
    order: list[str] = Field(min_length=1)


class SimulationResultOut(Schema):
    correct: bool
    first_wrong_step: int | None
    message: str
    points: int


class QuizSubmitIn(Schema):
    answers: dict[UUID, int]


class QuizQuestionResult(Schema):
    question_id: UUID
    correct: bool
    right_index: int
    reason: str


class QuizResultOut(Schema):
    score: int
    passed: bool
    pass_mark: int | None
    results: list[QuizQuestionResult]
    course_completed: bool


class LessonCompleteOut(Schema):
    progress_pct: int
    course_completed: bool
    next_lesson_id: UUID | None
    quiz_pending: bool


# ---- assignments --------------------------------------------------------------
class AssignIn(Schema):
    course_id: UUID
    audience: Audience
    due_on: date | None = None
    is_mandatory: bool = False


class AssignPreviewOut(Schema):
    course_title: str
    audience_label: str
    new_people: int
    already_assigned: int
    sample_names: list[str]
    message_preview: str


class BulkResultOut(Schema):
    bulk_action_id: UUID
    count: int
    undo_until: datetime
    summary: str


class AssignmentOut(Schema):
    id: UUID
    course_id: UUID
    course_title: str
    course_kind: str
    duration_minutes: int
    due_on: date | None
    status: str
    is_mandatory: bool
    progress_pct: int
    source: str
    is_overdue: bool
    completed_at: datetime | None


# ---- sessions & invitations -----------------------------------------------------
class SessionIn(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    course_id: UUID | None = None
    trainer_id: UUID | None = None
    starts_at: datetime
    ends_at: datetime
    meeting_link: str | None = None
    location: str | None = None
    audience: Audience

    @model_validator(mode="after")
    def _times(self) -> "SessionIn":
        if self.ends_at <= self.starts_at:
            raise ValueError("The session must end after it starts.")
        return self


class SessionOut(Schema):
    id: UUID
    title: str
    description: str
    course_id: UUID | None
    trainer_id: UUID | None
    trainer_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    meeting_link: str | None
    location: str | None
    audience_label: str
    invitations_sent_at: datetime | None
    accepted: int = 0
    declined: int = 0
    waiting: int = 0
    my_status: str | None = None


class InvitationPreviewOut(Schema):
    audience_label: str
    people: int
    message: str


class RsvpIn(Schema):
    accept: bool


class UndoOut(Schema):
    undone: int
