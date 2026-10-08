"""Courses: catalogue (L-05), course admin, and the course builder (A-05)."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.queue import Queues, defer_job
from app.modules.ai.provider import SourcePage
from app.modules.ai.service import extract_pages, get_assistant
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.models import (
    Assignment,
    Course,
    CourseKind,
    CourseQuestion,
    CourseStatus,
    Lesson,
    LessonKind,
    LessonProgress,
    SourceDocument,
)
from app.modules.learning.schemas import (
    ContentReplace,
    CourseAdminDetailOut,
    CourseDetailOut,
    CourseIn,
    CourseSummaryOut,
    CourseUpdate,
    DraftOptions,
    LessonOut,
    MyProgressOut,
    QuestionAdminOut,
)
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.skills.models import Skill
from app.shared.clock import utcnow

MAX_SOURCE_BYTES = 25 * 1024 * 1024


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # ---- reads -----------------------------------------------------------------
    async def get(self, course_id: UUID) -> Course:
        course = await self.session.get(Course, course_id)
        if course is None:
            raise NotFoundError("We could not find that course.")
        return course

    async def lessons(self, course_id: UUID) -> Sequence[Lesson]:
        stmt = select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.position)
        return (await self.session.scalars(stmt)).all()

    async def questions(self, course_id: UUID) -> Sequence[CourseQuestion]:
        stmt = select(CourseQuestion).where(CourseQuestion.course_id == course_id).order_by(CourseQuestion.position)
        return (await self.session.scalars(stmt)).all()

    async def catalogue(
        self, *, query: str | None = None, skill_id: UUID | None = None, include_unpublished: bool = False
    ) -> list[CourseSummaryOut]:
        stmt = select(Course).order_by(Course.title)
        if not include_unpublished:
            stmt = stmt.where(Course.status == CourseStatus.PUBLISHED.value)
        if query:
            stmt = stmt.where(Course.title.ilike(f"%{query}%"))
        if skill_id:
            stmt = stmt.where(Course.skill_id == skill_id)
        courses = (await self.session.scalars(stmt)).all()
        return await self._summaries(courses)

    async def _summaries(self, courses: Sequence[Course]) -> list[CourseSummaryOut]:
        if not courses:
            return []
        ids = [c.id for c in courses]
        counts = dict(
            (
                await self.session.execute(
                    select(Lesson.course_id, func.count()).where(Lesson.course_id.in_(ids)).group_by(Lesson.course_id)
                )
            ).all()
        )
        skill_ids = {c.skill_id for c in courses if c.skill_id}
        skills = {s.id: s.name for s in (await self.session.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()}
        return [
            CourseSummaryOut.model_validate(c).model_copy(
                update={"lesson_count": counts.get(c.id, 0), "skill_name": skills.get(c.skill_id) if c.skill_id else None}
            )
            for c in courses
        ]

    async def detail(self, course_id: UUID, viewer: User, *, admin: bool = False) -> CourseDetailOut:
        course = await self.get(course_id)
        if course.status != CourseStatus.PUBLISHED.value and not (admin or self._can_review(course, viewer)):
            raise NotFoundError("We could not find that course.")
        lessons = await self.lessons(course.id)
        questions = await self.questions(course.id)
        done = set(
            (
                await self.session.scalars(
                    select(LessonProgress.lesson_id).where(
                        LessonProgress.user_id == viewer.id, LessonProgress.course_id == course.id
                    )
                )
            ).all()
        )
        lesson_out = [LessonOut.model_validate(lsn).model_copy(update={"completed": lsn.id in done}) for lsn in lessons]
        summary = (await self._summaries([course]))[0]
        source = await self.session.get(SourceDocument, course.source_document_id) if course.source_document_id else None
        assignment = (
            await self.session.scalars(
                select(Assignment).where(Assignment.user_id == viewer.id, Assignment.course_id == course.id)
            )
        ).first()
        next_lesson = next((lsn.id for lsn in lessons if lsn.id not in done), None)
        progress = MyProgressOut(
            assignment_id=assignment.id if assignment else None,
            status=assignment.status if assignment else "not_started",
            progress_pct=assignment.progress_pct if assignment else 0,
            due_on=assignment.due_on if assignment else None,
            quiz_score=assignment.quiz_score if assignment else None,
            completed_lessons=len(done),
            next_lesson_id=next_lesson,
        )
        base = CourseDetailOut(
            **summary.model_dump(),
            lessons=lesson_out,
            question_count=len(questions),
            my_progress=progress,
            source_filename=source.filename if source else None,
            approver_id=course.approver_id,
            review_note=course.review_note,
            final_test_id=course.final_test_id,
        )
        if admin or self._can_review(course, viewer):
            return CourseAdminDetailOut(**base.model_dump(), questions=[QuestionAdminOut.model_validate(q) for q in questions])
        return base

    @staticmethod
    def _can_review(course: Course, viewer: User) -> bool:
        return course.approver_id == viewer.id or viewer.has_role("admin")

    # ---- admin writes ----------------------------------------------------------
    async def create(self, data: CourseIn, actor: User) -> Course:
        course = Course(**data.model_dump(), created_by_id=actor.id, status=CourseStatus.DRAFT.value)
        self.session.add(course)
        await self.session.flush()
        self.audit.record("course.created", "course", course.id, actor_id=actor.id, title=course.title)
        return course

    async def update(self, course_id: UUID, data: CourseUpdate, actor: User) -> Course:
        course = await self.get(course_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(course, key, value)
        if course.status == CourseStatus.PUBLISHED.value:
            # Changing a live course sends it back to the expert (humans decide).
            course.status = CourseStatus.IN_REVIEW.value if course.approver_id else CourseStatus.DRAFT.value
        await self.session.flush()
        self.audit.record("course.updated", "course", course.id, actor_id=actor.id)
        return course

    async def replace_content(self, course_id: UUID, data: ContentReplace, actor: User) -> Course:
        course = await self.get(course_id)
        if course.status == CourseStatus.DRAFTING.value:
            raise ConflictError("The draft is still being prepared. Please wait a moment.")
        for old in [*await self.lessons(course.id), *await self.questions(course.id)]:
            await self.session.delete(old)
        await self.session.flush()
        for i, lesson in enumerate(data.lessons, start=1):
            self.session.add(Lesson(course_id=course.id, position=i, **lesson.model_dump()))
        for i, question in enumerate(data.questions, start=1):
            self.session.add(CourseQuestion(course_id=course.id, position=i, **question.model_dump()))
        course.has_simulation = any(lsn.kind == LessonKind.SIMULATION.value for lsn in data.lessons)
        course.has_video = any(lsn.kind == LessonKind.VIDEO.value for lsn in data.lessons)
        course.duration_minutes = max(5, sum(lsn.duration_minutes for lsn in data.lessons))
        if course.status == CourseStatus.PUBLISHED.value:
            course.status = CourseStatus.IN_REVIEW.value
        await self.session.flush()
        self.audit.record("course.content_changed", "course", course.id, actor_id=actor.id, lessons=len(data.lessons))
        return course

    async def submit_for_review(self, course_id: UUID, approver_id: UUID, actor: User) -> Course:
        course = await self.get(course_id)
        if course.status not in {CourseStatus.DRAFT.value, CourseStatus.IN_REVIEW.value}:
            raise ConflictError("Only drafts can be sent for approval.")
        approver = await self.session.get(User, approver_id)
        if approver is None or not approver.has_role("expert", "admin"):
            raise ValidationFailedError("Choose a subject expert to approve this course.")
        if not await self.lessons(course.id):
            raise ValidationFailedError("Add at least one lesson before sending for approval.")
        course.status = CourseStatus.IN_REVIEW.value
        course.approver_id = approver_id
        await NotificationService(self.session).notify(
            approver_id,
            kind=NotificationKind.APPROVAL,
            title=f'Please check the course "{course.title}"',
            body="Nothing is published until you approve it.",
            link=f"/admin/courses/{course.id}",
            related=("course", course.id),
        )
        self.audit.record("course.submitted", "course", course.id, actor_id=actor.id, approver_id=approver_id)
        return course

    async def review(self, course_id: UUID, approve: bool, note: str, reviewer: User) -> Course:
        course = await self.get(course_id)
        if course.status != CourseStatus.IN_REVIEW.value:
            raise ConflictError("This course is not waiting for approval.")
        if course.approver_id != reviewer.id and not reviewer.has_role("admin"):
            raise PermissionDeniedError("Only the chosen expert can approve this course.")
        course.review_note = note or None
        if approve:
            course.status = CourseStatus.PUBLISHED.value
            course.approved_at = utcnow()
        else:
            course.status = CourseStatus.DRAFT.value
        if course.created_by_id and course.created_by_id != reviewer.id:
            await NotificationService(self.session).notify(
                course.created_by_id,
                kind=NotificationKind.APPROVAL,
                title=f'"{course.title}" was {"approved and published" if approve else "sent back with notes"}',
                body=note,
                link=f"/admin/courses/{course.id}",
                related=("course", course.id),
            )
        self.audit.record("course.reviewed", "course", course.id, actor_id=reviewer.id, approved=approve, note=note)
        return course

    async def archive(self, course_id: UUID, actor: User) -> Course:
        course = await self.get(course_id)
        course.status = CourseStatus.ARCHIVED.value
        self.audit.record("course.archived", "course", course.id, actor_id=actor.id)
        return course

    # ---- course builder (A-05) -------------------------------------------------
    async def start_draft(self, filename: str, content: bytes, options: DraftOptions, actor: User) -> Course:
        if len(content) > MAX_SOURCE_BYTES:
            raise ValidationFailedError("The file is larger than 25 MB.")
        pages = extract_pages(filename, content)
        if not any(p.text.strip() for p in pages):
            raise ValidationFailedError("We could not find any text in this file. Is it a scanned image?")
        source = SourceDocument(
            filename=filename,
            size_bytes=len(content),
            pages=[{"page": p.page, "text": p.text} for p in pages],
            uploaded_by_id=actor.id,
        )
        self.session.add(source)
        await self.session.flush()
        skill = await self.session.get(Skill, options.skill_id) if options.skill_id else None
        course = Course(
            title=skill.name if skill else _title_from_filename(filename),
            skill_id=options.skill_id,
            from_level=options.from_level,
            to_level=options.to_level,
            kind=CourseKind.CERTIFICATION.value if options.certification else CourseKind.SELF_PACED.value,
            pass_mark=80 if options.certification else None,
            status=CourseStatus.DRAFTING.value,
            languages=options.languages,
            has_video=options.narrated_video,
            has_simulation=options.simulation,
            source_document_id=source.id,
            created_by_id=actor.id,
        )
        self.session.add(course)
        await self.session.flush()
        defer_job(
            self.session,
            Queues.AUTHORING,
            "courses.draft_from_source",
            {"course_id": course.id, "options": options.model_dump(mode="json")},
        )
        self.audit.record("course.draft_started", "course", course.id, actor_id=actor.id, source=filename)
        return course

    async def build_draft(self, course_id: UUID, options: DraftOptions) -> None:
        """Runs in the worker: turn the source pages into lessons and quiz questions."""
        course = await self.get(course_id)
        if course.status != CourseStatus.DRAFTING.value:
            return
        source = await self.session.get(SourceDocument, course.source_document_id)
        pages = [SourcePage(p["page"], p["text"]) for p in (source.pages if source else [])]
        skill = await self.session.get(Skill, course.skill_id) if course.skill_id else None
        draft = await get_assistant().draft_course(
            pages=pages,
            skill_name=skill.name if skill else course.title,
            include_simulation=options.simulation,
            quiz_size=options.quiz_size,
        )
        page_text = {p.page: p.text for p in pages}
        for position, section in enumerate(draft.sections, start=1):
            is_sim = section.kind == "simulation"
            self.session.add(
                Lesson(
                    course_id=course.id,
                    position=position,
                    title=section.title,
                    kind=LessonKind.SIMULATION.value
                    if is_sim
                    else (LessonKind.VIDEO.value if options.narrated_video else LessonKind.READING.value),
                    summary=section.summary,
                    body=_body_for(section.source_ref, page_text) if not is_sim else section.summary,
                    source_ref=section.source_ref,
                    duration_minutes=5,
                    captions=_captions(section.summary, options.languages) if options.narrated_video and not is_sim else {},
                    scenario=_default_scenario(section.title) if is_sim else None,
                )
            )
        for position, q in enumerate(draft.quiz, start=1):
            self.session.add(
                CourseQuestion(
                    course_id=course.id,
                    position=position,
                    text=q.text,
                    options=q.options,
                    answer_index=q.answer_index,
                    reason=q.reason,
                )
            )
        course.status = CourseStatus.DRAFT.value
        course.duration_minutes = max(10, 5 * len(draft.sections))
        if course.created_by_id:
            await NotificationService(self.session).notify(
                course.created_by_id,
                kind=NotificationKind.SYSTEM,
                title=f'Your draft "{course.title}" is ready to check',
                link=f"/admin/courses/{course.id}",
                related=("course", course.id),
            )


def _title_from_filename(filename: str) -> str:
    import re

    stem = re.sub(r"\.[a-z0-9]+$", "", filename, flags=re.I)
    stem = re.sub(r"[_\-]+|\bv\d+\b", " ", stem, flags=re.I)
    return " ".join(stem.split()).strip().capitalize() or "New course"


def _body_for(source_ref: str, page_text: dict[int, str]) -> str:
    import re

    numbers = [int(n) for n in re.findall(r"\d+", source_ref)]
    if not numbers:
        return ""
    first, last = numbers[0], numbers[-1]
    return "\n\n".join(page_text.get(n, "") for n in range(first, last + 1)).strip()[:6000]


def _captions(text: str, languages: list[str]) -> dict[str, Any]:
    lines = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    timed = [{"at": i * 6, "text": line.rstrip(".") + "."} for i, line in enumerate(lines)]
    # Hindi captions are produced by the translation step; until then the English line is kept.
    return {lang: timed for lang in languages}


def _default_scenario(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "image": None,
        "ar_supported": True,
        "steps": [{"id": f"s{i}", "label": f"Step {i}", "x": 15 + i * 15, "y": 30 + (i % 2) * 25} for i in range(1, 6)],
        "correct_order": [f"s{i}" for i in range(1, 6)],
        "feedback": "Do the steps in the order the procedure gives.",
    }
