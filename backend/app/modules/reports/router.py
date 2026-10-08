from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field

from app.core.deps import ManagerUser, SessionDep
from app.modules.reports.service import FILTER_KEYS, ReportService
from app.modules.scheduler.registry import scheduled_task
from app.shared.schemas import Schema

router = APIRouter(prefix="/reports", tags=["reports"])


class ScheduleIn(Schema):
    frequency: str = Field(pattern="^(weekly|monthly)$")
    format: str = Field(default="xlsx", pattern="^(csv|xlsx|pdf)$")
    filters: dict[str, Any] = {}


class ScheduleOut(Schema):
    id: UUID
    report_id: str
    frequency: str
    export_format: str
    filters: dict[str, Any]
    last_sent_at: datetime | None


def _filters(request: Request) -> dict[str, Any]:
    return {k: v for k, v in request.query_params.items() if k in FILTER_KEYS}


@router.get("")
async def catalogue(session: SessionDep, user: ManagerUser) -> list[dict[str, Any]]:
    return ReportService(session).catalogue(user)


@router.get("/schedules", response_model=list[ScheduleOut])
async def my_schedules(session: SessionDep, user: ManagerUser) -> object:
    return await ReportService(session).schedules(user)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: UUID, session: SessionDep, user: ManagerUser) -> None:
    await ReportService(session).delete_schedule(schedule_id, user)


@router.get("/{report_id}")
async def run(report_id: str, request: Request, session: SessionDep, user: ManagerUser) -> dict[str, Any]:
    return await ReportService(session).run(report_id, user, _filters(request))


@router.get("/{report_id}/drill")
async def drill(
    report_id: str, row: str, column: str, request: Request, session: SessionDep, user: ManagerUser
) -> list[dict[str, Any]]:
    return await ReportService(session).drill(report_id, user, _filters(request), row, column)


@router.get("/{report_id}/export")
async def export(report_id: str, request: Request, session: SessionDep, user: ManagerUser, format: str = "xlsx") -> Response:
    content, media_type, filename = await ReportService(session).export(report_id, user, _filters(request), format)
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/{report_id}/schedule", response_model=ScheduleOut, status_code=201)
async def schedule(report_id: str, data: ScheduleIn, session: SessionDep, user: ManagerUser) -> object:
    return await ReportService(session).schedule(report_id, user, data.frequency, data.format, data.filters)


@scheduled_task("reports.scheduled", "weekly")
async def _send_scheduled(session: Any) -> int:
    return await ReportService(session).send_due_schedules()
