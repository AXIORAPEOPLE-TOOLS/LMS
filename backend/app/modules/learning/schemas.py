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
    kind: str = "choice"  # choice | written


class RubricPointIn(Schema):
    point: str = Field(min_length=2, max_length=300)
    marks: int = Field(default=1, ge=1, le=5)


class QuestionAdminOut(QuestionOut):
    answer_index: int
    reason: str
    model_answer: str = ""
    rubric: list[RubricPointIn] = []


class QuestionIn(Schema):
    text: str = Field(min_length=3)
    kind: str = Field(default="choice", pattern="^(choice|written)$")
    options: list[str] = Field(default=[], max_length=6)
    answer_index: int = Field(default=0, ge=0)
    reason: str = ""
    model_answer: str = ""
    rubric: list[RubricPointIn] = Field(default=[], max_length=6)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "QuestionIn":
        if self.kind == "written":
            if not self.rubric:
                raise ValueError("A written question needs at least one point to score against.")
            return self
        if len(self.options) < 2:
            raise ValueError("Give at least two options.")
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
    quiz_time_limit_minutes: int | None = None


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
    quiz_time_limit_minutes: int | None = Field(default=None, ge=1, le=180)


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
    quiz_time_limit_minutes: int | None = Field(default=None, ge=1, le=180)


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
    # Option index for choice questions, a few lines of text for written ones.
    answers: dict[UUID, int | str]


class QuizQuestionResult(Schema):
    question_id: UUID
    correct: bool
    # Only sent once the learner has passed, so answers cannot be read before a retake.
    right_index: int | None = None
    reason: str | None = None
    marks: int | None = None  # written answers
    max_marks: int | None = None
    feedback: str | None = None


class QuizResultOut(Schema):
    score: int
    passed: bool
    pass_mark: int
    correct_count: int
    total: int
    results: list[QuizQuestionResult]
    course_completed: bool
    attempts_used: int
    attempts_left: int | None  # None = no limit
    can_retake: bool
    under_review: bool = False  # a person is checking the written answers; the score may change


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


class AssignPersonOut(Schema):
    id: UUID
    name: str
    department: str | None
    job_role: str | None
    already_assigned: bool


class AssignPreviewOut(Schema):
    course_title: str
    skill_name: str | None = None
    due_on: date | None = None
    is_mandatory: bool = False
    pass_mark: int | None = None
    people: list[AssignPersonOut] = []
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


# ---- course test attempts (learner) and HR tracker ----------------------------------
class QuizAttemptOut(Schema):
    attempt_no: int
    score: int
    passed: bool
    submitted_at: datetime
    review_status: str = "none"


class WrittenAnswerOut(Schema):
    question_id: UUID
    question: str
    model_answer: str
    rubric: list[RubricPointIn]
    answer: str
    marks: int
    max_marks: int
    confidence: float
    feedback: str


class WrittenReviewOut(Schema):
    attempt_id: UUID
    course_id: UUID
    course_title: str
    person: str
    attempt_no: int
    submitted_at: datetime
    provisional_score: int
    pass_mark: int
    answers: list[WrittenAnswerOut]


class WrittenMarkIn(Schema):
    question_id: UUID
    marks: int = Field(ge=0, le=30)
    feedback: str = ""


class WrittenDecisionIn(Schema):
    marks: list[WrittenMarkIn]


class TrackerPersonOut(Schema):
    user_id: UUID
    name: str
    department: str | None
    state: str  # not_started | in_progress | course_done | failed | passed
    state_label: str
    overdue: bool
    due_on: date | None
    progress_pct: int
    lessons_done: int
    lessons_total: int
    best_score: int | None
    attempts: int
    completed_at: datetime | None


class TrackerCourseOut(Schema):
    course_id: UUID
    course_title: str
    skill_name: str | None
    total: int
    counts: dict[str, int]
    overdue: int


class TrackerOut(TrackerCourseOut):
    has_test: bool
    pass_mark: int | None
    people: list[TrackerPersonOut]
