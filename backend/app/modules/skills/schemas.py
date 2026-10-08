from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.shared.schemas import Schema


class SkillOut(Schema):
    id: UUID
    code: str
    name: str
    category: str
    description: str
    is_mandatory: bool


class SkillIn(Schema):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    category: str = "Core"
    description: str = ""
    is_mandatory: bool = False


class JobRoleOut(Schema):
    id: UUID
    code: str
    name: str
    industry_group: str
    family: str
    seniority: int


class JobRoleIn(Schema):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    industry_group: str = "Education services"
    family: str = "General"
    seniority: int = Field(default=1, ge=1, le=10)


class RoleSkillOut(Schema):
    skill_id: UUID
    skill_name: str
    required_level: int
    is_core: bool


class RoleDetailOut(JobRoleOut):
    skills: list[RoleSkillOut]
    people_count: int


class RoleSkillIn(Schema):
    skill_id: UUID
    required_level: int = Field(ge=0, le=5)
    is_core: bool = True


class RoleSkillsReplace(Schema):
    skills: list[RoleSkillIn]


class MySkillOut(Schema):
    skill_id: UUID
    skill_name: str
    category: str
    required_level: int | None
    current_level: int | None
    score: int | None
    gap: int
    rank: int | None
    out_of: int | None
    top_percent: int | None
    assessed_at: datetime | None


class RankingRowOut(Schema):
    rank: int
    user_id: UUID
    name: str
    department: str | None
    score: int
    level: int
    is_me: bool = False


class SkillRankingOut(Schema):
    skill_id: UUID
    skill_name: str
    rows: list[RankingRowOut]


class ManualLevelIn(Schema):
    level: int = Field(ge=0, le=5)
    reason: str = Field(min_length=3, max_length=500)
