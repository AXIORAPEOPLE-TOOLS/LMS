from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.modules.learning.schemas import QuestionIn
from app.shared.audience import Audience
from app.shared.schemas import Schema


class TestOut(Schema):
    id: UUID
    skill_id: UUID | None
    skill_name: str | None = None
    title: str
    instructions: str
    duration_minutes: int
    proctoring: str
    pass_mark: int | None
    is_mandatory: bool
    question_count: int = 0
    certificate_title: str | None = None


class TestIn(Schema):
    skill_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    instructions: str = "Answer how you really work. This is to help plan your learning."
    duration_minutes: int = Field(default=15, ge=1, le=240)
    proctoring: str = Field(default="none", pattern="^(none|camera)$")
    pass_mark: int | None = Field(default=None, ge=1, le=100)
    is_mandatory: bool = False
    certificate_title: str | None = None
    validity_months: int | None = Field(default=None, ge=1, le=60)
    questions: list[QuestionIn] = Field(min_length=1)


class MyTestOut(Schema):
    invite_id: UUID | None
    test: TestOut
    due_on: date | None
    status: str  # pending | in_progress | done
    attempt_id: UUID | None = None
    last_score: int | None = None
    last_level: int | None = None


class StartAttemptIn(Schema):
    consent: bool = False


class AttemptQuestionOut(Schema):
    id: UUID
    text: str
    options: list[str]
    selected: int | None = None


class AttemptOut(Schema):
    id: UUID
    test_id: UUID
    test_title: str
    status: str
    proctoring: str
    snapshot_seconds: int
    questions: list[AttemptQuestionOut]
    answered: int
    total: int
    seconds_left: int


class AnswerIn(Schema):
    question_id: UUID
    option_index: int = Field(ge=0, le=9)


class ProctorEventIn(Schema):
    kind: str = Field(pattern="^(snapshot|second_face|no_face|tab_switch|phone_seen|camera_off|noise)$")
    at_seconds: int = Field(ge=0)
    image_base64: str | None = Field(default=None, max_length=2_000_000)


class AttemptResultOut(Schema):
    attempt_id: UUID
    status: str
    score: int
    level: int | None
    level_name: str | None
    passed: bool | None
    pass_mark: int | None
    rank: int | None
    out_of: int | None
    top_percent: int | None
    required_level: int | None
    meets_requirement: bool | None
    skills_left_to_check: int
    message: str
    certificate_id: UUID | None = None


class CampaignIn(Schema):
    test_ids: list[UUID] = Field(min_length=1)
    audience: Audience
    due_on: date | None = None


class CampaignPreviewOut(Schema):
    audience_label: str
    people: int
    tests: int
    new_invites: int


class InPersonIn(Schema):
    preferred_dates: str = Field(default="", max_length=300)


class BookingOut(Schema):
    id: UUID
    user_id: UUID
    test_id: UUID
    preferred_dates: str
    status: str
    scheduled_at: datetime | None
    created_at: datetime


# ---- proctoring review (A-09) --------------------------------------------------------
class FlagOut(Schema):
    id: UUID
    kind: str
    at_seconds: int
    severity: str | None
    count: int
    has_image: bool


class ReviewQueueItemOut(Schema):
    attempt_id: UUID
    test_title: str
    employee_code: str | None
    flags: int
    severity: str
    submitted_at: datetime | None
    is_appeal: bool


class ReviewCaseOut(Schema):
    attempt_id: UUID
    test_title: str
    employee_code: str | None
    question_count: int
    score: int | None
    minutes: int
    duration_seconds: int
    flags: list[FlagOut]
    status: str
    appeal_note: str | None
    previous_decision: str | None
    previous_note: str | None


class DecisionIn(Schema):
    decision: str = Field(pattern="^(valid|retest|invalid)$")
    note: str = Field(min_length=3, max_length=2000)


class AppealIn(Schema):
    note: str = Field(min_length=10, max_length=2000)
