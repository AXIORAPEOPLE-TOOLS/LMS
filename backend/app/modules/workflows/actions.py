"""Workflow actions. Each action can preview (no side effects) and execute.

Adding a new action = one class + `register_action`; the engine never changes (OCP).
Actions reuse the feature services, so a workflow does exactly what a person
pressing the same button would do.
"""

from collections import defaultdict
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.shared.clock import today


class ActionResult(dict[str, Any]):
    """{'lines': [...plain words...], 'people': int}"""


class WorkflowAction(Protocol):
    code: str
    label: str

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult: ...
    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult: ...


async def _target_users(session: AsyncSession, context: dict[str, Any]) -> list[User]:
    stmt = select(User).where(User.is_active.is_(True))
    if context.get("user_ids"):
        stmt = stmt.where(User.id.in_([UUID(str(u)) for u in context["user_ids"]]))
    elif context.get("since_days"):
        from app.shared.clock import utcnow

        stmt = stmt.where(User.created_at >= utcnow() - timedelta(days=int(context["since_days"])))
    if context.get("job_role_ids"):
        stmt = stmt.where(User.job_role_id.in_([UUID(str(r)) for r in context["job_role_ids"]]))
    return list((await session.scalars(stmt.order_by(User.full_name))).all())


class AssignMandatoryTraining:
    code = "assign_mandatory_training"
    label = "Assign mandatory training"

    async def _plan(self, session: AsyncSession, context: dict[str, Any]) -> tuple[list[Any], dict[UUID, list[UUID]]]:
        from app.modules.learning.models import Assignment, Course, CourseStatus

        courses = list(
            (
                await session.scalars(
                    select(Course).where(Course.is_mandatory.is_(True), Course.status == CourseStatus.PUBLISHED.value)
                )
            ).all()
        )
        users = await _target_users(session, context)
        existing = set((await session.execute(select(Assignment.user_id, Assignment.course_id))).all())
        missing: dict[UUID, list[UUID]] = defaultdict(list)
        for course in courses:
            for user in users:
                if (user.id, course.id) not in existing:
                    missing[course.id].append(user.id)
        return courses, missing

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        courses, missing = await self._plan(session, context)
        titles = {c.id: c.title for c in courses}
        lines = [f'Assign "{titles[cid]}" to {len(uids)} people' for cid, uids in missing.items()]
        return ActionResult(
            lines=lines or ["Everyone already has their mandatory training."],
            people=len({u for uids in missing.values() for u in uids}),
        )

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.learning.assignment_service import AssignmentService
        from app.modules.learning.schemas import AssignIn
        from app.shared.audience import Audience

        _, missing = await self._plan(session, context)
        due = today() + timedelta(days=int(context.get("due_in_days", 14)))
        total = 0
        for course_id, user_ids in missing.items():
            result = await AssignmentService(session).assign(
                AssignIn(course_id=course_id, audience=Audience(user_ids=user_ids), due_on=due, is_mandatory=True),
                actor,
                source="workflow",
            )
            total += result.count
        return ActionResult(lines=[f"Assigned {total} mandatory items"], people=total)


class CreateSkillTests:
    code = "create_skill_tests"
    label = "Create skill tests for the role"

    async def _plan(self, session: AsyncSession, context: dict[str, Any]) -> dict[UUID, list[UUID]]:
        from app.modules.assessments.models import SkillTest, TestInvite
        from app.modules.skills.models import RoleSkill

        plan: dict[UUID, list[UUID]] = {}
        pending = set(
            (await session.execute(select(TestInvite.user_id, TestInvite.test_id).where(TestInvite.status == "pending"))).all()
        )
        for user in await _target_users(session, context):
            if not user.job_role_id:
                continue
            tests = (
                await session.scalars(
                    select(SkillTest.id)
                    .join(RoleSkill, RoleSkill.skill_id == SkillTest.skill_id)
                    .where(RoleSkill.job_role_id == user.job_role_id, SkillTest.is_active.is_(True))
                )
            ).all()
            todo = [t for t in tests if (user.id, t) not in pending]
            if todo:
                plan[user.id] = todo
        return plan

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        plan = await self._plan(session, context)
        count = sum(len(v) for v in plan.values())
        return ActionResult(lines=[f"Create {count} skill checks for {len(plan)} people"], people=len(plan))

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.assessments.schemas import CampaignIn
        from app.modules.assessments.service import AssessmentService
        from app.shared.audience import Audience

        plan = await self._plan(session, context)
        by_tests: dict[tuple[UUID, ...], list[UUID]] = defaultdict(list)
        for user_id, tests in plan.items():
            by_tests[tuple(sorted(tests))].append(user_id)
        created = 0
        for tests, users in by_tests.items():
            result = await AssessmentService(session).send_campaign(
                CampaignIn(
                    test_ids=list(tests),
                    audience=Audience(user_ids=users),
                    due_on=today() + timedelta(days=int(context.get("due_in_days", 14))),
                ),
                actor,
                automatic=actor is None,
            )
            created += result.count
        return ActionResult(lines=[f"Created {created} skill checks"], people=len(plan))


