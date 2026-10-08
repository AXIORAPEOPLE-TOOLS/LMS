"""Career map (L-07): up and sideways, with readiness from tested skills only."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.pathways.service import PathwayService
from app.modules.settings.service import SettingsService
from app.modules.skills import rules
from app.modules.skills.models import CareerMove, JobRole, RoleSkill, Skill, SkillLevel
from app.shared.schemas import Schema


class CareerOptionOut(Schema):
    role_id: UUID
    role_name: str
    direction: str  # up | side
    readiness_pct: int | None
    needs_more_tests: bool


class CareerMapOut(Schema):
    current_role_id: UUID | None
    current_role_name: str | None
    role_ready_skills: int
    core_skills: int
    options: list[CareerOptionOut]


class SkillGapOut(Schema):
    skill_id: UUID
    skill_name: str
    levels_to_go: int


class CareerDetailOut(Schema):
    role_id: UUID
    role_name: str
    readiness_pct: int
    tested: int
    total: int
    skills_to_close: list[SkillGapOut]
    test_next: list[str]
    weeks: int
    hours_per_week: int
    can_estimate: bool


class CareerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _requirements(self, user: User, role_id: UUID) -> list[tuple[Skill, int, int | None]]:
        levels = {
            sl.skill_id: sl.level
            for sl in (await self.session.scalars(select(SkillLevel).where(SkillLevel.user_id == user.id))).all()
        }
        rows = (
            await self.session.execute(
                select(Skill, RoleSkill.required_level)
                .join(RoleSkill, RoleSkill.skill_id == Skill.id)
                .where(RoleSkill.job_role_id == role_id)
            )
        ).all()
        return [(skill, required, levels.get(skill.id)) for skill, required in rows]

    async def map(self, user: User) -> CareerMapOut:
        current = await self.session.get(JobRole, user.job_role_id) if user.job_role_id else None
        options: list[CareerOptionOut] = []
        ready = core = 0
        if current:
            reqs = await self._requirements(user, current.id)
            core = len(reqs)
            ready = sum(1 for _, req, lvl in reqs if lvl is not None and lvl >= req)
            moves = (
                await self.session.execute(
                    select(CareerMove, JobRole)
                    .join(JobRole, JobRole.id == CareerMove.to_role_id)
                    .where(CareerMove.from_role_id == current.id)
                )
            ).all()
            for move, role in moves:
                result = rules.readiness(
                    [rules.Requirement(s.id, r, lvl) for s, r, lvl in await self._requirements(user, role.id)]
                )
                options.append(
                    CareerOptionOut(
                        role_id=role.id,
                        role_name=role.name,
                        direction="up" if move.kind == "vertical" else "side",
                        readiness_pct=result.percent if result.can_estimate else None,
                        needs_more_tests=not result.can_estimate,
                    )
                )
        options.sort(key=lambda o: (o.direction != "up", -(o.readiness_pct or -1)))
        return CareerMapOut(
            current_role_id=current.id if current else None,
            current_role_name=current.name if current else None,
            role_ready_skills=ready,
            core_skills=core,
            options=options,
        )

    async def detail(self, user: User, role_id: UUID) -> CareerDetailOut:
        role = await self.session.get(JobRole, role_id)
        if role is None:
            raise NotFoundError("We could not find that role.")
        reqs = await self._requirements(user, role.id)
        result = rules.readiness([rules.Requirement(s.id, r, lvl) for s, r, lvl in reqs])
        settings = SettingsService(self.session)
        hours_per_week = user.hours_per_week or await settings.get("pathways.default_hours_per_week")
        gaps = sorted(
            (
                SkillGapOut(skill_id=s.id, skill_name=s.name, levels_to_go=rules.gap(r, lvl))
                for s, r, lvl in reqs
                if lvl is not None and rules.gap(r, lvl) > 0
            ),
            key=lambda g: -g.levels_to_go,
        )
        return CareerDetailOut(
            role_id=role.id,
            role_name=role.name,
            readiness_pct=result.percent,
            tested=result.tested,
            total=result.total,
            skills_to_close=gaps,
            test_next=sorted(s.name for s, _, lvl in reqs if lvl is None),
            weeks=rules.weeks_to_close(
                sum(rules.gap(r, lvl) for _, r, lvl in reqs), await settings.get("pathways.hours_per_level"), hours_per_week
            ),
            hours_per_week=hours_per_week,
            can_estimate=result.can_estimate,
        )

    async def add_to_pathway(self, user: User, role_id: UUID) -> None:
        if await self.session.get(JobRole, role_id) is None:
            raise NotFoundError("We could not find that role.")
        await PathwayService(self.session).generate(user, user, target_role_id=role_id)

    async def talk_to_manager(self, user: User, role_id: UUID) -> None:
        role = await self.session.get(JobRole, role_id)
        if role is None:
            raise NotFoundError("We could not find that role.")
        if not user.manager_id:
            raise ValidationFailedError("You do not have a manager set yet. Ask HR to add one.")
        await NotificationService(self.session).notify(
            user.manager_id,
            kind=NotificationKind.SYSTEM,
            title=f"{user.full_name} would like to talk about the {role.name} role",
            link=f"/team/people/{user.id}",
            related=("job_role", role.id),
        )
