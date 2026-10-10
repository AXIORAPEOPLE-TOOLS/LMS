"""Written answers a person must check (LMS.pdf Assessment step 2; golden rule 5: humans decide scores in doubt)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.models import Course, CourseQuestion, CourseQuizAttempt
from app.modules.learning.player_service import PlayerService, score_attempt
from app.modules.learning.schemas import RubricPointIn, WrittenAnswerOut, WrittenMarkIn, WrittenReviewOut
from app.modules.settings.service import SettingsService
from app.shared.clock import utcnow


class WrittenReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _may_review(course: Course, viewer: User) -> bool:
        return viewer.has_role("admin") or course.approver_id == viewer.id

    async def queue(self, viewer: User) -> list[WrittenReviewOut]:
        rows = (
            await self.session.execute(
                select(CourseQuizAttempt, Course, User)
                .join(Course, Course.id == CourseQuizAttempt.course_id)
                .join(User, User.id == CourseQuizAttempt.user_id)
                .where(CourseQuizAttempt.review_status == "pending")
                .order_by(CourseQuizAttempt.submitted_at)
            )
        ).all()
        out = []
        for attempt, course, person in rows:
            if self._may_review(course, viewer):
                out.append(await self._to_out(attempt, course, person))
        return out

    async def _to_out(self, attempt: CourseQuizAttempt, course: Course, person: User) -> WrittenReviewOut:
        questions = await self._questions(course.id)
        pass_mark = course.pass_mark or int(await SettingsService(self.session).get("learning.quiz_pass_mark"))
        answers = []
        for q in questions:
            w = attempt.written.get(str(q.id))
            if q.kind != "written" or w is None:
                continue
            answers.append(
                WrittenAnswerOut(
                    question_id=q.id,
                    question=q.text,
                    model_answer=q.model_answer,
                    rubric=[RubricPointIn(point=r["point"], marks=int(r.get("marks", 1))) for r in q.rubric or []],
                    answer=str(attempt.answers.get(str(q.id), "")),
                    marks=int(w["marks"]),
                    max_marks=int(w["max"]),
                    confidence=float(w["confidence"]),
                    feedback=str(w.get("feedback", "")),
                )
            )
        return WrittenReviewOut(
            attempt_id=attempt.id,
            course_id=course.id,
            course_title=course.title,
            person=person.full_name,
            attempt_no=attempt.attempt_no,
            submitted_at=attempt.submitted_at,
            provisional_score=attempt.score,
            pass_mark=pass_mark,
            answers=answers,
        )

    async def _questions(self, course_id: UUID) -> list[CourseQuestion]:
        stmt = select(CourseQuestion).where(CourseQuestion.course_id == course_id).order_by(CourseQuestion.position)
        return list((await self.session.scalars(stmt)).all())

    async def decide(self, attempt_id: UUID, marks: list[WrittenMarkIn], reviewer: User) -> WrittenReviewOut:
        attempt = await self.session.get(CourseQuizAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("We could not find those answers.")
        course = await self.session.get(Course, attempt.course_id)
        person = await self.session.get(User, attempt.user_id)
        if course is None or person is None:
            raise NotFoundError("We could not find those answers.")
        if not self._may_review(course, reviewer):
            raise PermissionDeniedError("Only the course expert or an admin can check these answers.")
        if attempt.review_status != "pending":
            raise ConflictError("These answers were already checked.")
        written = {k: dict(v) for k, v in attempt.written.items()}
        for mark in marks:
            entry = written.get(str(mark.question_id))
            if entry is None:
                raise ValidationFailedError("That question is not a written answer in this attempt.")
            if mark.marks > int(entry["max"]):
                raise ValidationFailedError(f"Marks cannot be more than {entry['max']} for a question.")
            before = int(entry["marks"])
            entry.update(marks=mark.marks, confidence=1.0, checked_by_person=True, before=before)
            if mark.feedback.strip():
                entry["feedback"] = mark.feedback.strip()
        questions = await self._questions(course.id)
        score, _ = score_attempt(questions, attempt.answers, written)
        pass_mark = course.pass_mark or int(await SettingsService(self.session).get("learning.quiz_pass_mark"))
        changed = attempt.score != score
        attempt.written = written
        attempt.score = score
        attempt.passed = score >= pass_mark
        attempt.review_status = "done"
        attempt.reviewer_id = reviewer.id
        attempt.reviewed_at = utcnow()
        await self.session.flush()
        await PlayerService(self.session).finish_review(attempt, course, person)
        AuditService(self.session).record(
            "quiz.written_checked",
            "course_quiz_attempt",
            attempt.id,
            actor_id=reviewer.id,
            score=score,
            passed=attempt.passed,
            changed=changed,
        )
        return await self._to_out(attempt, course, person)
