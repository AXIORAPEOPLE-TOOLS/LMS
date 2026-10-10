"""Learner home (L-01): answers one question — what should I do next?"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessments.models import SkillTest, TestInvite
from app.modules.gamification.service import GamificationService
from app.modules.identity.models import User
from app.modules.learning.assignment_service import AssignmentService
from app.modules.learning.models import Invitation, LiveSession
from app.modules.pathways.service import PathwayService
from app.shared.clock import utcnow
from app.shared.schemas import Schema


class NextStep(Schema):
    kind: str  # assignment | pathway | skill_check | explore
    title: str
    detail: str
    action_label: str
    href: str
    is_overdue: bool = False


class ComingUpItem(Schema):
    kind: str  # session | skill_check | assignment
    title: str
    detail: str
    href: str
    at: datetime | None = None
    due_on: date | None = None


class HomeOut(Schema):
    first_name: str
    level_label: str | None
    streak_days: int
    points: int
    next_step: NextStep
    pathway_progress_pct: int | None
    pathway_wave: int | None
    pathway_status: str | None
    coming_up: list[ComingUpItem]


class HomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def home(self, user: User) -> HomeOut:
        profile = await GamificationService(self.session).profile(user)
        pathway = await PathwayService(self.session).view(user.id)
        assignments = await AssignmentService(self.session).for_user(user.id, include_completed=False)
        invites = (
            await self.session.execute(
                select(TestInvite, SkillTest)
                .join(SkillTest, SkillTest.id == TestInvite.test_id)
                .where(TestInvite.user_id == user.id, TestInvite.status == "pending", SkillTest.is_active.is_(True))
                .order_by(TestInvite.due_on.is_(None), TestInvite.due_on)
            )
        ).all()
        sessions = (
            await self.session.execute(
                select(LiveSession, Invitation.status)
                .join(Invitation, Invitation.session_id == LiveSession.id)
                .where(
                    Invitation.user_id == user.id,
                    Invitation.batch_id.is_not(None),
                    Invitation.status != "declined",
                    LiveSession.starts_at >= utcnow(),
                )
                .order_by(LiveSession.starts_at)
                .limit(3)
            )
        ).all()

        next_step = self._next_step(assignments, pathway, invites)
        coming: list[ComingUpItem] = [
            ComingUpItem(
                kind="session",
                title=f"Live class: {live.title}",
                detail=f"{live.starts_at:%a %H:%M} · {'You accepted' if status == 'accepted' else 'Please reply'}",
                href=f"/learn/sessions/{live.id}",
                at=live.starts_at,
            )
            for live, status in sessions
        ]
        for invite, test in invites[:3]:
            if next_step.kind == "skill_check" and next_step.href.endswith(str(test.id)):
                continue
            due = f" · by {invite.due_on:%d %b}" if invite.due_on else ""
            coming.append(
                ComingUpItem(
                    kind="skill_check",
                    title=f"Test: {test.title}",
                    detail=f"{test.duration_minutes} min{due}",
                    href=f"/learn/tests/{test.id}",
                    due_on=invite.due_on,
                )
            )
        for a in assignments[:3]:
            if next_step.href.endswith(str(a.course_id)):
                continue
            due = f" · due {a.due_on:%d %b}" if a.due_on else ""
            coming.append(
                ComingUpItem(
                    kind="assignment",
                    title=a.course_title,
                    detail=f"{a.duration_minutes} min{due}",
                    href=f"/learn/courses/{a.course_id}",
                    due_on=a.due_on,
                )
            )
        return HomeOut(
            first_name=user.full_name.split()[0],
            level_label=profile.skill_level_name,
            streak_days=profile.streak_days,
            points=profile.points,
            next_step=next_step,
            pathway_progress_pct=pathway.progress_pct if pathway else None,
            pathway_wave=pathway.current_wave if pathway else None,
            pathway_status=pathway.status if pathway else None,
            coming_up=coming[:5],
        )

    @staticmethod
    def _next_step(assignments, pathway, invites) -> NextStep:  # type: ignore[no-untyped-def]
        """Priority: overdue mandatory > pathway step > skill check > soonest due > explore."""
        overdue = [a for a in assignments if a.is_overdue and a.is_mandatory]
        if overdue:
            a = overdue[0]
            return NextStep(
                kind="assignment",
                title=a.course_title,
                is_overdue=True,
                detail=f"{a.duration_minutes} minutes · was due {a.due_on:%d %b}",
                action_label="Continue" if a.progress_pct else "Start",
                href=f"/learn/courses/{a.course_id}",
            )
        if pathway and pathway.next_step:
            step = pathway.next_step
            return NextStep(
                kind="pathway",
                title=step.title,
                detail=step.description,
                action_label=step.action_label,
                href=step.href or "/learn/path",
            )
        if invites:
            invite, test = invites[0]
            due = f" · by {invite.due_on:%d %b}" if invite.due_on else ""
            return NextStep(
                kind="skill_check",
                title=f"Test: {test.title}",
                detail=f"About {test.duration_minutes} minutes{due}",
                action_label="Start",
                href=f"/learn/tests/{test.id}",
            )
        if assignments:
            a = assignments[0]
            due = f" · due {a.due_on:%d %b}" if a.due_on else ""
            return NextStep(
                kind="assignment",
                title=a.course_title,
                is_overdue=a.is_overdue,
                detail=f"{a.duration_minutes} minutes{due}",
                action_label="Continue" if a.progress_pct else "Start learning",
                href=f"/learn/courses/{a.course_id}",
            )
        return NextStep(
            kind="explore",
            title="Pick something new to learn",
            detail="Browse short courses for your role.",
            action_label="Browse courses",
            href="/learn/catalogue",
        )
