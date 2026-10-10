"""Manager views (M-01 team, M-02 skills heatmap, M-03 approvals)."""

from collections import Counter
from datetime import date, timedelta
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.assessments.models import SkillTest, TestInvite
from app.modules.identity.models import User
from app.modules.learning.models import Assignment, AssignmentStatus, Course
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.pathways.service import PathwayService
from app.modules.skills.models import RoleSkill, Skill, SkillLevel
from app.modules.skills.service import short_name
from app.shared.clock import today, utcnow
from app.shared.schemas import Schema

DUE_SOON_DAYS = 7


class TeamCountsOut(Schema):
    on_track: int
    due_soon: int
    overdue: int
    to_approve: int
    people: int


class HeatmapOut(Schema):
    skills: list[dict[str, str]]  # [{"id", "name"}]
    rows: list[dict]  # [{"user_id", "name", "levels": [int | None], "required": [int | None]}]  # type: ignore[type-arg]


class AttentionOut(Schema):
    user_id: UUID
    name: str
    item: str
    detail: str
    overdue_days: int | None


class ApprovalOut(Schema):
    kind: str  # pathway | practise
    id: UUID
    title: str
    detail: str


class TeamOut(Schema):
    counts: TeamCountsOut
    heatmap: HeatmapOut
    attention: list[AttentionOut]
    approvals: list[ApprovalOut]


class NudgeIn(Schema):
    user_id: UUID
    item: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=500)


class ManagerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def team_members(self, manager: User) -> list[User]:
        stmt = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        if not manager.has_role("admin") or manager.has_role("manager"):
            stmt = stmt.where(User.manager_id == manager.id)
        return list((await self.session.scalars(stmt)).all())

    async def team(self, manager: User) -> TeamOut:
        people = await self.team_members(manager)
        ids = [p.id for p in people]
        open_items = (
            (
                await self.session.execute(
                    select(Assignment, Course.title)
                    .join(Course, Course.id == Assignment.course_id)
                    .where(Assignment.user_id.in_(ids), Assignment.status != AssignmentStatus.COMPLETED.value)
                )
            ).all()
            if ids
            else []
        )
        test_items = (
            (
                await self.session.execute(
                    select(TestInvite, SkillTest.title)
                    .join(SkillTest, SkillTest.id == TestInvite.test_id)
                    .where(TestInvite.user_id.in_(ids), TestInvite.status == "pending")
                )
            ).all()
            if ids
            else []
        )
        by_person: dict[UUID, list[tuple[str, date | None, str]]] = {p.id: [] for p in people}
        for a, title in open_items:
            by_person[a.user_id].append((title, a.due_on, "course"))
        for invite, title in test_items:
            by_person[invite.user_id].append((f"Test: {title}", invite.due_on, "test"))

        overdue_people, soon_people = set(), set()
        attention: list[AttentionOut] = []
        names = {p.id: p.full_name for p in people}
        for user_id, items in by_person.items():
            for title, due, _ in items:
                if due is None:
                    continue
                days = (due - today()).days
                if days < 0:
                    overdue_people.add(user_id)
                    attention.append(
                        AttentionOut(
                            user_id=user_id,
                            name=short_name(names[user_id]),
                            item=title,
                            detail=f"{title} · {-days} days overdue",
                            overdue_days=-days,
                        )
                    )
                elif days <= DUE_SOON_DAYS:
                    soon_people.add(user_id)
                    attention.append(
                        AttentionOut(
                            user_id=user_id,
                            name=short_name(names[user_id]),
                            item=title,
                            detail=f"{title} · due {due:%A}",
                            overdue_days=None,
                        )
                    )
        soon_people -= overdue_people
        attention.sort(key=lambda a: -(a.overdue_days or -1))
        approvals = await self.approvals(manager)
        return TeamOut(
            counts=TeamCountsOut(
                on_track=len(people) - len(overdue_people) - len(soon_people),
                due_soon=len(soon_people),
                overdue=len(overdue_people),
                to_approve=len(approvals),
                people=len(people),
            ),
            heatmap=await self.heatmap(people),
            attention=attention[:10],
            approvals=approvals,
        )

    async def heatmap(self, people: list[User], max_skills: int = 8) -> HeatmapOut:
        role_ids = {p.job_role_id for p in people if p.job_role_id}
        links = (
            (await self.session.scalars(select(RoleSkill).where(RoleSkill.job_role_id.in_(role_ids)))).all() if role_ids else []
        )
        frequency = Counter(link.skill_id for link in links)
        skill_ids = [sid for sid, _ in frequency.most_common(max_skills)]
        skills = {s.id: s for s in (await self.session.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()}
        required = {(link.job_role_id, link.skill_id): link.required_level for link in links}
        levels = (
            {
                (sl.user_id, sl.skill_id): sl.level
                for sl in (
                    await self.session.scalars(
                        select(SkillLevel).where(
                            SkillLevel.user_id.in_([p.id for p in people]), SkillLevel.skill_id.in_(skill_ids)
                        )
                    )
                ).all()
            }
            if people and skill_ids
            else {}
        )
        ordered = [sid for sid in skill_ids if sid in skills]
        return HeatmapOut(
            skills=[{"id": str(sid), "name": skills[sid].name} for sid in ordered],
            rows=[
                {
                    "user_id": str(p.id),
                    "name": short_name(p.full_name),
                    "levels": [levels.get((p.id, sid)) for sid in ordered],
                    "required": [required.get((p.job_role_id, sid)) for sid in ordered],
                }
                for p in people
            ],
        )

    async def approvals(self, manager: User) -> list[ApprovalOut]:
        pathways = PathwayService(self.session)
        out: list[ApprovalOut] = []
        for pathway in await pathways.pending_approvals(manager):
            person = await self.session.get(User, pathway.user_id)
            out.append(
                ApprovalOut(
                    kind="pathway",
                    id=pathway.id,
                    title=f"Pathway for {short_name(person.full_name) if person else 'team member'}",
                    detail="Waves built from skill gaps",
                )
            )
        for item, pathway in await pathways.pending_signoffs(manager):
            person = await self.session.get(User, pathway.user_id)
            skill = await self.session.get(Skill, item.skill_id)
            out.append(
                ApprovalOut(
                    kind="practise",
                    id=item.id,
                    title=f"Practise sign-off: {short_name(person.full_name) if person else ''}",
                    detail=f"{skill.name if skill else 'Skill'}: {(item.practise_evidence or '')[:140]}",
                )
            )
        return out

    async def nudge(self, manager: User, data: NudgeIn) -> None:
        person = await self.session.get(User, data.user_id)
        if person is None:
            raise NotFoundError("We could not find that person.")
        if person.manager_id != manager.id and not manager.has_role("admin"):
            raise PermissionDeniedError("This person is not in your team.")
        since = utcnow() - timedelta(hours=20)
        recent = (
            await self.session.scalars(
                select(Notification.id).where(
                    Notification.user_id == person.id,
                    Notification.kind == NotificationKind.NUDGE.value,
                    Notification.created_at >= since,
                )
            )
        ).first()
        if recent:
            raise ConflictError("You already nudged this person today. One kind reminder is enough.")
        first = manager.full_name.split()[0]
        await NotificationService(self.session).notify(
            person.id,
            kind=NotificationKind.NUDGE,
            title=f"A friendly reminder from {first}",
            body=data.message
            or (
                f'Could you find a few minutes for "{data.item}" this week?'
                if data.item
                else "Could you find a few minutes for your learning this week?"
            ),
            link="/home",
        )
