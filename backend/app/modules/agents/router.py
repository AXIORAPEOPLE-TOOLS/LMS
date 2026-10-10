"""Admin helpers (LMS.pdf "AI Agent" steps): build a course, write a quick check, assign from a request."""

from uuid import UUID

from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.agents.schemas import (
    AssignConfirmIn,
    AssignRequestIn,
    CourseBriefIn,
    QuizBriefIn,
    RunOut,
    RunSummaryOut,
)
from app.modules.agents.service import AgentService

router = APIRouter(prefix="/admin/helpers", tags=["helpers"])


@router.get("/runs", response_model=list[RunSummaryOut])
async def list_runs(session: SessionDep, _: AdminUser, limit: int = 30) -> object:
    return await AgentService(session).list_runs(limit=min(max(limit, 1), 100))


@router.get("/runs/{run_id}", response_model=RunOut)
async def run_detail(run_id: UUID, session: SessionDep, _: AdminUser) -> object:
    return await AgentService(session).detail(run_id)


@router.post("/course", response_model=RunOut, status_code=202)
async def build_course(data: CourseBriefIn, session: SessionDep, admin: AdminUser) -> object:
    """Starts in the background; poll the run to watch each step."""
    service = AgentService(session)
    run = await service.start_course(data, admin)
    return await service.detail(run.id)


@router.post("/quiz", response_model=RunOut, status_code=202)
async def write_quiz(data: QuizBriefIn, session: SessionDep, admin: AdminUser) -> object:
    service = AgentService(session)
    run = await service.start_quiz(data, admin)
    return await service.detail(run.id)


@router.post("/assign", response_model=RunOut, status_code=201)
async def plan_assignment(data: AssignRequestIn, session: SessionDep, admin: AdminUser) -> object:
    """Reads the request and shows who would get it. Nothing is sent until it is confirmed."""
    service = AgentService(session)
    run = await service.plan_assign(data, admin)
    return await service.detail(run.id)


@router.post("/runs/{run_id}/confirm", response_model=RunOut)
async def confirm_assignment(run_id: UUID, data: AssignConfirmIn, session: SessionDep, admin: AdminUser) -> object:
    service = AgentService(session)
    await service.confirm_assign(run_id, data, admin)
    return await service.detail(run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: UUID, session: SessionDep, admin: AdminUser) -> object:
    service = AgentService(session)
    await service.cancel(run_id, admin)
    return await service.detail(run_id)
