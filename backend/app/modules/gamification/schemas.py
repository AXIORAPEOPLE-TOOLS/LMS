from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.shared.schemas import Schema


class ProfileOut(Schema):
    user_id: UUID
    full_name: str
    initials: str
    skill_level_name: str | None
    points: int
    level_number: int
    level_name: str
    next_level_name: str | None
    points_to_next: int | None
    level_progress_pct: int
    streak_days: int
    levels_gained: int
    certificates: int
    week_points: int
    week_lessons: int
    week_tests: int
    show_name_on_boards: bool


class BadgeOut(Schema):
    code: str
    name: str
    description: str
    earned: bool
    awarded_at: datetime | None


class BadgesOut(Schema):
    earned: int
    total: int
    badges: list[BadgeOut]


class ChallengeOut(Schema):
    id: UUID
    title: str
    description: str
    goal_pct: int
    team_pct: int
    days_left: int
    ends_on: date
    reward_points: int
    reward_badge_code: str | None
    status: str
    joined: bool
    members: int
    my_part: list[str]


class ChallengeIn(Schema):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    department_id: UUID | None = None
    goal_pct: int = Field(default=80, ge=10, le=100)
    starts_on: date
    ends_on: date
    reward_points: int = Field(default=50, ge=0, le=1000)
    reward_badge_code: str | None = None


class BoardRowOut(Schema):
    rank: int
    user_id: UUID | None
    name: str
    department: str | None
    value: float
    display: str
    change: int | None  # places moved since the previous period (+ up)
    is_me: bool


class BoardOut(Schema):
    board: str
    title: str
    scope: str
    period: str
    rows: list[BoardRowOut]
    version: str


class DepartmentRateOut(Schema):
    department: str
    on_time_pct: int
    assigned: int


class ComplianceBoardOut(Schema):
    rows: list[DepartmentRateOut]
