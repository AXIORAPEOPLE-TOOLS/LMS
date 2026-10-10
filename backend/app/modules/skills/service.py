from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.identity.repository import DepartmentRepository, UserRepository
from app.modules.settings.service import SettingsService
from app.modules.skills import rules
from app.modules.skills.models import JobRole, RoleSkill, Skill, SkillLevel
from app.modules.skills.repository import (
    JobRoleRepository,
    RoleSkillRepository,
    SkillLevelRepository,
    SkillRepository,
)
from app.modules.skills.schemas import (
    JobRoleIn,
    MySkillOut,
    RankingRowOut,
    RoleDetailOut,
    RoleSkillOut,
    RoleSkillsReplace,
    SkillIn,
    SkillRankingOut,
)
from app.shared.clock import utcnow
from app.shared.events import DomainEvent, event_bus


class SkillsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.skills = SkillRepository(session)
        self.roles = JobRoleRepository(session)
        self.role_skills = RoleSkillRepository(session)
        self.levels = SkillLevelRepository(session)
        self.users = UserRepository(session)
        self.settings = SettingsService(session)
        self.audit = AuditService(session)

    # ---- catalogue -------------------------------------------------------
    async def list_skills(self, query: str | None = None) -> Sequence[Skill]:
        where = [Skill.name.ilike(f"%{query}%")] if query else []
        return await self.skills.list(*where, order_by=Skill.name)

    async def create_skill(self, data: SkillIn, actor: User) -> Skill:
        if await self.skills.first(Skill.code == data.code):
            raise ConflictError("A skill with this code already exists.")
        skill = await self.skills.add_and_flush(Skill(**data.model_dump()))
        self.audit.record("skill.created", "skill", skill.id, actor_id=actor.id, name=skill.name)
        return skill

    async def list_roles(self, query: str | None = None) -> Sequence[JobRole]:
        where = [JobRole.name.ilike(f"%{query}%")] if query else []
        return await self.roles.list(*where, order_by=JobRole.name)

    async def create_role(self, data: JobRoleIn, actor: User) -> JobRole:
        if await self.roles.first(JobRole.code == data.code):
            raise ConflictError("A role with this code already exists.")
        role = await self.roles.add_and_flush(JobRole(**data.model_dump()))
        self.audit.record("role.created", "job_role", role.id, actor_id=actor.id, name=role.name)
        return role

    async def role_detail(self, role_id: UUID) -> RoleDetailOut:
        role = await self.roles.get_or_raise(role_id)
        links = await self.role_skills.for_role(role_id)
        skills = await self.skills.by_ids([link.skill_id for link in links])
        rows = sorted(
            (
                RoleSkillOut(
                    skill_id=link.skill_id,
                    skill_name=skills[link.skill_id].name,
                    required_level=link.required_level,
                    is_core=link.is_core,
                )
                for link in links
                if link.skill_id in skills
            ),
            key=lambda r: (-r.required_level, r.skill_name),
        )
        people = await self.users.count(User.job_role_id == role_id, User.is_active.is_(True))
        return RoleDetailOut(**JobRoleIn.model_validate(role).model_dump(), id=role.id, skills=rows, people_count=people)

    async def replace_role_skills(self, role_id: UUID, data: RoleSkillsReplace, actor: User) -> RoleDetailOut:
        await self.roles.get_or_raise(role_id)
        for link in await self.role_skills.for_role(role_id):
            await self.session.delete(link)
        await self.session.flush()
        for item in data.skills:
            if await self.skills.get(item.skill_id) is None:
                raise NotFoundError("One of the skills does not exist.")
            self.role_skills.add(RoleSkill(job_role_id=role_id, **item.model_dump()))
        await self.session.flush()
        self.audit.record("role.skills_changed", "job_role", role_id, actor_id=actor.id, count=len(data.skills))
        return await self.role_detail(role_id)

    # ---- levels ----------------------------------------------------------
    async def level_for_score(self, score: float) -> int:
        return rules.score_to_level(score, await self.settings.get("skills.level_bands"))

    async def record_level(self, user_id: UUID, skill_id: UUID, *, level: int, score: int | None, source: str) -> SkillLevel:
        """Store the newest level and announce changes (points, pathways, boards react)."""
        current = await self.levels.get_for(user_id, skill_id)
        previous = current.level if current else None
        if current is None:
            current = self.levels.add(SkillLevel(user_id=user_id, skill_id=skill_id, level=level, score=score, source=source))
        else:
            current.previous_level = previous
            current.level, current.score, current.source = level, score, source
            current.assessed_at = utcnow()
        await self.session.flush()
        await event_bus.publish(
            self.session,
            DomainEvent(
                "skill.level_recorded",
                {"user_id": user_id, "skill_id": skill_id, "level": level, "previous": previous, "score": score},
            ),
        )
        return current

    async def set_level_manually(self, user_id: UUID, skill_id: UUID, level: int, reason: str, actor: User) -> SkillLevel:
        await self.users.get_or_raise(user_id)
        await self.skills.get_or_raise(skill_id)
        record = await self.record_level(user_id, skill_id, level=level, score=None, source="manual")
        self.audit.record(
            "skill_level.override", "skill_level", record.id, actor_id=actor.id, user_id=user_id, level=level, reason=reason
        )
        return record

    async def my_skills(self, user: User) -> list[MySkillOut]:
        required = await self.role_skills.required_map(user.job_role_id) if user.job_role_id else {}
        levels = await self.levels.for_user(user.id)
        skill_ids = list(set(required) | set(levels))
        skills = await self.skills.by_ids(skill_ids)
        training = await self._training_by_skill(user.id)
        out: list[MySkillOut] = []
        for skill_id in skill_ids:
            skill = skills.get(skill_id)
            if skill is None:
                continue
            record = levels.get(skill_id)
            rank = await self._rank_of(user.id, skill_id) if record and record.score is not None else None
            req = required.get(skill_id)
            out.append(
                MySkillOut(
                    skill_id=skill_id,
                    skill_name=skill.name,
                    category=skill.category,
                    required_level=req,
                    current_level=record.level if record else None,
                    score=record.score if record else None,
                    gap=rules.gap(req, record.level if record else None) if req is not None else 0,
                    rank=rank.rank if rank else None,
                    out_of=rank.out_of if rank else None,
                    top_percent=rank.top_percent if rank else None,
                    assessed_at=record.assessed_at if record else None,
                    required_by_role=req is not None,
                    training=training.get(skill_id, "none"),
                    proven=bool(record and record.assessed_at and req is not None and record.level >= req),
                )
            )
        return sorted(out, key=lambda s: (-s.gap, s.skill_name))

    async def _training_by_skill(self, user_id: UUID) -> dict[UUID, str]:
        """Most advanced training state per skill, from the person's course assignments."""
        from app.modules.learning.models import Assignment, Course  # late import: learning depends on skills

        rank = {"assigned": 1, "in_progress": 2, "course_done": 3}
        rows = (
            await self.session.execute(
                select(Course.skill_id, Assignment.status, Assignment.progress_pct)
                .join(Course, Course.id == Assignment.course_id)
                .where(Assignment.user_id == user_id, Course.skill_id.is_not(None))
            )
        ).all()
        out: dict[UUID, str] = {}
        for skill_id, status, progress in rows:
            state = (
                "course_done" if status == "completed" else "in_progress" if progress or status == "in_progress" else "assigned"
            )
            if rank[state] > rank.get(out.get(skill_id, ""), 0):
                out[skill_id] = state
        return out

    async def _rank_of(self, user_id: UUID, skill_id: UUID) -> rules.RankEntry | None:
        entries = rules.stack_rank((sl.user_id, sl.score) for sl in await self.levels.for_skill(skill_id) if sl.score is not None)
        return next((e for e in entries if e.key == user_id), None)

    async def ranking(self, skill_id: UUID, viewer: User, *, user_ids: Sequence[UUID] | None = None) -> SkillRankingOut:
        skill = await self.skills.get_or_raise(skill_id)
        records = [sl for sl in await self.levels.for_skill(skill_id) if sl.score is not None]
        if user_ids is not None:
            allowed = set(user_ids)
            records = [r for r in records if r.user_id in allowed]
        by_user = {r.user_id: r for r in records}
        people = {u.id: u for u in await self.users.list(User.id.in_(list(by_user)))} if by_user else {}
        departments = await DepartmentRepository(self.session).all_by_id()
        reveal_all = viewer.has_role("admin", "manager")
        rows: list[RankingRowOut] = []
        for entry in rules.stack_rank((uid, r.score or 0) for uid, r in by_user.items()):
            person = people.get(entry.key)
            if person is None:
                continue
            hidden = not person.show_name_on_boards and person.id != viewer.id and not reveal_all
            dept = departments.get(person.department_id) if person.department_id else None
            rows.append(
                RankingRowOut(
                    rank=entry.rank,
                    user_id=person.id,
                    name="A colleague" if hidden else short_name(person.full_name),
                    department=dept.name if dept else None,
                    score=int(entry.score),
                    level=by_user[person.id].level,
                    is_me=person.id == viewer.id,
                )
            )
        return SkillRankingOut(skill_id=skill.id, skill_name=skill.name, rows=rows)


def short_name(full_name: str) -> str:
    """'Asha Verma' -> 'Asha V.' (boards never show full surnames)."""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    return f"{parts[0]} {parts[-1][0]}."
