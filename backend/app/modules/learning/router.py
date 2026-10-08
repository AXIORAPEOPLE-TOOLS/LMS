from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import ValidationError

from app.core.deps import AdminUser, CurrentUser, SessionDep, require_roles
from app.core.errors import ValidationFailedError
from app.modules.identity.models import User
from app.modules.learning.assignment_service import AssignmentService
from app.modules.learning.bulk import BulkActionService
from app.modules.learning.course_service import MAX_SOURCE_BYTES, CourseService
from app.modules.learning.player_service import PlayerService
from app.modules.learning.schemas import (
    AssignIn,
    AssignmentOut,
    AssignPreviewOut,
    BulkResultOut,
    ContentReplace,
    CourseAdminDetailOut,
    CourseDetailOut,
    CourseIn,
    CourseSummaryOut,
    CourseUpdate,
    DraftOptions,
    InvitationPreviewOut,
    LessonCompleteOut,
    QuestionOut,
    QuizResultOut,
    QuizSubmitIn,
    ReviewDecisionIn,
    RsvpIn,
    SessionIn,
    SessionOut,
    SimulationAttemptIn,
    SimulationResultOut,
    SubmitForReviewIn,
    UndoOut,
)
from app.modules.learning.session_service import SessionService

router = APIRouter(tags=["learning"])
ExpertUser = Annotated[User, Depends(require_roles("expert", "admin"))]


