from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.deps import AdminUser, CurrentUser, SessionDep, require_roles
from app.modules.assessments.schemas import (
    AnswerIn,
    AppealIn,
    AttemptOut,
    AttemptResultOut,
    BookingOut,
    CampaignIn,
    CampaignPreviewOut,
    DecisionIn,
    InPersonIn,
    MyTestOut,
    ProctorEventIn,
    ReviewCaseOut,
    ReviewQueueItemOut,
    StartAttemptIn,
    TestIn,
    TestOut,
)
from app.modules.assessments.service import AssessmentService
from app.modules.identity.models import User
from app.modules.learning.schemas import BulkResultOut

router = APIRouter(tags=["assessments"])
ReviewerUser = Annotated[User, Depends(require_roles("reviewer", "admin"))]


@router.get("/me/tests", response_model=list[MyTestOut])
async def my_tests(session: SessionDep, user: CurrentUser) -> object:
    return await AssessmentService(session).my_tests(user)


@router.get("/tests/{test_id}", response_model=TestOut)
async def test_intro(test_id: UUID, session: SessionDep, _: CurrentUser) -> object:
    service = AssessmentService(session)
    return await service.test_out(await service.get_test(test_id))


@router.post("/tests/{test_id}/attempts", response_model=AttemptOut, status_code=201)
async def start_attempt(test_id: UUID, data: StartAttemptIn, session: SessionDep, user: CurrentUser) -> object:
    service = AssessmentService(session)
    attempt = await service.start(test_id, user, data.consent)
    return await service.attempt_view(attempt.id, user)


@router.post("/tests/{test_id}/in-person", response_model=BookingOut, status_code=201)
async def book_in_person(test_id: UUID, data: InPersonIn, session: SessionDep, user: CurrentUser) -> object:
    return await AssessmentService(session).book_in_person(test_id, user, data.preferred_dates)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
async def get_attempt(attempt_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await AssessmentService(session).attempt_view(attempt_id, user)


@router.put("/attempts/{attempt_id}/answer", status_code=204)
async def answer(attempt_id: UUID, data: AnswerIn, session: SessionDep, user: CurrentUser) -> None:
    await AssessmentService(session).answer(attempt_id, user, data.question_id, data.option_index)


@router.post("/attempts/{attempt_id}/proctor-events", status_code=204)
async def proctor_event(attempt_id: UUID, data: ProctorEventIn, session: SessionDep, user: CurrentUser) -> None:
    await AssessmentService(session).record_proctor_event(attempt_id, user, data.kind, data.at_seconds, data.image_base64)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResultOut)
async def submit(attempt_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await AssessmentService(session).submit(attempt_id, user)


@router.get("/attempts/{attempt_id}/result", response_model=AttemptResultOut)
async def result(attempt_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await AssessmentService(session).result(attempt_id, user)


@router.post("/attempts/{attempt_id}/appeal", status_code=204)
async def appeal(attempt_id: UUID, data: AppealIn, session: SessionDep, user: CurrentUser) -> None:
    await AssessmentService(session).appeal(attempt_id, user, data.note)


# ---- admin -----------------------------------------------------------------------
@router.get("/admin/tests", response_model=list[TestOut])
async def list_tests(session: SessionDep, _: AdminUser) -> object:
    return await AssessmentService(session).list_tests()


@router.post("/admin/tests", response_model=TestOut, status_code=201)
async def create_test(data: TestIn, session: SessionDep, admin: AdminUser) -> object:
    service = AssessmentService(session)
    return await service.test_out(await service.create_test(data, admin))


@router.post("/admin/tests/campaign/preview", response_model=CampaignPreviewOut)
async def campaign_preview(data: CampaignIn, session: SessionDep, _: AdminUser) -> object:
    return await AssessmentService(session).campaign_preview(data)


@router.post("/admin/tests/campaign", response_model=BulkResultOut, status_code=201)
async def send_campaign(data: CampaignIn, session: SessionDep, admin: AdminUser) -> object:
    return await AssessmentService(session).send_campaign(data, admin)


@router.get("/admin/tests/bookings", response_model=list[BookingOut])
async def in_person_bookings(session: SessionDep, _: AdminUser) -> object:
    return await AssessmentService(session).bookings()


# ---- proctoring review (A-09) ---------------------------------------------------------
@router.get("/proctoring/queue", response_model=list[ReviewQueueItemOut])
async def review_queue(session: SessionDep, _: ReviewerUser) -> object:
    return await AssessmentService(session).review_queue()


@router.get("/proctoring/attempts/{attempt_id}", response_model=ReviewCaseOut)
async def review_case(attempt_id: UUID, session: SessionDep, reviewer: ReviewerUser) -> object:
    return await AssessmentService(session).review_case(attempt_id, reviewer)


@router.get("/proctoring/events/{event_id}/image", response_class=FileResponse)
async def snapshot(event_id: UUID, session: SessionDep, reviewer: ReviewerUser) -> FileResponse:
    path = await AssessmentService(session).snapshot_path(event_id, reviewer)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/proctoring/attempts/{attempt_id}/decision", status_code=204)
async def decide(attempt_id: UUID, data: DecisionIn, session: SessionDep, reviewer: ReviewerUser) -> None:
    await AssessmentService(session).decide(attempt_id, data.decision, data.note, reviewer)
