"""Admin home (A-01): five quick actions (frontend) and live numbers."""

from datetime import timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessments.models import AttemptStatus, TestAttempt, TestInvite
from app.modules.certificates.models import Certificate
from app.modules.gamification.models import PointEntry
from app.modules.identity.models import User
from app.modules.learning.models import Assignment, AssignmentStatus, Course, CourseStatus
from app.modules.skills.models import RoleSkill, Skill, SkillLevel
from app.shared.clock import org_timezone, today, utcnow
from app.shared.schemas import Schema


class Metric(Schema):
    key: str
    label: str
    value: str
    change: int | None = None  # vs previous period, + is better


class AttentionItem(Schema):
    text: str
    href: str


class ContentGap(Schema):
    skill_id: str
    skill_name: str
    people: int
    text: str


class AdminHomeOut(Schema):
    metrics: list[Metric]
    attention: list[AttentionItem]
    content_gaps: list[ContentGap]


class AdminHomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _completion(self, start, end) -> int | None:  # type: ignore[no-untyped-def]
        total, done = (
            await self.session.execute(
                select(func.count(), func.count().filter(Assignment.status == AssignmentStatus.COMPLETED.value)).where(
                    Assignment.due_on >= start, Assignment.due_on <= end
                )
            )
        ).one()
        return round(done / total * 100) if total else None

    async def _on_time(self, start, end) -> int | None:  # type: ignore[no-untyped-def]
        rows = (
            await self.session.execute(
                select(Assignment.status, Assignment.due_on, Assignment.completed_at).where(
                    Assignment.is_mandatory.is_(True),
                    Assignment.due_on >= start,
                    Assignment.due_on <= end,
                    Assignment.due_on <= today(),
                )
            )
        ).all()
        if not rows:
            return None
        tz = org_timezone()
        on_time = sum(
            1
            for status, due, completed in rows
            if status == AssignmentStatus.COMPLETED.value and completed and completed.astimezone(tz).date() <= due
        )
        return round(on_time / len(rows) * 100)

    async def overview(self) -> AdminHomeOut:
        now, day = utcnow(), today()
        week_start = day - timedelta(days=day.weekday())
        active = int(
            await self.session.scalar(
                select(func.count(distinct(PointEntry.user_id))).where(PointEntry.at >= now - timedelta(days=7))
            )
            or 0
        )
        completion = await self._completion(week_start, week_start + timedelta(days=6))
        completion_prev = await self._completion(week_start - timedelta(days=7), week_start - timedelta(days=1))
        on_time = await self._on_time(day - timedelta(days=90), day)
        on_time_prev = await self._on_time(day - timedelta(days=180), day - timedelta(days=91))
        overdue = int(
            await self.session.scalar(
                select(func.count()).where(Assignment.status != AssignmentStatus.COMPLETED.value, Assignment.due_on < day)
            )
            or 0
        )
        invited, done = (await self.session.execute(select(func.count(), func.count().filter(TestInvite.status == "done")))).one()

        metrics = [
            Metric(key="active_learners", label="Active learners", value=str(active)),
            Metric(
                key="completion_week",
                label="Completion this week",
                value=f"{completion}%" if completion is not None else "–",
                change=completion - completion_prev if completion is not None and completion_prev is not None else None,
            ),
            Metric(
                key="on_time_compliance",
                label="On-time compliance",
                value=f"{on_time}%" if on_time is not None else "–",
                change=on_time - on_time_prev if on_time is not None and on_time_prev is not None else None,
            ),
            Metric(key="overdue", label="Overdue items", value=str(overdue)),
            Metric(key="tests", label="Tests completed", value=f"{done} / {invited}"),
        ]
        return AdminHomeOut(metrics=metrics, attention=await self._attention(), content_gaps=await self._content_gaps())

    async def _attention(self) -> list[AttentionItem]:
        items: list[AttentionItem] = []
        day = today()
        expiring = int(
            await self.session.scalar(
                select(func.count()).where(
                    Certificate.status == "valid",
                    Certificate.valid_until.is_not(None),
                    Certificate.valid_until <= day + timedelta(days=7),
                    Certificate.valid_until >= day,
                )
            )
            or 0
        )
        if expiring:
            items.append(
                AttentionItem(
                    text=f"{expiring} certificate{'s' if expiring != 1 else ''} expire in 7 days",
                    href="/admin/reports?report=certificates_expiring",
                )
            )
        not_started = (
            await self.session.execute(
                select(Course.title, func.count())
                .join(Assignment, Assignment.course_id == Course.id)
                .where(Course.is_mandatory.is_(True), Assignment.status == AssignmentStatus.NOT_STARTED.value)
                .group_by(Course.title)
                .order_by(func.count().desc())
                .limit(3)
            )
        ).all()
        for title, count in not_started:
            items.append(
                AttentionItem(text=f"{title}: {count} people not started", href="/admin/reports?report=mandatory_compliance")
            )
        flagged = int(
            await self.session.scalar(select(func.count()).where(TestAttempt.status == AttemptStatus.UNDER_REVIEW.value)) or 0
        )
        if flagged:
            items.append(
                AttentionItem(
                    text=f"{flagged} flagged proctored attempt{'s' if flagged != 1 else ''} to review", href="/admin/proctoring"
                )
            )
        return items

    async def _content_gaps(self, limit: int = 3) -> list[ContentGap]:
        """Skills where people have gaps but no published course exists yet."""
        covered = select(Course.skill_id).where(Course.status == CourseStatus.PUBLISHED.value, Course.skill_id.is_not(None))
        rows = (
            await self.session.execute(
                select(User.id, RoleSkill.skill_id, RoleSkill.required_level, SkillLevel.level)
                .join(RoleSkill, RoleSkill.job_role_id == User.job_role_id)
                .outerjoin(SkillLevel, (SkillLevel.user_id == User.id) & (SkillLevel.skill_id == RoleSkill.skill_id))
                .where(User.is_active.is_(True), RoleSkill.skill_id.not_in(covered))
            )
        ).all()
        people: dict = {}  # type: ignore[type-arg]
        for user_id, skill_id, required, level in rows:
            if level is not None and level < required:
                people.setdefault(skill_id, set()).add(user_id)
        ranked = sorted(people.items(), key=lambda kv: -len(kv[1]))[:limit]
        names = (
            dict((await self.session.execute(select(Skill.id, Skill.name).where(Skill.id.in_([k for k, _ in ranked])))).all())
            if ranked
            else {}
        )
        return [
            ContentGap(
                skill_id=str(sid),
                skill_name=names.get(sid, "Skill"),
                people=len(users),
                text=f"{names.get(sid, 'Skill')}: {len(users)} people need it",
            )
            for sid, users in ranked
        ]
