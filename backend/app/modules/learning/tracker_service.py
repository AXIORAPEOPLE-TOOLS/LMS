"""HR training tracker: where every assigned person stands, per course.

States are kept separate on purpose (core flow): finishing the lessons is not passing the test.

    not_started  nothing opened yet
    in_progress  some lessons done
    course_done  all lessons done, test not passed yet (or not taken)
    failed       last test attempt failed
    passed       course completed (test passed, or no test)

`overdue` is a flag on top of the state: due date gone and not completed.
"""

import csv
import io
from collections import Counter
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.identity.models import Department, User
from app.modules.learning.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseQuestion,
    CourseQuizAttempt,
    Lesson,
    LessonProgress,
)
from app.modules.learning.schemas import TrackerCourseOut, TrackerOut, TrackerPersonOut
from app.modules.settings.service import SettingsService
from app.modules.skills.models import Skill
from app.shared.clock import today

STATES = ("not_started", "in_progress", "course_done", "failed", "passed")
STATE_LABEL = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "course_done": "Course done, test not passed",
    "failed": "Failed the test",
    "passed": "Passed",
}


class TrackerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _team_filter(self, viewer: User) -> list[UUID] | None:
        """Admins see everyone; managers see only the people who report to them."""
        if viewer.has_role("admin"):
            return None
        return list((await self.session.scalars(select(User.id).where(User.manager_id == viewer.id))).all())

    async def courses(self, viewer: User) -> list[TrackerCourseOut]:
        team = await self._team_filter(viewer)
        stmt = select(Assignment.course_id).distinct()
        if team is not None:
            stmt = stmt.where(Assignment.user_id.in_(team))
        course_ids = list((await self.session.scalars(stmt)).all())
        out = []
        for course_id in course_ids:
            tracker = await self.course(course_id, viewer)
            out.append(
                TrackerCourseOut(
                    course_id=tracker.course_id,
                    course_title=tracker.course_title,
                    skill_name=tracker.skill_name,
                    total=tracker.total,
                    counts=tracker.counts,
                    overdue=tracker.overdue,
                )
            )
        return sorted(out, key=lambda c: (-c.overdue, c.course_title))

    async def course(self, course_id: UUID, viewer: User) -> TrackerOut:
        course = await self.session.get(Course, course_id)
        if course is None:
            raise NotFoundError("We could not find that course.")
        team = await self._team_filter(viewer)
        stmt = (
            select(Assignment, User.full_name, Department.name)
            .join(User, User.id == Assignment.user_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(Assignment.course_id == course_id)
            .order_by(User.full_name)
        )
        if team is not None:
            stmt = stmt.where(Assignment.user_id.in_(team))
        rows = (await self.session.execute(stmt)).all()

        lesson_total = (
            await self.session.scalar(select(func.count()).select_from(Lesson).where(Lesson.course_id == course_id)) or 0
        )
        has_quiz = bool(
            await self.session.scalar(select(CourseQuestion.id).where(CourseQuestion.course_id == course_id).limit(1))
        )
        pass_mark = course.pass_mark or int(await SettingsService(self.session).get("learning.quiz_pass_mark"))
        user_ids = [a.user_id for a, _, _ in rows]
        lessons_done = (
            dict(
                (
                    await self.session.execute(
                        select(LessonProgress.user_id, func.count())
                        .where(LessonProgress.course_id == course_id, LessonProgress.user_id.in_(user_ids))
                        .group_by(LessonProgress.user_id)
                    )
                ).all()
            )
            if user_ids
            else {}
        )
        last_attempt = await self._last_attempts(course_id, user_ids)
        skill = await self.session.get(Skill, course.skill_id) if course.skill_id else None

        people: list[TrackerPersonOut] = []
        for assignment, name, department in rows:
            done = lessons_done.get(assignment.user_id, 0)
            last = last_attempt.get(assignment.user_id)
            state = self._state(assignment, done, lesson_total, has_quiz, last)
            overdue = bool(
                assignment.due_on and assignment.due_on < today() and assignment.status != AssignmentStatus.COMPLETED.value
            )
            people.append(
                TrackerPersonOut(
                    user_id=assignment.user_id,
                    name=name,
                    department=department,
                    state=state,
                    state_label=STATE_LABEL[state],
                    overdue=overdue,
                    due_on=assignment.due_on,
                    progress_pct=assignment.progress_pct,
                    lessons_done=done,
                    lessons_total=lesson_total,
                    best_score=assignment.quiz_score,
                    attempts=assignment.quiz_attempts,
                    completed_at=assignment.completed_at,
                )
            )
        counts = Counter(p.state for p in people)
        return TrackerOut(
            course_id=course.id,
            course_title=course.title,
            skill_name=skill.name if skill else None,
            has_test=has_quiz,
            pass_mark=pass_mark if has_quiz else None,
            total=len(people),
            counts={s: counts.get(s, 0) for s in STATES},
            overdue=sum(p.overdue for p in people),
            people=people,
        )

    async def _last_attempts(self, course_id: UUID, user_ids: list[UUID]) -> dict[UUID, CourseQuizAttempt]:
        if not user_ids:
            return {}
        attempts = (
            await self.session.scalars(
                select(CourseQuizAttempt)
                .where(CourseQuizAttempt.course_id == course_id, CourseQuizAttempt.user_id.in_(user_ids))
                .order_by(CourseQuizAttempt.attempt_no)
            )
        ).all()
        return {a.user_id: a for a in attempts}  # last one wins

    @staticmethod
    def _state(
        assignment: Assignment, lessons_done: int, lesson_total: int, has_quiz: bool, last: CourseQuizAttempt | None
    ) -> str:
        if assignment.status == AssignmentStatus.COMPLETED.value:
            return "passed"
        if has_quiz and last is not None and not last.passed:
            return "failed"
        if lesson_total and lessons_done >= lesson_total:
            return "course_done"
        if lessons_done or assignment.progress_pct or assignment.status == AssignmentStatus.IN_PROGRESS.value:
            return "in_progress"
        return "not_started"

    async def course_csv(self, course_id: UUID, viewer: User) -> tuple[str, str]:
        tracker = await self.course(course_id, viewer)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Name", "Department", "State", "Overdue", "Due", "Progress %", "Lessons", "Best score", "Tries"])
        for p in tracker.people:
            writer.writerow(
                [
                    p.name,
                    p.department or "",
                    p.state_label,
                    "yes" if p.overdue else "",
                    p.due_on or "",
                    p.progress_pct,
                    f"{p.lessons_done}/{p.lessons_total}",
                    p.best_score if p.best_score is not None else "",
                    p.attempts,
                ]
            )
        return f"{tracker.course_title}.csv", buffer.getvalue()
