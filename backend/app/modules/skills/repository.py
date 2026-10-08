from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.modules.skills.models import CareerMove, JobRole, RoleSkill, Skill, SkillLevel
from app.shared.repository import Repository


class SkillRepository(Repository[Skill]):
    model = Skill
    not_found_message = "We could not find that skill."

    async def by_ids(self, ids: Sequence[UUID]) -> dict[UUID, Skill]:
        if not ids:
            return {}
        return {s.id: s for s in await self.list(Skill.id.in_(ids))}


class JobRoleRepository(Repository[JobRole]):
    model = JobRole
    not_found_message = "We could not find that role."


class RoleSkillRepository(Repository[RoleSkill]):
    model = RoleSkill

    async def for_role(self, job_role_id: UUID) -> Sequence[RoleSkill]:
        return await self.list(RoleSkill.job_role_id == job_role_id)

    async def required_map(self, job_role_id: UUID) -> dict[UUID, int]:
        return {rs.skill_id: rs.required_level for rs in await self.for_role(job_role_id)}


class CareerMoveRepository(Repository[CareerMove]):
    model = CareerMove

    async def from_role(self, job_role_id: UUID) -> Sequence[CareerMove]:
        return await self.list(CareerMove.from_role_id == job_role_id)


class SkillLevelRepository(Repository[SkillLevel]):
    model = SkillLevel

    async def for_user(self, user_id: UUID) -> dict[UUID, SkillLevel]:
        return {sl.skill_id: sl for sl in await self.list(SkillLevel.user_id == user_id)}

    async def for_skill(self, skill_id: UUID) -> Sequence[SkillLevel]:
        return await self.list(SkillLevel.skill_id == skill_id)

    async def for_users(self, user_ids: Sequence[UUID]) -> Sequence[SkillLevel]:
        if not user_ids:
            return []
        return await self.scalars(select(SkillLevel).where(SkillLevel.user_id.in_(user_ids)))

    async def get_for(self, user_id: UUID, skill_id: UUID) -> SkillLevel | None:
        return await self.first(SkillLevel.user_id == user_id, SkillLevel.skill_id == skill_id)
