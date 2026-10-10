"""Taking a course: lessons, simulations, quiz, completion (L-03)."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.modules.ai.provider import RubricPoint
from app.modules.ai.service import get_assistant
from app.modules.identity.models import User
from app.modules.learning.models import (
    Assignment,
    AssignmentStatus,
    Course,
    CourseKind,
    CourseQuestion,
    CourseQuizAttempt,
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

    async def submit_quiz(self, course_id: UUID, answers: dict[UUID, int | str], user: User) -> QuizResultOut:
        course = await self._course(course_id)
        questions = await self._questions(course.id)
        if not questions:
            raise ValidationFailedError("This course has no quiz.")
        settings = SettingsService(self.session)
        max_attempts = int(await settings.get("learning.quiz_max_attempts"))
        pass_mark = await self._pass_mark(course)
        assignment = await self._assignment(user, course)
        if await self._pending_review(assignment.id):
            raise ConflictError("Your last answers are still being checked. You will get the result soon.")
        already_passed = assignment.quiz_score is not None and assignment.quiz_score >= pass_mark
        if max_attempts and assignment.quiz_attempts >= max_attempts and not already_passed:
            raise ConflictError(f"You have used all {max_attempts} tries for this quick check. Ask your manager to reopen it.")
        written: dict[str, Any] = {}
        for q in questions:
            if q.kind == "written":
                text = str(answers.get(q.id) or "")
                result = await get_assistant().score_written(
                    question=q.text, model_answer=q.model_answer, rubric=rubric_of(q), answer=text
                )
                written[str(q.id)] = {
                    "marks": result.marks,
                    "max": result.max_marks,
                    "confidence": result.confidence,
                    "feedback": result.feedback,
                    "points_met": result.points_met,
                }
        stored = {str(k): v for k, v in answers.items()}
        score, correct = score_attempt(questions, stored, written)
        # Golden rule 5: when the written scoring is unsure, a person decides before the result counts.
        review_below = float(await settings.get("learning.written_review_below"))
        under_review = any(w["confidence"] < review_below for w in written.values())
        passed = score >= pass_mark
        assignment.quiz_attempts += 1
        attempt = CourseQuizAttempt(
            user_id=user.id,
            course_id=course.id,
            assignment_id=assignment.id,
            attempt_no=assignment.quiz_attempts,
            answers=stored,
            score=score,
            passed=passed,
            written=written,
            review_status="pending" if under_review else "none",
        )
        self.session.add(attempt)
        await self.session.flush()
        left = max(0, max_attempts - assignment.quiz_attempts) if max_attempts else None
        if under_review:
            await self._ask_for_review(course, user, attempt)
            return QuizResultOut(
                score=score,
                passed=False,
                pass_mark=pass_mark,
                correct_count=sum(correct),
                total=len(questions),
                results=[QuizQuestionResult(question_id=q.id, correct=ok) for q, ok in zip(questions, correct, strict=True)],
                course_completed=False,
                attempts_used=assignment.quiz_attempts,
                attempts_left=left,
                can_retake=False,
                under_review=True,
            )
        assignment.quiz_score = max(score, assignment.quiz_score or 0)
        refreshed = await self._refresh(course, assignment, user)
        await self._send_result(user, course, score, pass_mark, passed, left)
        return QuizResultOut(
            score=score,
            passed=passed,
            pass_mark=pass_mark,
            correct_count=sum(correct),
            total=len(questions),
            results=question_results(questions, correct, written, show_answers=passed),
            course_completed=refreshed.course_completed,
            attempts_used=assignment.quiz_attempts,
            attempts_left=left,
            can_retake=not passed and (left is None or left > 0),
        )

    async def _questions(self, course_id: UUID) -> list[CourseQuestion]:
        stmt = select(CourseQuestion).where(CourseQuestion.course_id == course_id).order_by(CourseQuestion.position)
        return list((await self.session.scalars(stmt)).all())

    async def _pending_review(self, assignment_id: UUID) -> bool:
        stmt = select(CourseQuizAttempt.id).where(
            CourseQuizAttempt.assignment_id == assignment_id, CourseQuizAttempt.review_status == "pending"
        )
        return (await self.session.scalars(stmt.limit(1))).first() is not None

    async def _ask_for_review(self, course: Course, user: User, attempt: CourseQuizAttempt) -> None:
        from app.modules.notifications.models import NotificationKind
        from app.modules.notifications.service import NotificationService

        notifications = NotificationService(self.session)
        await notifications.notify(
            user.id,
            kind=NotificationKind.SYSTEM,
            title=f"Your answers for {course.title} are being checked",
            body="A person is checking your written answers. You will get your result soon.",
            link=f"/learn/courses/{course.id}",
            related=("course", course.id),
            automatic=True,
        )
        reviewers = [course.approver_id] if course.approver_id else await admin_ids(self.session)
        for reviewer_id in reviewers:
            await notifications.notify(
                reviewer_id,
                kind=NotificationKind.APPROVAL,
                title=f"Written answers to check: {course.title}",
                body=f"{user.full_name}, try {attempt.attempt_no}. The score is held until you confirm it.",
                link="/admin/answers",
                related=("course", course.id),
            )

    async def _send_result(self, user: User, course: Course, score: int, pass_mark: int, passed: bool, left: int | None) -> None:
        """Result and feedback to the employee (LMS.pdf: Assessment / Evaluation, step 4)."""
        from app.modules.notifications.models import NotificationKind
        from app.modules.notifications.service import NotificationService

        if passed:
            body = f"You scored {score} out of 100 (pass mark {pass_mark}). Well done."
        elif left == 0:
            body = f"You scored {score} out of 100 (pass mark {pass_mark}). No tries left; your manager can reopen it."
        else:
            tries = "" if left is None else f" You have {left} {'try' if left == 1 else 'tries'} left."
            body = f"You scored {score} out of 100 (pass mark {pass_mark}). Go over the lessons and try again.{tries}"
        await NotificationService(self.session).notify(
            user.id,
            kind=NotificationKind.SYSTEM,
            title=f"{'Passed' if passed else 'Not passed yet'}: {course.title}",
            body=body,
            link=f"/learn/courses/{course.id}",
            related=("course", course.id),
            automatic=True,
        )

    async def my_attempts(self, course_id: UUID, user: User) -> list[CourseQuizAttempt]:
        return list(
            (
                await self.session.scalars(
                    select(CourseQuizAttempt)
                    .where(CourseQuizAttempt.course_id == course_id, CourseQuizAttempt.user_id == user.id)
                    .order_by(CourseQuizAttempt.attempt_no)
                )
            ).all()
        )

    async def _pass_mark(self, course: Course) -> int:
        return course.pass_mark or int(await SettingsService(self.session).get("learning.quiz_pass_mark"))

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
        pass_mark = await self._pass_mark(course)
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

    async def finish_review(self, attempt: CourseQuizAttempt, course: Course, user: User) -> None:
        """After a person confirms the written marks the result counts (used by WrittenReviewService)."""
        assignment = await self.session.get(Assignment, attempt.assignment_id)
        if assignment is None:
            return
        pass_mark = await self._pass_mark(course)
        assignment.quiz_score = max(attempt.score, assignment.quiz_score or 0)
        await self._refresh(course, assignment, user)
        max_attempts = int(await SettingsService(self.session).get("learning.quiz_max_attempts"))
        left = max(0, max_attempts - assignment.quiz_attempts) if max_attempts else None
        await self._send_result(user, course, attempt.score, pass_mark, attempt.passed, left)

    async def mark_completed(self, assignment: Assignment, course: Course, *, score: int | None) -> None:
        assignment.status = AssignmentStatus.COMPLETED.value
        assignment.progress_pct = 100
        assignment.completed_at = utcnow()
        payload = {"user_id": assignment.user_id, "course_id": course.id, "assignment_id": assignment.id, "score": score}
        await event_bus.publish(self.session, DomainEvent("course.completed", payload))
        if course.kind == CourseKind.CERTIFICATION.value:
            await event_bus.publish(self.session, DomainEvent("certification.passed", payload))


async def admin_ids(session: AsyncSession) -> list[UUID]:
    users = (await session.scalars(select(User).where(User.is_active.is_(True)))).all()
    return [u.id for u in users if u.has_role("admin")]


def rubric_of(question: CourseQuestion) -> list[RubricPoint]:
    return [RubricPoint(str(r.get("point", "")), int(r.get("marks", 1))) for r in question.rubric or []]


def score_attempt(questions: list[CourseQuestion], answers: dict[str, Any], written: dict[str, Any]) -> tuple[int, list[bool]]:
    """Score out of 100: a choice question is worth 1 mark, a written one its rubric marks."""
    got, total, correct = 0, 0, []
    for q in questions:
        if q.kind == "written":
            fallback = {"marks": 0, "max": max(1, sum(int(r.get("marks", 1)) for r in q.rubric or []))}
            w = written.get(str(q.id), fallback)
            got, total = got + int(w["marks"]), total + int(w["max"])
            correct.append(int(w["marks"]) * 2 >= int(w["max"]))
        else:
            ok = answers.get(str(q.id)) == q.answer_index
            got, total = got + int(ok), total + 1
            correct.append(ok)
    return (round(got / total * 100) if total else 0), correct


def question_results(
    questions: list[CourseQuestion], correct: list[bool], written: dict[str, Any], *, show_answers: bool
) -> list[QuizQuestionResult]:
    out = []
    for q, ok in zip(questions, correct, strict=True):
        w = written.get(str(q.id))
        out.append(
            QuizQuestionResult(
                question_id=q.id,
                correct=ok,
                right_index=q.answer_index if show_answers and not w else None,
                reason=(q.reason or None) if show_answers and not w else None,
                marks=w["marks"] if w else None,
                max_marks=w["max"] if w else None,
                feedback=w["feedback"] if w and show_answers else None,
            )
        )
    return out