class SendWelcome:
    code = "send_welcome"
    label = "Send welcome"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        users = await _target_users(session, context)
        return ActionResult(lines=[f"Welcome message to {len(users)} people"], people=len(users))

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.notifications.models import NotificationKind
        from app.modules.notifications.service import NotificationService

        users = await _target_users(session, context)
        for user in users:
            await NotificationService(session).notify(
                user.id,
                kind=NotificationKind.WELCOME,
                title=f"Welcome, {user.full_name.split()[0]}!",
                body="Start with a short skill check. It shows your level and builds your learning plan.",
                link="/home",
                automatic=actor is None,
            )
        return ActionResult(lines=[f"Welcomed {len(users)} people"], people=len(users))


class SendCompletionReminders:
    code = "send_completion_reminders"
    label = "Send completion reminders"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        from app.modules.reminders.service import ReminderService

        planned = await ReminderService(session).preview()
        return ActionResult(lines=[f"{p.name} at {p.local_time} ({p.channels})" for p in planned[:20]], people=len(planned))

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.reminders.service import ReminderService

        created = await ReminderService(session).run(automatic=actor is None)
        return ActionResult(lines=[f"Scheduled {created} reminders"], people=created)


class CertificateRenewals:
    code = "certificate_renewal_reminders"
    label = "Remind about certificate renewal"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        from app.modules.certificates.models import Certificate

        horizon = today() + timedelta(days=60)
        count = len(
            (
                await session.scalars(
                    select(Certificate.id).where(
                        Certificate.status == "valid", Certificate.valid_until.is_not(None), Certificate.valid_until <= horizon
                    )
                )
            ).all()
        )
        return ActionResult(lines=[f"{count} certificates end within 60 days"], people=count)

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.certificates.service import CertificateService

        sent = await CertificateService(session).send_renewal_reminders()
        return ActionResult(lines=[f"Sent {sent} renewal reminders"], people=sent)


class SendSessionInvitations:
    code = "send_session_invitations"
    label = "Send session invitations"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        from app.modules.learning.session_service import SessionService

        if not context.get("session_id"):
            return ActionResult(lines=["No session chosen."], people=0)
        p = await SessionService(session).preview(UUID(str(context["session_id"])))
        return ActionResult(lines=[p.message, p.audience_label], people=p.people)

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.learning.session_service import SessionService

        if not context.get("session_id"):
            return ActionResult(lines=["No session chosen."], people=0)
        result = await SessionService(session).send_invitations(UUID(str(context["session_id"])), actor, automatic=actor is None)
        return ActionResult(lines=[result.summary], people=result.count)


class WeeklyOverdueSummary:
    code = "weekly_overdue_summary"
    label = "Send each manager one overdue list"

    async def _lists(self, session: AsyncSession) -> dict[UUID, list[str]]:
        from app.modules.learning.models import Assignment, AssignmentStatus, Course

        rows = (
            await session.execute(
                select(User, Course.title, Assignment.due_on)
                .join(Assignment, Assignment.user_id == User.id)
                .join(Course, Course.id == Assignment.course_id)
                .where(
                    Assignment.status != AssignmentStatus.COMPLETED.value,
                    Assignment.due_on < today(),
                    User.manager_id.is_not(None),
                    User.is_active.is_(True),
                )
            )
        ).all()
        lists: dict[UUID, list[str]] = defaultdict(list)
        for user, title, due in rows:
            assert user.manager_id is not None
            lists[user.manager_id].append(f"{user.full_name}: {title} ({(today() - due).days} days overdue)")
        return lists

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        lists = await self._lists(session)
        return ActionResult(
            lines=[f"{len(lists)} managers get one list ({sum(map(len, lists.values()))} items)"], people=len(lists)
        )

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.notifications.models import NotificationKind
        from app.modules.notifications.service import NotificationService

        lists = await self._lists(session)
        for manager_id, lines in lists.items():
            await NotificationService(session).notify(
                manager_id,
                kind=NotificationKind.SUMMARY,
                title=f"{len(lines)} overdue items in your team",
                body="\n".join(lines[:15]),
                link="/team",
                automatic=actor is None,
            )
        return ActionResult(lines=[f"Sent {len(lists)} manager lists"], people=len(lists))


