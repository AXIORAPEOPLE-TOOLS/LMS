"""Quiz writer (LMS.pdf Quiz / Assessment Creation): draft ~10 questions with answers, set pass mark and time limit,
check them, save them to the course and try it once. A subject expert approves before learners see it."""

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailedError
from app.modules.agents.checks import check_questions, difficulty_mix, trial_run
from app.modules.ai.provider import DraftQuestion, LessonText
from app.modules.ai.service import get_assistant
from app.modules.learning.models import Course, CourseQuestion, CourseStatus, Lesson, LessonKind
from app.modules.settings.service import SettingsService


@dataclass
class QuizPlan:
    choice_count: int
    written_count: int
    pass_mark: int
    time_limit: int


async def course_lessons(session: AsyncSession, course_id: object) -> list[Lesson]:
    stmt = select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.position)
    return list((await session.scalars(stmt)).all())


def lesson_texts(lessons: list[Lesson]) -> list[LessonText]:
    return [
        LessonText(lsn.title, f"{lsn.summary}\n{lsn.body}".strip())
        for lsn in lessons
        if lsn.kind != LessonKind.SIMULATION.value and (lsn.body or lsn.summary).strip()
    ]


async def plan_quiz(
    session: AsyncSession,
    course: Course,
    *,
    choice_count: int | None = None,
    written_count: int | None = None,
    pass_mark: int | None = None,
    time_limit: int | None = None,
) -> QuizPlan:
    settings = SettingsService(session)
    size = int(await settings.get("learning.quiz_default_size"))
    written = int(await settings.get("learning.quiz_written_count")) if written_count is None else written_count
    choice = max(0, size - written) if choice_count is None else choice_count
    if choice + written == 0:
        raise ValidationFailedError("Ask for at least one question.")
    mark = pass_mark or course.pass_mark or int(await settings.get("learning.quiz_pass_mark"))
    per_question = float(await settings.get("learning.quiz_minutes_per_question"))
    # Written answers take longer: count each as two questions for the time limit.
    minutes = time_limit or max(5, math.ceil((choice + 2 * written) * per_question))
    return QuizPlan(choice, written, mark, minutes)


async def draft(course: Course, lessons: list[Lesson], plan: QuizPlan) -> list[DraftQuestion]:
    texts = lesson_texts(lessons)
    if not texts:
        raise ValidationFailedError("The course has no lesson text to write questions from.")
    goals = [lsn.summary for lsn in lessons if lsn.summary][:6]
    return await get_assistant().draft_quiz(
        title=course.title, goals=goals, lessons=texts, choice_count=plan.choice_count, written_count=plan.written_count
    )


async def save(session: AsyncSession, course: Course, questions: list[DraftQuestion], plan: QuizPlan) -> list[CourseQuestion]:
    old = (await session.scalars(select(CourseQuestion).where(CourseQuestion.course_id == course.id))).all()
    for q in old:
        await session.delete(q)
    await session.flush()
    saved = []
    for position, q in enumerate(questions, start=1):
        row = CourseQuestion(
            course_id=course.id,
            position=position,
            text=q.text,
            options=list(q.options),
            answer_index=q.answer_index,
            reason=q.reason,
            kind=q.kind,
            model_answer=q.model_answer,
            rubric=[{"point": r.point, "marks": r.marks} for r in q.rubric],
        )
        session.add(row)
        saved.append(row)
    course.pass_mark = plan.pass_mark
    course.quiz_time_limit_minutes = plan.time_limit
    if course.status == CourseStatus.PUBLISHED.value:
        # A live course with new questions goes back to the expert (humans decide).
        course.status = CourseStatus.IN_REVIEW.value if course.approver_id else CourseStatus.DRAFT.value
    await session.flush()
    return saved


def describe_check(kept: list[DraftQuestion], removed: list[str]) -> str:
    text = f"Kept {len(kept)}: {difficulty_mix(kept)}."
    if removed:
        reasons = sorted(set(removed))
        text += f" Removed {len(removed)} ({', '.join(reasons)})."
    return text


async def write_for_course(session: AsyncSession, course: Course, plan: QuizPlan) -> tuple[str, str]:
    """All steps in one go (used inside the course builder). Returns (summary, trial detail)."""
    lessons = await course_lessons(session, course.id)
    drafts = await draft(course, lessons, plan)
    result = check_questions(drafts)
    if not result.kept:
        return "No usable questions could be written; add them by hand.", ""
    saved = await save(session, course, result.kept, plan)
    _, trial = trial_run(lessons, saved, plan.pass_mark)
    summary = f"{describe_check(result.kept, result.removed)} Pass mark {plan.pass_mark}, time limit {plan.time_limit} minutes."
    return summary, trial