# ---- catalogue & taking courses (learner) ----------------------------------------
@router.get("/courses", response_model=list[CourseSummaryOut])
async def catalogue(session: SessionDep, _: CurrentUser, q: str | None = None, skill_id: UUID | None = None) -> object:
    return await CourseService(session).catalogue(query=q, skill_id=skill_id)


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
async def course_detail(course_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await CourseService(session).detail(course_id, user)


@router.get("/courses/{course_id}/quiz", response_model=list[QuestionOut])
async def course_quiz(course_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    """Quiz questions for learners: never includes the answers."""
    service = CourseService(session)
    await service.detail(course_id, user)  # same visibility rules as the course
    return await service.questions(course_id)


@router.post("/courses/{course_id}/start", status_code=204)
async def start_course(course_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await PlayerService(session).start(course_id, user)


@router.post("/lessons/{lesson_id}/complete", response_model=LessonCompleteOut)
async def complete_lesson(lesson_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await PlayerService(session).complete_lesson(lesson_id, user)


@router.post("/lessons/{lesson_id}/simulation", response_model=SimulationResultOut)
async def try_simulation(lesson_id: UUID, data: SimulationAttemptIn, session: SessionDep, user: CurrentUser) -> object:
    return await PlayerService(session).check_simulation(lesson_id, data.order, user)


@router.post("/courses/{course_id}/quiz", response_model=QuizResultOut)
async def submit_quiz(course_id: UUID, data: QuizSubmitIn, session: SessionDep, user: CurrentUser) -> object:
    return await PlayerService(session).submit_quiz(course_id, data.answers, user)


@router.get("/me/assignments", response_model=list[AssignmentOut])
async def my_assignments(session: SessionDep, user: CurrentUser, open_only: bool = False) -> object:
    return await AssignmentService(session).for_user(user.id, include_completed=not open_only)


# ---- course admin & builder --------------------------------------------------------
@router.get("/admin/courses", response_model=list[CourseSummaryOut])
async def admin_courses(session: SessionDep, _: ExpertUser, q: str | None = None) -> object:
    return await CourseService(session).catalogue(query=q, include_unpublished=True)


@router.get("/admin/courses/{course_id}", response_model=CourseAdminDetailOut)
async def admin_course_detail(course_id: UUID, session: SessionDep, user: ExpertUser) -> object:
    return await CourseService(session).detail(course_id, user, admin=True)


@router.post("/admin/courses", response_model=CourseSummaryOut, status_code=201)
async def create_course(data: CourseIn, session: SessionDep, admin: AdminUser) -> object:
    course = await CourseService(session).create(data, admin)
    return CourseSummaryOut.model_validate(course)


@router.patch("/admin/courses/{course_id}", response_model=CourseSummaryOut)
async def update_course(course_id: UUID, data: CourseUpdate, session: SessionDep, admin: AdminUser) -> object:
    return CourseSummaryOut.model_validate(await CourseService(session).update(course_id, data, admin))


@router.put("/admin/courses/{course_id}/content", status_code=204)
async def replace_content(course_id: UUID, data: ContentReplace, session: SessionDep, admin: AdminUser) -> None:
    await CourseService(session).replace_content(course_id, data, admin)


@router.post("/admin/courses/drafts", response_model=CourseSummaryOut, status_code=202)
async def draft_from_document(
    file: UploadFile, session: SessionDep, admin: AdminUser, options: Annotated[str, Form()] = "{}"
) -> object:
    """Step 1 of the course builder: upload an SOP, the draft is prepared in the background."""
    try:
        parsed = DraftOptions.model_validate_json(options)
    except ValidationError as exc:
        raise ValidationFailedError("Please check the course options.") from exc
    content = await file.read(MAX_SOURCE_BYTES + 1)
    course = await CourseService(session).start_draft(file.filename or "source.pdf", content, parsed, admin)
    return CourseSummaryOut.model_validate(course)


@router.post("/admin/courses/{course_id}/submit", status_code=204)
async def submit_for_review(course_id: UUID, data: SubmitForReviewIn, session: SessionDep, admin: AdminUser) -> None:
    await CourseService(session).submit_for_review(course_id, data.approver_id, admin)


@router.post("/admin/courses/{course_id}/review", status_code=204)
async def review_course(course_id: UUID, data: ReviewDecisionIn, session: SessionDep, expert: ExpertUser) -> None:
    await CourseService(session).review(course_id, data.approve, data.note, expert)


@router.post("/admin/courses/{course_id}/archive", status_code=204)
async def archive_course(course_id: UUID, session: SessionDep, admin: AdminUser) -> None:
    await CourseService(session).archive(course_id, admin)


# ---- assignments -------------------------------------------------------------------
@router.post("/admin/assignments/preview", response_model=AssignPreviewOut)
async def preview_assignment(data: AssignIn, session: SessionDep, _: AdminUser) -> object:
    return await AssignmentService(session).preview(data)


@router.post("/admin/assignments", response_model=BulkResultOut, status_code=201)
async def assign(data: AssignIn, session: SessionDep, admin: AdminUser) -> object:
    return await AssignmentService(session).assign(data, admin)


@router.post("/admin/bulk/{bulk_id}/undo", response_model=UndoOut)
async def undo_bulk(bulk_id: UUID, session: SessionDep, admin: AdminUser) -> UndoOut:
    return UndoOut(undone=await BulkActionService(session).undo(bulk_id, admin))


# ---- live sessions -------------------------------------------------------------------
@router.get("/me/sessions", response_model=list[SessionOut])
async def my_sessions(session: SessionDep, user: CurrentUser) -> list[SessionOut]:
    service = SessionService(session)
    return [await service.to_out(s, user) for s in await service.for_user(user)]


@router.post("/sessions/{session_id}/rsvp", response_model=SessionOut)
async def rsvp(session_id: UUID, data: RsvpIn, session: SessionDep, user: CurrentUser) -> SessionOut:
    service = SessionService(session)
    await service.respond(session_id, user, data.accept)
    return await service.to_out(await service.get(session_id), user)


@router.get("/admin/sessions", response_model=list[SessionOut])
async def admin_sessions(session: SessionDep, _: AdminUser, upcoming_only: bool = True) -> list[SessionOut]:
    service = SessionService(session)
    return [await service.to_out(s) for s in await service.list_all(upcoming_only=upcoming_only)]


@router.post("/admin/sessions", response_model=SessionOut, status_code=201)
async def create_session(data: SessionIn, session: SessionDep, admin: AdminUser) -> SessionOut:
    service = SessionService(session)
    return await service.to_out(await service.create(data, admin))


@router.get("/admin/sessions/{session_id}/preview", response_model=InvitationPreviewOut)
async def preview_invitations(session_id: UUID, session: SessionDep, _: AdminUser) -> object:
    return await SessionService(session).preview(session_id)


@router.post("/admin/sessions/{session_id}/send", response_model=BulkResultOut)
async def send_invitations(session_id: UUID, session: SessionDep, admin: AdminUser) -> object:
    return await SessionService(session).send_invitations(session_id, admin)
