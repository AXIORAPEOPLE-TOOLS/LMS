"""Taking a course: lessons, simulations, quiz, completion (L-03)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.modules.identity.models import User
from app.modules.learning.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseKind,
    CourseQuestion,
    CourseStatus,
    Lesson,
    LessonKind,
    LessonProgress,
)
from app.modules.learning.schemas import (
    LessonCompleteOut,
    QuizQuestionResult,
    QuizResultOut,
    SimulationResultOut,
)
from app.modules.settings.service import SettingsService
from app.shared.clock import utcnow
from app.shared.events import DomainEvent, event_bus

DEFAULT_PASS_MARK = 60


class PlayerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _course(self, course_id: UUID) -> Course:
        course = await self.session.get(Course, course_id)
        if course is None or course.status != CourseStatus.PUBLISHED.value:
            raise NotFoundError("We could not find that course.")
        return course

    async def _lesson(self, lesson_id: UUID) -> tuple[Lesson, Course]:
        lesson = await self.session.get(Lesson, lesson_id)
        if lesson is None:
            raise NotFoundError("We could not find that lesson.")
        return lesson, await self._course(lesson.course_id)

    async def _assignment(self, user: User, course: Course) -> Assignment:
        """Opening a course you were not assigned enrols you (self-chosen learning)."""
        assignment = (
            await self.session.scalars(select(Assignment).where(Assignment.user_id == user.id, Assignment.course_id == course.id))
        ).first()
        if assignment is None:
            assignment = Assignment(user_id=user.id, course_id=course.id, source="self", assigned_by_id=user.id)
            self.session.add(assignment)
            await self.session.flush()
        if assignment.status == AssignmentStatus.NOT_STARTED.value:
            assignment.status = AssignmentStatus.IN_PROGRESS.value
            assignment.started_at = utcnow()
        return assignment

    async def start(self, course_id: UUID, user: User) -> Assignment:
        course = await self._course(course_id)
        return await self._assignment(user, course)

    async def complete_lesson(self, lesson_id: UUID, user: User, *, score: int | None = None) -> LessonCompleteOut:
        lesson, course = await self._lesson(lesson_id)
        assignment = await self._assignment(user, course)
        progress = (
            await self.session.scalars(
                select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson.id)
            )
        ).first()
        if progress is None:
            self.session.add(
                LessonProgress(
                    user_id=user.id, lesson_id=lesson.id, course_id=course.id, score=score, minutes=lesson.duration_minutes
                )
            )
            await self.session.flush()
            await event_bus.publish(
                self.session,
                DomainEvent(
                    "lesson.completed",
                    {"user_id": user.id, "lesson_id": lesson.id, "course_id": course.id, "minutes": lesson.duration_minutes},
                ),
            )
        return await self._refresh(course, assignment, user)

    async def check_simulation(self, lesson_id: UUID, order: list[str], user: User) -> SimulationResultOut:
        lesson, _ = await self._lesson(lesson_id)
        if lesson.kind != LessonKind.SIMULATION.value or not lesson.scenario:
            raise ValidationFailedError("This lesson is not a simulation.")
        correct_order: list[str] = lesson.scenario.get("correct_order", [])
        first_wrong = next((i for i, (a, b) in enumerate(zip(order, correct_order, strict=False)) if a != b), None)
        if first_wrong is None and len(order) != len(correct_order):
            first_wrong = min(len(order), len(correct_order))
        correct = first_wrong is None
        points = (await SettingsService(self.session).get("gamification.points"))["lesson"] * 2 if correct else 0
        if correct:
            await self.complete_lesson(lesson_id, user, score=100)
        labels = {s["id"]: s["label"] for s in lesson.scenario.get("steps", [])}
        message = (
            "Right order!"
            if correct
            else f"Not quite. Step {first_wrong + 1} should be {labels.get(correct_order[first_wrong], 'different')}."
            if first_wrong is not None and first_wrong < len(correct_order)
            else "Not quite. Try again."
        )
        return SimulationResultOut(correct=correct, first_wrong_step=first_wrong, message=message, points=points)

    async def submit_quiz(self, course_id: UUID, answers: dict[UUID, int], user: User) -> QuizResultOut:
        course = await self._course(course_id)
        questions = (
            await self.session.scalars(
                select(CourseQuestion).where(CourseQuestion.course_id == course.id).order_by(CourseQuestion.position)
            )
        ).all()
        if not questions:
            raise ValidationFailedError("This course has no quiz.")
        results = [
            QuizQuestionResult(
                question_id=q.id, correct=answers.get(q.id) == q.answer_index, right_index=q.answer_index, reason=q.reason
            )
            for q in questions
        ]
        score = round(sum(r.correct for r in results) / len(results) * 100)
        pass_mark = course.pass_mark or DEFAULT_PASS_MARK
        passed = score >= pass_mark
        assignment = await self._assignment(user, course)
        assignment.quiz_score = max(score, assignment.quiz_score or 0)
        refreshed = await self._refresh(course, assignment, user)
        return QuizResultOut(
            score=score,
            passed=passed,
            pass_mark=course.pass_mark,
            results=results,
            course_completed=refreshed.course_completed,
        )

    async def _refresh(self, course: Course, assignment: Assignment, user: User) -> LessonCompleteOut:
        lessons = (
            await self.session.scalars(select(Lesson).where(Lesson.course_id == course.id).order_by(Lesson.position))
        ).all()
        done = set(
            (
                await self.session.scalars(
                    select(LessonProgress.lesson_id).where(
                        LessonProgress.user_id == user.id, LessonProgress.course_id == course.id
                    )
                )
            ).all()
        )
        has_quiz = bool(
            (await self.session.scalars(select(CourseQuestion.id).where(CourseQuestion.course_id == course.id).limit(1))).first()
        )
        total_steps = len(lessons) + (1 if has_quiz else 0)
        pass_mark = course.pass_mark or DEFAULT_PASS_MARK
        quiz_ok = not has_quiz or (assignment.quiz_score is not None and assignment.quiz_score >= pass_mark)
        finished_steps = len(done) + (1 if has_quiz and quiz_ok else 0)
        assignment.progress_pct = round(finished_steps / total_steps * 100) if total_steps else 100
        # A course ending in a proctored test completes when that test passes (assessments module).
        all_done = len(done) >= len(lessons) and quiz_ok and course.final_test_id is None
        newly_completed = all_done and assignment.status != AssignmentStatus.COMPLETED.value
        if newly_completed:
            await self.mark_completed(assignment, course, score=assignment.quiz_score)
        await self.session.flush()
        next_lesson = next((lsn.id for lsn in lessons if lsn.id not in done), None)
        return LessonCompleteOut(
            progress_pct=assignment.progress_pct,
            course_completed=assignment.status == AssignmentStatus.COMPLETED.value,
            next_lesson_id=next_lesson,
            quiz_pending=has_quiz and not quiz_ok and next_lesson is None,
        )

    async def mark_completed(self, assignment: Assignment, course: Course, *, score: int | None) -> None:
        assignment.status = AssignmentStatus.COMPLETED.value
        assignment.progress_pct = 100
        assignment.completed_at = utcnow()
        payload = {"user_id": assignment.user_id, "course_id": course.id, "assignment_id": assignment.id, "score": score}
        await event_bus.publish(self.session, DomainEvent("course.completed", payload))
        if course.kind == CourseKind.CERTIFICATION.value:
            await event_bus.publish(self.session, DomainEvent("certification.passed", payload))
