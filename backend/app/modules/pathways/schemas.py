from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.shared.schemas import Schema


class PathwayItemOut(Schema):
    id: UUID
    wave: int
    position: int
    skill_id: UUID
    skill_name: str
    from_level: int
    to_level: int
    step: str
    course_id: UUID | None
    course_title: str | None
    mentor_id: UUID | None
    mentor_name: str | None
    practise_task: str
    practise_evidence: str | None
    practise_submitted_at: datetime | None
    waiting_for_signoff: bool
    certificate_on_pass: bool
    estimated_hours: float


class WaveOut(Schema):
    number: int
    status: str  # active | locked | done
    hours: float
    weeks: int
    progress_pct: int
    items: list[PathwayItemOut]


class NextStepOut(Schema):
    item_id: UUID
    step: str
    title: str
    description: str
    action_label: str
    href: str | None


class PathwayOut(Schema):
    id: UUID
    user_id: UUID
    status: str
    hours_per_week: int
    target_role_id: UUID | None
    target_role_name: str | None
    approved_by_name: str | None
    current_wave: int | None
    total_waves: int
    progress_pct: int
    waves: list[WaveOut]
    next_step: NextStepOut | None


class EvidenceIn(Schema):
    evidence: str = Field(min_length=10, max_length=4000)


class GenerateIn(Schema):
    target_role_id: UUID | None = None