class SendDeadlineReminders:
    code = "send_deadline_reminders"
    label = "Remind 7 days, 2 days and on the due date"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        from app.modules.reminders.deadlines import DeadlineService, stage_title

        items = await DeadlineService(session).due_today()
        return ActionResult(
            lines=[f"{i.user.full_name}: {stage_title(i.days_left, i.course_title)}" for i in items[:20]], people=len(items)
        )

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.reminders.deadlines import DeadlineService

        sent = await DeadlineService(session).run(automatic=actor is None)
        return ActionResult(lines=[f"Sent {sent} due-date reminders"], people=sent)


class OverdueAfterDeadline:
    code = "overdue_after_deadline"
    label = "After the deadline, send each manager the overdue list"

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        from app.modules.reminders.deadlines import DeadlineService

        lists = await DeadlineService(session).overdue_lists()
        return ActionResult(lines=[f"{len(lists)} managers, {sum(map(len, lists.values()))} people overdue"], people=len(lists))

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.reminders.deadlines import DeadlineService

        sent = await DeadlineService(session).send_overdue_lists(automatic=actor is None)
        return ActionResult(lines=[f"Sent {sent} manager lists"], people=sent)


class ResultsSummary:
    code = "results_summary"
    label = "Share yesterday's test results with HR and managers"

    async def _lines(self, session: AsyncSession) -> tuple[dict[UUID, list[tuple[str, bool]]], list[str]]:
        from datetime import datetime, time

        from app.modules.learning.models import Course, CourseQuizAttempt
        from app.shared.clock import org_timezone

        yesterday = today() - timedelta(days=1)
        start = datetime.combine(yesterday, time(0), tzinfo=org_timezone())
        end = start + timedelta(days=1)
        rows = (
            await session.execute(
                select(User, Course.title, CourseQuizAttempt.score, CourseQuizAttempt.passed)
                .join(CourseQuizAttempt, CourseQuizAttempt.user_id == User.id)
                .join(Course, Course.id == CourseQuizAttempt.course_id)
                .where(CourseQuizAttempt.submitted_at >= start, CourseQuizAttempt.submitted_at < end)
                .order_by(User.full_name)
            )
        ).all()
        by_manager: dict[UUID, list[tuple[str, bool]]] = defaultdict(list)
        everyone: list[str] = []
        for user, title, score, passed in rows:
            line = f"{user.full_name}: {title}: {'passed' if passed else 'not passed'} ({score}/100)"
            everyone.append(line)
            if user.manager_id:
                by_manager[user.manager_id].append((line, passed))
        return by_manager, everyone

    async def preview(self, session: AsyncSession, context: dict[str, Any]) -> ActionResult:
        by_manager, everyone = await self._lines(session)
        return ActionResult(
            lines=[f"{len(everyone)} results yesterday, {len(by_manager)} managers get their team's"], people=len(by_manager)
        )

    async def execute(self, session: AsyncSession, context: dict[str, Any], actor: User | None) -> ActionResult:
        from app.modules.notifications.models import NotificationKind
        from app.modules.notifications.service import NotificationService

        by_manager, everyone = await self._lines(session)
        if not everyone:
            return ActionResult(lines=["No test results yesterday"], people=0)
        notifications = NotificationService(session)
        for manager_id, lines in by_manager.items():
            passed = sum(ok for _, ok in lines)
            await notifications.notify(
                manager_id,
                kind=NotificationKind.SUMMARY,
                title=f"Team results: {passed} of {len(lines)} passed",
                body="\n".join(line for line, _ in lines[:20]),
                link="/admin/training",
                automatic=actor is None,
            )
        admins = [u for u in (await session.scalars(select(User).where(User.is_active.is_(True)))).all() if u.has_role("admin")]
        for admin in admins:
            await notifications.notify(
                admin.id,
                kind=NotificationKind.SUMMARY,
                title=f"Yesterday's test results: {len(everyone)}",
                body="\n".join(everyone[:30]),
                link="/admin/training",
                automatic=actor is None,
            )
        return ActionResult(
            lines=[f"Shared {len(everyone)} results with {len(by_manager)} managers and {len(admins)} HR admins"],
            people=len(by_manager) + len(admins),
        )


ACTIONS: dict[str, WorkflowAction] = {}


def register_action(action: WorkflowAction) -> None:
    ACTIONS[action.code] = action


for _action in (
    AssignMandatoryTraining(),
    CreateSkillTests(),
    SendWelcome(),
    SendCompletionReminders(),
    CertificateRenewals(),
    SendSessionInvitations(),
    WeeklyOverdueSummary(),
    SendDeadlineReminders(),
    OverdueAfterDeadline(),
    ResultsSummary(),
):
    register_action(_action)
