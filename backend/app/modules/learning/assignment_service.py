"""Assign training to people or a role, with preview first and undo (golden rule 4)."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.modules.identity.models import User
from app.modules.learning.bulk import BulkActionService, register_undo
from app.modules.learning.models import Assignment, AssignmentStatus, Course, CourseStatus
from app.modules.learning.schemas import AssignIn, AssignmentOut, AssignPreviewOut, BulkResultOut
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.shared.audience import resolve_audience
from app.shared.clock import today


class AssignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _published(self, course_id: UUID) -> Course:
        course = await self.session.get(Course, course_id)
        if course is None:
            raise NotFoundError("We could not find that course.")
        if course.status != CourseStatus.PUBLISHED.value:
            raise ValidationFailedError("Only published courses can be assigned.")
        return course

    async def _split(self, course_id: UUID, user_ids: list[UUID]) -> tuple[list[UUID], set[UUID]]:
        existing = (
            set(
                (
                    await self.session.scalars(
                        select(Assignment.user_id).where(Assignment.course_id == course_id, Assignment.user_id.in_(user_ids))
                    )
                ).all()
            )
            if user_ids
            else set()
        )
        return [u for u in user_ids if u not in existing], existing

    async def preview(self, data: AssignIn) -> AssignPreviewOut:
        course = await self._published(data.course_id)
        audience = await resolve_audience(self.session, data.audience)
        new, existing = await self._split(course.id, audience.user_ids)
        names = (await self.session.scalars(select(User.full_name).where(User.id.in_(new[:5])))).all() if new else []
        due = f" by {data.due_on:%d %b}" if data.due_on else ""
        return AssignPreviewOut(
            course_title=course.title,
            audience_label=audience.label,
            new_people=len(new),
            already_assigned=len(existing),
            sample_names=list(names),
            message_preview=f'Hi {{first name}}, "{course.title}" has been added to your learning{due}. '
            f"It takes about {course.duration_minutes} minutes.",
        )

    async def assign(self, data: AssignIn, actor: User | None, *, source: str = "manual") -> BulkResultOut:
        course = await self._published(data.course_id)
        audience = await resolve_audience(self.session, data.audience)
        new, _ = await self._split(course.id, audience.user_ids)
        bulk = await BulkActionService(self.session).start(
            "assign_course", actor, f'"{course.title}" to {audience.label}', len(new)
        )
        notifications = NotificationService(self.session)
        for user_id in new:
            self.session.add(
                Assignment(
                    user_id=user_id,
                    course_id=course.id,
                    assigned_by_id=actor.id if actor else None,
                    due_on=data.due_on,
                    is_mandatory=data.is_mandatory or course.is_mandatory,
                    source=source,
                    batch_id=bulk.id,
                )
            )
            due = f" by {data.due_on:%d %b}" if data.due_on else ""
            await notifications.notify(
                user_id,
                kind=NotificationKind.SYSTEM,
                title=f'New learning: "{course.title}"',
                body=f"About {course.duration_minutes} minutes{due}.",
                link=f"/learn/courses/{course.id}",
                actions=[{"label": "Start now", "href": f"/learn/courses/{course.id}"}],
                related=("course", course.id),
                automatic=source == "workflow",
            )
        await self.session.flush()
        return BulkResultOut(bulk_action_id=bulk.id, count=len(new), undo_until=bulk.undo_until, summary=bulk.summary)

    async def for_user(self, user_id: UUID, *, include_completed: bool = True) -> list[AssignmentOut]:
        stmt = (
            select(Assignment, Course)
            .join(Course, Course.id == Assignment.course_id)
            .where(Assignment.user_id == user_id)
            .order_by(Assignment.due_on.is_(None), Assignment.due_on, Course.title)
        )
        if not include_completed:
            stmt = stmt.where(Assignment.status != AssignmentStatus.COMPLETED.value)
        rows = (await self.session.execute(stmt)).all()
        return [to_out(a, c) for a, c in rows]

    async def open_items(self, user_ids: Sequence[UUID]) -> Sequence[Assignment]:
        if not user_ids:
            return []
        return (
            await self.session.scalars(
                select(Assignment).where(Assignment.user_id.in_(user_ids), Assignment.status != AssignmentStatus.COMPLETED.value)
            )
        ).all()


def to_out(a: Assignment, c: Course) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        course_id=c.id,
        course_title=c.title,
        course_kind=c.kind,
        duration_minutes=c.duration_minutes,
        due_on=a.due_on,
        status=a.status,
        is_mandatory=a.is_mandatory,
        progress_pct=a.progress_pct,
        source=a.source,
        is_overdue=is_overdue(a.due_on, a.status),
        completed_at=a.completed_at,
    )


def is_overdue(due_on: date | None, status: str) -> bool:
    return bool(due_on and due_on < today() and status != AssignmentStatus.COMPLETED.value)


async def _undo_assignments(session: AsyncSession, batch_id: UUID) -> int:
    result = await session.execute(
        delete(Assignment).where(Assignment.batch_id == batch_id, Assignment.status == AssignmentStatus.NOT_STARTED.value)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


register_undo("assign_course", _undo_assignments)
